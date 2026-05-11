"""
Management command: nba_backtest_bpr

Validates NBA Box BPR quality via two checks and optional LEBRON comparison:

  1. Same-season: minutes-weighted team box_bpr → team wins (descriptive fit)
  2. Predictive:  box_bpr from season N → team wins in season N+1 (Spearman r)
     Target: r ≥ 0.60
  3. LEBRON comparison (optional --lebron-csv): individual-level Spearman r
     between box_bpr, baseline RAPM, and prior-informed RAPM vs LEBRON ratings
  4. Prior-informed RAPM leaderboard: LEBRON-style on-off regularized toward box_bpr

Also prints top-30 BPR leaderboard showing box_bpr alongside prior-informed RAPM.

Usage:
  python manage.py nba_backtest_bpr --seasons 2024 2025 2026
  python manage.py nba_backtest_bpr --seasons 2025 --lebron-csv /path/to/lebron.csv
"""

import csv
import difflib
import logging
from collections import defaultdict

import scipy.stats
from django.core.management.base import BaseCommand, CommandError

from nba.analytics.rapm import build_nba_observations, fit_prior_informed_rapm
from nba.models import NBAGame, NBAPlayer, NBAPlayerSeasonStats, NBATeamSeasonRatings

logger = logging.getLogger(__name__)


def _spearman(x, y):
    r, p = scipy.stats.spearmanr(x, y)
    return float(r), float(p)


def _pearson(x, y):
    r, p = scipy.stats.pearsonr(x, y)
    return float(r), float(p)


def _fuzzy_match(name: str, candidates: set[str], cutoff: float = 0.82) -> str | None:
    matches = difflib.get_close_matches(name.lower(), candidates, n=1, cutoff=cutoff)
    return matches[0] if matches else None


def _load_lebron_csv(path: str) -> tuple[dict[int, dict], dict[str, dict]]:
    """
    Load LEBRON ratings CSV. Returns two lookup dicts:
      - by_id:   {nba_id: entry}   (exact match via NBA.com player_id)
      - by_name: {name_lower: entry} (fuzzy fallback)

    Handles both underscore and dash variants: O-LEBRON / O_LEBRON.
    Entry: {"total": float, "off": float|None, "def": float|None, "_name": str}
    """
    by_id: dict[int, dict] = {}
    by_name: dict[str, dict] = {}

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # Normalize headers: strip, lowercase, replace dashes with underscores
        raw_headers = reader.fieldnames or []
        headers = {h.lower().strip().replace("-", "_"): h for h in raw_headers}

        def _col(*candidates):
            for c in candidates:
                key = c.lower().replace("-", "_")
                if key in headers:
                    return headers[key]
            return None

        id_col    = _col("nba_id", "player_id", "id")
        name_col  = _col("player", "player_name", "name")
        total_col = _col("lebron", "total", "lebron_total", "bpr")
        off_col   = _col("o_lebron", "olebron", "off", "lebron_off", "o_bpr")
        def_col   = _col("d_lebron", "dlebron", "def", "lebron_def", "d_bpr")

        if not name_col:
            raise CommandError(
                f"Cannot find player name column in {path}. "
                f"Headers: {raw_headers}"
            )
        if not total_col:
            raise CommandError(
                f"Cannot find LEBRON total column in {path}. "
                f"Headers: {raw_headers}"
            )

        for row in reader:
            name = (row.get(name_col) or "").strip()
            if not name:
                continue
            try:
                entry = {
                    "total": float(row.get(total_col) or 0),
                    "off":   float(row.get(off_col) or 0) if off_col else None,
                    "def":   float(row.get(def_col) or 0) if def_col else None,
                    "_name": name,
                }
            except (ValueError, TypeError):
                continue

            by_name[name.lower()] = entry
            if id_col:
                raw_id = (row.get(id_col) or "").strip()
                if raw_id:
                    try:
                        by_id[int(raw_id)] = entry
                    except ValueError:
                        pass

    return by_id, by_name


