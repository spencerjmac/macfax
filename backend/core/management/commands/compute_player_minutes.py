"""
compute_player_minutes — Generate Phase 2 roster‑context minutes allocations.

Runs AFTER compute_player_projections: reads PlayerSeasonProjection rows
produced by Phase 1, groups them by team, runs the minutes allocator for
each team, and writes the Phase 2 fields back.

Phase 2 fields written to PlayerSeasonProjection:
  • role_bucket       — "G" / "Wing" / "Big" (position grouping)
  • minutes_share_p2  — projected mpg / 40; sums to 5.00 per team
  • mpg_p2            — projected MPG = minutes_share_p2 × 40
  • rotation_rank     — 1 = most projected minutes on this roster
  • minutes_overridden — always False for baseline run; True for sandbox overrides

Usage:
  python manage.py compute_player_minutes --season 2026
  python manage.py compute_player_minutes --season 2026 --validate
"""

import logging

from django.core.management.base import BaseCommand, CommandError

from core.analytics.player_value.minutes.service import run_minutes_pipeline

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Phase 2: Compute roster‑context minutes allocations for all "
        "PlayerSeasonProjection rows in the given from_season."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=int,
            required=True,
            help="From‑season year whose projections to process (e.g. 2026).",
        )
        parser.add_argument(
            "--validate",
            action="store_true",
            default=False,
            help="Print diagnostic tables after computing.",
        )

    def handle(self, *args, **options):
        season_year  = options["season"]
        do_validate  = options["validate"]

        logging.basicConfig(level=logging.INFO)

        self.stdout.write(
            f"Computing Phase 2 minutes allocations for season {season_year} …"
        )

        try:
            summary = run_minutes_pipeline(season_year=season_year, verbose=True)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {summary['n_players']} players across "
                f"{summary['n_teams']} teams — "
                f"{summary['n_written']} projection rows updated."
            )
        )

        if do_validate:
            self._run_validation(season_year)

    def _run_validation(self, season_year: int) -> None:
        from core.models import PlayerSeasonProjection
        from django.db.models import Sum, Count

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(f"MINUTES VALIDATION — from_season={season_year}")
        self.stdout.write("=" * 70)

        rows = list(
            PlayerSeasonProjection.objects
            .filter(from_season__year=season_year, minutes_share_p2__isnull=False)
            .select_related("player", "team")
            .order_by("team_id", "rotation_rank")
        )

        if not rows:
            self.stdout.write("  No Phase 2 minutes data found.")
            return

        # ── Top 25 by projected minutes ───────────────────────────────────
        top25 = sorted(rows, key=lambda r: r.minutes_share_p2 or 0, reverse=True)[:25]
        self.stdout.write(f"\nTop 25 by projected MPG (→ {season_year + 1}):\n")
        hdr = (f"{'Player':<28} {'Team':<22} {'Bucket':<6} {'Rank':>4} "
               f"{'BPR':>6} {'MPG':>6} {'Share':>7}")
        self.stdout.write(hdr)
        self.stdout.write("-" * len(hdr))
        for r in top25:
            team_name = r.team.name if r.team else "—"
            self.stdout.write(
                f"{r.player.display_name:<28} {team_name:<22} "
                f"{(r.role_bucket or '?'):<6} "
                f"{(r.rotation_rank or 0):>4} "
                f"{(r.projected_bpr or 0):>6.2f} "
                f"{(r.mpg_p2 or 0):>6.1f} "
                f"{(r.minutes_share_p2 or 0):>7.3f}"
            )

        # ── Team‑level minute sums (spot‑check) ───────────────────────────
        self.stdout.write("\nPer‑team minutes share sums (sample 10 teams):\n")
        from collections import defaultdict
        team_sums: dict[int, float] = defaultdict(float)
        team_names: dict[int, str]  = {}
        for r in rows:
            team_sums[r.team_id or 0] += r.minutes_share_p2 or 0
            team_names[r.team_id or 0] = r.team.name if r.team else "Unknown"
        teams_sorted = sorted(team_sums.items(), key=lambda x: x[1], reverse=True)[:10]
        for tid, total in teams_sorted:
            flag = "  ✓" if abs(total - 5.0) < 0.05 else "  ⚠ MISMATCH"
            self.stdout.write(f"  {team_names[tid]:<28} share_sum={total:.4f}{flag}")

        # ── Bucket distribution ───────────────────────────────────────────
        self.stdout.write("\nRole bucket distribution:")
        bucket_counts: dict[str, int] = defaultdict(int)
        for r in rows:
            bucket_counts[r.role_bucket or "?"] += 1
        for bucket, cnt in sorted(bucket_counts.items()):
            pct = 100.0 * cnt / max(len(rows), 1)
            self.stdout.write(f"  {bucket:<8} {cnt:>5}  ({pct:.1f}%)")

        # ── Concentration check ───────────────────────────────────────────
        self.stdout.write("\nMinutes concentration (top‑N share per team, averaged):")
        from statistics import mean
        top5_shares: list[float]  = []
        top8_shares: list[float]  = []
        top9_shares: list[float]  = []
        by_team: dict[int, list]  = defaultdict(list)
        for r in rows:
            by_team[r.team_id or 0].append(r.minutes_share_p2 or 0)
        for team_shares in by_team.values():
            desc = sorted(team_shares, reverse=True)
            top5_shares.append(sum(desc[:5]))
            top8_shares.append(sum(desc[:8]))
            top9_shares.append(sum(desc[:9]))
        self.stdout.write(
            f"  Avg top‑5  share: {mean(top5_shares):.3f} / 5.00"
        )
        self.stdout.write(
            f"  Avg top‑8  share: {mean(top8_shares):.3f} / 5.00"
        )
        self.stdout.write(
            f"  Avg top‑9  share: {mean(top9_shares):.3f} / 5.00"
        )
