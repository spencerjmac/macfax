"""
Management command: nba_compute_box_bpr

Computes NBA Box BPR (box_obpr, box_dbpr, box_bpr) for all qualified
players in a season using Ridge regression on per-100-possession
box-score features.

Training targets (in priority order):
  1. baseline_obpr / baseline_dbpr from RAPM + LEBRON blend (when metrics CSV exists)
     blend = 0.7 × RAPM + 0.3 × O_LEBRON/D_LEBRON
     LEBRON blend pulls star targets higher, reduces role-player context inflation
  2. baseline_obpr / baseline_dbpr from RAPM only (when no LEBRON data)
  3. o_mpir / d_mpir (NBA.com E_OFF/DEF_RATING residuals, fallback)

Run nba_compute_baseline_rapm before this command to enable RAPM targets.

Usage:
  python manage.py nba_compute_box_bpr --season 2026
  python manage.py nba_compute_box_bpr --season 2026 --dry-run
  python manage.py nba_compute_box_bpr --season 2026 --oof
  python manage.py nba_compute_box_bpr --season 2026 --validate
"""

import logging
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from nba.analytics.box_bpr import (
    compute_opp_quality_map,
    compute_team_adj_em_map,
    out_of_fold_box_bpr,
    predict_nba_box_bpr,
    train_nba_box_bpr,
)
from nba.analytics.career_stats import build_career_stats_map
from nba.models import NBAPlayer, NBAPlayerSeasonStats

logger = logging.getLogger(__name__)

SCRIPT_DIR      = Path(__file__).parent.parent.parent.parent.parent   # project root
METRICS_DIR     = SCRIPT_DIR / "metrics_output"
LEBRON_BLEND_W  = 0.7    # weight given to LEBRON in the target blend (0.3 RAPM + 0.7 LEBRON)


def _norm_name(s: str) -> str:
    s = str(s).lower().encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", s).strip()


def _load_lebron_targets(season_year: int, player_pks: list[int]) -> dict[int, tuple[float, float]]:
    """
    Load O-LEBRON / D-LEBRON directly from lebron-data-{year}.csv and match to NBAPlayer PKs.
    Returns {player_pk: (o_lebron, d_lebron)} — only players with both values.
    Falls back to empty dict if CSV not found.
    Available for seasons 2016-2026.
    """
    try:
        import pandas as pd
        from rapidfuzz import fuzz, process as rfp
    except ImportError:
        return {}

    csv_path = SCRIPT_DIR / f"lebron-data-{season_year}.csv"
    if not csv_path.exists():
        return {}

    df = pd.read_csv(csv_path)
    # Raw column names: Player, O-LEBRON, D-LEBRON, nba_id
    df = df.rename(columns={"Player": "player_name", "O-LEBRON": "O_LEBRON", "D-LEBRON": "D_LEBRON"})
    df = df.sort_values("MPG", ascending=False).drop_duplicates("player_name", keep="first")
    df = df.dropna(subset=["O_LEBRON", "D_LEBRON"])

    lebron_norms = df["player_name"].apply(_norm_name).tolist()

    # Build pk → norm_name for players in this season
    pk_to_norm = {
        p.pk: _norm_name(p.name)
        for p in NBAPlayer.objects.filter(pk__in=player_pks).only("pk", "name")
    }

    result: dict[int, tuple[float, float]] = {}
    for pk, norm in pk_to_norm.items():
        match = rfp.extractOne(norm, lebron_norms, scorer=fuzz.WRatio, score_cutoff=82)
        if match:
            row = df.iloc[match[2]]
            result[pk] = (float(row["O_LEBRON"]), float(row["D_LEBRON"]))

    return result


