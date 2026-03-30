"""
Validate and sync D1 team rosters and conference data from ESPN for a given season.

ESPN's /teams endpoint with ?season=YYYY returns the exact set of D1 teams that
existed in that season. This command:

  1. AUDIT  — Cross-reference ESPN's season roster against our TeamExternalId table.
              Reports any ESPN D1 teams that map to a non-D1 team in our DB (bad
              mappings) and any ESPN D1 teams with no mapping at all (missing teams).

  2. FIX    — With --fix: for each bad ESPN→non-D1 mapping, tries to find the correct
              canonical D1 team using TeamMapper and migrates all Game/TeamGameStats
              records for historical seasons to the correct team, then reassigns the
              TeamExternalId. A dry-run first is recommended.

  3. CONFERENCES — With --conferences: for each D1 team we have a mapping for, fetches
                   their conference for this season from ESPN's team detail endpoint and
                   updates TeamSeasonMetrics.conference (if that record exists). Also
                   creates any missing Conference objects in the DB.

Usage:
    # Audit only (safe, no writes):
    python manage.py sync_season_rosters --season 2008

    # Audit and preview fixes:
    python manage.py sync_season_rosters --season 2008 --fix --dry-run

    # Audit and apply fixes:
    python manage.py sync_season_rosters --season 2008 --fix

    # Audit + fix + seed conferences (run after compute_team_metrics):
    python manage.py sync_season_rosters --seasons 2005,2006,2007,2008 --fix --conferences

    # All historical seasons:
    python manage.py sync_season_rosters --from-season 2005 --to-season 2025 --conferences
"""

import time
import requests

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import (
    Conference,
    Game,
    Season,
    Team,
    TeamExternalId,
    TeamGameStats,
    TeamSeasonMetrics,
)
from core.utils.team_mapping import TeamMapper


ESPN_TEAMS_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams"
ESPN_TEAM_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams/{team_id}"

# Map ESPN's standingSummary conference names to our Conference codes.
# "2nd in Big Ten"  →  "Big Ten"  →  "B10"
ESPN_CONF_NAME_TO_CODE = {
    "America East": "AE",
    "American": "Amer",
    "American Athletic": "Amer",
    "Atlantic 10": "A10",
    "ASUN": "ASun",
    "A-Sun": "ASun",
    "Atlantic Coast": "ACC",
    "ACC": "ACC",
    "Big 12": "B12",
    "Big East": "BE",
    "Big Sky": "BSky",
    "Big South": "BSth",
    "Big Ten": "B10",
    "Big West": "BW",
    "Colonial": "CAA",
    "CAA": "CAA",
    "Conference USA": "CUSA",
    "Horizon": "Horz",
    "Ivy": "Ivy",
    "Ivy League": "Ivy",
    "MAAC": "MAAC",
    "Metro Atlantic": "MAAC",
    "MAC": "MAC",
    "Mid-American": "MAC",
    "MEAC": "MEAC",
    "Mid-Eastern Athletic": "MEAC",
    "Missouri Valley": "MVC",
    "Mountain West": "MWC",
    "Northeast": "NEC",
    "Ohio Valley": "OVC",
    "Patriot": "Pat",
    "Patriot League": "Pat",
    "SEC": "SEC",
    "Southeastern": "SEC",
    "Southern": "SC",
    "Southern Conference": "SC",
    "Southland": "Slnd",
    "Summit": "Sum",
    "Summit League": "Sum",
    "Sun Belt": "SB",
    "SWAC": "SWAC",
    "Southwestern Athletic": "SWAC",
    "WAC": "WAC",
    "Western Athletic": "WAC",
    "WCC": "WCC",
    "West Coast": "WCC",
    "Big West": "BW",
    # Historical conferences that may appear in older seasons
    "Atlantic Sun": "ASun",
    "Trans America Athletic": "ASun",
    "Mid-Continent": "Sum",
    "Mid-Continent Conference": "Sum",
    "Great West": "GW",
    "Colonial Athletic": "CAA",
}


