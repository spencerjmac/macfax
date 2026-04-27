"""
Management command: compute_team_projections

Usage:
    python manage.py compute_team_projections --season 2026
    python manage.py compute_team_projections --season 2026 --validate
    python manage.py compute_team_projections --season 2026 --dry-run
"""

from django.core.management.base import BaseCommand, CommandError

from ncaa.analytics.player_value.team_projection.service import (
    get_projection_distribution_stats,
    get_top_teams,
    run_team_projection_pipeline,
)


class Command(BaseCommand):
    help = "Run Phase 5 team projection pipeline for a given season"

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=int,
            required=True,
            help="Source season year (e.g. 2026 uses Phase 1-4 data from the 2025-26 season)",
        )
        parser.add_argument(
            "--validate",
            action="store_true",
            default=False,
            help="After running (or if projections already exist), print distribution stats and top/bottom 10",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Compute projections but skip all DB writes",
        )

    def handle(self, *args, **options):
        season_year = options["season"]
        dry_run = options["dry_run"]
        validate = options["validate"]

        self.stdout.write(
            self.style.NOTICE(
                f"Phase 5 — computing team projections for season {season_year} "
                f"{'(DRY RUN)' if dry_run else ''}"
            )
        )

        try:
            written = run_team_projection_pipeline(season_year, dry_run=dry_run)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"Wrote / updated {len(written)} TeamSeasonProjection rows")
            )
            if validate:
                self._print_validation(season_year)
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry run complete — {len(written)} projections computed, no rows written"
                )
            )
            if validate:
                self._print_validation_from_objects(written)

    def _print_validation(self, season_year: int) -> None:
        """Print distribution stats + top/bottom 10 teams for quick sanity-check."""
        stats = get_projection_distribution_stats(season_year)
        self.stdout.write("\n── Projection Distribution Stats ──────────────────────")
        for k, v in stats.items():
            self.stdout.write(f"  {k:20s}: {v}")

        self.stdout.write("\n── Top 10 Teams (by projected AdjEM) ─────────────────")
        top = get_top_teams(season_year, n=10)
        if not top:
            self.stdout.write("  (no projections found — run pipeline first)")
            return

        header = f"  {'Rank':>4}  {'Team':<30}  {'AdjO':>6}  {'AdjD':>6}  {'AdjEM':>7}  {'RankRange':>12}  {'Uncert':>7}"
        self.stdout.write(header)
        for row in top:
            rank_range = (
                f"{row['national_rank_range_low']}–{row['national_rank_range_high']}"
                if row["national_rank_range_low"] is not None else "?"
            )
            self.stdout.write(
                f"  {row['projected_national_rank']:>4}  "
                f"{row['team__name']:<30}  "
                f"{row['projected_adj_o']:>6.2f}  "
                f"{row['projected_adj_d']:>6.2f}  "
                f"{row['projected_adj_em']:>+7.2f}  "
                f"{rank_range:>12}  "
                f"{row['team_projection_uncertainty']:>7.3f}"
            )

        self.stdout.write("\n── Bottom 10 Teams (by projected AdjEM) ───────────────")
        from ncaa.models import TeamSeasonProjection  # noqa: PLC0415
        bottom = list(
            TeamSeasonProjection.objects.filter(from_season__year=season_year)
            .select_related("team")
            .order_by("-projected_national_rank")[:10]
            .values(
                "projected_national_rank",
                "team__name",
                "projected_adj_o",
                "projected_adj_d",
                "projected_adj_em",
                "national_rank_range_low",
                "national_rank_range_high",
                "team_projection_uncertainty",
            )
        )
        for row in reversed(bottom):  # show worst → less-worst
            rank_range = (
                f"{row['national_rank_range_low']}–{row['national_rank_range_high']}"
                if row["national_rank_range_low"] is not None else "?"
            )
            self.stdout.write(
                f"  {row['projected_national_rank']:>4}  "
                f"{row['team__name']:<30}  "
                f"{row['projected_adj_o']:>6.2f}  "
                f"{row['projected_adj_d']:>6.2f}  "
                f"{row['projected_adj_em']:>+7.2f}  "
                f"{rank_range:>12}  "
                f"{row['team_projection_uncertainty']:>7.3f}"
            )

        self.stdout.write("")

    def _print_validation_from_objects(self, projections: list) -> None:
        """Print distribution stats + top/bottom 10 from freshly computed in-memory projections."""
        if not projections:
            self.stdout.write("  (no projections computed)")
            return

        import statistics  # noqa: PLC0415
        from ncaa.models import Team  # noqa: PLC0415

        # Load team names for display (single query)
        team_ids = [p.team_id for p in projections]
        name_by_id = dict(Team.objects.filter(id__in=team_ids).values_list("id", "name"))

        em_vals = [p.projected_adj_em for p in projections if p.projected_adj_em is not None]
        o_vals = [p.projected_adj_o for p in projections if p.projected_adj_o is not None]
        d_vals = [p.projected_adj_d for p in projections if p.projected_adj_d is not None]
        u_vals = [p.team_projection_uncertainty for p in projections if p.team_projection_uncertainty is not None]
        n = len(em_vals)

        stats = {
            "n": n,
            "avg_o": round(statistics.mean(o_vals), 3) if o_vals else None,
            "std_o": round(statistics.stdev(o_vals), 3) if len(o_vals) > 1 else 0.0,
            "avg_d": round(statistics.mean(d_vals), 3) if d_vals else None,
            "std_d": round(statistics.stdev(d_vals), 3) if len(d_vals) > 1 else 0.0,
            "avg_em": round(statistics.mean(em_vals), 3) if em_vals else None,
            "std_em": round(statistics.stdev(em_vals), 3) if len(em_vals) > 1 else 0.0,
            "min_em": round(min(em_vals), 3) if em_vals else None,
            "max_em": round(max(em_vals), 3) if em_vals else None,
            "avg_uncertainty": round(statistics.mean(u_vals), 3) if u_vals else None,
        }

        self.stdout.write("\n── Projection Distribution Stats (in-memory dry run) ──────")
        for k, v in stats.items():
            self.stdout.write(f"  {k:20s}: {v}")

        header = f"  {'Rank':>4}  {'Team':<30}  {'AdjO':>6}  {'AdjD':>6}  {'AdjEM':>7}  {'RankRange':>12}  {'Uncert':>7}"

        def _fmt_row(p):
            name = name_by_id.get(p.team_id, f"team:{p.team_id}")
            rk = p.projected_national_rank or 0
            rng = (
                f"{p.national_rank_range_low}–{p.national_rank_range_high}"
                if p.national_rank_range_low is not None else "?"
            )
            return (
                f"  {rk:>4}  "
                f"{name:<30}  "
                f"{p.projected_adj_o:>6.2f}  "
                f"{p.projected_adj_d:>6.2f}  "
                f"{p.projected_adj_em:>+7.2f}  "
                f"{rng:>12}  "
                f"{p.team_projection_uncertainty:>7.3f}"
            )

        sorted_proj = sorted(
            projections,
            key=lambda p: p.projected_national_rank if p.projected_national_rank else 99999,
        )
        self.stdout.write("\n── Top 10 Teams (by projected AdjEM) ────────────────────")
        self.stdout.write(header)
        for p in sorted_proj[:10]:
            self.stdout.write(_fmt_row(p))

        self.stdout.write("\n── Bottom 10 Teams (by projected AdjEM) ─────────────────")
        self.stdout.write(header)
        for p in sorted_proj[-10:]:
            self.stdout.write(_fmt_row(p))

        self.stdout.write("")
