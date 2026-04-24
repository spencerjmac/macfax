"""
compute_player_ffi — Fit 4 factor-specific RAPM models and write the
new Four Factor Impact Index (four_factor_impact_index) and its 8 component
impacts + 4 combined margins to PlayerSeasonStats.

This command implements the player-specific Four Factor Impact system that
is DISTINCT from the existing on-court Four Factors (which measure lineup
environment, not individual player impact).

How it works
============
For each of the four factors (eFG%, TOV%, ORB%, FTR%), we fit a separate
lineup-adjusted regression (RAPM-style) where:
  - Each lineup segment produces two observations (home-offense, away-offense)
  - The target is the factor rate for the offensive side
  - The weights are the relevant opportunity counts
  - The design matrix has offensive and defensive player columns

The resulting coefficients for each player, after sign-convention adjustment,
are:
  off_efg_impact   — player's effect on team eFG% when on offense (pp vs avg)
  def_efg_impact   — player's effect on opp eFG% when on defense (pp vs avg, positive-good)
  off_tov_impact   — player's effect on team TOV% when on offense (pp vs avg, positive-good)
  def_tov_impact   — player's effect on opp TOV% when on defense (pp vs avg, positive-good)
  off_orb_impact   — player's effect on team ORB% when on offense (pp vs avg)
  def_reb_impact   — player's effect on opp ORB% when on defense (pp vs avg, positive-good)
  off_ftr_impact   — player's effect on team FTR when on offense (pp vs avg)
  def_ftr_impact   — player's effect on opp FTR when on defense (pp vs avg, positive-good)

Combined two-way margins and a final 0-100 index are then computed using the
same weights as the Macfax team Four Factor Index (efg=0.45, tov=0.24,
reb=0.22, ftr=0.09).

Run AFTER:
  python manage.py sync_ncaa_pbp   (creates PlayerGameStint rows)

Usage:
  python manage.py compute_player_ffi --season 2026
  python manage.py compute_player_ffi --season 2026 --lambda 500
  python manage.py compute_player_ffi --season 2026 --rapm-years 2024 2025 2026
  python manage.py compute_player_ffi --season 2026 --validate
"""

import logging
import statistics

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.analytics.player_value.ffi.pipeline import run_ffi_pipeline, MIN_POSS_FFI
from core.analytics.player_value.ffi.rapm import FFI_RAPM_LAMBDA_DEFAULT
from core.models import PlayerSeasonStats, Season

logger = logging.getLogger(__name__)

FFI_FIELDS = [
    "off_efg_impact", "def_efg_impact",
    "off_tov_impact", "def_tov_impact",
    "off_orb_impact", "def_reb_impact",
    "off_ftr_impact", "def_ftr_impact",
    "efg_impact_margin", "tov_impact_margin",
    "reb_impact_margin", "ftr_impact_margin",
    "four_factor_impact_index",
]


