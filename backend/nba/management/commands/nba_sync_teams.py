"""
nba_sync_teams — seed all 30 NBA franchises into the NBATeam table.

Conference/division data doesn't come from nba_api (it only has city/name/abbr
in its static dataset), so it's maintained as a hardcoded mapping here.
The NBA has had stable conference/division boundaries since the 2004 realignment.

Usage:
    uv run python manage.py nba_sync_teams
    uv run python manage.py nba_sync_teams --dry-run
"""

from django.core.management.base import BaseCommand

from nba.models import NBATeam

# ── Static data ───────────────────────────────────────────────────────────────

# nba_team_id values come from NBA.com — verified against nba_api.stats.static.teams
NBA_TEAMS: list[dict] = [
    # East — Atlantic
    {"nba_team_id": 1610612738, "name": "Boston Celtics",        "abbreviation": "BOS", "city": "Boston",        "conference": "East", "division": "Atlantic"},
    {"nba_team_id": 1610612751, "name": "Brooklyn Nets",         "abbreviation": "BKN", "city": "Brooklyn",      "conference": "East", "division": "Atlantic"},
    {"nba_team_id": 1610612752, "name": "New York Knicks",       "abbreviation": "NYK", "city": "New York",      "conference": "East", "division": "Atlantic"},
    {"nba_team_id": 1610612755, "name": "Philadelphia 76ers",    "abbreviation": "PHI", "city": "Philadelphia",  "conference": "East", "division": "Atlantic"},
    {"nba_team_id": 1610612761, "name": "Toronto Raptors",       "abbreviation": "TOR", "city": "Toronto",       "conference": "East", "division": "Atlantic"},
    # East — Central
    {"nba_team_id": 1610612741, "name": "Chicago Bulls",         "abbreviation": "CHI", "city": "Chicago",       "conference": "East", "division": "Central"},
    {"nba_team_id": 1610612739, "name": "Cleveland Cavaliers",   "abbreviation": "CLE", "city": "Cleveland",     "conference": "East", "division": "Central"},
    {"nba_team_id": 1610612765, "name": "Detroit Pistons",       "abbreviation": "DET", "city": "Detroit",       "conference": "East", "division": "Central"},
    {"nba_team_id": 1610612754, "name": "Indiana Pacers",        "abbreviation": "IND", "city": "Indiana",       "conference": "East", "division": "Central"},
    {"nba_team_id": 1610612749, "name": "Milwaukee Bucks",       "abbreviation": "MIL", "city": "Milwaukee",     "conference": "East", "division": "Central"},
    # East — Southeast
    {"nba_team_id": 1610612737, "name": "Atlanta Hawks",         "abbreviation": "ATL", "city": "Atlanta",       "conference": "East", "division": "Southeast"},
    {"nba_team_id": 1610612766, "name": "Charlotte Hornets",     "abbreviation": "CHA", "city": "Charlotte",     "conference": "East", "division": "Southeast"},
    {"nba_team_id": 1610612748, "name": "Miami Heat",            "abbreviation": "MIA", "city": "Miami",         "conference": "East", "division": "Southeast"},
    {"nba_team_id": 1610612753, "name": "Orlando Magic",         "abbreviation": "ORL", "city": "Orlando",       "conference": "East", "division": "Southeast"},
    {"nba_team_id": 1610612764, "name": "Washington Wizards",    "abbreviation": "WAS", "city": "Washington",    "conference": "East", "division": "Southeast"},
    # West — Northwest
    {"nba_team_id": 1610612743, "name": "Denver Nuggets",        "abbreviation": "DEN", "city": "Denver",        "conference": "West", "division": "Northwest"},
    {"nba_team_id": 1610612750, "name": "Minnesota Timberwolves","abbreviation": "MIN", "city": "Minnesota",     "conference": "West", "division": "Northwest"},
    {"nba_team_id": 1610612760, "name": "Oklahoma City Thunder", "abbreviation": "OKC", "city": "Oklahoma City", "conference": "West", "division": "Northwest"},
    {"nba_team_id": 1610612757, "name": "Portland Trail Blazers","abbreviation": "POR", "city": "Portland",      "conference": "West", "division": "Northwest"},
    {"nba_team_id": 1610612762, "name": "Utah Jazz",             "abbreviation": "UTA", "city": "Utah",          "conference": "West", "division": "Northwest"},
    # West — Pacific
    {"nba_team_id": 1610612744, "name": "Golden State Warriors", "abbreviation": "GSW", "city": "Golden State",  "conference": "West", "division": "Pacific"},
    {"nba_team_id": 1610612746, "name": "Los Angeles Clippers",  "abbreviation": "LAC", "city": "Los Angeles",   "conference": "West", "division": "Pacific"},
    {"nba_team_id": 1610612747, "name": "Los Angeles Lakers",    "abbreviation": "LAL", "city": "Los Angeles",   "conference": "West", "division": "Pacific"},
    {"nba_team_id": 1610612756, "name": "Phoenix Suns",          "abbreviation": "PHX", "city": "Phoenix",       "conference": "West", "division": "Pacific"},
    {"nba_team_id": 1610612758, "name": "Sacramento Kings",      "abbreviation": "SAC", "city": "Sacramento",    "conference": "West", "division": "Pacific"},
    # West — Southwest
    {"nba_team_id": 1610612742, "name": "Dallas Mavericks",      "abbreviation": "DAL", "city": "Dallas",        "conference": "West", "division": "Southwest"},
    {"nba_team_id": 1610612745, "name": "Houston Rockets",       "abbreviation": "HOU", "city": "Houston",       "conference": "West", "division": "Southwest"},
    {"nba_team_id": 1610612763, "name": "Memphis Grizzlies",     "abbreviation": "MEM", "city": "Memphis",       "conference": "West", "division": "Southwest"},
    {"nba_team_id": 1610612740, "name": "New Orleans Pelicans",  "abbreviation": "NOP", "city": "New Orleans",   "conference": "West", "division": "Southwest"},
    {"nba_team_id": 1610612759, "name": "San Antonio Spurs",     "abbreviation": "SAS", "city": "San Antonio",   "conference": "West", "division": "Southwest"},
]


class Command(BaseCommand):
    help = "Seed all 30 NBA teams. Idempotent — safe to re-run."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        created = updated = 0

        for team_data in NBA_TEAMS:
            defaults = {
                "name": team_data["name"],
                "abbreviation": team_data["abbreviation"],
                "city": team_data["city"],
                "conference": team_data["conference"],
                "division": team_data["division"],
                "logo_url": f"https://cdn.nba.com/logos/nba/{team_data['nba_team_id']}/global/L/logo.svg",
            }
            if dry_run:
                exists = NBATeam.objects.filter(nba_team_id=team_data["nba_team_id"]).exists()
                self.stdout.write(
                    f"  {'UPDATE' if exists else 'CREATE'} {team_data['abbreviation']} "
                    f"({team_data['conference']}/{team_data['division']})"
                )
                continue

            _, is_new = NBATeam.objects.update_or_create(
                nba_team_id=team_data["nba_team_id"],
                defaults=defaults,
            )
            if is_new:
                created += 1
            else:
                updated += 1

        if dry_run:
            self.stdout.write(self.style.WARNING(f"DRY RUN — {len(NBA_TEAMS)} teams previewed, no changes written"))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Done — {created} created, {updated} updated ({created + updated} total)"
                )
            )
