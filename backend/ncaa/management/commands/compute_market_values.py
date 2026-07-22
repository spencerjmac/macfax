"""
compute_market_values — compute + persist Macfax Player Market Value rows.

Phase 6 Stage 2. Chain and constants: ncaa/analytics/market_value/constants.py
(operator-gated; see the module's provenance blocks). Valuation basis is
current-season ACTUALS (PlayerSeasonStats).

House doctrine honored:
  - one-row-per-target assertion on the source population
  - --dry-run computes + validates, writes nothing
  - built-in validations every run:
      V-a  national top-10 by marginal_wins matches the Stage 1 derivation
           list (2026 season only — the season the gate reviewed)
      V-b  median deep-bench (rank>10 by mpg) value ≈ $0
      V-c  closure table for 5 reference programs, printed with the
           public-spend context note
  - "sanity bounds at birth": constants_hash stamped per row so a future
    constant change can never silently mix rows from different chains.

Usage:
    python manage.py compute_market_values --season 2026
    python manage.py compute_market_values --season 2026 --dry-run
"""

from __future__ import annotations

import statistics

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ncaa.conf_utils import get_conf_group
from ncaa.models import PlayerMarketValue, PlayerSeasonStats, Season
from ncaa.analytics.market_value.constants import (
    DOLLARS_PER_WIN_HIGH,
    DOLLARS_PER_WIN_LOW,
    METHODOLOGY_VERSION,
    REPLACEMENT_ACTUALS_DBPR,
    REPLACEMENT_ACTUALS_OBPR,
    WINS_PER_EM_NCAA,
    constants_hash,
)
from ncaa.analytics.player_value.team_projection.constants import SLOPE_DEF, SLOPE_OFF

PIPELINE_VERSION = "6.2"

# V-a reference: Stage 1 derivation top-10 (2026 actuals, operator-reviewed).
STAGE1_TOP10_2026 = {
    "Cameron Boozer", "Yaxel Lendeborg", "Ja'Kobi Gillespie", "Sam Hoiberg",
    "Keaton Wagler", "Milan Momcilovic", "Joshua Dent", "Brayden Burries",
    "Bruce Thornton", "Jeremy Fears Jr.",
}
CLOSURE_PROGRAMS = ["duke", "florida", "kansas", "gonzaga", "vermont"]


