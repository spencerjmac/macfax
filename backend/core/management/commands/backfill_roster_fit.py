"""
backfill_roster_fit — Run the full Phase 1→2→3→4 fit pipeline for historical
BPR-capable source seasons so that historical TeamRosterFit rows exist and
Model E in the backtest becomes genuinely testable.

A season is "BPR-capable" when it has PlayerGameStint (PBP) data, which is the
prerequisite for the RAPM-based BPR pipeline.  Without stints there is no RAPM;
without RAPM-informed BPR, the projected_obpr/dbpr values in Phase 1 fall back
to box-score-only proxies, providing insufficient signal for meaningful fit
scores.

Currently BPR-capable: seasons with PlayerGameStint rows (auto-detected from DB).
For this codebase that is 2023, 2024, 2025 (and 2026 for the live season).
2021 and 2022 PSS exists but without stints — those seasons are ineligible.

Pipeline per season Y:
  Phase 1 — compute_player_projections  → PlayerSeasonProjection rows
  Phase 2 — compute_player_minutes      → minutes_share_p2 / role_bucket etc.
  Phase 3 — compute_roster_fit (Phase3) → TeamRosterFit rows (overall/off/def scores)
  Phase 4 — compute_roster_fit (Phase4) → adjusted_off_fit / adjusted_def_fit
             (uses pace + scheme style from game logs; gracefully skips if unavailable)

Leakage safety:
  All inputs are from source season Y only (PSS for Y, game logs for Y).
  The TeamRosterFit from_season=Y is used to predict Y+1 outcomes — no
  target-year information enters the computation.

Usage:
  python manage.py backfill_roster_fit
  python manage.py backfill_roster_fit --bpr-capable-only
  python manage.py backfill_roster_fit --seasons 2024 2025
  python manage.py backfill_roster_fit --seasons 2023 --dry-run
"""

import logging

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


def bpr_capable_seasons() -> list[int]:
    """
    Return sorted list of seasons that qualify for historical TeamRosterFit
    backfill.

    A season qualifies when it has PlayerGameStint data (the prerequisite for the
    RAPM / BPR pipeline).  Seasons without stints (e.g. 2021, 2022) are
    ineligible: their PSS rows have null obpr/dbpr and produce fit scores that
    carry no RAPM-informed signal.

    This is intentionally data-driven rather than hard-coded so future ingests
    automatically expand the eligible set.
    """
    from core.models import PlayerGameStint
    return sorted(
        set(
            PlayerGameStint.objects
            .values_list("game__season_year", flat=True)
            .distinct()
        )
    )