def _team_wins(season_year: int) -> dict[int, int]:
    """Return {team_pk: win_count} from game results."""
    wins: dict[int, int] = defaultdict(int)
    for game in NBAGame.objects.filter(
        season__year=season_year,
        status="Final",
        counts_toward_regular_season=True,
    ).only("home_team_id", "away_team_id", "home_score", "away_score"):
        if game.home_score is not None and game.away_score is not None:
            if game.home_score > game.away_score:
                wins[game.home_team_id] += 1
            else:
                wins[game.away_team_id] += 1
    return dict(wins)


def _team_box_bpr(season_year: int) -> dict[int, float]:
    """
    Minutes-weighted team box_bpr from player season stats.
    Returns {team_pk: weighted_avg_box_bpr}.
    """
    team_total: dict[int, float] = defaultdict(float)
    team_weight: dict[int, float] = defaultdict(float)

    for row in NBAPlayerSeasonStats.objects.filter(
        season__year=season_year,
        season_type="regular",
        box_bpr__isnull=False,
        on_court_poss__isnull=False,
    ).only("team_id", "box_bpr", "on_court_poss"):
        if row.team_id is None or row.on_court_poss is None:
            continue
        w = row.on_court_poss
        team_total[row.team_id] += (row.box_bpr or 0.0) * w
        team_weight[row.team_id] += w

    return {
        t: team_total[t] / team_weight[t]
        for t in team_total
        if team_weight[t] > 0
    }


