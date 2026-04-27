"""
compute_player_projections — Generate next-season player projections.

For every player with a PlayerSeasonStats row in the target season,
fits a Phase 1 projection of their expected performance in the following
season and writes PlayerSeasonProjection records.

Projection pipeline (10 steps in engine.py):
  1.  Classify recruitment_type (returner / transfer / newcomer)
  2.  Extract current-season RAPM + Box BPR signals
  3.  Select talent signal (RAPM primary; box BPR only as fallback when RAPM absent)
  4.  Estimate possession counts (fall back to MPG if absent)
  5.  Year-to-year shrinkage toward D1 average
  6.  Multi-year trend (if prior RAPM available)
  7.  Development / aging adjustment by experience stage
  8.  Transfer competition translation (transfers only)
  9.  Projection uncertainty score (0 = low, 1 = high)
  10. Baseline minutes share estimate

Run AFTER:
  python manage.py compute_ncaa_bpr --season YEAR     (provides obpr/dbpr)
  python manage.py compute_player_ffi --season YEAR   (optional, not required)

Usage:
  python manage.py compute_player_projections --season 2026
  python manage.py compute_player_projections --season 2026 --validate
"""

import logging

from django.core.management.base import BaseCommand, CommandError

from ncaa.analytics.player_value.projection.pipeline import run_projection_pipeline

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Generate Phase 1 next-season player projections and write PlayerSeasonProjection records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=int,
            required=True,
            help="From-season year (e.g. 2026 → projects into 2027).",
        )
        parser.add_argument(
            "--validate",
            action="store_true",
            default=False,
            help="Print diagnostic tables after computing.",
        )

    def handle(self, *args, **options):
        season_year: int = options["season"]
        do_validate: bool = options["validate"]

        logging.basicConfig(level=logging.INFO)

        self.stdout.write(
            f"Computing player projections from season {season_year} "
            f"→ {season_year + 1} …"
        )

        try:
            summary = run_projection_pipeline(season_year=season_year, verbose=True)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        breakdown = summary["recruitment_type_breakdown"]
        split_note = f", split-season: {summary.get('n_split_season', 0)} canonicalized" if summary.get('n_split_season') else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {summary['n_projected']} projections "
                f"({summary['n_created']} created, {summary['n_updated']} updated"
                f"{split_note}). "
                f"Types: returners={breakdown.get('returner', 0)}, "
                f"transfers={breakdown.get('transfer', 0)}, "
                f"newcomers={breakdown.get('newcomer', 0)} [umbrella bucket]. "
                f"With prior RAPM: {summary['n_with_prior_rapm']}."
            )
        )

        if do_validate:
            self._run_validation(season_year, summary)

    def _run_validation(self, season_year: int, summary: dict) -> None:
        from ncaa.models import PlayerSeasonProjection

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(f"PROJECTION VALIDATION — from_season={season_year}")
        self.stdout.write("=" * 70)

        rows = list(
            PlayerSeasonProjection.objects
            .filter(from_season__year=season_year)
            .select_related("player", "team")
            .order_by("-projected_bpr")
        )

        # ── Top 25 by projected BPR ───────────────────────────────────────────
        self.stdout.write(f"\nTop 25 by projected BPR (→ {season_year + 1}):\n")
        header = f"{'Player':<28} {'Team':<22} {'Type':<10} {'OBPR':>6} {'DBPR':>6} {'BPR':>6} {'Min%':>6} {'Unc':>6}"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))
        for r in rows[:25]:
            team_name = r.team.name if r.team else "—"
            self.stdout.write(
                f"{r.player.display_name:<28} {team_name:<22} "
                f"{r.recruitment_type:<10} "
                f"{(r.projected_obpr or 0):>6.2f} "
                f"{(r.projected_dbpr or 0):>6.2f} "
                f"{(r.projected_bpr or 0):>6.2f} "
                f"{(r.projected_minutes_share or 0):>6.3f} "
                f"{(r.projection_uncertainty or 0):>6.3f}"
            )

        # ── Split-season info ────────────────────────────────────────────────
        n_split = summary.get("n_split_season", 0)
        if n_split:
            self.stdout.write(
                f"\nSplit-season players: {n_split} (canonical row = highest poss)."
            )

        # ── Distribution by recruitment type ────────────────────────────────────
        self.stdout.write("\nRecruitment type breakdown:")
        for rtype, count in summary["recruitment_type_breakdown"].items():
            pct = 100.0 * count / max(summary["n_projected"], 1)
            note = "  ← umbrella (freshman + grad-transfer + JUCO; requires roster data to split)" if rtype == "newcomer" else ""
            self.stdout.write(f"  {rtype:<12} {count:>5} ({pct:.1f}%){note}")

        # ── Uncertainty distribution ───────────────────────────────────────────
        uncertainties = [r.projection_uncertainty for r in rows if r.projection_uncertainty is not None]
        if uncertainties:
            import statistics
            self.stdout.write(
                f"\nUncertainty: mean={statistics.mean(uncertainties):.3f}, "
                f"median={statistics.median(uncertainties):.3f}, "
                f"stdev={statistics.stdev(uncertainties):.3f}"
            )

        # ── Consistency check: projected_bpr ≈ projected_obpr + projected_dbpr ─
        mismatches = 0
        for r in rows:
            if r.projected_obpr is not None and r.projected_dbpr is not None and r.projected_bpr is not None:
                expected = round(r.projected_obpr + r.projected_dbpr, 4)
                if abs(expected - r.projected_bpr) > 0.01:
                    mismatches += 1
        if mismatches:
            self.stdout.write(
                self.style.WARNING(
                    f"\nWARNING: {mismatches} rows where projected_bpr ≠ obpr + dbpr (rounding?)"
                )
            )
        else:
            self.stdout.write("\nConsistency check passed: projected_bpr = obpr + dbpr ✓")