class Command(BaseCommand):
    help = (
        "Backfill historical TeamRosterFit for BPR-capable source seasons "
        "(requires PlayerGameStint → runs Phase 1→2→3→4 fit pipeline per season)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--seasons",
            nargs="+",
            type=int,
            default=None,
            help=(
                "Explicit list of from-season years to backfill (e.g. --seasons 2023 2024 2025). "
                "If omitted, uses --bpr-capable-only behaviour."
            ),
        )
        parser.add_argument(
            "--bpr-capable-only",
            action="store_true",
            default=False,
            help=(
                "Automatically select all seasons with PlayerGameStint data as "
                "the eligible set (default behaviour when --seasons is omitted)."
            ),
        )
        parser.add_argument(
            "--skip-phase4",
            action="store_true",
            default=False,
            help=(
                "Skip Phase 4 (pace & scheme contextual modifiers). "
                "adjusted_off_fit / adjusted_def_fit will remain null; "
                "the engine falls back to 50 (neutral) for those seasons."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Show which seasons would be processed and exit without writing.",
        )

    def handle(self, *args, **options):
        seasons_arg = options["seasons"]
        dry_run = options["dry_run"]
        skip_phase4 = options["skip_phase4"]

        capable = bpr_capable_seasons()

        if seasons_arg is not None:
            ineligible = [s for s in seasons_arg if s not in capable]
            if ineligible:
                raise CommandError(
                    f"Season(s) {ineligible} are not BPR-capable (no PlayerGameStint data). "
                    f"BPR-capable seasons: {capable}. "
                    f"Use --bpr-capable-only to auto-select eligible seasons."
                )
            target_seasons = sorted(seasons_arg)
        else:
            target_seasons = capable

        self.stdout.write(
            f"\n{'='*68}\n"
            f"  Historical TeamRosterFit Backfill\n"
            f"{'='*68}"
        )
        self.stdout.write(f"  BPR-capable seasons (auto-detected) : {capable}")
        self.stdout.write(f"  Seasons to process                  : {target_seasons}")
        self.stdout.write(f"  Phase 4 (context)                   : {'skip' if skip_phase4 else 'run'}")
        if dry_run:
            self.stdout.write("\n  DRY RUN — no writes will occur.")
            return

        self.stdout.write("")

        total_summary = []

        for season_year in target_seasons:
            self.stdout.write(f"--- Season {season_year} ---")
            season_result = self._backfill_season(season_year, skip_phase4=skip_phase4)
            total_summary.append(season_result)
            if season_result["phase4_skipped"]:
                phase4_str = "skipped"
            else:
                phase4_str = (
                    f"{season_result['phase4_n_teams']} teams "
                    f"({season_result['phase4_n_with_style']} with style)"
                )
            self.stdout.write(
                self.style.SUCCESS(
                    f"  Season {season_year}: "
                    f"Phase1={season_result['phase1_n']} projections, "
                    f"Phase2={season_result['phase2_n']} updated, "
                    f"Phase3={season_result['phase3_n_teams']} teams, "
                    f"Phase4={phase4_str}"
                )
            )

        self.stdout.write(
            f"\n{'='*68}\n"
            f"  Backfill complete: {len(target_seasons)} season(s) processed.\n"
            f"  TeamRosterFit now exists for: {target_seasons}\n"
            f"{'='*68}"
        )

    def _backfill_season(self, season_year: int, skip_phase4: bool) -> dict:
        """
        Run Phase 1→2→3(→4) for one season year.

        Leakage safety: all inputs come from `season_year` PSS / game data.
        The resulting TeamRosterFit.from_season=season_year predicts season_year+1.
        """
        from core.analytics.player_value.projection.pipeline import run_projection_pipeline
        from core.analytics.player_value.minutes.service import run_minutes_pipeline
        from core.analytics.player_value.fit.service import run_fit_pipeline

        # Phase 1 — Player projections from season_year PSS
        self.stdout.write(f"  [Phase 1] compute_player_projections --season {season_year}")
        p1 = run_projection_pipeline(season_year=season_year)
        n_p1 = p1.get("n_created", 0) + p1.get("n_updated", 0)
        self.stdout.write(f"            → {n_p1} projection records "
                          f"({p1.get('n_created', 0)} created, {p1.get('n_updated', 0)} updated)")

        # Phase 2 — Minutes allocation
        self.stdout.write(f"  [Phase 2] compute_player_minutes --season {season_year}")
        p2 = run_minutes_pipeline(season_year=season_year)
        n_p2 = p2.get("n_written", 0)
        self.stdout.write(f"            → {n_p2} projection rows updated")

        # Phase 3 — Roster fit
        self.stdout.write(f"  [Phase 3] compute_roster_fit --season {season_year}")
        p3 = run_fit_pipeline(season_year=season_year, verbose=False)
        n_p3_teams = p3.get("n_teams", 0)
        n_p3_written = p3.get("n_written", 0)
        self.stdout.write(f"            → {n_p3_teams} teams scored, {n_p3_written} TeamRosterFit rows written")

        # Phase 4 — Contextual (pace + scheme) adjustments
        p4_n_teams = 0
        p4_n_with_style = 0
        p4_skipped = skip_phase4

        if not skip_phase4:
            self.stdout.write(f"  [Phase 4] compute_roster_fit --context --season {season_year}")
            try:
                from core.analytics.player_value.fit.context.service import run_contextual_fit_pipeline
                p4 = run_contextual_fit_pipeline(season_year=season_year, verbose=False)
                p4_n_teams = p4.get("n_teams", 0)
                p4_n_with_style = p4.get("n_with_style", 0)
                self.stdout.write(
                    f"            → {p4_n_teams} teams scored, {p4_n_with_style} with style data"
                )
            except Exception as exc:
                logger.warning(
                    "[BackfillRosterFit] Phase 4 failed for season %d: %s",
                    season_year, exc,
                )
                self.stdout.write(
                    self.style.WARNING(
                        f"          Phase 4 failed for {season_year}: {exc}. "
                        f"adjusted_off_fit / adjusted_def_fit will remain null."
                    )
                )
                p4_skipped = True

        return {
            "season_year": season_year,
            "phase1_n": n_p1,
            "phase2_n": n_p2,
            "phase3_n_teams": n_p3_teams,
            "phase3_n_written": n_p3_written,
            "phase4_n_teams": p4_n_teams,
            "phase4_n_with_style": p4_n_with_style,
            "phase4_skipped": p4_skipped,
        }