def _fetch_espn_d1_teams(season_year: int) -> dict:
    """Return {espn_id: display_name} for all D1 teams in the given season."""
    resp = requests.get(
        ESPN_TEAMS_URL,
        params={"groups": "50", "limit": "500", "season": str(season_year)},
        timeout=20,
    )
    resp.raise_for_status()
    teams = (
        resp.json()
        .get("sports", [{}])[0]
        .get("leagues", [{}])[0]
        .get("teams", [])
    )
    return {t["team"]["id"]: t["team"]["displayName"] for t in teams}


def _fetch_espn_team_season_conf(espn_id: str, season_year: int) -> tuple[str | None, str | None]:
    """
    Returns (conf_code, conf_name) for a team in a given season, or (None, None).
    Parses ESPN's standingSummary: "2nd in Big Ten" → ("B10", "Big Ten").
    """
    try:
        resp = requests.get(
            ESPN_TEAM_URL.format(team_id=espn_id),
            params={"season": str(season_year)},
            timeout=10,
        )
        if resp.status_code != 200:
            return None, None
        team_data = resp.json().get("team", {})
        summary = team_data.get("standingSummary", "")
        # Format: "3rd in Big Ten" or "T-2nd in SEC"
        if " in " in summary:
            conf_name = summary.split(" in ", 1)[1].strip()
            code = ESPN_CONF_NAME_TO_CODE.get(conf_name)
            return code, conf_name
    except Exception:
        pass
    return None, None


