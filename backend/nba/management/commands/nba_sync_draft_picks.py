"""
nba_sync_draft_picks — pull completed draft from NBA.com and create drafted TeamOutseasonMove rows.

Pulls DraftHistory for a given year, fuzzy-matches player names against an optional
prospects JSON for MPS scores, and bulk-creates move rows idempotently.

Usage:
  python manage.py nba_sync_draft_picks --year 2026
  python manage.py nba_sync_draft_picks --year 2026 --prospects-json web/src/data/prospects_2026.json
  python manage.py nba_sync_draft_picks --year 2026 --round 1 --dry-run
"""

import json
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from nba.models import NBATeam, TeamOutseasonMove, TeamSeasonOutlook
from nba.utils.name_utils import normalize_name


def _impact_from_pick(overall_pick: int) -> str:
    if overall_pick <= 5:
        return "high"
    if overall_pick <= 20:
        return "medium"
    return "low"


class Command(BaseCommand):
    help = "Sync NBA draft picks from NBA.com DraftHistory and create drafted TeamOutseasonMove rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--year", type=int, default=2026, metavar="YEAR",
            help="Draft year (default 2026).",
        )
        parser.add_argument(
            "--prospects-json", dest="prospects_json", metavar="PATH",
            help="Path to prospects JSON for MPS score matching.",
        )
        parser.add_argument(
            "--round", dest="round_filter", type=int, default=None, choices=[1, 2],
            metavar="ROUND",
            help="Only sync picks from this round (1 or 2). Default: all rounds.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Print what would be created without writing to the database.",
        )

    def handle(self, *args, **options):
        year: int = options["year"]
        prospects_path: str | None = options.get("prospects_json")
        round_filter: int | None = options.get("round_filter")
        dry_run: bool = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no rows will be written.\n"))

        # ── Load prospects JSON for MPS matching ─────────────────────────────
        prospects_by_full: dict[str, dict] = {}
        prospects_by_last: dict[str, list[dict]] = {}

        if prospects_path:
            ppath = Path(prospects_path)
            if not ppath.exists():
                raise CommandError(f"Prospects JSON not found: {prospects_path}")
            with ppath.open(encoding="utf-8") as fh:
                data = json.load(fh)
            for p in data.get("prospects", []):
                key = normalize_name(p["name"])
                prospects_by_full[key] = p
                last = key.split()[-1] if key.split() else key
                prospects_by_last.setdefault(last, []).append(p)
            self.stdout.write(
                f"Prospects JSON loaded: {len(prospects_by_full)} prospects for MPS matching.\n"
            )

        # ── Build team and outlook lookups ────────────────────────────────────
        teams_by_abbr: dict[str, NBATeam] = {
            t.abbreviation: t for t in NBATeam.objects.all()
        }
        _all_outlooks = list(TeamSeasonOutlook.objects.all())
        outlooks_by_slug: dict[str, TeamSeasonOutlook] = {
            o.team_slug: o for o in _all_outlooks
        }
        outlooks_by_abbr: dict[str, TeamSeasonOutlook] = {
            o.team_abbr: o for o in _all_outlooks
        }

        # ── Fetch draft history from NBA.com ──────────────────────────────────
        try:
            from nba_api.stats.endpoints import drafthistory
        except ImportError:
            raise CommandError("nba_api not installed. Run: pip install nba-api")

        self.stdout.write(f"Fetching {year} draft from NBA.com…")
        try:
            result = drafthistory.DraftHistory(
                league_id="00",
                season_year_nullable=str(year),
                timeout=30,
            )
            df = result.draft_history.get_data_frame()
        except Exception as exc:
            raise CommandError(f"NBA.com DraftHistory call failed: {exc}")

        if df.empty:
            raise CommandError(f"No draft data returned for year {year}.")

        self.stdout.write(f"Fetched {len(df)} picks.\n")

        # ── Process picks ─────────────────────────────────────────────────────
        created = skipped = fuzzy_matched = fuzzy_unmatched = 0
        unmatched_names: list[str] = []

        current_round = None

        for _, row in df.iterrows():
            round_num = int(row["ROUND_NUMBER"])
            round_pick = int(row["ROUND_PICK"])
            overall_pick = int(row["OVERALL_PICK"])
            player_name: str = row["PLAYER_NAME"]
            team_abbr: str = row["TEAM_ABBREVIATION"]

            if round_filter is not None and round_num != round_filter:
                continue

            if round_num != current_round:
                current_round = round_num
                self.stdout.write(f"\nRound {round_num}")

            # ── MPS matching ──────────────────────────────────────────────────
            prospect = self._fuzzy_match(
                player_name, prospects_by_full, prospects_by_last
            )
            mps: float | None = None
            if prospect:
                mps = prospect.get("mps") or prospect.get("mpsComposite")
                fuzzy_matched += 1
            else:
                fuzzy_unmatched += 1
                unmatched_names.append(player_name)

            notes = f"Round {round_num}, Pick {overall_pick}"
            if mps is not None:
                notes += f". MPS: {mps:.1f}"

            impact = _impact_from_pick(overall_pick)
            mps_tag = f"[MPS: {mps:.1f}]" if mps is not None else "[no MPS match]"

            # ── Team/outlook lookup ───────────────────────────────────────────
            team = teams_by_abbr.get(team_abbr)
            if team is None:
                self.stderr.write(
                    f"  Pick {overall_pick:>2}  {team_abbr:<4}  {player_name}"
                    f"  — unknown team abbreviation, skipping."
                )
                skipped += 1
                continue

            outlook = outlooks_by_slug.get(team.slug) or outlooks_by_abbr.get(team_abbr)
            if outlook is None:
                self.stderr.write(
                    f"  Pick {overall_pick:>2}  {team_abbr:<4}  {player_name}"
                    f"  — no TeamSeasonOutlook for slug '{team.slug}' or abbr '{team_abbr}', skipping."
                )
                skipped += 1
                continue

            # ── Create move row ───────────────────────────────────────────────
            label = f"  Pick {overall_pick:>2}  {team_abbr:<4}  {player_name:<28} {mps_tag}"

            if dry_run:
                self.stdout.write(f"{label}  → WOULD CREATE")
                created += 1
                continue

            _, was_created = TeamOutseasonMove.objects.get_or_create(
                team=outlook,
                player_name=player_name,
                move_type="drafted",
                defaults={
                    "detail": notes,
                    "impact_rating": impact,
                    "round_number": round_num,
                    "overall_pick": overall_pick,
                    "mps_score": mps,
                },
            )

            if was_created:
                self.stdout.write(f"{label}  → CREATED")
                created += 1
            else:
                self.stdout.write(f"{label}  → already exists")
                skipped += 1

        # ── Summary ───────────────────────────────────────────────────────────
        action = "Would create" if dry_run else "Created"
        self.stdout.write(
            f"\n{'─' * 60}\n"
            f"Summary: {created + skipped} picks processed.\n"
            f"  {action}: {created}   Skipped (duplicate/error): {skipped}\n"
        )
        if prospects_path:
            self.stdout.write(
                f"  MPS matched: {fuzzy_matched}   Unmatched: {fuzzy_unmatched}"
            )
            if unmatched_names:
                self.stdout.write("  Unmatched players:")
                for name in unmatched_names:
                    self.stdout.write(f"    - {name}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nRe-run without --dry-run to apply."))

    # ── helpers ───────────────────────────────────────────────────────────────

    def _fuzzy_match(
        self,
        player_name: str,
        by_full: dict[str, dict],
        by_last: dict[str, list[dict]],
    ) -> dict | None:
        if not by_full:
            return None

        key = normalize_name(player_name)

        # Exact normalized match
        if key in by_full:
            return by_full[key]

        # Last-name fallback — only use if exactly one candidate
        last = key.split()[-1] if key.split() else key
        candidates = by_last.get(last, [])
        if len(candidates) == 1:
            return candidates[0]

        return None