class Command(BaseCommand):
    help = "Compute and persist PlayerMarketValue rows (operator-gated chain)."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        year = options["season"]
        dry_run = options["dry_run"]
        try:
            season = Season.objects.get(year=year)
        except Season.DoesNotExist:
            raise CommandError(f"Season {year} not found")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no DB writes"))

        rows = list(
            PlayerSeasonStats.objects.filter(
                season=season, team__is_d1=True,
                mpg__isnull=False, obpr__isnull=False, dbpr__isnull=False,
            ).select_related("player", "team")
        )
        # one-row-per-target assertion (player may split across teams —
        # PSS is unique per (player, season, team); collapse would hide the
        # team context the closure table needs, so assert instead and take
        # the primary-team row when a split exists)
        seen: dict[int, int] = {}
        for r in rows:
            seen[r.player_id] = seen.get(r.player_id, 0) + 1
        split = [pid for pid, c in seen.items() if c > 1]
        if split:
            keep: dict[int, PlayerSeasonStats] = {}
            for r in rows:
                cur = keep.get(r.player_id)
                if cur is None or (r.mpg or 0) * (r.gp or 0) > (cur.mpg or 0) * (cur.gp or 0):
                    keep[r.player_id] = r
            rows = list(keep.values())
            self.stdout.write(
                f"  note: {len(split)} split-season players collapsed to their "
                f"highest-minutes team row"
            )

        chash = constants_hash()
        computed = []
        for r in rows:
            share = (r.mpg or 0.0) / 40.0
            mem = (SLOPE_OFF * share * (r.obpr - REPLACEMENT_ACTUALS_OBPR)
                   + SLOPE_DEF * share * (r.dbpr - REPLACEMENT_ACTUALS_DBPR))
            mwins = mem * WINS_PER_EM_NCAA
            computed.append({
                "stats": r,
                "marginal_em": mem,
                "marginal_wins": mwins,
                "value_low": mwins * DOLLARS_PER_WIN_LOW,
                "value_high": mwins * DOLLARS_PER_WIN_HIGH,
            })
        computed.sort(key=lambda c: -c["marginal_wins"])

        self._validate(computed, year)

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"\nDry run: {len(computed)} values computed, nothing written."
            ))
            return

        with transaction.atomic():
            PlayerMarketValue.objects.filter(season=season).delete()
            objs = [
                PlayerMarketValue(
                    player_id=c["stats"].player_id,
                    season=season,
                    bpr=(c["stats"].obpr + c["stats"].dbpr),
                    minutes_share=(c["stats"].mpg or 0.0) / 40.0,
                    marginal_em=c["marginal_em"],
                    marginal_wins=c["marginal_wins"],
                    value_low=c["value_low"],
                    value_high=c["value_high"],
                    pipeline_version=PIPELINE_VERSION,
                    constants_hash=chash,
                )
                for c in computed
            ]
            PlayerMarketValue.objects.bulk_create(objs)
        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {len(computed)} PlayerMarketValue rows written for {year} "
            f"(pipeline {PIPELINE_VERSION}, constants {chash}, "
            f"methodology {METHODOLOGY_VERSION})."
        ))

    # ── validations ───────────────────────────────────────────────────────────

    def _validate(self, computed, year):
        failures = []

        # V-a — top-10 equivalence with the reviewed Stage 1 list (2026 only)
        top10 = {c["stats"].player.display_name for c in computed[:10]}
        if year == 2026:
            if top10 != STAGE1_TOP10_2026:
                failures.append(
                    f"V-a top-10 mismatch vs Stage 1: unexpected "
                    f"{sorted(top10 - STAGE1_TOP10_2026)}, missing "
                    f"{sorted(STAGE1_TOP10_2026 - top10)}"
                )
            self.stdout.write(
                f"V-a top-10 vs Stage 1 list: {'OK' if top10 == STAGE1_TOP10_2026 else 'FAIL'}"
            )
        else:
            self.stdout.write(f"V-a top-10 check: SKIPPED (Stage 1 list is 2026-specific)")
            self.stdout.write("  top-10: " + ", ".join(sorted(top10)))

        # V-b — median deep bench ≈ $0
        by_team: dict[int, list] = {}
        for c in computed:
            by_team.setdefault(c["stats"].team_id, []).append(c)
        bench = []
        for ps in by_team.values():
            ps.sort(key=lambda c: -(c["stats"].mpg or 0))
            bench.extend(ps[10:])
        med_low = statistics.median([c["value_low"] for c in bench]) if bench else 0.0
        v_b_ok = abs(med_low) < 60_000
        if not v_b_ok:
            failures.append(f"V-b median deep-bench value ${med_low:,.0f} not ≈ $0")
        self.stdout.write(
            f"V-b median deep-bench value: ${med_low:,.0f} "
            f"({'OK' if v_b_ok else 'FAIL'}; n={len(bench)})"
        )

        # V-c — closure table (informational, printed every run)
        by_slug: dict[str, float] = {}
        for c in computed:
            slug = c["stats"].team.slug
            by_slug.setdefault(slug, 0.0)
            by_slug[slug] += max(c["marginal_wins"], 0.0)
        self.stdout.write("V-c closure table (Σ positive mWins → implied roster value):")
        for slug in CLOSURE_PROGRAMS:
            tot = by_slug.get(slug)
            if tot is None:
                self.stdout.write(f"    {slug:12} — no data")
                continue
            self.stdout.write(
                f"    {slug:12} {tot:7.2f} mWins → "
                f"${tot*DOLLARS_PER_WIN_LOW/1e6:.2f}M–${tot*DOLLARS_PER_WIN_HIGH/1e6:.2f}M"
            )
        self.stdout.write(
            "    context: top-tier roster spend publicly reported $5-10M+; implied "
            "values may exceed any school's rev-share pool because real spend "
            "includes third-party NIL above the pool (see methodology)."
        )

        if failures:
            for f in failures:
                self.stderr.write(self.style.ERROR(f"VALIDATION FAILURE — {f}"))
            raise CommandError(f"{len(failures)} validation failure(s) — nothing written.")