class Command(BaseCommand):
    help = "Fit factor-specific RAPM and write Four Factor Impact Index to PlayerSeasonStats."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season", type=int, required=True,
            help="Target season year (e.g., 2026)",
        )
        parser.add_argument(
            "--rapm-years", type=int, nargs="+", default=None,
            help="Season years to pool for RAPM (default: target season only). "
                 "E.g. --rapm-years 2024 2025 2026",
        )
        parser.add_argument(
            "--lambda", dest="lambda_val", type=float,
            default=None,
            help=f"RAPM regularization strength (default: auto-tune per factor via CV). "
                 "Providing this value disables per-factor CV and uses a fixed λ for all factors.",
        )
        parser.add_argument(
            "--no-auto-tune", dest="no_auto_tune", action="store_true", default=False,
            help=f"Disable per-factor λ CV and use the fixed --lambda value (default {FFI_RAPM_LAMBDA_DEFAULT}).",
        )
        parser.add_argument(
            "--validate", action="store_true", default=False,
            help="Print diagnostic tables after computing (top-25, comparisons, etc.)",
        )

    def handle(self, *args, **options):
        season_year: int = options["season"]
        rapm_years: list[int] | None = options["rapm_years"]
        lambda_val_opt: float | None = options["lambda_val"]
        no_auto_tune: bool = options["no_auto_tune"]
        do_validate: bool = options["validate"]

        # Determine whether to auto-tune λ per factor:
        # - auto-tune ON by default
        # - disabled if --lambda is explicitly passed or --no-auto-tune is set
        auto_tune = not no_auto_tune and lambda_val_opt is None
        lambda_val: float = lambda_val_opt if lambda_val_opt is not None else FFI_RAPM_LAMBDA_DEFAULT

        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            raise CommandError(f"Season {season_year} not found.")

        years = rapm_years if rapm_years else [season_year]
        self.stdout.write(
            f"Computing Four Factor Impact for season {season_year} "
            f"(RAPM window: {years}, λ={'auto-tune' if auto_tune else lambda_val}) …"
        )

        # ── Fit all 4 factor RAPM models ──────────────────────────────────────────────
        logging.basicConfig(level=logging.INFO)
        results = run_ffi_pipeline(
            years,
            lambda_val=lambda_val,
            auto_tune_lambda=auto_tune,
            verbose=True,
        )

        ffii_count = sum(1 for d in results.values() if d.get("four_factor_impact_index") is not None)
        self.stdout.write(
            f"Factor RAPM done: {len(results)} players with impacts, "
            f"{ffii_count} with four_factor_impact_index"
        )

        # ── Load existing PlayerSeasonStats rows ──────────────────────────────
        stat_map: dict[int, PlayerSeasonStats] = {
            s.player_id: s
            for s in PlayerSeasonStats.objects.filter(season=season)
        }

        # ── Write to DB ───────────────────────────────────────────────────────
        updated = 0
        with transaction.atomic():
            for player_id, impact_dict in results.items():
                stat = stat_map.get(player_id)
                if stat is None:
                    continue  # player not in target season
                for field in FFI_FIELDS:
                    setattr(stat, field, impact_dict.get(field))
                stat.save(update_fields=FFI_FIELDS)
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Written to DB: {updated} PlayerSeasonStats rows updated."
        ))

        # ── Validation diagnostics ────────────────────────────────────────────
        if do_validate:
            self._run_validation(season, results, stat_map, lambda_val)

    def _run_validation(
        self,
        season,
        results: dict,
        stat_map: dict,
        lambda_val: float,
    ) -> None:
        from django.db.models import F

        self.stdout.write("\n" + "="*70)
        self.stdout.write("FOUR FACTOR IMPACT VALIDATION")
        self.stdout.write("="*70)

        # ── Component sign sanity ─────────────────────────────────────────────
        all_vals = {k: [] for k in FFI_FIELDS}
        for d in results.values():
            for k in FFI_FIELDS:
                v = d.get(k)
                if v is not None:
                    all_vals[k].append(v)

        self.stdout.write("\n[Component ranges across all players]")
        for k in FFI_FIELDS:
            vals = all_vals[k]
            if vals:
                self.stdout.write(
                    f"  {k:<30} n={len(vals):5}  "
                    f"min={min(vals):+.2f}  "
                    f"mean={statistics.mean(vals):+.2f}  "
                    f"max={max(vals):+.2f}"
                )

        # ── Top 25 by new FFII ────────────────────────────────────────────────
        self.stdout.write("\n[Top 25 by four_factor_impact_index (new, RAPM-based)]")
        top_new = sorted(
            [(pid, d) for pid, d in results.items() if d.get("four_factor_impact_index") is not None],
            key=lambda x: x[1]["four_factor_impact_index"],
            reverse=True,
        )[:25]

        # Pull display names
        pid_to_name = {
            s.player_id: (
                s.player.display_name if hasattr(s, "player") and s.player else str(s.player_id)
            )
            for s in PlayerSeasonStats.objects.filter(season=season).select_related("player")
        }

        self.stdout.write(f"  {'Rank':<5} {'Player':<28} {'FFII':>6} {'eFG':>7} {'TOV':>7} {'REB':>7} {'FTR':>7}")
        self.stdout.write("  " + "-"*68)
        for rank, (pid, d) in enumerate(top_new, 1):
            name = pid_to_name.get(pid, str(pid))[:26]
            self.stdout.write(
                f"  {rank:<5} {name:<28} "
                f"{d['four_factor_impact_index']:>6.1f} "
                f"{d['efg_impact_margin']:>+7.2f} "
                f"{d['tov_impact_margin']:>+7.2f} "
                f"{d['reb_impact_margin']:>+7.2f} "
                f"{d['ftr_impact_margin']:>+7.2f}"
            )

        # ── Top 25 by old on-court FFI ────────────────────────────────────────
        self.stdout.write("\n[Top 25 by on_court_ffi (old, lineup-environment-based)]")
        old_top = (
            PlayerSeasonStats.objects
            .filter(season=season, on_court_ffi__isnull=False)
            .select_related("player")
            .order_by("-on_court_ffi")[:25]
        )
        self.stdout.write(f"  {'Rank':<5} {'Player':<28} {'on_court_ffi':>13} {'FFII':>6}")
        self.stdout.write("  " + "-"*58)
        for rank, stat in enumerate(old_top, 1):
            name = stat.player.display_name[:26] if stat.player else str(stat.player_id)
            new_ffii = results.get(stat.player_id, {}).get("four_factor_impact_index")
            new_str = f"{new_ffii:.1f}" if new_ffii is not None else " N/A"
            self.stdout.write(
                f"  {rank:<5} {name:<28} "
                f"{stat.on_court_ffi:>13.1f} "
                f"{new_str:>6}"
            )

        # ── Biggest movers (difference old vs new) ────────────────────────────
        self.stdout.write("\n[Players with biggest rank changes (old on_court_ffi → new FFII)]")
        old_ranks: dict[int, int] = {}
        for rank, stat in enumerate(
            PlayerSeasonStats.objects
            .filter(season=season, on_court_ffi__isnull=False)
            .order_by("-on_court_ffi"), 1
        ):
            old_ranks[stat.player_id] = rank

        new_ranks: dict[int, int] = {}
        sorted_new = sorted(
            [(pid, d) for pid, d in results.items() if d.get("four_factor_impact_index") is not None],
            key=lambda x: x[1]["four_factor_impact_index"],
            reverse=True,
        )
        for rank, (pid, _) in enumerate(sorted_new, 1):
            new_ranks[pid] = rank

        # Only players who have BOTH old and new FFII
        common_pids = set(old_ranks) & set(new_ranks)
        rank_deltas = [
            (pid, old_ranks[pid] - new_ranks[pid])  # positive = improved in new system
            for pid in common_pids
        ]
        # Sort by absolute change
        rank_deltas.sort(key=lambda x: abs(x[1]), reverse=True)

        self.stdout.write(f"  {'Player':<28} {'OldRank':>8} {'NewRank':>8} {'Δ':>6}")
        self.stdout.write("  " + "-"*54)
        for pid, delta in rank_deltas[:20]:
            name = pid_to_name.get(pid, str(pid))[:26]
            self.stdout.write(
                f"  {name:<28} "
                f"{old_ranks[pid]:>8} "
                f"{new_ranks[pid]:>8} "
                f"{delta:>+6}"
            )

        # ── Factor means sanity (should be ~0 for all) ────────────────────────
        self.stdout.write("\n[Factor mean impacts across ALL players (should be near 0)]")
        for factor_key, label in [
            ("off_efg_impact", "Off eFG impact"),
            ("def_efg_impact", "Def eFG impact"),
            ("off_tov_impact", "Off TOV impact"),
            ("def_tov_impact", "Def TOV impact"),
            ("off_orb_impact", "Off ORB impact"),
            ("def_reb_impact", "Def REB impact"),
            ("off_ftr_impact", "Off FTR impact"),
            ("def_ftr_impact", "Def FTR impact"),
        ]:
            vals = [d[factor_key] for d in results.values() if factor_key in d]
            if vals:
                self.stdout.write(
                    f"  {label:<26} mean={statistics.mean(vals):+.4f}  "
                    f"std={statistics.pstdev(vals):.4f}"
                )

        self.stdout.write("\n" + "="*70)
        self.stdout.write("VALIDATION COMPLETE")
        self.stdout.write("="*70 + "\n")
