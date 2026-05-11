"""
Management command: nba_compute_box_bpr

Computes NBA Box BPR (box_obpr, box_dbpr, box_bpr) for all qualified
players in a season using Ridge regression on per-100-possession
box-score features.

Training targets (in priority order):
  1. baseline_obpr / baseline_dbpr from RAPM (team-quality-adjusted, preferred)
  2. o_mpir / d_mpir (NBA.com E_OFF/DEF_RATING residuals, fallback)

Run nba_compute_baseline_rapm before this command to enable RAPM targets.

Usage:
  python manage.py nba_compute_box_bpr --season 2026
  python manage.py nba_compute_box_bpr --season 2026 --dry-run
  python manage.py nba_compute_box_bpr --season 2026 --oof
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from nba.analytics.box_bpr import (
    compute_opp_quality_map,
    compute_team_adj_em_map,
    out_of_fold_box_bpr,
    predict_nba_box_bpr,
    train_nba_box_bpr,
)
from nba.models import NBAPlayerSeasonStats

logger = logging.getLogger(__name__)


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

    def handle(self, *args, **options):
        season_year: int = options["season"]
        dry_run: bool = options["dry_run"]
        use_oof: bool = options["oof"]

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
                "stl_pct", "blk_pct",
                "on_court_poss", "on_court_adj_em",
                "on_court_adj_d",
                "o_mpir", "d_mpir",
                "baseline_obpr", "baseline_dbpr",
            )
        )

        self.stdout.write(f"Loaded {len(stats_values)} player-season rows")

        if not stats_values:
            raise CommandError(f"No stats found for season {season_year}. Run nba_compute_player_stats first.")

        # ── 2. Build lookup maps ───────────────────────────────────────────────
        self.stdout.write("Computing opponent quality and team adj_em maps...")
        opp_quality_map = compute_opp_quality_map(season_year)
        team_adj_em_map = compute_team_adj_em_map(season_year)
        self.stdout.write(f"  opp_quality: {len(opp_quality_map)} teams")
        self.stdout.write(f"  team_adj_em: {len(team_adj_em_map)} teams")

        # ── 3. Build target maps — prefer RAPM (team-quality-adjusted) ──────────
        target_obpr: dict[int, float] = {}
        target_dbpr: dict[int, float] = {}
        n_rapm_off = n_rapm_def = n_mpir_off = n_mpir_def = 0

        for p in stats_values:
            pid = p["player_id"]
            if p.get("baseline_obpr") is not None:
                target_obpr[pid] = p["baseline_obpr"]
                n_rapm_off += 1
            elif p.get("o_mpir") is not None:
                target_obpr[pid] = p["o_mpir"]
                n_mpir_off += 1
            if p.get("baseline_dbpr") is not None:
                target_dbpr[pid] = p["baseline_dbpr"]
                n_rapm_def += 1
            elif p.get("d_mpir") is not None:
                target_dbpr[pid] = p["d_mpir"]
                n_mpir_def += 1

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

        # ── 4. Train / predict ────────────────────────────────────────────────
        now = timezone.now()

        if use_oof:
            self.stdout.write("Running out-of-fold Box BPR (--oof)...")
            predictions, _ = out_of_fold_box_bpr(
                stats=stats_values,
                opp_quality_map=opp_quality_map,
                team_adj_em_map=team_adj_em_map,
                target_obpr=target_obpr,
                target_dbpr=target_dbpr,
            )
        else:
            self.stdout.write("Training Box BPR on full season...")
            artifacts = train_nba_box_bpr(
                stats=stats_values,
                opp_quality_map=opp_quality_map,
                team_adj_em_map=team_adj_em_map,
                target_obpr=target_obpr,
                target_dbpr=target_dbpr,
            )
            self.stdout.write(
                f"  off alpha={artifacts['off_cv_alpha']:.2f} (n={artifacts['n_train_off']}), "
                f"def alpha={artifacts['def_cv_alpha']:.2f} (n={artifacts['n_train_def']})"
            )
            predictions = predict_nba_box_bpr(
                stats=stats_values,
                opp_quality_map=opp_quality_map,
                team_adj_em_map=team_adj_em_map,
                model_artifacts=artifacts,
            )

        self.stdout.write(f"Box BPR computed for {len(predictions)} players")

        # ── 5. Write results ───────────────────────────────────────────────────
        if dry_run:
            self._print_top_players(predictions, stats_values)
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