class Command(BaseCommand):
    help = "Compute NBA Box BPR (box_obpr, box_dbpr, box_bpr) for a season"

    def add_arguments(self, parser):
        parser.add_argument(
            "--season", type=int, required=True, help="Season ending year (e.g. 2026)"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compute but do not write to database",
        )
        parser.add_argument(
            "--oof",
            action="store_true",
            help="Use out-of-fold predictions to avoid train/predict leakage",
        )
        parser.add_argument(
            "--validate",
            action="store_true",
            help="Compute without writing to DB; run validation checks and save comparison CSV",
        )

    def handle(self, *args, **options):
        season_year: int = options["season"]
        dry_run: bool = options["dry_run"]
        use_oof: bool = options["oof"]
        validate: bool = options.get("validate", False)
        if validate:
            dry_run = True   # --validate implies no DB writes

        self.stdout.write(f"\n[NBA BOX BPR] Season {season_year}")
        if dry_run:
            self.stdout.write("[DRY RUN] No writes to database")

        # ── 1. Load season stats ───────────────────────────────────────────────
        stats_qs = NBAPlayerSeasonStats.objects.filter(
            season__year=season_year
        ).select_related("player", "team", "season")

        stats_values = list(
            stats_qs.values(
                "player_id", "team_id",
                "gp", "mpg",
                "pts", "ast", "stl", "blk", "tov",
                "oreb_pg", "dreb_pg", "fga_pg", "fg3a_pg", "fta_pg",
                "efg_pct", "ts_pct", "usg_pct", "ast_pct",
                "oreb_pct", "dreb_pct", "ast_to",
                "stl_pct", "blk_pct", "tov_pct",
                "on_court_poss", "on_court_adj_em",
                "on_court_adj_o", "on_court_adj_d",
                "o_mpir", "d_mpir",
                "baseline_obpr", "baseline_dbpr",
            )
        )

        # Snapshot old box_bpr before computing new model (for --validate)
        old_box_bpr: dict[int, float] = {}
        if validate:
            for row in stats_qs.filter(box_bpr__isnull=False).values("player_id", "box_bpr"):
                old_box_bpr[row["player_id"]] = row["box_bpr"]

        self.stdout.write(f"Loaded {len(stats_values)} player-season rows")

        if not stats_values:
            raise CommandError(f"No stats found for season {season_year}. Run nba_compute_player_stats first.")

        # ── 2. Build lookup maps ───────────────────────────────────────────────
        self.stdout.write("Computing opponent quality and team adj_em maps...")
        opp_quality_map = compute_opp_quality_map(season_year)
        team_adj_em_map = compute_team_adj_em_map(season_year)
        self.stdout.write(f"  opp_quality: {len(opp_quality_map)} teams")
        self.stdout.write(f"  team_adj_em: {len(team_adj_em_map)} teams")

        self.stdout.write("Building career-stabilized stats map...")
        career_stats_map = build_career_stats_map(
            target_season_year=season_year,
            min_season_year=2016,
        )
        self.stdout.write(f"  Career map: {len(career_stats_map)} players")

        # ── 3. Build target maps — prefer RAPM (team-quality-adjusted) ──────────
        target_obpr: dict[int, float] = {}
        target_dbpr: dict[int, float] = {}
        rapm_off_pids: set[int] = set()
        rapm_def_pids: set[int] = set()
        n_rapm_off = n_rapm_def = n_mpir_off = n_mpir_def = 0

        for p in stats_values:
            pid = p["player_id"]
            if p.get("baseline_obpr") is not None:
                target_obpr[pid] = p["baseline_obpr"]
                rapm_off_pids.add(pid)
                n_rapm_off += 1
            elif p.get("o_mpir") is not None:
                target_obpr[pid] = p["o_mpir"]
                n_mpir_off += 1
            if p.get("baseline_dbpr") is not None:
                target_dbpr[pid] = p["baseline_dbpr"]
                rapm_def_pids.add(pid)
                n_rapm_def += 1
            elif p.get("d_mpir") is not None:
                target_dbpr[pid] = p["d_mpir"]
                n_mpir_def += 1

        # Clean training set: players with RAPM targets for BOTH off and def
        rapm_pids = rapm_off_pids & rapm_def_pids

        self.stdout.write(
            f"Targets: off={len(target_obpr)} "
            f"(rapm={n_rapm_off}, mpir={n_mpir_off}), "
            f"def={len(target_dbpr)} "
            f"(rapm={n_rapm_def}, mpir={n_mpir_def})"
        )
        if n_rapm_off > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  Using RAPM targets for {n_rapm_off} off / {n_rapm_def} def players "
                    "(team-quality-adjusted)"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "  No RAPM targets found — falling back to MPIR. "
                    "Run nba_compute_baseline_rapm for better accuracy."
                )
            )

        if len(target_obpr) < 30 or len(target_dbpr) < 30:
            raise CommandError(
                "Insufficient targets (<30). Run nba_sync_player_advanced "
                "or nba_compute_baseline_rapm first."
            )

        # ── 3b. Blend LEBRON into RAPM targets ────────────────────────────────
        # For players with RAPM targets: target = 0.7 × RAPM + 0.3 × LEBRON
        # Pulls star targets higher (LEBRON rates Jokić/SGA higher than single-season RAPM)
        # Moderates role player inflation (LEBRON less susceptible to lineup-context noise)
        # Only applied when a season-specific metrics CSV exists.
        all_pks = [p["player_id"] for p in stats_values]
        lebron_map = _load_lebron_targets(season_year, all_pks)

        n_blended = 0
        if lebron_map:
            for pid in list(rapm_pids):  # only blend for RAPM-trained players
                if pid in lebron_map:
                    o_leb, d_leb = lebron_map[pid]
                    if pid in target_obpr:
                        target_obpr[pid] = (1 - LEBRON_BLEND_W) * target_obpr[pid] + LEBRON_BLEND_W * o_leb
                    if pid in target_dbpr:
                        target_dbpr[pid] = (1 - LEBRON_BLEND_W) * target_dbpr[pid] + LEBRON_BLEND_W * d_leb
                    n_blended += 1

        if lebron_map:
            self.stdout.write(
                f"  LEBRON blend applied: {n_blended} players "
                f"({1-LEBRON_BLEND_W:.0%}×RAPM + {LEBRON_BLEND_W:.0%}×LEBRON) | no-match: {len(rapm_pids) - n_blended} players (pure RAPM)"
            )
        else:
            self.stdout.write(
                f"  LEBRON blend: skipped (no metrics CSV for {season_year})"
            )

        # ── 4. Train / predict ────────────────────────────────────────────────
        now = timezone.now()

        if validate and use_oof:
            self.stdout.write(self.style.WARNING("--validate requires full training (ignoring --oof)"))
            use_oof = False

        artifacts: dict = {}
        if use_oof:
            self.stdout.write("Running out-of-fold Box BPR (--oof)...")
            predictions, _ = out_of_fold_box_bpr(
                stats=stats_values,
                opp_quality_map=opp_quality_map,
                team_adj_em_map=team_adj_em_map,
                target_obpr=target_obpr,
                target_dbpr=target_dbpr,
                rapm_pids=rapm_pids,
                career_stats_map=career_stats_map,
            )
        else:
            self.stdout.write(
                f"Training Box BPR on full season "
                f"(RAPM-only training set: {len(rapm_pids)} players, "
                f"MPIR-only excluded from training: {n_mpir_off})..."
            )
            artifacts = train_nba_box_bpr(
                stats=stats_values,
                opp_quality_map=opp_quality_map,
                team_adj_em_map=team_adj_em_map,
                target_obpr=target_obpr,
                target_dbpr=target_dbpr,
                rapm_pids=rapm_pids,
                career_stats_map=career_stats_map,
            )
            self.stdout.write(
                f"  off alpha={artifacts['off_cv_alpha']:.2f} (n={artifacts['n_train_off']}), "
                f"def alpha={artifacts['def_cv_alpha']:.2f} (n={artifacts['n_train_def']}), "
                f"mpir_excluded={artifacts.get('n_mpir_excluded', 0)}"
            )
            predictions = predict_nba_box_bpr(
                stats=stats_values,
                opp_quality_map=opp_quality_map,
                team_adj_em_map=team_adj_em_map,
                model_artifacts=artifacts,
                career_stats_map=career_stats_map,
            )

        self.stdout.write(f"Box BPR computed for {len(predictions)} players")

        # ── 5. Write results ───────────────────────────────────────────────────
        if dry_run:
            self._print_top_players(predictions, stats_values)
            if validate:
                self._run_validation(predictions, stats_values, artifacts, old_box_bpr, season_year)
            return

        updated = 0
        skipped = 0
        for stat_row in stats_qs:
            pid = stat_row.player_id
            if pid not in predictions:
                skipped += 1
                continue
            pred = predictions[pid]
            stat_row.box_obpr = pred["box_obpr"]
            stat_row.box_dbpr = pred["box_dbpr"]
            stat_row.box_bpr = round(pred["box_obpr"] + pred["box_dbpr"], 3)
            stat_row.nba_archetype = pred["archetype"]
            stat_row.bpr_last_updated = now
            stat_row.save(update_fields=[
                "box_obpr", "box_dbpr", "box_bpr",
                "nba_archetype", "bpr_last_updated",
            ])
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"[OK] box_bpr written: {updated} updated, {skipped} skipped (below min threshold)"
            )
        )
        self._print_top_players(predictions, stats_values)
        self._print_fix_summary(predictions, stats_values, artifacts, season_year,
                                n_total_before=len(target_obpr), n_rapm=len(rapm_pids),
                                n_mpir=n_mpir_off)

    def _print_top_players(
        self, predictions: dict[int, dict], stats_values: list[dict]
    ) -> None:
        name_map = {}
        for p in stats_values:
            pid = p["player_id"]
            if pid not in name_map:
                name_map[pid] = f"player_id={pid}"

        # Fetch names (predictions keyed by NBAPlayer.pk, not NBA.com player_id)
        from nba.models import NBAPlayer
        for player in NBAPlayer.objects.filter(pk__in=predictions.keys()).only("pk", "name"):
            name_map[player.pk] = player.name

        self.stdout.write("\nTop 15 by box_bpr:")
        sorted_preds = sorted(
            predictions.items(),
            key=lambda x: x[1]["box_obpr"] + x[1]["box_dbpr"],
            reverse=True,
        )
        for pid, pred in sorted_preds[:15]:
            total = pred["box_obpr"] + pred["box_dbpr"]
            self.stdout.write(
                f"  {name_map.get(pid, pid):30s}  "
                f"obpr={pred['box_obpr']:+.2f}  dbpr={pred['box_dbpr']:+.2f}  "
                f"total={total:+.2f}  [{pred['archetype']}]"
            )

        self.stdout.write("\nArchetype distribution:")
        from collections import Counter
        arch_counts = Counter(pred["archetype"] for pred in predictions.values())
        for arch, count in sorted(arch_counts.items(), key=lambda x: -x[1]):
            self.stdout.write(f"  {arch:15s}: {count}")

    def _print_fix_summary(
        self,
        predictions: dict[int, dict],
        stats_values: list[dict],
        artifacts: dict,
        season_year: int,
        n_total_before: int,
        n_rapm: int,
        n_mpir: int,
    ) -> None:
        """Print Issue 1 fix diagnostic summary."""
        import re
        import numpy as np
        import scipy.stats
        from pathlib import Path

        self.stdout.write("\n" + "=" * 55)
        self.stdout.write("ISSUE 1 FIX SUMMARY")
        self.stdout.write("=" * 55)
        self.stdout.write(f"Training set before fix: {n_total_before} players (RAPM + MPIR mixed)")
        self.stdout.write(f"Training set after fix:  {n_rapm} players (RAPM only)")
        self.stdout.write(f"MPIR players predicted not trained: {n_mpir}")
        self.stdout.write(f"Offensive alpha: {artifacts.get('off_cv_alpha', '?'):.2f}")
        self.stdout.write(f"Defensive alpha: {artifacts.get('def_cv_alpha', '?'):.2f}")

        # Jokić check
        from nba.models import NBAPlayer
        name_map = {
            p.pk: p.name
            for p in NBAPlayer.objects.filter(pk__in=predictions.keys()).only("pk", "name")
        }
        jokic_pid = next(
            (pid for pid, name in name_map.items() if "joki" in name.lower()), None
        )
        if jokic_pid and jokic_pid in predictions:
            pred = predictions[jokic_pid]
            self.stdout.write(
                f"Jokić box_obpr: {pred['box_obpr']:+.3f}  box_dbpr: {pred['box_dbpr']:+.3f}  "
                f"total: {pred['box_obpr']+pred['box_dbpr']:+.3f}"
            )

        # BPM correlation and Q4 divergence (2026 only — needs metrics CSV)
        metrics_path = Path(__file__).parent.parent.parent.parent.parent / "metrics_output" / "nba_metrics_2025_26.csv"
        if metrics_path.exists() and season_year == 2026:
            try:
                import pandas as pd
                mdf = pd.read_csv(metrics_path)
                bpm_map = {
                    str(r["player_name"]).lower().strip(): float(r["BPM"])
                    for _, r in mdf.iterrows() if str(r.get("BPM", "")).strip() not in ("", "nan")
                }
                usg_map = {
                    str(r["player_name"]).lower().strip(): float(r["USG_pct"])
                    for _, r in mdf.iterrows() if str(r.get("USG_pct", "")).strip() not in ("", "nan")
                }
                bpr_vals, bpm_vals, usg_vals = [], [], []
                for pid, pred in predictions.items():
                    name = name_map.get(pid, "")
                    bpm = bpm_map.get(name.lower().strip())
                    usg = usg_map.get(name.lower().strip(), 0)
                    if bpm is not None:
                        bpr_vals.append(pred["box_obpr"] + pred["box_dbpr"])
                        bpm_vals.append(bpm)
                        usg_vals.append(usg)
                if len(bpr_vals) >= 20:
                    r_bpm, _ = scipy.stats.pearsonr(bpr_vals, bpm_vals)
                    self.stdout.write(f"BPM correlation: {r_bpm:.3f} (was 0.592)")
                    # Q4 divergence — BBref stores USG% as percentage (33.4) not decimal (0.334)
                    bpr_arr = np.array(bpr_vals)
                    bpm_arr = np.array(bpm_vals)
                    usg_arr = np.array(usg_vals)
                    # Auto-detect format: if median > 1, it's percentage
                    usg_threshold = 28.0 if np.median(usg_arr[usg_arr > 0]) > 1.0 else 0.28
                    q4_mask = usg_arr > usg_threshold
                    if q4_mask.sum() >= 3 and bpr_arr.std() > 0 and bpm_arr.std() > 0:
                        z_bpr = (bpr_arr - bpr_arr.mean()) / bpr_arr.std()
                        z_bpm = (bpm_arr - bpm_arr.mean()) / bpm_arr.std()
                        q4_div = float((z_bpr[q4_mask] - z_bpm[q4_mask]).mean())
                        self.stdout.write(f"Q4 divergence:   {q4_div:+.3f} (was -0.978)")
                    # Determine status
                    improved = r_bpm > 0.592
                    status = self.style.SUCCESS("IMPROVEMENT") if improved else self.style.WARNING("NO CHANGE / REGRESSION")
                    self.stdout.write(f"Status: {status}")
            except Exception as e:
                self.stdout.write(f"  (BPM/Q4 checks skipped: {e})")
        self.stdout.write("=" * 55)

    def _run_validation(
        self,
        predictions: dict[int, dict],
        stats_values: list[dict],
        artifacts: dict,
        old_box_bpr: dict[int, float],
        season_year: int,
    ) -> None:
        """Run validation checks, print summary, save comparison CSV."""
        import numpy as np
        import scipy.stats
        import pandas as pd

        # ── Load BPM from metrics CSV ──────────────────────────────────────────
        metrics_path = Path(__file__).parent.parent.parent.parent.parent / "metrics_output" / "nba_metrics_2025_26.csv"
        bpm_map: dict[str, float] = {}
        if metrics_path.exists():
            mdf = pd.read_csv(metrics_path)
            for _, row in mdf.iterrows():
                if pd.notna(row.get("BPM")):
                    bpm_map[str(row["player_name"]).lower().strip()] = float(row["BPM"])

        # ── Build comparison rows ──────────────────────────────────────────────
        from nba.models import NBAPlayer
        name_map = {
            p.pk: p.name
            for p in NBAPlayer.objects.filter(pk__in=predictions.keys()).only("pk", "name")
        }
        # minutes + usg lookup (keyed by player_id)
        min_map = {p["player_id"]: (p.get("mpg") or 0) * (p.get("gp") or 0)
                   for p in stats_values}
        team_map = {p["player_id"]: p.get("team_id") for p in stats_values}
        usg_map  = {p["player_id"]: (p.get("usg_pct") or 0.0) for p in stats_values}

        rows = []
        for pid, pred in predictions.items():
            name   = name_map.get(pid, f"id={pid}")
            new_b  = round(pred["box_obpr"] + pred["box_dbpr"], 3)
            old_b  = old_box_bpr.get(pid)
            bpm    = bpm_map.get(name.lower().strip())
            rows.append({
                "player_name":   name,
                "player_id":     pid,
                "team_id":       team_map.get(pid),
                "minutes":       min_map.get(pid, 0),
                "usg_pct":       usg_map.get(pid, 0.0),
                "box_bpr_old":   old_b,
                "box_bpr_new":   new_b,
                "box_obpr_new":  pred["box_obpr"],
                "box_dbpr_new":  pred["box_dbpr"],
                "BPM":           bpm,
                "divergence_old": round(old_b - bpm, 3) if (old_b is not None and bpm is not None) else None,
                "divergence_new": round(new_b - bpm, 3) if bpm is not None else None,
            })

        df = pd.DataFrame(rows)
        out_path = metrics_path.parent / "box_bpr_fixed_2025_26.csv"
        df.to_csv(out_path, index=False)
        self.stdout.write(f"\n[SAVED] {out_path}")

        # ── Validation checks ──────────────────────────────────────────────────
        off_alpha = artifacts.get("off_cv_alpha", float("nan"))
        def_alpha = artifacts.get("def_cv_alpha", float("nan"))

        # Check: BPM correlation
        valid_bpm = df[df["BPM"].notna() & df["box_bpr_new"].notna()]
        r_bpm = float(scipy.stats.pearsonr(valid_bpm["box_bpr_new"], valid_bpm["BPM"])[0]) if len(valid_bpm) > 10 else float("nan")

        # Check: Jokić z-score
        jokic_row = df[df["player_name"].str.contains("Joki", na=False)]
        z_jokic = float("nan")
        if not jokic_row.empty and not df["box_bpr_new"].std() == 0:
            mu, sigma = df["box_bpr_new"].mean(), df["box_bpr_new"].std()
            z_jokic = float((jokic_row.iloc[0]["box_bpr_new"] - mu) / sigma)

        # Check: Q4 usage divergence — usg_pct is decimal (0.28 = 28%), not percentage
        usg_threshold = 0.28 if df["usg_pct"].median() < 1.0 else 28.0
        valid_q4 = df[(df["usg_pct"] > usg_threshold) & df["BPM"].notna() & df["box_bpr_new"].notna()]
        q4_divergence = float("nan")
        if len(valid_q4) >= 3:
            def _z(s): return (s - s.mean()) / s.std() if s.std() > 0 else s * 0
            full_valid = df[df["BPM"].notna() & df["box_bpr_new"].notna()].copy()
            full_valid["z_bpr"] = _z(full_valid["box_bpr_new"])
            full_valid["z_cons"] = _z(full_valid["BPM"])
            full_valid["div"] = full_valid["z_bpr"] - full_valid["z_cons"]
            q4_mask = full_valid["player_name"].isin(valid_q4["player_name"])
            q4_divergence = float(full_valid[q4_mask]["div"].mean())

        top_off_feat = artifacts.get("off_importance", [("?", 0)])[0][0]
        top_def_feat = artifacts.get("def_importance", [("?", 0)])[0][0]

        # ── Print summary ──────────────────────────────────────────────────────
        self.stdout.write("\n" + "=" * 55)
        self.stdout.write("BOX BPR FIX VALIDATION")
        self.stdout.write("=" * 55)
        self.stdout.write(f"Alpha selected (OBPR): {off_alpha:.2f}")
        self.stdout.write(f"Alpha selected (DBPR): {def_alpha:.2f}")

        def _check(label, val, target, direction="above", was=None):
            if was is not None:
                was_str = f" (was {was})"
            else:
                was_str = ""
            ok = (val > target) if direction == "above" else (val < target)
            status = self.style.SUCCESS("PASS") if ok else self.style.WARNING("FAIL")
            tgt_sym = ">" if direction == "above" else "<"
            self.stdout.write(
                f"{label}: {val:.3f}{was_str} — [{status}] (target {tgt_sym}{target})"
            )
            return ok

        c1 = _check("box_bpr vs BPM correlation", r_bpm,        0.70, "above", was=0.493)
        c2 = _check("Jokić z-score",              z_jokic,      2.0,  "above", was=1.36)
        c3 = _check("Q4 usage divergence",        q4_divergence,-0.30,"above", was=-0.742)
        c4 = off_alpha < 50.0
        self.stdout.write(
            f"Alpha < 50 (OBPR): {'PASS' if c4 else 'FAIL'} (was 50, now {off_alpha:.2f})"
        )
        self.stdout.write(f"Top offensive feature: {top_off_feat}")
        self.stdout.write(f"Top defensive feature: {top_def_feat}")

        n_pass = sum([c1, c2, c3, c4])
        ready = n_pass >= 3
        overall = self.style.SUCCESS("READY FOR RAPM INTEGRATION") if ready else self.style.WARNING("NEEDS FURTHER WORK")
        self.stdout.write(f"\nOverall ({n_pass}/4 passed): {overall}")
        self.stdout.write("=" * 55)
