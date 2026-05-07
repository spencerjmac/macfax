"""
Management command: nba_validate_rapm

Three-source validation stack for NBA baseline RAPM:

  1. Backtest — primary, automatic, no CSV needed
     Minutes-weighted team BPR from season N-1 vs team wins in season N.
     Target: Spearman r ≥ 0.70

  2. nbarapm.com correlation — requires CSV download from nbarapm.com
     Spearman r vs their multi-year weighted RAPM.
     Target: total r ≥ 0.75, off r ≥ 0.65, def r ≥ 0.65

  3. Basketball Reference BPM correlation — requires CSV from bbref
     Spearman r vs BPM (box-score only baseline).
     Expected range: 0.55-0.75 (BPM box-only; our RAPM should beat it)

Usage:
  python manage.py nba_validate_rapm --season 2026
  python manage.py nba_validate_rapm --season 2026 --rapm-csv nbarapm_2026.csv
  python manage.py nba_validate_rapm --season 2026 --rapm-csv rapm.csv --bpm-csv bpm.csv
"""

import csv
import difflib
import logging
from collections import defaultdict

from django.core.management.base import BaseCommand

from nba.models import NBAGame, NBAPlayer, NBAPlayerSeasonStats, NBATeamSeasonRatings

logger = logging.getLogger(__name__)


def _spearman_r(x: list[float], y: list[float]) -> float:
    """Compute Spearman rank correlation."""
    import scipy.stats
    r, p = scipy.stats.spearmanr(x, y)
    return float(r), float(p)


def _load_csv_rapm(path: str) -> dict[str, dict]:
    """
    Load nbarapm.com CSV. Expected columns (flexible — tries common names):
      player_name / Player, rapm / RAPM / total, off / ORAPM, def / DRAPM
    Returns: {name_normalized: {"total": float, "off": float, "def": float}}
    """
    result = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = [h.lower().strip() for h in reader.fieldnames or []]

        def _col(*candidates):
            for c in candidates:
                for h in headers:
                    if c.lower() == h:
                        return h
            return None

        name_col  = _col("player", "player_name", "name")
        total_col = _col("rapm", "total", "rapm_total")
        off_col   = _col("orapm", "off", "rapm_off", "o_rapm")
        def_col   = _col("drapm", "def", "rapm_def", "d_rapm")

        if not name_col:
            raise ValueError(f"Cannot find player name column in {path}. Headers: {reader.fieldnames}")

        for row in reader:
            keys = {h.lower().strip(): v for h, v in row.items()}
            name = keys.get(name_col, "").strip()
            if not name:
                continue
            try:
                result[name.lower()] = {
                    "total": float(keys.get(total_col, 0) or 0) if total_col else None,
                    "off":   float(keys.get(off_col,   0) or 0) if off_col   else None,
                    "def":   float(keys.get(def_col,   0) or 0) if def_col   else None,
                    "_name": name,
                }
            except (ValueError, TypeError):
                pass

    return result


def _load_csv_bpm(path: str) -> dict[str, float]:
    """
    Load Basketball Reference BPM CSV.
    Expected columns: Player, BPM (or bpm).
    Returns: {name_normalized: bpm_float}
    """
    result = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = {h.lower().strip(): h for h in (reader.fieldnames or [])}
        name_col = headers.get("player") or headers.get("player_name")
        bpm_col  = headers.get("bpm")
        if not name_col or not bpm_col:
            raise ValueError(f"Cannot find Player/BPM columns in {path}. Headers: {reader.fieldnames}")
        for row in reader:
            name = (row.get(name_col) or "").strip()
            bpm_str = (row.get(bpm_col) or "").strip()
            if name and bpm_str:
                try:
                    result[name.lower()] = float(bpm_str)
                except ValueError:
                    pass
    return result


def _fuzzy_match(name: str, candidates: set[str], cutoff: float = 0.82) -> str | None:
    matches = difflib.get_close_matches(name.lower(), candidates, n=1, cutoff=cutoff)
    return matches[0] if matches else None


