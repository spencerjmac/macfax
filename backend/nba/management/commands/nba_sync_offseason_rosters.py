"""
nba_sync_offseason_rosters — diff NBA.com current rosters against prior-season
player-team associations from NBAPlayerSeasonStats, then create TeamOutseasonMove
rows for detected departures and acquisitions.

This is the automated equivalent of manually entering trades and FA signings in
moves_2026.csv.  Run after the dust settles on a season's offseason transactions
(typically July–August).

Usage:
  python manage.py nba_sync_offseason_rosters \\
      --source-season 2026 --target-season 2027 --dry-run

  python manage.py nba_sync_offseason_rosters \\
      --source-season 2026 --target-season 2027

  python manage.py nba_sync_offseason_rosters \\
      --source-season 2026 --target-season 2027 --team portland-trail-blazers

After a successful run, re-execute compute_nba_team_outlooks to pick up the
new move rows.
"""

import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from nba.models import (
    NBASeason,
    NBATeam,
    NBAPlayer,
    NBAPlayerSeasonStats,
    TeamOutseasonMove,
    TeamSeasonOutlook,
)
from nba.providers.nba_api_provider import NBAApiProvider
from nba.utils.name_utils import normalize_name

MIN_MPG = 5.0
MIN_GP = 10


class Command(BaseCommand):
    help = (
        "Diff NBA.com current rosters against prior-season stats and create "
        "TeamOutseasonMove rows for departures and acquisitions."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-season", dest="source_season", type=int, required=True,
            metavar="YEAR",
            help="Ending year of the prior season, e.g. 2026 for 2025-26.",
        )
        parser.add_argument(
            "--target-season", dest="target_season", type=int, required=True,
            metavar="YEAR",
            help="Ending year of the projection season, e.g. 2027 for 2026-27.",
        )
        parser.add_argument(
            "--nba-season", dest="nba_season", default=None, metavar="SEASON_STR",
            help='NBA.com season string, e.g. "2025-26". Defaults to auto-derived from --source-season.',
        )
        parser.add_argument(
            "--team", dest="team_filter", default=None, metavar="SLUG",
            help="Process a single team slug (useful for spot-checking).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Print what would be created without writing to the database.",
        )
        parser.add_argument(
            "--skip-existing", dest="skip_existing", action="store_true",
            help="Skip players who already have any TeamOutseasonMove for the target outlook.",
        )
        parser.add_argument(
            "--replace", action="store_true",
            help=(
                "Delete existing source='sync' moves for the target season before "
                "recreating them, so departed / re-signed players self-heal instead "
                "of lingering. Draft- and manual-sourced rows are left untouched."
            ),
        )

    def handle(self, *args, **options):
        source_season: int = options["source_season"]
        target_season: int = options["target_season"]
        nba_season_str: str = options["nba_season"] or f"{source_season - 1}-{str(source_season)[2:]}"
        team_filter: str | None = options.get("team_filter")
        dry_run: bool = options["dry_run"]
        skip_existing: bool = options["skip_existing"]
        replace: bool = options["replace"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no rows will be written.\n"))

        # ── Step 1: Load prior season associations ────────────────────────────
        try:
            source_season_obj = NBASeason.objects.get(year=source_season)
        except NBASeason.DoesNotExist:
            raise CommandError(f"NBASeason with year={source_season} not found.")

        self.stdout.write(
            f"Loading prior-season player-team associations "
            f"(season {source_season_obj.display_name}, gp≥{MIN_GP}, mpg≥{MIN_MPG})…"
        )

        qs = NBAPlayerSeasonStats.objects.select_related("player", "team").filter(
            season=source_season_obj,
            season_type="regular",
            gp__gte=MIN_GP,
            mpg__gte=MIN_MPG,
        )

        prior_team_by_player_id: dict[int, str] = {}
        prior_team_by_name: dict[str, str] = {}
        player_name_by_id: dict[int, str] = {}

        for row in qs:
            if row.team is None:
                continue
            pid = row.player.player_id
            prior_team_by_player_id[pid] = row.team.slug
            player_name_by_id[pid] = row.player.name
            prior_team_by_name[normalize_name(row.player.name)] = row.team.slug

        self.stdout.write(
            f"  {len(prior_team_by_player_id)} qualifying players from prior season.\n"
        )

        # ── Step 2: Load current rosters from NBA.com ─────────────────────────
        self.stdout.write(
            f"Fetching current rosters from NBA.com (season={nba_season_str})…"
        )
        provider = NBAApiProvider()

        all_teams = list(NBATeam.objects.all().order_by("abbreviation"))
        if team_filter:
            all_teams = [t for t in all_teams if t.slug == team_filter]
            if not all_teams:
                raise CommandError(f"No NBATeam found with slug='{team_filter}'.")

        current_team_by_player_id: dict[int, str] = {}
        current_team_by_name: dict[str, str] = {}
        current_player_names: dict[int, str] = {}
        ambiguous_players: set[int] = set()
        teams_with_empty_roster: list[str] = []

        for team in all_teams:
            roster = provider.get_team_roster(team.nba_team_id, source_season)
            if not roster:
                teams_with_empty_roster.append(team.slug)
                self.stderr.write(
                    f"  WARNING: empty roster for {team.abbreviation} ({team.slug}) — skipping"
                )
                continue

            for entry in roster:
                pid = entry.player_id
                name = entry.name
                if pid in current_team_by_player_id and current_team_by_player_id[pid] != team.slug:
                    self.stderr.write(
                        f"  AMBIGUOUS: {name} (id={pid}) appears on multiple teams — skipping"
                    )
                    ambiguous_players.add(pid)
                    continue
                current_team_by_player_id[pid] = team.slug
                current_player_names[pid] = name
                current_team_by_name[normalize_name(name)] = team.slug

            self.stdout.write(
                f"  {team.abbreviation}: {len(roster)} players"
            )

        # Remove ambiguous players from current lookups (they were added before conflict detected)
        for pid in ambiguous_players:
            current_team_by_player_id.pop(pid, None)
            current_player_names.pop(pid, None)

        self.stdout.write(
            f"\n{len(current_team_by_player_id)} players on current rosters "
            f"({len(ambiguous_players)} ambiguous, {len(teams_with_empty_roster)} teams skipped).\n"
        )

        # ── Step 3: Build diff ────────────────────────────────────────────────
        departures: dict[int, dict] = {}
        acquisitions: dict[int, dict] = {}
        name_fallback_matches: list[str] = []

        for pid, prior_team in prior_team_by_player_id.items():
            if pid in ambiguous_players:
                continue
            current_team = current_team_by_player_id.get(pid)
            if current_team is None:
                norm = normalize_name(player_name_by_id[pid])
                current_team = current_team_by_name.get(norm)
                if current_team:
                    name_fallback_matches.append(
                        f"  {player_name_by_id[pid]} → {current_team} (via name)"
                    )
            if current_team == prior_team:
                continue
            departures[pid] = {
                "name": player_name_by_id[pid],
                "prior_team": prior_team,
                "current_team": current_team,
            }
            if current_team:
                acquisitions[pid] = {
                    "name": player_name_by_id[pid],
                    "current_team": current_team,
                    "prior_team": prior_team,
                }

        # Players on current rosters with no prior-season record
        for pid, current_team in current_team_by_player_id.items():
            if pid in ambiguous_players or pid in prior_team_by_player_id:
                continue
            name = current_player_names[pid]
            if normalize_name(name) not in prior_team_by_name:
                acquisitions[pid] = {
                    "name": name,
                    "current_team": current_team,
                    "prior_team": None,
                }

        # ── Step 4: Build outlook lookup helper ───────────────────────────────
        # Scope to the target season's outlook rows — team_slug is no longer
        # globally unique, so an unscoped .all() would collapse to an arbitrary
        # season's row per slug once multiple seasons exist.
        all_outlooks = list(TeamSeasonOutlook.objects.filter(season__year=target_season))
        outlooks_by_slug: dict[str, TeamSeasonOutlook] = {o.team_slug: o for o in all_outlooks}
        outlooks_by_abbr: dict[str, TeamSeasonOutlook] = {o.team_abbr: o for o in all_outlooks}
        teams_by_slug: dict[str, NBATeam] = {t.slug: t for t in NBATeam.objects.all()}

        def get_outlook(team_slug: str) -> TeamSeasonOutlook | None:
            o = outlooks_by_slug.get(team_slug)
            if o:
                return o
            # LAC-style mismatch: NBATeam.slug != TeamSeasonOutlook.team_slug
            nba_team = teams_by_slug.get(team_slug)
            if nba_team:
                return outlooks_by_abbr.get(nba_team.abbreviation)
            return None

        # Phase 4 D4: "outside NBA" was emitted whenever prior_team was None —
        # but None only means the sync didn't capture a prior team (e.g. the
        # player missed the source-season minutes threshold), NOT that they
        # have no NBA history. Recover the true most-recent team for any name
        # that resolves to an NBAPlayer with stats. Trade-vs-signing is NOT
        # touched (undecidable from origin alone); move_type stays as-is.
        _norm_player_index: dict[str, list] = {}
        for _p in NBAPlayer.objects.all().only("id", "name"):
            _norm_player_index.setdefault(normalize_name(_p.name), []).append(_p)

        def recent_team_slug(name: str) -> str | None:
            exact = list(NBAPlayer.objects.filter(name__iexact=name).only("id")[:2])
            cands = exact if len(exact) == 1 else _norm_player_index.get(normalize_name(name), [])
            if len(cands) != 1:
                return None  # unresolvable or ambiguous → leave as-is
            st = (
                NBAPlayerSeasonStats.objects.filter(
                    player_id=cands[0].id, season_type="regular", team__isnull=False
                )
                .select_related("team")
                .order_by("-season__year")
                .first()
            )
            return st.team.slug if st else None

        # ── Step 5 & 6: Create rows + build CSV audit data ────────────────────
        csv_rows: list[dict] = []

        dep_created = dep_existed = dep_no_outlook = 0
        acq_created = acq_existed = acq_no_outlook = acq_drafted_skip = 0

        # ── Step 5a: --replace purge (source="sync" only) ─────────────────────
        # get_or_create never removes rows, so a player who left (or re-signed
        # elsewhere) leaves a stale sync move behind on every re-run. --replace
        # clears this command's own rows for the target season first; draft- and
        # manual-sourced moves are untouched so a routine re-sync can't nuke them.
        if replace:
            stale = TeamOutseasonMove.objects.filter(
                team__in=all_outlooks, source="sync"
            )
            n = stale.count()
            if dry_run:
                self.stdout.write(self.style.WARNING(
                    f"  --replace: WOULD delete {n} existing source='sync' moves.\n"
                ))
            else:
                stale.delete()
                self.stdout.write(self.style.WARNING(
                    f"  --replace: deleted {n} existing source='sync' moves.\n"
                ))

        # Departures
        for pid, dep in departures.items():
            outlook = get_outlook(dep["prior_team"])
            if outlook is None:
                self.stderr.write(
                    f"  WARN: no TeamSeasonOutlook for prior team '{dep['prior_team']}' "
                    f"({dep['name']}) — skipping departure"
                )
                dep_no_outlook += 1
                csv_rows.append(_csv_row(pid, dep["name"], dep["prior_team"],
                                         dep["current_team"], "departure",
                                         False, "outlook_not_found"))
                continue

            detail = (
                f"Left via offseason — now on {dep['current_team'] or 'no NBA roster'}"
            )
            csv_row_skip = None

            if not dry_run:
                _, was_created = TeamOutseasonMove.objects.get_or_create(
                    team=outlook,
                    season=outlook.season,
                    player_name=dep["name"],
                    move_type="lost",
                    # source="sync": roster-diff origin (vs manual CSV). transaction_date
                    # left NULL — a snapshot diff has no per-transaction date to stamp.
                    defaults={"detail": detail, "impact_rating": "medium",
                              "source": "sync"},
                )
                if was_created:
                    dep_created += 1
                    csv_row_skip = ""
                else:
                    dep_existed += 1
                    csv_row_skip = "already_exists"
            else:
                dep_created += 1
                csv_row_skip = ""

            csv_rows.append(_csv_row(pid, dep["name"], dep["prior_team"],
                                     dep["current_team"], "departure",
                                     csv_row_skip == "", csv_row_skip or ""))

        # Acquisitions
        for pid, acq in acquisitions.items():
            outlook = get_outlook(acq["current_team"])
            if outlook is None:
                self.stderr.write(
                    f"  WARN: no TeamSeasonOutlook for current team '{acq['current_team']}' "
                    f"({acq['name']}) — skipping acquisition"
                )
                acq_no_outlook += 1
                csv_rows.append(_csv_row(pid, acq["name"], acq.get("prior_team"),
                                         acq["current_team"], "acquisition",
                                         False, "outlook_not_found"))
                continue

            # Drafted skip guard
            if outlook.offseason_moves.filter(
                move_type="drafted", player_name__iexact=acq["name"]
            ).exists():
                acq_drafted_skip += 1
                csv_rows.append(_csv_row(pid, acq["name"], acq.get("prior_team"),
                                         acq["current_team"], "acquisition",
                                         False, "drafted"))
                continue

            # Skip-existing guard
            if skip_existing and outlook.offseason_moves.filter(
                player_name__iexact=acq["name"]
            ).exists():
                acq_existed += 1
                csv_rows.append(_csv_row(pid, acq["name"], acq.get("prior_team"),
                                         acq["current_team"], "acquisition",
                                         False, "already_exists"))
                continue

            # Phase 4 D4: recover a real source team before falling back to
            # "outside NBA" (a player with NBA stats is never "outside NBA").
            source_team = acq["prior_team"] or recent_team_slug(acq["name"])
            detail = f"Acquired from {source_team or 'outside NBA'}"
            csv_row_skip = None

            if not dry_run:
                _, was_created = TeamOutseasonMove.objects.get_or_create(
                    team=outlook,
                    season=outlook.season,
                    player_name=acq["name"],
                    move_type="signed",
                    # source="sync": roster-diff origin (vs manual CSV). transaction_date
                    # left NULL — a snapshot diff has no per-transaction date to stamp.
                    defaults={"detail": detail, "impact_rating": "medium",
                              "source": "sync"},
                )
                if was_created:
                    acq_created += 1
                    csv_row_skip = ""
                else:
                    acq_existed += 1
                    csv_row_skip = "already_exists"
            else:
                acq_created += 1
                csv_row_skip = ""

            csv_rows.append(_csv_row(pid, acq["name"], acq.get("prior_team"),
                                     acq["current_team"], "acquisition",
                                     csv_row_skip == "", csv_row_skip or ""))

        # ── Step 7: Write CSV ─────────────────────────────────────────────────
        csv_path = (
            Path(settings.BASE_DIR)
            / "nba"
            / "analytics"
            / "backtest_results"
            / f"roster_diff_{source_season}_{target_season}.csv"
        )
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["player_name", "player_id", "prior_team", "current_team",
                            "row_type", "move_created", "skip_reason"],
            )
            writer.writeheader()
            writer.writerows(csv_rows)

        # ── Step 8: Terminal summary ──────────────────────────────────────────
        off_all_rosters = [
            dep for dep in departures.values() if dep["current_team"] is None
        ]
        action = "Would create" if dry_run else "Created"

        self.stdout.write(
            f"\n{'─' * 60}\n"
            f"Roster diff — {source_season - 1}-{str(source_season)[2:]} "
            f"→ {target_season - 1}-{str(target_season)[2:]}\n"
            f"{'─' * 60}\n"
        )
        self.stdout.write(
            f"Departures detected:  {len(departures)}\n"
            f"  {action}:           {dep_created}\n"
            f"  Already existed:    {dep_existed}\n"
            f"  Outlook not found:  {dep_no_outlook}\n"
        )
        self.stdout.write(
            f"Acquisitions detected: {len(acquisitions)}\n"
            f"  Drafted (skipped):  {acq_drafted_skip}\n"
            f"  {action}:           {acq_created}\n"
            f"  Already existed:    {acq_existed}\n"
            f"  Outlook not found:  {acq_no_outlook}\n"
        )

        # Phase 4 D4: how many EXISTING rows a re-import would correct — a
        # move whose stored detail says "outside NBA" but whose player now
        # resolves to a real recent NBA team. Report only; no rows touched here.
        correctable = []
        for m in TeamOutseasonMove.objects.filter(detail__icontains="outside NBA"):
            recovered = recent_team_slug(m.player_name)
            if recovered:
                correctable.append((m.player_name, recovered))
        self.stdout.write(
            f"\n[Phase 4 D4] Existing 'outside NBA' rows a re-import would correct: "
            f"{len(correctable)} (report only — no rows modified). "
            f"Trigger a full re-import to apply."
        )
        for name, slug in correctable[:15]:
            self.stdout.write(f"    {name:28} → Acquired from {slug}")
        if len(correctable) > 15:
            self.stdout.write(f"    … and {len(correctable) - 15} more")

        if off_all_rosters:
            self.stdout.write(
                f"\nPlayers off all rosters (departed NBA entirely): {len(off_all_rosters)}"
            )
            for dep in sorted(off_all_rosters, key=lambda d: d["name"]):
                self.stdout.write(f"  - {dep['name']} (prior: {dep['prior_team']})")

        if name_fallback_matches:
            self.stdout.write(
                f"\nName-fallback matches used (verify these):"
            )
            for m in name_fallback_matches:
                self.stdout.write(m)

        if teams_with_empty_roster:
            self.stdout.write(
                f"\nTeams with empty CommonTeamRoster response (skipped):"
            )
            for slug in teams_with_empty_roster:
                self.stdout.write(f"  {slug}")
        else:
            self.stdout.write("\nTeams with empty CommonTeamRoster response: none")

        self.stdout.write(f"\nAudit CSV: {csv_path.relative_to(Path(settings.BASE_DIR).parent)}\n")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nRe-run without --dry-run to apply."))


def _csv_row(
    player_id: int,
    player_name: str,
    prior_team: str | None,
    current_team: str | None,
    row_type: str,
    move_created: bool,
    skip_reason: str,
) -> dict:
    return {
        "player_name": player_name,
        "player_id": player_id,
        "prior_team": prior_team or "",
        "current_team": current_team or "",
        "row_type": row_type,
        "move_created": move_created,
        "skip_reason": skip_reason,
    }
