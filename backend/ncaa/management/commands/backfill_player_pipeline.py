"""
backfill_player_pipeline — Run the full NCAA player data pipeline for one or
more historical seasons in dependency order.

Pipeline stages (run per season, in sequence):

  Stage 1  sync_ncaa_player_gamelogs     Player box score ingest (ESPN)
  Stage 2  compute_ncaa_player_season_stats  Aggregate game logs → season averages
  Stage 3  sync_ncaa_pbp                 Play-by-play → PlayerGameStint lineup stints
  Stage 4  compute_ncaa_player_impact    On-court ratings + Four Factors + MPIR
  Stage 5  compute_ncaa_bpr              Bayesian Performance Rating (RAPM + Box prior)
  Stage 6  compute_player_ffi            Four Factor Impact Index
  Stage 7  compute_player_projections    Phase 1 player projections (next season)
  Stage 8  compute_player_minutes        Phase 2 roster-context minutes allocation
  Stage 9  compute_roster_fit            Phase 3+4 roster fit scoring (TeamRosterFit)
  Stage 10 compute_team_projections      Phase 5 team projections (TeamSeasonProjection)

Stages 7–10 produce forward-looking data (projections FROM this season INTO the
next). They are skipped for the final season in a range unless that season is
also the production forecast season (e.g. 2026). Use --skip-projections to
suppress them for all seasons.

Dependency notes:
  - Stages 1–6 must exist for a season before stages 7–10 can run.
  - compute_ncaa_bpr benefits from passing the two prior seasons via
    --rapm-years so cross-season priors are available. This is handled
    automatically: for each season Y, rapm_years = [Y-2, Y-1, Y] (filtered
    to seasons we actually have data for).
  - Stages 1 and 3 are network-bound ESPN ingests; --workers controls
    parallel HTTP workers for both.
  - Stages 1 and 3 are skipped with --skip-ingest; all compute stages still run.

PBP availability:
  ESPN PBP data is reliable from ~2015 onward. For seasons 2005–2014, stage 3
  will attempt the fetch but most games will have no PBP events. Stage 4 will
  still run but on-court Four Factors and MPIR will be absent. Stage 5 falls
  back to box_bpr / flat priors automatically when stance data is sparse.
  Use --skip-pbp to skip stage 3 entirely for pre-2015 seasons.

Usage examples:
    # Full backfill 2015–2025 (ingest + all compute, no projections for old seasons)
    python manage.py backfill_player_pipeline --from-season 2015 --to-season 2025

    # Single season
    python manage.py backfill_player_pipeline --season 2023

    # Specific years
    python manage.py backfill_player_pipeline --seasons 2023,2024,2025

    # Skip network ingest (recompute only — stages 2,4,5,6,… from existing data)
    python manage.py backfill_player_pipeline --from-season 2015 --to-season 2025 --skip-ingest

    # Skip PBP (no lineup stints; faster for pre-2015 box-score-only backfill)
    python manage.py backfill_player_pipeline --from-season 2005 --to-season 2014 --skip-pbp

    # Include projections for every season (useful if you want all years as source years)
    python manage.py backfill_player_pipeline --from-season 2015 --to-season 2025 --include-projections

    # Only run specific stages
    python manage.py backfill_player_pipeline --from-season 2023 --to-season 2025 --only-stages 5,6

    # Stop after BPR (no FFI, no projections)
    python manage.py backfill_player_pipeline --from-season 2015 --to-season 2025 --through-stage 5

    # Parallel HTTP workers for ingest
    python manage.py backfill_player_pipeline --from-season 2020 --to-season 2025 --workers 4

    # Dry run: print what would be done without executing
    python manage.py backfill_player_pipeline --from-season 2023 --to-season 2025 --dry-run
"""

from __future__ import annotations

import sys
from datetime import date

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from ncaa.models import Season

# ── Stage definitions ─────────────────────────────────────────────────────────
# Each entry: (stage_number, short_name, display_label)
# stage_number is what users pass to --only-stages / --through-stage.

