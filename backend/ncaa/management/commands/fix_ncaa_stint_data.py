"""
Management command: fix_ncaa_stint_data

Repairs the NCAA stint-layer defects found by the 2026-07 BPR data audit
(docs/bpr_audit/02_data_integrity_report.md):

  1. PHANTOM OT STINTS (bug 1.2) — sync_ncaa_pbp's end-of-game handling opens
     a full 300-second period-3+ stint block for every player still on court,
     in ~82% of games. Detection per (game, period>=3): every stint in the
     period spans the full 300s clock AND the period's stints carry zero
     points on both sides. Real overtimes always score. Phantom blocks are
     deleted.

  2. went_to_ot / period_count NEVER SET (bug 1.4) — backfilled from the
     surviving stint data: went_to_ot = a real (scoring) period-3 stint
     exists; period_count = max surviving stint period (default 2).

  3. EXACT DUPLICATE STINTS (bug 1.3, duplicate class only) — rows identical
     on (player, game, period, clock_start, clock_end) but different
     stint_index. Keeps the lowest stint_index, deletes the rest.
     Overlapping-but-not-identical stints are NOT touched here — those 2026
     games need a --force re-sync (see a2_overlaps_2026.csv for the list).

Deletes only provably-corrupt rows. Run with --dry-run first; per-season
before/after counts are printed and should be pasted into the audit report.
After a season is repaired, recompute its on-court aggregates:
    python manage.py compute_ncaa_player_impact --season YYYY

Usage:
  python manage.py fix_ncaa_stint_data --seasons 2021 2022 2023 2024 2025 2026 --dry-run
  python manage.py fix_ncaa_stint_data --seasons 2024 --skip-ot-flags
"""

from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

OT_PERIOD_SECS = 300