class Command(BaseCommand):
    help = "Backtest NBA Box BPR quality (team wins prediction + optional LEBRON comparison)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--seasons", type=int, nargs="+", required=True,
            help="Season ending years to evaluate (e.g. 2023 2024 2025)",
        )
        parser.add_argument(
            "--lebron-csv", type=str,
            help="Path to LEBRON ratings CSV for individual-level comparison",
        )
        parser.add_argument(
            "--top-n", type=int, default=30,
            help="Players to show in leaderboard (default: 30)",
        )

    def handle(self, *args, **options):
        seasons: list[int] = sorted(options["seasons"])
        lebron_path: str | None = options.get("lebron_csv")
        top_n: int = options["top_n"]

        self.stdout.write(f"\n{'='*65}")
        self.stdout.write("NBA Box BPR Backtest")
        self.stdout.write(f"{'='*65}\n")

        # ── 1. Same-season fit ─────────────────────────────────────────────────
        self.stdout.write("[SAME-SEASON] Team box_bpr → team wins (descriptive fit)")
        for yr in seasons:
            self._run_same_season(yr)

        # ── 2. Predictive backtest ─────────────────────────────────────────────
        self.stdout.write(f"\n[PREDICTIVE] Season N box_bpr → season N+1 wins (target r ≥ 0.60)")
        for yr in seasons:
            next_yr = yr + 1
            self._run_predictive(yr, next_yr)

        # ── 3. Compute prior-informed RAPM (LEBRON-style) ──────────────────────
        prior_rapm: dict[int, dict[int, dict]] = {}  # season_year → {nba_id: {obpr, dbpr}}
        for yr in seasons:
            self.stdout.write(f"\n[PRIOR-RAPM] Computing prior-informed RAPM for {yr}...")
            pr = self._compute_prior_rapm(yr)
            if pr:
                prior_rapm[yr] = pr
                self.stdout.write(f"  Done — {len(pr)} players")

        # ── 4. LEBRON comparison ───────────────────────────────────────────────
        if lebron_path:
            for yr in seasons:
                self.stdout.write(f"\n[LEBRON] Season {yr} individual comparison (from {lebron_path})")
                self._run_lebron_comparison(yr, lebron_path, prior_rapm.get(yr))

        # ── 5. Leaderboard (prior-informed RAPM) ──────────────────────────────
        for yr in seasons:
            self._print_leaderboard(yr, top_n, prior_rapm.get(yr))

        self.stdout.write(f"\n{'='*65}")

    def _compute_prior_rapm(self, season_year: int) -> dict[int, dict] | None:
        """
        Fit LEBRON-style prior-informed RAPM (box_bpr as prior mean, lineup stints as data).
        Returns {nba_player_id: {"obpr": float, "dbpr": float}} or None on failure.
        """
        from nba.models import NBAPlayerSeasonStats

        # Load box_bpr priors keyed by NBA.com player_id
        box_stats = list(
            NBAPlayerSeasonStats.objects.filter(
                season__year=season_year,
                season_type="regular",
                box_obpr__isnull=False,
            ).select_related("player").only(
                "player__player_id", "box_obpr", "box_dbpr"
            )
        )
        if not box_stats:
            self.stdout.write(self.style.WARNING(
                f"  No box_bpr found for {season_year} — run nba_compute_box_bpr first"
            ))
            return None

        prior_obpr: dict[int, float] = {}
        prior_dbpr: dict[int, float] = {}
        for row in box_stats:
            nba_id = row.player.player_id
            if nba_id:
                prior_obpr[nba_id] = row.box_obpr or 0.0
                prior_dbpr[nba_id] = row.box_dbpr or 0.0

        # Pool 3 years of stints — same window as baseline RAPM.
        rapm_years = [season_year - 2, season_year - 1, season_year]
        try:
            observations = build_nba_observations(
                season_year=season_year,
                rapm_years=rapm_years,
            )
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"  Failed to load stints: {exc}"))
            return None

        if not observations:
            self.stdout.write(self.style.WARNING(
                f"  No stint observations for {season_year} — run nba_sync_play_by_play first"
            ))
            return None

        self.stdout.write(f"  {len(observations)} observations, {len(prior_obpr)} box priors")

        # Build player-season index
        all_ps: set[tuple[int, int]] = set()
        for obs in observations:
            yr = obs["season_year"]
            for pid in obs["home_player_ids"] + obs["away_player_ids"]:
                all_ps.add((pid, yr))
        player_season_index = {ps: i for i, ps in enumerate(sorted(all_ps))}
        n_ps = len(player_season_index)

        # Match λ=1000 from 3yr CV-selected baseline RAPM.
        lambda_val = 1000.0

        try:
            result = fit_prior_informed_rapm(
                observations=observations,
                player_season_index=player_season_index,
                n_player_seasons=n_ps,
                prior_obpr=prior_obpr,
                prior_dbpr=prior_dbpr,
                lambda_val=lambda_val,
            )
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"  Prior-RAPM fit failed: {exc}"))
            return None

        # Return {nba_player_id: {obpr, dbpr}} for target season only
        out = {}
        for (pid, yr), obpr_val in result["obpr"].items():
            if yr == season_year:
                dbpr_val = result["dbpr"].get((pid, yr), 0.0)
                out[pid] = {"obpr": obpr_val, "dbpr": dbpr_val}
        return out

    def _run_same_season(self, season_year: int) -> None:
        team_bpr = _team_box_bpr(season_year)
        wins = _team_wins(season_year)

        pairs = [
            (team_bpr[t], wins[t])
            for t in team_bpr
            if t in wins and wins[t] > 0
        ]

        if len(pairs) < 10:
            self.stdout.write(
                f"  {season_year}: only {len(pairs)} teams matched — skip"
            )
            return

        bpr_v, win_v = zip(*pairs)
        r_sp, p_sp = _spearman(bpr_v, win_v)
        r_pe, _ = _pearson(bpr_v, win_v)

        ok = r_sp >= 0.65
        status = self.style.SUCCESS("PASS") if ok else self.style.WARNING("WARN")
        self.stdout.write(
            f"  {season_year}: n={len(pairs)} teams | "
            f"Spearman r={r_sp:.3f} p={p_sp:.4f} | Pearson r={r_pe:.3f}  "
            f"[{status}] (target ≥0.65)"
        )

    def _run_predictive(self, prior_year: int, target_year: int) -> None:
        team_bpr = _team_box_bpr(prior_year)
        if not team_bpr:
            self.stdout.write(
                f"  {prior_year}→{target_year}: no box_bpr data for {prior_year} — skip"
            )
            return

        wins = _team_wins(target_year)
        if not wins:
            self.stdout.write(
                f"  {prior_year}→{target_year}: no game results for {target_year} — skip"
            )
            return

        pairs = [
            (team_bpr[t], wins[t])
            for t in team_bpr
            if t in wins and wins[t] > 0
        ]

        if len(pairs) < 10:
            self.stdout.write(
                f"  {prior_year}→{target_year}: only {len(pairs)} teams matched — skip"
            )
            return

        bpr_v, win_v = zip(*pairs)
        r_sp, p_sp = _spearman(bpr_v, win_v)
        r_pe, _ = _pearson(bpr_v, win_v)

        ok = r_sp >= 0.60
        status = self.style.SUCCESS("PASS") if ok else self.style.WARNING("WARN")
        self.stdout.write(
            f"  {prior_year}→{target_year}: n={len(pairs)} teams | "
            f"Spearman r={r_sp:.3f} p={p_sp:.4f} | Pearson r={r_pe:.3f}  "
            f"[{status}] (target ≥0.60)"
        )

    def _run_lebron_comparison(
        self, season_year: int, csv_path: str,
        prior_rapm: dict[int, dict] | None = None,
    ) -> None:
        try:
            lebron_by_id, lebron_by_name = _load_lebron_csv(csv_path)
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"  Error loading CSV: {exc}"))
            return

        self.stdout.write(
            f"  LEBRON CSV: {len(lebron_by_id)} id-keyed, {len(lebron_by_name)} name-keyed entries"
        )

        our_stats = list(
            NBAPlayerSeasonStats.objects.filter(
                season__year=season_year,
                season_type="regular",
                box_bpr__isnull=False,
            ).select_related("player").only(
                "player__name", "player__player_id",
                "box_obpr", "box_dbpr", "box_bpr",
                "baseline_obpr", "baseline_dbpr",
            )
        )
        if not our_stats:
            self.stdout.write(f"  No box_bpr data for {season_year}")
            return

        ext_names = set(lebron_by_name.keys())
        pairs_total, pairs_off, pairs_def = [], [], []
        matched_names: list[str] = []
        n_id_match = n_name_match = 0

        for row in our_stats:
            # Prefer exact NBA.com ID match; fall back to fuzzy name
            nba_id = getattr(row.player, "player_id", None)
            entry = None
            if nba_id and nba_id in lebron_by_id:
                entry = lebron_by_id[nba_id]
                n_id_match += 1
            else:
                name_key = row.player.name.lower()
                match_key = name_key if name_key in ext_names else _fuzzy_match(name_key, ext_names)
                if match_key is not None:
                    entry = lebron_by_name[match_key]
                    n_name_match += 1

            if entry is None:
                continue

            our_total = row.box_bpr or 0.0
            pairs_total.append((our_total, entry["total"]))
            matched_names.append(row.player.name)
            if entry["off"] is not None:
                pairs_off.append((row.box_obpr or 0.0, entry["off"]))
            if entry["def"] is not None:
                pairs_def.append((row.box_dbpr or 0.0, entry["def"]))

        self.stdout.write(
            f"  Matched {len(pairs_total)} players "
            f"(id={n_id_match}, fuzzy_name={n_name_match})"
        )
        if len(pairs_total) < 20:
            self.stdout.write(self.style.WARNING("  Too few matches for meaningful correlation"))
            return

        # Also build RAPM pairs for side-by-side comparison
        rapm_pairs_total = []
        rapm_pairs_off = []
        rapm_pairs_def = []
        for row in our_stats:
            nba_id = getattr(row.player, "player_id", None)
            entry = None
            if nba_id and nba_id in lebron_by_id:
                entry = lebron_by_id[nba_id]
            else:
                name_key = row.player.name.lower()
                match_key = name_key if name_key in ext_names else _fuzzy_match(name_key, ext_names)
                if match_key is not None:
                    entry = lebron_by_name[match_key]
            if entry is None:
                continue
            rapm_total = (row.baseline_obpr or 0.0) + (row.baseline_dbpr or 0.0)
            if row.baseline_obpr is not None and row.baseline_dbpr is not None:
                rapm_pairs_total.append((rapm_total, entry["total"]))
                if entry["off"] is not None:
                    rapm_pairs_off.append((row.baseline_obpr, entry["off"]))
                if entry["def"] is not None:
                    rapm_pairs_def.append((row.baseline_dbpr, entry["def"]))

        def _check(pairs, label, target_r, prefix=""):
            ours, theirs = zip(*pairs)
            r_sp, p_sp = _spearman(ours, theirs)
            ok = r_sp >= target_r
            status = self.style.SUCCESS("PASS") if ok else self.style.WARNING("WARN")
            self.stdout.write(
                f"  {prefix}{label:8s}: Spearman r={r_sp:.3f} p={p_sp:.4f}  "
                f"[{status}] (target ≥{target_r})"
            )
            return r_sp

        self.stdout.write("  ── box_bpr vs LEBRON ──")
        _check(pairs_total, "Total",   0.70)
        if pairs_off: _check(pairs_off, "Offense", 0.60)
        if pairs_def: _check(pairs_def, "Defense", 0.55)

        if rapm_pairs_total:
            self.stdout.write(f"  ── RAPM (baseline) vs LEBRON  n={len(rapm_pairs_total)} ──")
            _check(rapm_pairs_total, "Total",   0.70)
            if rapm_pairs_off: _check(rapm_pairs_off, "Offense", 0.60)
            if rapm_pairs_def: _check(rapm_pairs_def, "Defense", 0.55)

        if prior_rapm:
            pr_pairs_total, pr_pairs_off, pr_pairs_def = [], [], []
            for row in our_stats:
                nba_id = getattr(row.player, "player_id", None)
                entry = None
                if nba_id and nba_id in lebron_by_id:
                    entry = lebron_by_id[nba_id]
                else:
                    name_key = row.player.name.lower()
                    match_key = name_key if name_key in ext_names else _fuzzy_match(name_key, ext_names)
                    if match_key is not None:
                        entry = lebron_by_name[match_key]
                if entry is None or nba_id not in prior_rapm:
                    continue
                pr = prior_rapm[nba_id]
                pr_total = pr["obpr"] + pr["dbpr"]
                pr_pairs_total.append((pr_total, entry["total"]))
                if entry["off"] is not None:
                    pr_pairs_off.append((pr["obpr"], entry["off"]))
                if entry["def"] is not None:
                    pr_pairs_def.append((pr["dbpr"], entry["def"]))

            if pr_pairs_total:
                self.stdout.write(
                    f"  ── Prior-informed RAPM vs LEBRON  n={len(pr_pairs_total)} ──"
                )
                _check(pr_pairs_total, "Total",   0.70)
                if pr_pairs_off: _check(pr_pairs_off, "Offense", 0.60)
                if pr_pairs_def: _check(pr_pairs_def, "Defense", 0.55)

        # Flag large rank disagreements
        if len(pairs_total) >= 20:
            import numpy as np
            ours_v, theirs_v = zip(*pairs_total)
            our_ranks  = np.argsort(np.argsort(ours_v))
            ext_ranks  = np.argsort(np.argsort(theirs_v))
            rank_diffs = abs(our_ranks - ext_ranks)

            big = sorted(
                [(rank_diffs[i], matched_names[i] if i < len(matched_names) else f"idx={i}")
                 for i in range(min(len(rank_diffs), len(matched_names)))
                 if rank_diffs[i] > 40],
                reverse=True,
            )[:8]
            if big:
                self.stdout.write("\n  Top rank disagreements vs LEBRON (Δrank > 40):")
                for diff, name in big:
                    self.stdout.write(f"    {name}: Δrank={diff}")

    def _print_leaderboard(
        self, season_year: int, top_n: int,
        prior_rapm: dict[int, dict] | None = None,
    ) -> None:
        rows = list(
            NBAPlayerSeasonStats.objects.filter(
                season__year=season_year,
                season_type="regular",
                box_bpr__isnull=False,
            ).select_related("player", "team").only(
                "player__name", "player__player_id", "team__abbreviation",
                "box_obpr", "box_dbpr", "box_bpr",
                "baseline_obpr", "baseline_dbpr",
                "on_court_poss", "nba_archetype",
            )
        )

        if not rows:
            self.stdout.write(f"\n  No box_bpr data for {season_year}")
            return

        # Deduplicate traded players (multiple rows per nba_id) — keep highest box_bpr row
        seen_ids: set[int] = set()
        deduped = []
        for r in sorted(rows, key=lambda x: (x.box_bpr or 0.0), reverse=True):
            nba_id = r.player.player_id
            if nba_id not in seen_ids:
                seen_ids.add(nba_id)
                deduped.append(r)
        rows = deduped

        # Sort by prior-RAPM total if available, else box_bpr
        if prior_rapm:
            rows.sort(
                key=lambda r: (
                    prior_rapm.get(r.player.player_id, {}).get("obpr", 0.0)
                    + prior_rapm.get(r.player.player_id, {}).get("dbpr", 0.0)
                ),
                reverse=True,
            )
            sort_label = "prior-informed RAPM"
        else:
            rows.sort(key=lambda r: (r.box_bpr or 0.0), reverse=True)
            sort_label = "box_bpr"

        rows = rows[:top_n]

        self.stdout.write(
            f"\n[LEADERBOARD] Top {top_n} by {sort_label} — Season {season_year}"
        )
        if prior_rapm:
            self.stdout.write(
                f"  {'#':>3}  {'Player':<28} {'Team':<5} "
                f"{'PR_O':>6} {'PR_D':>6} {'PR_T':>6}  "
                f"{'BOX_O':>6} {'BOX_D':>6} {'BOX_T':>6}  {'Arch'}"
            )
            self.stdout.write("  " + "-" * 95)
        else:
            self.stdout.write(
                f"  {'#':>3}  {'Player':<28} {'Team':<5} {'OBPR':>6} {'DBPR':>6} {'BPR':>6} "
                f"{'R_OBPR':>7} {'R_DBPR':>7}  {'Arch'}"
            )
            self.stdout.write("  " + "-" * 85)

        for i, row in enumerate(rows, 1):
            team_abbr = row.team.abbreviation if row.team else "???"
            nba_id = row.player.player_id
            if prior_rapm and nba_id in prior_rapm:
                pr = prior_rapm[nba_id]
                pr_o = pr["obpr"]
                pr_d = pr["dbpr"]
                pr_t = pr_o + pr_d
                self.stdout.write(
                    f"  {i:>3}  {row.player.name:<28} {team_abbr:<5} "
                    f"{pr_o:>+6.2f} {pr_d:>+6.2f} {pr_t:>+6.2f}  "
                    f"{(row.box_obpr or 0):>+6.2f} {(row.box_dbpr or 0):>+6.2f} "
                    f"{(row.box_bpr or 0):>+6.2f}  "
                    f"{row.nba_archetype or '—'}"
                )
            else:
                rapm_o = f"{row.baseline_obpr:+.2f}" if row.baseline_obpr is not None else "  —  "
                rapm_d = f"{row.baseline_dbpr:+.2f}" if row.baseline_dbpr is not None else "  —  "
                self.stdout.write(
                    f"  {i:>3}  {row.player.name:<28} {team_abbr:<5} "
                    f"{(row.box_obpr or 0):>+6.2f} {(row.box_dbpr or 0):>+6.2f} "
                    f"{(row.box_bpr or 0):>+6.2f} "
                    f"{rapm_o:>7} {rapm_d:>7}  "
                    f"{row.nba_archetype or '—'}"
                )