class Command(BaseCommand):
    help = "Audit and sync ESPN D1 team rosters and conference data for historical seasons"

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--season", type=int, help="Single season year (e.g. 2008)")
        group.add_argument("--seasons", type=str, help="Comma-separated list (e.g. 2005,2006,2007)")
        group.add_argument("--from-season", type=int, help="Start of range (use with --to-season)")

        parser.add_argument("--to-season", type=int, help="End of range for --from-season")
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Fix bad ESPN→non-D1 mappings and migrate game data",
        )
        parser.add_argument(
            "--conferences",
            action="store_true",
            help="Fetch and store per-season conference data from ESPN (requires TeamSeasonMetrics to exist)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be done without writing to the DB",
        )

    def handle(self, *args, **options):
        fix = options["fix"]
        conferences = options["conferences"]
        dry_run = options["dry_run"]

        # Build list of seasons to process
        if options["season"]:
            seasons = [options["season"]]
        elif options["seasons"]:
            seasons = [int(y.strip()) for y in options["seasons"].split(",")]
        else:
            from_yr = options["from_season"]
            to_yr = options.get("to_season") or from_yr
            seasons = list(range(from_yr, to_yr + 1))

        if dry_run and (fix or conferences):
            self.stdout.write(self.style.WARNING("[DRY RUN] No database changes will be made.\n"))

        for season_year in seasons:
            self._process_season(season_year, fix=fix, conferences=conferences, dry_run=dry_run)

    def _process_season(self, season_year: int, fix: bool, conferences: bool, dry_run: bool):
        self.stdout.write(self.style.SUCCESS(f"\n{'='*60}"))
        self.stdout.write(self.style.SUCCESS(f"Season {season_year}"))
        self.stdout.write(self.style.SUCCESS(f"{'='*60}"))

        # --- 1. Fetch ESPN D1 team list ---
        self.stdout.write(f"Fetching ESPN D1 team list for season {season_year}...")
        try:
            espn_teams = _fetch_espn_d1_teams(season_year)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"  Failed to fetch ESPN team list: {e}"))
            return

        self.stdout.write(f"  ESPN D1 teams: {len(espn_teams)}")

        # --- 2. Audit mappings ---
        bad_mappings = []   # ESPN D1 team → non-D1 team in DB (wrong mapping)
        missing = []        # ESPN D1 team → no mapping in DB at all

        for espn_id, espn_name in espn_teams.items():
            try:
                ext = TeamExternalId.objects.get(source="espn", external_id=espn_id)
                if not ext.team.is_d1:
                    bad_mappings.append((espn_id, espn_name, ext.team))
            except TeamExternalId.DoesNotExist:
                missing.append((espn_id, espn_name))

        self.stdout.write(f"  Bad mappings (ESPN D1 → non-D1 team): {len(bad_mappings)}")
        self.stdout.write(f"  Missing (no mapping found): {len(missing)}")

        for espn_id, espn_name, wrong_team in bad_mappings:
            self.stdout.write(
                self.style.ERROR(
                    f"    BAD: ESPN '{espn_name}' (id={espn_id}) → DB '{wrong_team.name}' (is_d1=False)"
                )
            )

        for espn_id, espn_name in missing:
            self.stdout.write(
                self.style.WARNING(f"    MISSING: ESPN '{espn_name}' (id={espn_id})")
            )

        # --- 3. Fix bad mappings ---
        if fix and bad_mappings:
            self._fix_bad_mappings(bad_mappings, season_year, dry_run)

        if fix and missing:
            self._fix_missing_teams(missing, dry_run)

        if not bad_mappings and not missing:
            self.stdout.write(self.style.SUCCESS("  All ESPN D1 team mappings look correct."))

        # --- 4. Seed conference data ---
        if conferences:
            self._seed_conferences(espn_teams, season_year, dry_run)

    def _fix_bad_mappings(self, bad_mappings, season_year, dry_run):
        """For each ESPN D1 team mapped to a non-D1 team, find the correct D1 team and migrate data."""
        self.stdout.write(f"\n  Fixing {len(bad_mappings)} bad mapping(s)...")
        mapper = TeamMapper(source="espn")

        for espn_id, espn_name, wrong_team in bad_mappings:
            self.stdout.write(f"\n  Fixing: ESPN '{espn_name}' (id={espn_id}) → should not be '{wrong_team.name}'")

            # Try to find the correct D1 team
            correct_team, confidence, is_override = mapper.find_team(
                external_name=espn_name,
                external_id=espn_id,
            )

            if not correct_team:
                self.stdout.write(
                    self.style.WARNING(
                        f"    ⚠ Could not find correct mapping for '{espn_name}'. Skipping."
                    )
                )
                continue

            if not correct_team.is_d1:
                self.stdout.write(
                    self.style.WARNING(
                        f"    ⚠ Best match '{correct_team.name}' is also non-D1. Skipping."
                    )
                )
                continue

            self.stdout.write(
                f"    → Correct team: '{correct_team.name}' (confidence={confidence:.3f})"
            )

            if dry_run:
                # Count what would be migrated
                home_count = Game.objects.filter(home_team=wrong_team).exclude(season_year__gt=season_year).count()
                away_count = Game.objects.filter(away_team=wrong_team).exclude(season_year__gt=season_year).count()
                tgs_count = TeamGameStats.objects.filter(team=wrong_team).exclude(game__season_year__gt=season_year).count()
                self.stdout.write(
                    f"    [DRY RUN] Would migrate: {home_count} home games, {away_count} away games, {tgs_count} TeamGameStats"
                )
                continue

            with transaction.atomic():
                # Only migrate games from historical seasons (where wrong_team was used via ESPN)
                # We identify historical ESPN-ingested games as any season before current season
                # where the wrong_team appears as a D1-caliber competitor
                from datetime import date
                current_year = date.today().year if date.today().month >= 6 else date.today().year - 1
                # Current season ending year
                current_season = current_year + 1 if date.today().month >= 6 else current_year

                historical_seasons = list(range(2005, current_season))

                home_updated = Game.objects.filter(
                    home_team=wrong_team, season_year__in=historical_seasons
                ).update(home_team=correct_team)

                away_updated = Game.objects.filter(
                    away_team=wrong_team, season_year__in=historical_seasons
                ).update(away_team=correct_team)

                tgs_updated = TeamGameStats.objects.filter(
                    team=wrong_team, game__season_year__in=historical_seasons
                ).update(team=correct_team)

                # Reassign TeamExternalId
                TeamExternalId.objects.filter(source="espn", external_id=espn_id).update(team=correct_team)

                self.stdout.write(
                    self.style.SUCCESS(
                        f"    ✓ Migrated: {home_updated} home games, {away_updated} away games, "
                        f"{tgs_updated} TeamGameStats → reassigned espn:{espn_id} to '{correct_team.name}'"
                    )
                )

    def _fix_missing_teams(self, missing, dry_run):
        """For ESPN D1 teams with no mapping, create TeamExternalId entries."""
        self.stdout.write(f"\n  Processing {len(missing)} missing team(s)...")
        mapper = TeamMapper(source="espn")

        for espn_id, espn_name in missing:
            correct_team, confidence, is_override = mapper.find_team(
                external_name=espn_name,
                external_id=espn_id,
            )

            if correct_team and correct_team.is_d1:
                if dry_run:
                    self.stdout.write(
                        f"    [DRY RUN] Would map espn:{espn_id} ('{espn_name}') → '{correct_team.name}'"
                    )
                else:
                    TeamExternalId.objects.get_or_create(
                        source="espn",
                        external_id=espn_id,
                        defaults={"team": correct_team},
                    )
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"    ✓ Mapped espn:{espn_id} ('{espn_name}') → '{correct_team.name}'"
                        )
                    )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"    ⚠ No D1 match for ESPN '{espn_name}' (id={espn_id}). "
                        f"Team may not exist in our DB yet."
                    )
                )

    def _seed_conferences(self, espn_teams: dict, season_year: int, dry_run: bool):
        """
        For each team with a TeamSeasonMetrics record, fetch their conference
        from ESPN's team detail endpoint and update the conference FK.
        """
        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            self.stdout.write(
                self.style.WARNING(f"\n  Season {season_year} not in DB — cannot seed conferences.")
            )
            return

        metrics_qs = TeamSeasonMetrics.objects.filter(season=season).select_related("team")
        if not metrics_qs.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"\n  No TeamSeasonMetrics for season {season_year}. "
                    f"Run compute_team_metrics first, then re-run with --conferences."
                )
            )
            return

        self.stdout.write(f"\n  Seeding conference data for {metrics_qs.count()} teams in season {season_year}...")

        # Build ESPN ID lookup (team.id → espn external_id)
        espn_id_map = {
            ext.team_id: ext.external_id
            for ext in TeamExternalId.objects.filter(source="espn")
        }

        updated = 0
        no_espn_id = 0
        no_conf = 0
        unknown_conf = 0

        conf_cache = {}  # conf_code → Conference object

        for metrics in metrics_qs:
            espn_id = espn_id_map.get(metrics.team_id)
            if not espn_id:
                no_espn_id += 1
                continue

            conf_code, conf_name = _fetch_espn_team_season_conf(espn_id, season_year)
            time.sleep(0.05)  # Be gentle with the API

            if not conf_code:
                if conf_name:
                    unknown_conf += 1
                    self.stdout.write(
                        self.style.WARNING(f"    Unknown conf name: '{conf_name}' for {metrics.team.name}")
                    )
                else:
                    no_conf += 1
                continue

            # Get or create Conference object
            if conf_code not in conf_cache:
                conf_obj, _ = Conference.objects.get_or_create(
                    code=conf_code,
                    defaults={"name": conf_name or conf_code},
                )
                conf_cache[conf_code] = conf_obj
            else:
                conf_obj = conf_cache[conf_code]

            if metrics.conference_id != conf_obj.id:
                if not dry_run:
                    metrics.conference = conf_obj
                    metrics.save(update_fields=["conference"])
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"  Conferences: {updated} updated, {no_espn_id} skipped (no ESPN ID), "
                f"{no_conf} skipped (no conf data), {unknown_conf} unknown conf names"
            )
        )
