"""
Management command: check_recruiting_data

Post-import validation and coverage reporting for PlayerRecruitingProfile
(pairs with `import_recruiting`; see docs/bpr_audit/08_post_v2_experiments.md §3).

Read-only. Reports per season:
  - coverage: % of newcomers (PlayerSeasonProjection.recruitment_type='newcomer')
    with a recruiting profile, split by star tier
  - match quality: profiles whose player has no game/season stats that year
    (likely bad fuzzy match or wrong class_year)
  - missing high-minute freshmen: newcomers with >= --min-mpg and no profile
    (the players whose priors would benefit most)
  - duplicates: multiple profiles per (player) across class years

Usage:
  python manage.py check_recruiting_data --seasons 2021 2022 2023 2024 2025 2026
  python manage.py check_recruiting_data --seasons 2026 --min-mpg 15
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Validation + coverage reports for recruiting profiles (read-only)."

    def add_arguments(self, parser):
        parser.add_argument("--seasons", nargs="+", type=int, required=True)
        parser.add_argument("--min-mpg", type=float, default=12.0,
                            help="High-minute threshold for the missing-profile report")
        parser.add_argument("--out-dir", type=str,
                            default="backtest_output/bpr_audit")

    def handle(self, *args, **opts):
        from ncaa.models import (
            PlayerRecruitingProfile, PlayerSeasonProjection, PlayerSeasonStats,
        )

        out_dir = Path(opts["out_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        min_mpg = opts["min_mpg"]

        # duplicates across class years (same player, >1 profile)
        by_player = Counter(
            PlayerRecruitingProfile.objects.values_list("player_id", flat=True))
        dupes = {pid: n for pid, n in by_player.items() if n > 1}
        if dupes:
            self.stdout.write(self.style.WARNING(
                f"{len(dupes)} players hold multiple recruiting profiles "
                f"(distinct class years is legal but review): "
                f"{list(dupes.items())[:10]}"))

        missing_rows = []
        for season in sorted(opts["seasons"]):
            # Newcomer = has stats this season, none in any earlier season.
            # Derived from PlayerSeasonStats directly — PlayerSeasonProjection's
            # universe misses players who joined after its build (e.g. the
            # 2026 five-star class; known bug, see docs/bpr_audit/08 §3).
            this_year = set(
                PlayerSeasonStats.objects
                .filter(season__year=season)
                .values_list("player_id", flat=True))
            before = set(
                PlayerSeasonStats.objects
                .filter(season__year__lt=season,
                        player_id__in=this_year)
                .values_list("player_id", flat=True))
            newcomers = this_year - before
            profiles = {
                p["player_id"]: p
                for p in PlayerRecruitingProfile.objects
                .filter(class_year=season)
                .values("player_id", "stars", "national_rank", "source")
            }
            covered = newcomers & set(profiles)

            tier = Counter(
                (profiles[pid]["stars"] or 0) for pid in covered)
            self.stdout.write(
                f"\n=== {season} ===  newcomers={len(newcomers)}  "
                f"profiles={len(profiles)}  coverage="
                f"{len(covered)}/{len(newcomers)} "
                f"({len(covered)/max(len(newcomers),1):.1%})")
            if tier:
                self.stdout.write("  covered by stars: " + "  ".join(
                    f"{s}★:{n}" for s, n in sorted(tier.items(), reverse=True)))

            # profiles pointing at players with no stats that season → match audit
            with_stats = set(
                PlayerSeasonStats.objects
                .filter(season__year=season,
                        player_id__in=list(profiles))
                .values_list("player_id", flat=True))
            orphans = set(profiles) - with_stats
            if orphans:
                self.stdout.write(self.style.WARNING(
                    f"  {len(orphans)} profiles have no {season} season stats "
                    f"(bad match / redshirt / wrong class_year)"))

            # missing high-minute freshmen — the priority ingest list
            hi = (PlayerSeasonStats.objects
                  .filter(season__year=season, mpg__gte=min_mpg,
                          player_id__in=list(newcomers - covered))
                  .select_related("player", "team")
                  .order_by("-mpg"))
            n_hi = hi.count()
            self.stdout.write(
                f"  high-minute newcomers (mpg>={min_mpg}) WITHOUT profile: {n_hi}")
            for pss in hi[:1000]:
                missing_rows.append({
                    "season": season,
                    "player_id": pss.player_id,
                    "espn_id": pss.player.espn_athlete_id,
                    "name": pss.player.display_name,
                    "team": pss.team.name if pss.team else "",
                    "mpg": round(pss.mpg, 1),
                    "bpr": pss.bpr,
                })

        if missing_rows:
            path = out_dir / "recruiting_missing_profiles.csv"
            with open(path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(missing_rows[0].keys()))
                w.writeheader()
                w.writerows(missing_rows)
            self.stdout.write(self.style.SUCCESS(
                f"\nPriority ingest list → {path} ({len(missing_rows)} players)"))