class Command(BaseCommand):
    help = "Validate NBA baseline RAPM against external sources and backtesting"

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument("--rapm-csv", type=str, help="Path to nbarapm.com CSV download")
        parser.add_argument("--bpm-csv",  type=str, help="Path to Basketball Reference BPM CSV")
        parser.add_argument(
            "--prior-season", type=int,
            help="Season N-1 for backtest (default: --season - 1)",
        )

    def handle(self, *args, **options):
        season_year   = options["season"]
        rapm_csv_path = options.get("rapm_csv")
        bpm_csv_path  = options.get("bpm_csv")
        prior_year    = options.get("prior_season") or (season_year - 1)

        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"NBA RAPM Validation — {season_year - 1}-{str(season_year)[2:]}")
        self.stdout.write(f"{'='*60}\n")

        # ── 1. Load our RAPM results ──────────────────────────────────────────
        our_stats = list(
            NBAPlayerSeasonStats.objects.filter(
                season__year=season_year,
                season_type="regular",
                baseline_obpr__isnull=False,
            ).select_related("player")
        )
        if not our_stats:
            self.stdout.write(self.style.ERROR(
                f"No baseline_obpr found for {season_year}. "
                f"Run nba_compute_baseline_rapm first."
            ))
            return

        our_total: dict[int, float] = {}  # NBA.com player_id → obpr + dbpr
        our_off:   dict[int, float] = {}
        our_def:   dict[int, float] = {}
        our_names: dict[int, str]   = {}

        for row in our_stats:
            pid = row.player.player_id
            our_off[pid]   = row.baseline_obpr or 0.0
            our_def[pid]   = row.baseline_dbpr or 0.0
            our_total[pid] = (row.baseline_obpr or 0.0) + (row.baseline_dbpr or 0.0)
            our_names[pid] = row.player.name

        self.stdout.write(f"Our baseline RAPM: {len(our_total)} players\n")

        # ── 2. Backtest: N-1 BPR → N wins ────────────────────────────────────
        self.stdout.write("[BACKTEST] Predicting season N team wins from N-1 player BPR")
        self._run_backtest(prior_year, season_year)

        # ── 3. nbarapm.com correlation ────────────────────────────────────────
        if rapm_csv_path:
            self.stdout.write(f"\n[EXTERNAL] nbarapm.com correlation (from {rapm_csv_path})")
            self._run_rapm_correlation(our_names, our_total, our_off, our_def, rapm_csv_path)

        # ── 4. BPM correlation ────────────────────────────────────────────────
        if bpm_csv_path:
            self.stdout.write(f"\n[EXTERNAL] Basketball Reference BPM (from {bpm_csv_path})")
            self._run_bpm_correlation(our_names, our_total, bpm_csv_path)

        self.stdout.write(f"\n{'='*60}")

    def _run_backtest(self, prior_year: int, target_year: int) -> None:
        """Minutes-weighted team BPR from prior_year → team wins in target_year."""
        import scipy.stats

        # Prior season player BPR
        prior_stats = list(
            NBAPlayerSeasonStats.objects.filter(
                season__year=prior_year,
                season_type="regular",
                baseline_obpr__isnull=False,
            ).select_related("player", "team")
        )
        if not prior_stats:
            self.stdout.write(self.style.WARNING(
                f"  No prior-season ({prior_year}) baseline RAPM. Skipping backtest."
            ))
            return

        # Team BPR prediction: minutes-weighted sum of player BPR
        team_bpr: dict[int, float] = defaultdict(float)    # team_pk → predicted BPR
        team_poss: dict[int, float] = defaultdict(float)   # team_pk → total poss

        for row in prior_stats:
            if row.team is None or row.off_poss is None:
                continue
            team_pk = row.team.pk
            player_bpr = (row.baseline_obpr or 0.0) + (row.baseline_dbpr or 0.0)
            weight = row.off_poss or 0.0
            team_bpr[team_pk]  += player_bpr * weight
            team_poss[team_pk] += weight

        team_bpr_norm = {
            t: team_bpr[t] / team_poss[t]
            for t in team_bpr if team_poss[t] > 0
        }

        # Target season wins
        target_ratings = {
            r.team_id: r
            for r in NBATeamSeasonRatings.objects.filter(season__year=target_year)
            .select_related("team")
        }

        # Compute wins from game results
        team_wins: dict[int, int] = defaultdict(int)
        for game in NBAGame.objects.filter(
            season__year=target_year,
            status="Final",
            counts_toward_regular_season=True,
        ).select_related("home_team", "away_team"):
            if game.home_score is not None and game.away_score is not None:
                if game.home_score > game.away_score:
                    team_wins[game.home_team.pk] += 1
                else:
                    team_wins[game.away_team.pk] += 1

        # Build paired (bpr_pred, wins) list for teams appearing in both
        pairs = [
            (team_bpr_norm[t], team_wins[t])
            for t in team_bpr_norm
            if t in team_wins and team_wins[t] > 0
        ]

        if len(pairs) < 10:
            self.stdout.write(self.style.WARNING(
                f"  Only {len(pairs)} teams matched. Need target-season data. Skipping."
            ))
            return

        bpr_vals, win_vals = zip(*pairs)
        r, p = scipy.stats.spearmanr(bpr_vals, win_vals)

        status = self.style.SUCCESS("PASS") if r >= 0.70 else self.style.WARNING("WARN")
        self.stdout.write(
            f"  Teams: {len(pairs)} | Spearman r: {r:.3f} | p={p:.4f}  [{status}] (target ≥0.70)"
        )

        # Adj-net secondary check
        adj_pairs = [
            (team_bpr_norm[t], target_ratings[t].adj_net)
            for t in team_bpr_norm
            if t in target_ratings and target_ratings[t].adj_net is not None
        ]
        if adj_pairs:
            bpr_v, adj_v = zip(*adj_pairs)
            r2, p2 = scipy.stats.spearmanr(bpr_v, adj_v)
            status2 = self.style.SUCCESS("PASS") if r2 >= 0.60 else self.style.WARNING("WARN")
            self.stdout.write(
                f"  vs adj_net: Spearman r: {r2:.3f} | p={p2:.4f}  [{status2}] (target ≥0.60)"
            )

    def _run_rapm_correlation(
        self,
        our_names: dict[int, str],
        our_total: dict[int, float],
        our_off: dict[int, float],
        our_def: dict[int, float],
        csv_path: str,
    ) -> None:
        import scipy.stats

        try:
            ext = _load_csv_rapm(csv_path)
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"  Error loading CSV: {exc}"))
            return

        ext_names = set(ext.keys())
        matched_total, matched_off, matched_def = [], [], []
        our_total_m, our_off_m, our_def_m = [], [], []
        disagreements = []

        for pid, name in our_names.items():
            key = name.lower()
            if key not in ext_names:
                key = _fuzzy_match(key, ext_names)
            if key is None:
                continue
            entry = ext[key]
            if entry.get("total") is not None:
                matched_total.append(entry["total"])
                our_total_m.append(our_total[pid])
            if entry.get("off") is not None:
                matched_off.append(entry["off"])
                our_off_m.append(our_off[pid])
            if entry.get("def") is not None:
                matched_def.append(entry["def"])
                our_def_m.append(our_def[pid])

        n = len(matched_total)
        self.stdout.write(f"  Matched {n} players")

        if n < 20:
            self.stdout.write(self.style.WARNING("  Too few matches for meaningful correlation."))
            return

        def _check(ours, theirs, label, target_r):
            r, p = scipy.stats.spearmanr(ours, theirs)
            ok = r >= target_r
            status = self.style.SUCCESS("PASS") if ok else self.style.WARNING("WARN")
            self.stdout.write(
                f"  {label:8s}: Spearman r={r:.3f} | p={p:.4f}  [{status}] (target ≥{target_r})"
            )
            return r

        _check(our_total_m, matched_total, "Total",   0.75)
        if matched_off: _check(our_off_m, matched_off, "Offense", 0.65)
        if matched_def: _check(our_def_m, matched_def, "Defense", 0.65)

        # Flag large disagreements
        if matched_total:
            import numpy as np
            our_ranks  = np.argsort(np.argsort(our_total_m))
            ext_ranks  = np.argsort(np.argsort(matched_total))
            rank_diffs = abs(our_ranks - ext_ranks)
            big_disagreements = sorted(
                [(rank_diffs[i], list(our_names.values())[i] if i < len(our_names) else f"idx={i}")
                 for i in range(len(rank_diffs)) if rank_diffs[i] > 50],
                reverse=True,
            )[:5]
            if big_disagreements:
                self.stdout.write("\n  Top rank disagreements (Δrank > 50):")
                for diff, name in big_disagreements:
                    self.stdout.write(f"    {name}: Δrank={diff}")

    def _run_bpm_correlation(
        self,
        our_names: dict[int, str],
        our_total: dict[int, float],
        csv_path: str,
    ) -> None:
        import scipy.stats

        try:
            ext = _load_csv_bpm(csv_path)
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"  Error loading CSV: {exc}"))
            return

        ext_names = set(ext.keys())
        our_vals, bpm_vals = [], []
        for pid, name in our_names.items():
            key = name.lower()
            if key not in ext_names:
                key = _fuzzy_match(key, ext_names)
            if key is None:
                continue
            our_vals.append(our_total[pid])
            bpm_vals.append(ext[key])

        n = len(our_vals)
        self.stdout.write(f"  Matched {n} players")

        if n < 20:
            self.stdout.write(self.style.WARNING("  Too few matches."))
            return

        r, p = scipy.stats.spearmanr(our_vals, bpm_vals)
        ok = 0.55 <= r <= 0.80
        status = self.style.SUCCESS("OK") if ok else self.style.WARNING("CHECK")
        self.stdout.write(
            f"  Total: Spearman r={r:.3f} | p={p:.4f}  [{status}] (expected 0.55-0.80)"
        )
        if r < 0.55:
            self.stdout.write("  r < 0.55 vs BPM suggests data issue (box stats or stints)")
        elif r > 0.80:
            self.stdout.write("  r > 0.80 vs BPM may indicate over-regularization (RAPM too close to box)")