class Command(BaseCommand):
    help = "Repair phantom OT stints, OT flags, and exact duplicate stints (audit bugs 1.2-1.4)."

    def add_arguments(self, parser):
        parser.add_argument("--seasons", nargs="+", type=int, required=True)
        parser.add_argument("--dry-run", action="store_true", default=False)
        parser.add_argument("--skip-phantoms", action="store_true", default=False)
        parser.add_argument("--skip-dupes", action="store_true", default=False)
        parser.add_argument("--skip-ot-flags", action="store_true", default=False)
        parser.add_argument("--skip-zero-length", action="store_true", default=False)

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        tag = "[dry-run] " if dry else ""
        for season in sorted(opts["seasons"]):
            self.stdout.write(f"\n=== Season {season} ===")
            if not opts["skip_phantoms"]:
                self._fix_phantom_ot(season, dry, tag)
            if not opts["skip_dupes"]:
                self._fix_exact_dupes(season, dry, tag)
            if not opts["skip_zero_length"]:
                self._fix_zero_length(season, dry, tag)
            if not opts["skip_ot_flags"]:
                self._backfill_ot_flags(season, dry, tag)

    # ── 1. Phantom OT stints ──────────────────────────────────────────────────

    def _fix_phantom_ot(self, season: int, dry: bool, tag: str) -> None:
        from ncaa.models import PlayerGameStint

        # Per (game, period>=3): total points and whether every stint spans
        # the full OT clock. Zero-point full-span blocks are phantoms.
        period_pts: dict[tuple, int] = defaultdict(int)
        period_all_fullspan: dict[tuple, bool] = defaultdict(lambda: True)
        period_stint_ids: dict[tuple, list[int]] = defaultdict(list)

        qs = (PlayerGameStint.objects
              .filter(game__season_year=season, period__gte=3)
              .values_list("id", "game_id", "period",
                           "clock_start_secs", "clock_end_secs",
                           "pts_scored", "pts_allowed"))
        for sid, gid, period, cs, ce, ps, pa in qs.iterator(chunk_size=50000):
            key = (gid, period)
            period_pts[key] += ps + pa
            if not (cs == OT_PERIOD_SECS and ce == 0):
                period_all_fullspan[key] = False
            period_stint_ids[key].append(sid)

        phantom_ids: list[int] = []
        n_phantom_periods = 0
        n_real_ot_periods = 0
        for key, ids in period_stint_ids.items():
            if period_pts[key] == 0 and period_all_fullspan[key]:
                phantom_ids.extend(ids)
                n_phantom_periods += 1
            else:
                n_real_ot_periods += 1

        total_before = PlayerGameStint.objects.filter(
            game__season_year=season).count()
        self.stdout.write(
            f"  {tag}phantom OT: {len(phantom_ids)} stints in "
            f"{n_phantom_periods} phantom periods (kept {n_real_ot_periods} "
            f"real OT periods) | season stints before: {total_before}"
        )
        if not dry and phantom_ids:
            with transaction.atomic():
                # chunked delete — SQLite parameter limits
                for i in range(0, len(phantom_ids), 5000):
                    PlayerGameStint.objects.filter(
                        id__in=phantom_ids[i:i + 5000]).delete()
            total_after = PlayerGameStint.objects.filter(
                game__season_year=season).count()
            self.stdout.write(
                f"  deleted {total_before - total_after} rows | after: {total_after}")

    # ── 2. Exact duplicate stints ─────────────────────────────────────────────

    def _fix_exact_dupes(self, season: int, dry: bool, tag: str) -> None:
        from ncaa.models import PlayerGameStint

        seen: dict[tuple, int] = {}
        dupe_ids: list[int] = []
        qs = (PlayerGameStint.objects
              .filter(game__season_year=season)
              .order_by("stint_index")
              .values_list("id", "player_id", "game_id", "period",
                           "clock_start_secs", "clock_end_secs"))
        for sid, pid, gid, period, cs, ce in qs.iterator(chunk_size=50000):
            key = (pid, gid, period, cs, ce)
            if key in seen:
                dupe_ids.append(sid)   # keeps lowest stint_index (order_by)
            else:
                seen[key] = sid

        self.stdout.write(f"  {tag}exact dupes: {len(dupe_ids)} rows")
        if not dry and dupe_ids:
            with transaction.atomic():
                PlayerGameStint.objects.filter(id__in=dupe_ids).delete()
            self.stdout.write(f"  deleted {len(dupe_ids)} duplicate rows")

    # ── 2b. Zero-length stints ────────────────────────────────────────────────

    def _fix_zero_length(self, season: int, dry: bool, tag: str) -> None:
        """Remove secs_on=0 rows (parser guard artifacts) — carry no signal."""
        from ncaa.models import PlayerGameStint

        qs = PlayerGameStint.objects.filter(
            game__season_year=season, secs_on=0,
            pts_scored=0, pts_allowed=0)
        n = qs.count()
        self.stdout.write(f"  {tag}zero-length stints: {n} rows")
        if not dry and n:
            with transaction.atomic():
                qs.delete()

    # ── 3. went_to_ot / period_count backfill ─────────────────────────────────

    def _backfill_ot_flags(self, season: int, dry: bool, tag: str) -> None:
        from ncaa.models import Game, PlayerGameStint

        # Max surviving stint period per game (run AFTER phantom deletion)
        max_period: dict[int, int] = {}
        for gid, period in (PlayerGameStint.objects
                            .filter(game__season_year=season)
                            .values_list("game_id", "period")
                            .iterator(chunk_size=100000)):
            if period > max_period.get(gid, 0):
                max_period[gid] = period

        games = list(Game.objects.filter(
            season_year=season, id__in=list(max_period)))
        to_update = []
        n_ot = 0
        for g in games:
            mp = max_period.get(g.id, 2)
            went_ot = mp >= 3
            pc = max(mp, 2)
            if g.went_to_ot != went_ot or g.period_count != pc:
                g.went_to_ot = went_ot
                g.period_count = pc
                to_update.append(g)
            if went_ot:
                n_ot += 1

        self.stdout.write(
            f"  {tag}OT flags: {len(to_update)} games to update "
            f"({n_ot} OT games detected from surviving stints)")
        if not dry and to_update:
            with transaction.atomic():
                Game.objects.bulk_update(
                    to_update, ["went_to_ot", "period_count"], batch_size=500)
            self.stdout.write(f"  updated {len(to_update)} games")