STAGES = [
    (1,  "sync_ncaa_player_gamelogs",        "Player box score ingest (ESPN)"),
    (2,  "compute_ncaa_player_season_stats",  "Aggregate game logs → season stats"),
    (3,  "sync_ncaa_pbp",                     "Play-by-play → lineup stints"),
    (4,  "compute_ncaa_player_impact",        "On-court ratings + Four Factors + MPIR"),
    (5,  "compute_ncaa_bpr",                  "Bayesian Performance Rating (BPR)"),
    (6,  "compute_player_ffi",                "Four Factor Impact Index (FFI)"),
    (7,  "compute_player_projections",        "Phase 1 player projections"),
    (8,  "compute_player_minutes",            "Phase 2 roster-context minutes"),
    (9,  "compute_roster_fit",                "Phase 3+4 roster fit scoring"),
    (10, "compute_team_projections",          "Phase 5 team projections"),
]

# Stages that are network ingests (skipped by --skip-ingest)
INGEST_STAGES = {1, 3}

# Stages that produce forward projections (suppressed for non-final seasons
# unless --include-projections is set)
PROJECTION_STAGES = {7, 8, 9, 10}


class Command(BaseCommand):
    help = (
        "Run the full NCAA player data pipeline for one or more historical seasons."
    )

    def add_arguments(self, parser):
        # ── Season selection (mutually exclusive) ──────────────────────────────
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--season",
            type=int,
            metavar="YEAR",
            help="Single season year (e.g. 2025 for 2024-25).",
        )
        group.add_argument(
            "--from-season",
            type=int,
            metavar="YEAR",
            help="Start of a year range (inclusive).",
        )
        group.add_argument(
            "--seasons",
            type=str,
            metavar="YEARS",
            help="Comma-separated list of season years (e.g. 2022,2023,2025).",
        )

        parser.add_argument(
            "--to-season",
            type=int,
            metavar="YEAR",
            default=None,
            help="End of year range (inclusive; used with --from-season).",
        )

        # ── Stage control ──────────────────────────────────────────────────────
        parser.add_argument(
            "--only-stages",
            type=str,
            metavar="N,N",
            default=None,
            help=(
                "Comma-separated list of stage numbers to run (e.g. '5,6'). "
                "All other stages are skipped."
            ),
        )
        parser.add_argument(
            "--through-stage",
            type=int,
            metavar="N",
            default=None,
            help=(
                "Run stages 1 through N only (e.g. --through-stage 6 stops after BPR). "
                "Ignored when --only-stages is also set."
            ),
        )
        parser.add_argument(
            "--skip-ingest",
            action="store_true",
            help="Skip all network ingest stages (1 and 3). Recompute only.",
        )
        parser.add_argument(
            "--skip-pbp",
            action="store_true",
            help=(
                "Skip stage 3 (sync_ncaa_pbp). Useful for pre-2015 seasons "
                "where PBP data is absent or unreliable."
            ),
        )
        parser.add_argument(
            "--include-projections",
            action="store_true",
            help=(
                "Run stages 7–10 (projections) for every season in the range. "
                "By default, projection stages are only run for the last/only season."
            ),
        )

        # ── BPR options ────────────────────────────────────────────────────────
        parser.add_argument(
            "--rapm-years",
            type=str,
            metavar="Y,Y,Y",
            default=None,
            help=(
                "Comma-separated list of years to pass to compute_ncaa_bpr as "
                "--rapm-years (overrides auto-derived [Y-2, Y-1, Y] window)."
            ),
        )
        parser.add_argument(
            "--skip-box-bpr",
            action="store_true",
            help="Pass --skip-box-bpr to compute_ncaa_bpr (flat priors only).",
        )

        # ── Roster fit options ─────────────────────────────────────────────────
        parser.add_argument(
            "--skip-fit-context",
            action="store_true",
            help=(
                "Run Phase 3 roster fit only — skip Phase 4 contextual modifiers. "
                "Useful when TeamSeasonRatings have not yet been computed for this season."
            ),
        )

        # ── Ingest options ─────────────────────────────────────────────────────
        parser.add_argument(
            "--workers",
            type=int,
            default=1,
            metavar="N",
            help="Parallel HTTP workers for stages 1 and 3 (default: 1; safe up to 4).",
        )
        parser.add_argument(
            "--force-pbp",
            action="store_true",
            help=(
                "Pass --force to sync_ncaa_pbp (stage 3), re-syncing all stints even "
                "if they already exist. Required when stints were ingested before "
                "migration 0032 added box-event fields (team_fgm/fga/fg3m/etc.). "
                "Stage 1 still uses --skip-done so box scores are not re-fetched."
            ),
        )
        # ── Safety ────────────────────────────────────────────────────────────
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the plan without executing any stage.",
        )
        parser.add_argument(
            "--continue-on-error",
            action="store_true",
            help=(
                "Continue to the next season when a stage fails rather than "
                "halting the entire backfill (default: halt on first failure)."
            ),
        )

    # ──────────────────────────────────────────────────────────────────────────

    def handle(self, *args, **options):  # noqa: C901
        years = self._resolve_years(options)
        active_stages = self._resolve_active_stages(options, years)
        workers = max(1, options["workers"])
        dry_run = options["dry_run"]
        continue_on_error = options["continue_on_error"]
        skip_box_bpr = options["skip_box_bpr"]
        skip_fit_context = options["skip_fit_context"]
        force_pbp = options["force_pbp"]
        rapm_years_override = (
            [int(y.strip()) for y in options["rapm_years"].split(",")]
            if options.get("rapm_years")
            else None
        )

        start_time = timezone.now()

        # Seed prior years from all seasons already in the DB that have BPR data,
        # so rolling RAPM windows work correctly even when starting mid-range.
        from ncaa.models import PlayerSeasonStats  # noqa: PLC0415
        db_bpr_years: set[int] = set(
            PlayerSeasonStats.objects.filter(
                bpr__isnull=False,
                season__year__lt=min(years),
            ).values_list("season__year", flat=True).distinct()
        )

        self._print_header(years, active_stages, workers, dry_run)

        all_season_results: list[dict] = []
        completed_years: list[int] = sorted(db_bpr_years)

        for i, year in enumerate(years):
            is_last_season = (i == len(years) - 1)
            season_results = self._run_season(
                year=year,
                active_stages=active_stages,
                is_last_season=is_last_season,
                include_projections=options["include_projections"],
                workers=workers,
                dry_run=dry_run,
                skip_box_bpr=skip_box_bpr,
                skip_fit_context=skip_fit_context,
                force_pbp=force_pbp,
                rapm_years_override=rapm_years_override,
                all_prior_years=completed_years.copy(),
            )
            all_season_results.append(season_results)

            # Track completed years for rolling RAPM windows in subsequent seasons
            if year not in completed_years:
                completed_years.append(year)
                completed_years.sort()

            if not dry_run and not season_results["ok"] and not continue_on_error:
                self.stderr.write(
                    self.style.ERROR(
                        f"\n[HALT] Season {year} had a stage failure. "
                        "Use --continue-on-error to skip past failures.\n"
                    )
                )
                self._print_summary(start_time, all_season_results)
                sys.exit(1)

        self._print_summary(start_time, all_season_results)

        if any(not r["ok"] for r in all_season_results):
            sys.exit(1)

    # ──────────────────────────────────────────────────────────────────────────
    # Per-season runner
    # ──────────────────────────────────────────────────────────────────────────

    def _run_season(
        self,
        *,
        year: int,
        active_stages: set[int],
        is_last_season: bool,
        include_projections: bool,
        workers: int,
        dry_run: bool,
        skip_box_bpr: bool,
        skip_fit_context: bool,
        force_pbp: bool,
        rapm_years_override: list[int] | None,
        all_prior_years: list[int],
    ) -> dict:
        self.stdout.write("\n" + "─" * 76)
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"  Season {year} ({year - 1}-{str(year)[2:]})"
            )
        )
        self.stdout.write("─" * 76)

        steps: list[tuple[str, bool, str | None]] = []
        ok = True

        # Derive RAPM years: [Y-2, Y-1, Y] filtered to seasons we already have
        if rapm_years_override:
            rapm_years = rapm_years_override
        else:
            candidate_rapm_years = [year - 2, year - 1, year]
            available_years = set(all_prior_years) | {year}
            rapm_years = [y for y in candidate_rapm_years if y in available_years]

        for stage_num, cmd_name, label in STAGES:
            if stage_num not in active_stages:
                continue

            # Projection stages: only run for last season unless --include-projections
            if stage_num in PROJECTION_STAGES and not is_last_season and not include_projections:
                if not dry_run:
                    self.stdout.write(
                        f"  [SKIP] Stage {stage_num}: {label} "
                        f"(projection stages suppressed for non-final seasons; "
                        f"use --include-projections to enable)"
                    )
                steps.append((label, True, "Skipped (not final season)"))
                continue

            kwargs = self._build_kwargs(
                stage_num=stage_num,
                cmd_name=cmd_name,
                year=year,
                workers=workers,
                skip_box_bpr=skip_box_bpr,
                skip_fit_context=skip_fit_context,
                force_pbp=force_pbp,
                rapm_years=rapm_years,
            )

            if dry_run:
                kwarg_str = " ".join(f"--{k.replace('_', '-')} {v}" for k, v in kwargs.items() if k != "season")
                self.stdout.write(
                    f"  [DRY] Stage {stage_num}: python manage.py {cmd_name} "
                    f"--season {year} {kwarg_str}"
                )
                steps.append((label, True, "Dry run"))
                continue

            self.stdout.write(f"  [Stage {stage_num}/{len(STAGES)}] {label}...")
            try:
                connection.close()
                call_command(cmd_name, **kwargs)
                self.stdout.write(self.style.SUCCESS(f"  [OK] {label}"))
                steps.append((label, True, None))
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"  [FAIL] {label}: {exc}"))
                steps.append((label, False, str(exc)))
                ok = False
                break  # stop this season on first failure (caller decides whether to continue)

        return {"year": year, "ok": ok, "steps": steps}

    # ──────────────────────────────────────────────────────────────────────────
    # Argument builders per stage
    # ──────────────────────────────────────────────────────────────────────────

    def _build_kwargs(
        self,
        *,
        stage_num: int,
        cmd_name: str,
        year: int,
        workers: int,
        skip_box_bpr: bool,
        skip_fit_context: bool,
        force_pbp: bool,
        rapm_years: list[int],
    ) -> dict:
        base = {"season": year}

        if stage_num == 1:  # sync_ncaa_player_gamelogs
            return {**base, "workers": workers, "skip_done": True}

        if stage_num == 3:  # sync_ncaa_pbp
            kwargs = {**base, "workers": workers}
            if force_pbp:
                kwargs["force"] = True
            return kwargs

        if stage_num == 5:  # compute_ncaa_bpr
            kwargs = {**base}
            if rapm_years:
                kwargs["rapm_years"] = rapm_years
            if skip_box_bpr:
                kwargs["skip_box_bpr"] = True
            return kwargs

        if stage_num == 9:  # compute_roster_fit
            kwargs = {**base}
            if not skip_fit_context:
                kwargs["context"] = True
            return kwargs

        # All other stages only need --season
        return base

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _resolve_years(self, options: dict) -> list[int]:
        if options.get("season"):
            return [options["season"]]
        if options.get("seasons"):
            try:
                return sorted(int(y.strip()) for y in options["seasons"].split(","))
            except ValueError:
                raise CommandError(
                    "--seasons must be a comma-separated list of integers, "
                    "e.g. 2022,2023,2025"
                )
        from_year = options["from_season"]
        to_year = options.get("to_season") or date.today().year
        if to_year < from_year:
            raise CommandError("--to-season must be >= --from-season")
        return list(range(from_year, to_year + 1))

    def _resolve_active_stages(self, options: dict, years: list[int]) -> set[int]:
        all_stage_nums = {s[0] for s in STAGES}

        # --only-stages overrides everything else
        if options.get("only_stages"):
            try:
                chosen = {int(s.strip()) for s in options["only_stages"].split(",")}
            except ValueError:
                raise CommandError("--only-stages must be a comma-separated list of integers.")
            invalid = chosen - all_stage_nums
            if invalid:
                raise CommandError(
                    f"Unknown stage numbers: {sorted(invalid)}. "
                    f"Valid: 1–{max(all_stage_nums)}."
                )
            return chosen

        # --through-stage: run stages 1..N
        if options.get("through_stage"):
            through = options["through_stage"]
            if through not in all_stage_nums:
                raise CommandError(
                    f"--through-stage must be between 1 and {max(all_stage_nums)}."
                )
            active = {n for n in all_stage_nums if n <= through}
        else:
            active = set(all_stage_nums)

        # --skip-ingest removes stages 1 and 3
        if options["skip_ingest"]:
            active -= INGEST_STAGES

        # --skip-pbp removes stage 3 only
        if options["skip_pbp"]:
            active.discard(3)

        return active

    def _print_header(
        self,
        years: list[int],
        active_stages: set[int],
        workers: int,
        dry_run: bool,
    ) -> None:
        self.stdout.write("\n" + "=" * 76)
        self.stdout.write("MACFAX — NCAA PLAYER PIPELINE BACKFILL")
        self.stdout.write("=" * 76)
        self.stdout.write(
            f"  Seasons   : {years[0]}–{years[-1]}  ({len(years)} season(s))"
        )
        active_sorted = sorted(active_stages)
        stage_labels = {s[0]: s[2] for s in STAGES}
        self.stdout.write(
            f"  Stages    : {active_sorted}  "
            f"({len(active_sorted)} active of {len(STAGES)} total)"
        )
        for n in active_sorted:
            self.stdout.write(f"              {n:>2}. {stage_labels[n]}")
        self.stdout.write(f"  Workers   : {workers} (for ingest stages 1 & 3)")
        if dry_run:
            self.stdout.write(self.style.WARNING("  DRY RUN   : no changes will be made"))
        self.stdout.write("=" * 76)

    def _print_summary(
        self,
        start_time,
        all_season_results: list[dict],
    ) -> None:
        end_time = timezone.now()
        duration = int((end_time - start_time).total_seconds())
        mins, secs = divmod(duration, 60)

        total_seasons = len(all_season_results)
        failed_seasons = [r for r in all_season_results if not r["ok"]]
        ok_seasons = [r for r in all_season_results if r["ok"]]

        self.stdout.write("\n" + "=" * 76)
        if not failed_seasons:
            self.stdout.write(
                self.style.SUCCESS(
                    f"BACKFILL COMPLETE — {total_seasons}/{total_seasons} seasons OK"
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    f"BACKFILL COMPLETED WITH ERRORS — "
                    f"{len(ok_seasons)}/{total_seasons} seasons OK, "
                    f"{len(failed_seasons)} failed"
                )
            )

        self.stdout.write(f"Duration: {mins}m {secs}s")
        self.stdout.write("")

        for r in all_season_results:
            year = r["year"]
            if r["ok"]:
                self.stdout.write(self.style.SUCCESS(f"  ✓ {year}"))
            else:
                failed_step = next((s for s in r["steps"] if not s[1]), None)
                reason = failed_step[2] if failed_step else "unknown"
                self.stdout.write(
                    self.style.ERROR(
                        f"  ✗ {year}  — failed at: {failed_step[0] if failed_step else '?'}"
                    )
                )
                if reason:
                    self.stdout.write(f"          {reason[:120]}")

        self.stdout.write("=" * 76 + "\n")
