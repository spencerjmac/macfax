"""
compute_roster_fit — Phase 3 + Phase 4 roster fit scoring.

Runs AFTER compute_player_minutes: reads PlayerSeasonProjection rows that
already carry Phase 2 minutes output (role_bucket, minutes_share_p2, etc.),
groups them by team, scores offensive + defensive roster fit, and writes one
TeamRosterFit row per (team, from_season).

Pass --context to also run Phase 4 (pace & scheme contextual modifiers) after
Phase 3 completes.  Phase 3 must succeed first.

Usage:
  python manage.py compute_roster_fit --season 2026
  python manage.py compute_roster_fit --season 2026 --validate
  python manage.py compute_roster_fit --season 2026 --context
  python manage.py compute_roster_fit --season 2026 --context --validate
"""

import logging

from django.core.management.base import BaseCommand, CommandError

from ncaa.analytics.player_value.fit.service import run_fit_pipeline
from ncaa.analytics.player_value.fit.context.service import run_contextual_fit_pipeline

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Phase 3 + Phase 4: Compute roster fit scores for all teams in the given "
        "from_season and persist results to TeamRosterFit. "
        "Use --context to also run Phase 4 pace & scheme modifiers."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=int,
            required=True,
            help="From-season year whose projections to score (e.g. 2026).",
        )
        parser.add_argument(
            "--validate",
            action="store_true",
            default=False,
            help="Print top/bottom teams and subcomponent distributions after scoring.",
        )
        parser.add_argument(
            "--context",
            action="store_true",
            default=False,
            help="Also run Phase 4 (pace & scheme contextual modifiers) after Phase 3.",
        )

    def handle(self, *args, **options):
        season_year = options["season"]
        do_validate = options["validate"]
        do_context  = options["context"]

        logging.basicConfig(level=logging.INFO)

        self.stdout.write(
            f"[Phase 3] Computing roster fit scores for season {season_year} …"
        )

        try:
            summary = run_fit_pipeline(season_year=season_year, verbose=True)
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {summary['n_players']} players · "
                f"{summary['n_teams']} teams scored · "
                f"{summary['n_written']} TeamRosterFit rows written · "
                f"{summary['n_errors']} errors."
            )
        )

        if do_context:
            self.stdout.write(
                f"\n[Phase 4] Computing pace & scheme contextual fit for season {season_year} …"
            )
            try:
                ctx_summary = run_contextual_fit_pipeline(season_year=season_year, verbose=True)
            except Exception as exc:  # noqa: BLE001
                raise CommandError(str(exc)) from exc

            self.stdout.write(
                self.style.SUCCESS(
                    f"Phase 4 done: {ctx_summary['n_teams']} teams scored · "
                    f"{ctx_summary['n_with_style']} with style data · "
                    f"{ctx_summary['n_written']} rows updated · "
                    f"{ctx_summary['n_errors']} errors."
                )
            )

        if do_validate:
            self._run_validation(season_year, include_context=do_context)

    def _run_validation(self, season_year: int, include_context: bool = False) -> None:
        from ncaa.models import TeamRosterFit
        from django.db.models import Avg, StdDev, Max, Min

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(f"ROSTER FIT VALIDATION — from_season={season_year}")
        self.stdout.write("=" * 70)

        qs = TeamRosterFit.objects.filter(from_season__year=season_year)
        n = qs.count()
        if not n:
            self.stdout.write("  No TeamRosterFit rows found.")
            return

        self.stdout.write(f"\n  Total teams scored: {n}")

        # ── Score distributions ───────────────────────────────────────────
        stats = qs.aggregate(
            avg_overall=Avg("overall_fit_score"),
            avg_off=Avg("offensive_fit_score"),
            avg_def=Avg("defensive_fit_score"),
            std_overall=StdDev("overall_fit_score"),
            max_overall=Max("overall_fit_score"),
            min_overall=Min("overall_fit_score"),
        )

        self.stdout.write("\n  Score distributions (overall / off / def):")
        self.stdout.write(
            f"    mean: {stats['avg_overall']:.1f} / "
            f"{stats['avg_off']:.1f} / {stats['avg_def']:.1f}"
        )
        self.stdout.write(
            f"    std:  {stats['std_overall']:.1f}"
        )
        self.stdout.write(
            f"    range: {stats['min_overall']:.1f} – {stats['max_overall']:.1f}"
        )

        # ── Top 10 overall ────────────────────────────────────────────────
        self.stdout.write("\n  TOP 10 teams by overall fit:")
        top10 = (
            qs.select_related("team")
            .order_by("-overall_fit_score")[:10]
        )
        for rank, row in enumerate(top10, 1):
            self.stdout.write(
                f"    {rank:2d}. {str(row.team):<30s}  "
                f"overall={row.overall_fit_score:.1f}  "
                f"off={row.offensive_fit_score:.1f}  "
                f"def={row.defensive_fit_score:.1f}"
            )

        # ── Bottom 10 overall ─────────────────────────────────────────────
        self.stdout.write("\n  BOTTOM 10 teams by overall fit:")
        bot10 = (
            qs.select_related("team")
            .order_by("overall_fit_score")[:10]
        )
        for rank, row in enumerate(bot10, 1):
            self.stdout.write(
                f"    {rank:2d}. {str(row.team):<30s}  "
                f"overall={row.overall_fit_score:.1f}  "
                f"off={row.offensive_fit_score:.1f}  "
                f"def={row.defensive_fit_score:.1f}"
            )

        # ── Subcomponent averages ─────────────────────────────────────────
        sub_stats = qs.aggregate(
            creation=Avg("creation_fit"),
            shooting=Avg("shooting_fit"),
            ball_sec=Avg("ball_security_fit"),
            finishing=Avg("finishing_fit"),
            pressure=Avg("pressure_fit"),
            off_reb=Avg("off_rebounding_fit"),
            role_off=Avg("role_balance_off_fit"),
            rim=Avg("rim_protection_fit"),
            def_reb=Avg("def_rebounding_fit"),
            disruption=Avg("disruption_fit"),
            foul_disc=Avg("foul_discipline_fit"),
            perimeter=Avg("perimeter_defense_fit"),
            size=Avg("size_coverage_fit"),
            mobility=Avg("mobility_fit"),
            role_def=Avg("role_balance_def_fit"),
        )

        self.stdout.write("\n  Average subcomponent scores (target ≈ 50):")
        self.stdout.write("  Offensive:")
        for label, key in [
            ("  creation",     "creation"),
            ("  shooting",     "shooting"),
            ("  ball_security","ball_sec"),
            ("  finishing",    "finishing"),
            ("  pressure",     "pressure"),
            ("  off_rebound",  "off_reb"),
            ("  role_balance", "role_off"),
        ]:
            val = sub_stats[key]
            bar = int((val or 50) / 2)
            self.stdout.write(f"    {label:<18s} {val:5.1f}")

        self.stdout.write("  Defensive:")
        for label, key in [
            ("  rim_protection",  "rim"),
            ("  def_rebounding",  "def_reb"),
            ("  disruption",      "disruption"),
            ("  foul_discipline", "foul_disc"),
            ("  perimeter_def",   "perimeter"),
            ("  size_coverage",   "size"),
            ("  mobility",        "mobility"),
            ("  role_balance",    "role_def"),
        ]:
            val = sub_stats[key]
            self.stdout.write(f"    {label:<18s} {val:5.1f}")

        # ── Phase 4 contextual validation ─────────────────────────────────
        if include_context:
            self.stdout.write("\n" + "=" * 70)
            self.stdout.write("PHASE 4 CONTEXTUAL FIT — pace & scheme modifiers")
            self.stdout.write("=" * 70)

            ctx_qs = qs.filter(has_team_style_data=True)
            n_ctx = ctx_qs.count()
            n_neutral = qs.filter(has_team_style_data=False).count()
            self.stdout.write(
                f"\n  Teams with style data: {n_ctx}  |  "
                f"Neutral (no style data): {n_neutral}"
            )

            if n_ctx:
                ctx_stats = ctx_qs.aggregate(
                    avg_pace_align=Avg("pace_alignment_score"),
                    avg_pace_mod=Avg("pace_modifier"),
                    avg_off_scheme_align=Avg("off_scheme_alignment_score"),
                    avg_off_scheme_mod=Avg("off_scheme_modifier"),
                    avg_def_scheme_align=Avg("def_scheme_alignment_score"),
                    avg_def_scheme_mod=Avg("def_scheme_modifier"),
                    avg_off_ctx=Avg("off_contextual_modifier"),
                    avg_def_ctx=Avg("def_contextual_modifier"),
                    avg_adj_overall=Avg("adjusted_overall_fit"),
                    max_adj_overall=Max("adjusted_overall_fit"),
                    min_adj_overall=Min("adjusted_overall_fit"),
                )
                self.stdout.write("\n  Contextual modifier averages (should be ~0 on average):")
                self.stdout.write(
                    f"    pace alignment   : {ctx_stats['avg_pace_align']:.1f} "
                    f"(modifier: {ctx_stats['avg_pace_mod']:+.2f})"
                )
                self.stdout.write(
                    f"    off scheme align : {ctx_stats['avg_off_scheme_align']:.1f} "
                    f"(modifier: {ctx_stats['avg_off_scheme_mod']:+.2f})"
                )
                self.stdout.write(
                    f"    def scheme align : {ctx_stats['avg_def_scheme_align']:.1f} "
                    f"(modifier: {ctx_stats['avg_def_scheme_mod']:+.2f})"
                )
                self.stdout.write(
                    f"    off contextual   : {ctx_stats['avg_off_ctx']:+.2f}"
                )
                self.stdout.write(
                    f"    def contextual   : {ctx_stats['avg_def_ctx']:+.2f}"
                )
                self.stdout.write(
                    f"\n  Adjusted overall — avg: {ctx_stats['avg_adj_overall']:.1f}  "
                    f"range: {ctx_stats['min_adj_overall']:.1f}–{ctx_stats['max_adj_overall']:.1f}"
                )

                self.stdout.write("\n  TOP 10 by adjusted overall fit:")
                top10_ctx = (
                    qs.filter(has_team_style_data=True)
                    .select_related("team")
                    .order_by("-adjusted_overall_fit")[:10]
                )
                for rank, row in enumerate(top10_ctx, 1):
                    delta = (row.adjusted_overall_fit or 0) - (row.overall_fit_score or 0)
                    self.stdout.write(
                        f"    {rank:2d}. {str(row.team):<30s}  "
                        f"adj={row.adjusted_overall_fit:.1f}  "
                        f"phase3={row.overall_fit_score:.1f}  "
                        f"delta={delta:+.1f}"
                    )

