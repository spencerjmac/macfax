"""
Seed one TeamSeasonOutlook row per NBA team with 2025-26 final season data.

Usage:
    python manage.py seed_team_outlooks            # upsert all 30
    python manage.py seed_team_outlooks --skip-existing  # skip rows already present
"""

from django.core.management.base import BaseCommand

from nba.models import TeamSeasonOutlook

TEAM_DATA = [
    {
        "team_name": "Oklahoma City Thunder", "team_abbr": "OKC", "team_slug": "oklahoma-city-thunder",
        "conference": "West", "primary_color": "#007AC1", "secondary_color": "#EF3B24",
        "wins": 64, "losses": 18, "adj_offensive_rating": 116.6, "adj_defensive_rating": 107.3,
        "adj_net_rating": 9.3, "ffi": 81.3, "pace": 102.3,
        "efg_pct": 56.1, "opp_efg_pct": 51.9, "tov_pct": 11.2, "opp_tov_pct": 14.6,
        "oreb_pct": 22.3, "opp_oreb_pct": 25.6, "fta_rate": 26.1, "opp_fta_rate": 24.8,
    },
    {
        "team_name": "San Antonio Spurs", "team_abbr": "SAS", "team_slug": "san-antonio-spurs",
        "conference": "West", "primary_color": "#C4CED4", "secondary_color": "#000000",
        "wins": 62, "losses": 20, "adj_offensive_rating": 117.2, "adj_defensive_rating": 110.9,
        "adj_net_rating": 6.3, "ffi": 66.5, "pace": 102.8,
        "efg_pct": 55.9, "opp_efg_pct": 52.2, "tov_pct": 11.8, "opp_tov_pct": 11.5,
        "oreb_pct": 26.2, "opp_oreb_pct": 22.7, "fta_rate": 27.4, "opp_fta_rate": 22.8,
    },
    {
        "team_name": "Detroit Pistons", "team_abbr": "DET", "team_slug": "detroit-pistons",
        "conference": "East", "primary_color": "#C8102E", "secondary_color": "#006BB6",
        "wins": 60, "losses": 22, "adj_offensive_rating": 114.6, "adj_defensive_rating": 109.3,
        "adj_net_rating": 5.4, "ffi": 72.3, "pace": 103.1,
        "efg_pct": 54.6, "opp_efg_pct": 51.7, "tov_pct": 13.0, "opp_tov_pct": 14.8,
        "oreb_pct": 30.9, "opp_oreb_pct": 25.8, "fta_rate": 29.2, "opp_fta_rate": 31.9,
    },
    {
        "team_name": "Boston Celtics", "team_abbr": "BOS", "team_slug": "boston-celtics",
        "conference": "East", "primary_color": "#007A33", "secondary_color": "#BA9653",
        "wins": 56, "losses": 26, "adj_offensive_rating": 117.3, "adj_defensive_rating": 112.3,
        "adj_net_rating": 5.0, "ffi": 64.7, "pace": 98.3,
        "efg_pct": 55.3, "opp_efg_pct": 52.3, "tov_pct": 11.2, "opp_tov_pct": 11.4,
        "oreb_pct": 29.2, "opp_oreb_pct": 24.3, "fta_rate": 20.7, "opp_fta_rate": 24.5,
    },
    {
        "team_name": "New York Knicks", "team_abbr": "NYK", "team_slug": "new-york-knicks",
        "conference": "East", "primary_color": "#F58426", "secondary_color": "#006BB6",
        "wins": 53, "losses": 29, "adj_offensive_rating": 117.3, "adj_defensive_rating": 112.7,
        "adj_net_rating": 4.6, "ffi": 64.0, "pace": 99.7,
        "efg_pct": 55.7, "opp_efg_pct": 54.1, "tov_pct": 12.1, "opp_tov_pct": 13.1,
        "oreb_pct": 29.3, "opp_oreb_pct": 23.3, "fta_rate": 23.8, "opp_fta_rate": 26.5,
    },
    {
        "team_name": "Denver Nuggets", "team_abbr": "DEN", "team_slug": "denver-nuggets",
        "conference": "West", "primary_color": "#0E2240", "secondary_color": "#FEC524",
        "wins": 54, "losses": 28, "adj_offensive_rating": 120.0, "adj_defensive_rating": 116.8,
        "adj_net_rating": 3.2, "ffi": 58.1, "pace": 102.2,
        "efg_pct": 57.7, "opp_efg_pct": 54.3, "tov_pct": 11.5, "opp_tov_pct": 10.4,
        "oreb_pct": 23.6, "opp_oreb_pct": 24.7, "fta_rate": 29.4, "opp_fta_rate": 25.4,
    },
    {
        "team_name": "Houston Rockets", "team_abbr": "HOU", "team_slug": "houston-rockets",
        "conference": "West", "primary_color": "#CE1141", "secondary_color": "#C4CED4",
        "wins": 52, "losses": 30, "adj_offensive_rating": 115.2, "adj_defensive_rating": 112.6,
        "adj_net_rating": 2.6, "ffi": 55.0, "pace": 100.4,
        "efg_pct": 54.2, "opp_efg_pct": 53.0, "tov_pct": 13.3, "opp_tov_pct": 12.1,
        "oreb_pct": 34.8, "opp_oreb_pct": 25.5, "fta_rate": 26.0, "opp_fta_rate": 25.1,
    },
    {
        "team_name": "Cleveland Cavaliers", "team_abbr": "CLE", "team_slug": "cleveland-cavaliers",
        "conference": "East", "primary_color": "#860038", "secondary_color": "#FDBB30",
        "wins": 52, "losses": 30, "adj_offensive_rating": 116.8, "adj_defensive_rating": 114.4,
        "adj_net_rating": 2.4, "ffi": 62.2, "pace": 102.8,
        "efg_pct": 56.1, "opp_efg_pct": 54.3, "tov_pct": 12.2, "opp_tov_pct": 13.1,
        "oreb_pct": 26.9, "opp_oreb_pct": 25.6, "fta_rate": 26.5, "opp_fta_rate": 26.3,
    },
    {
        "team_name": "Minnesota Timberwolves", "team_abbr": "MIN", "team_slug": "minnesota-timberwolves",
        "conference": "West", "primary_color": "#0C2340", "secondary_color": "#236192",
        "wins": 49, "losses": 33, "adj_offensive_rating": 114.6, "adj_defensive_rating": 112.5,
        "adj_net_rating": 2.1, "ffi": 61.4, "pace": 103.4,
        "efg_pct": 55.9, "opp_efg_pct": 52.9, "tov_pct": 12.9, "opp_tov_pct": 13.0,
        "oreb_pct": 25.7, "opp_oreb_pct": 26.3, "fta_rate": 28.5, "opp_fta_rate": 28.2,
    },
    {
        "team_name": "Toronto Raptors", "team_abbr": "TOR", "team_slug": "toronto-raptors",
        "conference": "East", "primary_color": "#CE1141", "secondary_color": "#000000",
        "wins": 46, "losses": 36, "adj_offensive_rating": 113.6, "adj_defensive_rating": 112.4,
        "adj_net_rating": 1.2, "ffi": 62.1, "pace": 101.5,
        "efg_pct": 54.6, "opp_efg_pct": 54.0, "tov_pct": 12.2, "opp_tov_pct": 14.3,
        "oreb_pct": 25.5, "opp_oreb_pct": 26.0, "fta_rate": 26.5, "opp_fta_rate": 27.9,
    },
    {
        "team_name": "Charlotte Hornets", "team_abbr": "CHA", "team_slug": "charlotte-hornets",
        "conference": "East", "primary_color": "#1D1160", "secondary_color": "#00788C",
        "wins": 44, "losses": 38, "adj_offensive_rating": 115.3, "adj_defensive_rating": 114.2,
        "adj_net_rating": 1.1, "ffi": 50.3, "pace": 101.1,
        "efg_pct": 55.2, "opp_efg_pct": 54.0, "tov_pct": 13.5, "opp_tov_pct": 11.6,
        "oreb_pct": 30.5, "opp_oreb_pct": 23.4, "fta_rate": 24.4, "opp_fta_rate": 23.2,
    },
    {
        "team_name": "Miami Heat", "team_abbr": "MIA", "team_slug": "miami-heat",
        "conference": "East", "primary_color": "#98002E", "secondary_color": "#F9A01B",
        "wins": 43, "losses": 39, "adj_offensive_rating": 114.7, "adj_defensive_rating": 113.6,
        "adj_net_rating": 1.0, "ffi": 57.4, "pace": 106.1,
        "efg_pct": 54.2, "opp_efg_pct": 54.0, "tov_pct": 11.6, "opp_tov_pct": 12.8,
        "oreb_pct": 25.4, "opp_oreb_pct": 25.1, "fta_rate": 26.8, "opp_fta_rate": 24.0,
    },
    {
        "team_name": "Los Angeles Lakers", "team_abbr": "LAL", "team_slug": "los-angeles-lakers",
        "conference": "West", "primary_color": "#552583", "secondary_color": "#FDB927",
        "wins": 53, "losses": 29, "adj_offensive_rating": 116.3, "adj_defensive_rating": 115.5,
        "adj_net_rating": 0.8, "ffi": 57.9, "pace": 100.5,
        "efg_pct": 57.3, "opp_efg_pct": 55.5, "tov_pct": 13.2, "opp_tov_pct": 13.0,
        "oreb_pct": 23.9, "opp_oreb_pct": 25.7, "fta_rate": 32.0, "opp_fta_rate": 24.1,
    },
    {
        "team_name": "Atlanta Hawks", "team_abbr": "ATL", "team_slug": "atlanta-hawks",
        "conference": "East", "primary_color": "#E03A3E", "secondary_color": "#C1D32F",
        "wins": 46, "losses": 36, "adj_offensive_rating": 114.0, "adj_defensive_rating": 113.3,
        "adj_net_rating": 0.6, "ffi": 59.4, "pace": 104.6,
        "efg_pct": 55.4, "opp_efg_pct": 54.6, "tov_pct": 12.3, "opp_tov_pct": 13.9,
        "oreb_pct": 24.4, "opp_oreb_pct": 25.5, "fta_rate": 23.4, "opp_fta_rate": 26.0,
    },
    {
        "team_name": "Phoenix Suns", "team_abbr": "PHX", "team_slug": "phoenix-suns",
        "conference": "West", "primary_color": "#1D1160", "secondary_color": "#E56020",
        "wins": 45, "losses": 37, "adj_offensive_rating": 112.9, "adj_defensive_rating": 112.7,
        "adj_net_rating": 0.2, "ffi": 55.5, "pace": 100.5,
        "efg_pct": 53.7, "opp_efg_pct": 54.1, "tov_pct": 12.8, "opp_tov_pct": 14.5,
        "oreb_pct": 28.9, "opp_oreb_pct": 28.1, "fta_rate": 22.5, "opp_fta_rate": 27.6,
    },
    {
        "team_name": "LA Clippers", "team_abbr": "LAC", "team_slug": "la-clippers",
        "conference": "West", "primary_color": "#C8102E", "secondary_color": "#1D428A",
        "wins": 42, "losses": 40, "adj_offensive_rating": 115.2, "adj_defensive_rating": 115.1,
        "adj_net_rating": 0.1, "ffi": 53.2, "pace": 99.3,
        "efg_pct": 55.9, "opp_efg_pct": 54.5, "tov_pct": 13.2, "opp_tov_pct": 12.9,
        "oreb_pct": 23.7, "opp_oreb_pct": 27.1, "fta_rate": 29.5, "opp_fta_rate": 24.8,
    },
    {
        "team_name": "Philadelphia 76ers", "team_abbr": "PHI", "team_slug": "philadelphia-76ers",
        "conference": "East", "primary_color": "#006BB6", "secondary_color": "#ED174C",
        "wins": 45, "losses": 37, "adj_offensive_rating": 113.2, "adj_defensive_rating": 114.3,
        "adj_net_rating": -1.0, "ffi": 52.4, "pace": 103.0,
        "efg_pct": 53.0, "opp_efg_pct": 54.1, "tov_pct": 11.9, "opp_tov_pct": 13.3,
        "oreb_pct": 26.2, "opp_oreb_pct": 27.5, "fta_rate": 27.5, "opp_fta_rate": 27.0,
    },
    {
        "team_name": "Orlando Magic", "team_abbr": "ORL", "team_slug": "orlando-magic",
        "conference": "East", "primary_color": "#0077C0", "secondary_color": "#C4CED4",
        "wins": 45, "losses": 37, "adj_offensive_rating": 112.5, "adj_defensive_rating": 113.8,
        "adj_net_rating": -1.3, "ffi": 49.5, "pace": 103.6,
        "efg_pct": 53.1, "opp_efg_pct": 54.5, "tov_pct": 12.4, "opp_tov_pct": 13.1,
        "oreb_pct": 25.0, "opp_oreb_pct": 24.4, "fta_rate": 31.1, "opp_fta_rate": 28.5,
    },
    {
        "team_name": "Golden State Warriors", "team_abbr": "GSW", "team_slug": "golden-state-warriors",
        "conference": "West", "primary_color": "#1D428A", "secondary_color": "#FFC72C",
        "wins": 37, "losses": 45, "adj_offensive_rating": 112.8, "adj_defensive_rating": 114.5,
        "adj_net_rating": -1.6, "ffi": 48.4, "pace": 102.4,
        "efg_pct": 54.9, "opp_efg_pct": 55.3, "tov_pct": 13.8, "opp_tov_pct": 14.0,
        "oreb_pct": 25.8, "opp_oreb_pct": 27.1, "fta_rate": 23.8, "opp_fta_rate": 24.7,
    },
    {
        "team_name": "Portland Trail Blazers", "team_abbr": "POR", "team_slug": "portland-trail-blazers",
        "conference": "West", "primary_color": "#E03A3E", "secondary_color": "#000000",
        "wins": 42, "losses": 40, "adj_offensive_rating": 111.4, "adj_defensive_rating": 113.8,
        "adj_net_rating": -2.4, "ffi": 44.7, "pace": 104.4,
        "efg_pct": 53.4, "opp_efg_pct": 54.1, "tov_pct": 14.6, "opp_tov_pct": 13.5,
        "oreb_pct": 31.3, "opp_oreb_pct": 27.3, "fta_rate": 28.0, "opp_fta_rate": 27.2,
    },
    {
        "team_name": "New Orleans Pelicans", "team_abbr": "NOP", "team_slug": "new-orleans-pelicans",
        "conference": "West", "primary_color": "#0C2340", "secondary_color": "#C8102E",
        "wins": 26, "losses": 56, "adj_offensive_rating": 112.3, "adj_defensive_rating": 117.4,
        "adj_net_rating": -5.2, "ffi": 40.2, "pace": 103.7,
        "efg_pct": 52.7, "opp_efg_pct": 55.5, "tov_pct": 12.2, "opp_tov_pct": 12.4,
        "oreb_pct": 27.0, "opp_oreb_pct": 28.6, "fta_rate": 28.4, "opp_fta_rate": 25.8,
    },
    {
        "team_name": "Chicago Bulls", "team_abbr": "CHI", "team_slug": "chicago-bulls",
        "conference": "East", "primary_color": "#CE1141", "secondary_color": "#000000",
        "wins": 31, "losses": 51, "adj_offensive_rating": 111.5, "adj_defensive_rating": 117.2,
        "adj_net_rating": -5.7, "ffi": 36.0, "pace": 105.2,
        "efg_pct": 54.7, "opp_efg_pct": 55.3, "tov_pct": 13.3, "opp_tov_pct": 11.1,
        "oreb_pct": 23.1, "opp_oreb_pct": 24.5, "fta_rate": 24.6, "opp_fta_rate": 24.5,
    },
    {
        "team_name": "Dallas Mavericks", "team_abbr": "DAL", "team_slug": "dallas-mavericks",
        "conference": "West", "primary_color": "#00538C", "secondary_color": "#002B5E",
        "wins": 26, "losses": 56, "adj_offensive_rating": 109.3, "adj_defensive_rating": 115.8,
        "adj_net_rating": -6.4, "ffi": 37.0, "pace": 105.2,
        "efg_pct": 52.7, "opp_efg_pct": 54.6, "tov_pct": 12.6, "opp_tov_pct": 11.4,
        "oreb_pct": 23.2, "opp_oreb_pct": 25.9, "fta_rate": 28.7, "opp_fta_rate": 23.8,
    },
    {
        "team_name": "Memphis Grizzlies", "team_abbr": "MEM", "team_slug": "memphis-grizzlies",
        "conference": "West", "primary_color": "#5D76A9", "secondary_color": "#12173F",
        "wins": 25, "losses": 57, "adj_offensive_rating": 110.6, "adj_defensive_rating": 117.6,
        "adj_net_rating": -7.0, "ffi": 36.7, "pace": 104.5,
        "efg_pct": 53.3, "opp_efg_pct": 56.2, "tov_pct": 13.0, "opp_tov_pct": 13.3,
        "oreb_pct": 24.7, "opp_oreb_pct": 29.1, "fta_rate": 25.1, "opp_fta_rate": 26.2,
    },
    {
        "team_name": "Milwaukee Bucks", "team_abbr": "MIL", "team_slug": "milwaukee-bucks",
        "conference": "East", "primary_color": "#00471B", "secondary_color": "#EEE1C6",
        "wins": 32, "losses": 50, "adj_offensive_rating": 111.4, "adj_defensive_rating": 118.4,
        "adj_net_rating": -7.0, "ffi": 36.8, "pace": 100.2,
        "efg_pct": 56.5, "opp_efg_pct": 55.8, "tov_pct": 13.9, "opp_tov_pct": 11.7,
        "oreb_pct": 21.1, "opp_oreb_pct": 25.9, "fta_rate": 22.3, "opp_fta_rate": 27.4,
    },
    {
        "team_name": "Indiana Pacers", "team_abbr": "IND", "team_slug": "indiana-pacers",
        "conference": "East", "primary_color": "#002D62", "secondary_color": "#FDBB30",
        "wins": 19, "losses": 63, "adj_offensive_rating": 109.6, "adj_defensive_rating": 117.6,
        "adj_net_rating": -8.0, "ffi": 31.9, "pace": 103.6,
        "efg_pct": 53.3, "opp_efg_pct": 55.6, "tov_pct": 12.8, "opp_tov_pct": 11.7,
        "oreb_pct": 21.7, "opp_oreb_pct": 25.9, "fta_rate": 25.2, "opp_fta_rate": 28.2,
    },
    {
        "team_name": "Utah Jazz", "team_abbr": "UTA", "team_slug": "utah-jazz",
        "conference": "West", "primary_color": "#002B5C", "secondary_color": "#F9A01B",
        "wins": 22, "losses": 60, "adj_offensive_rating": 112.3, "adj_defensive_rating": 120.9,
        "adj_net_rating": -8.5, "ffi": 29.2, "pace": 105.7,
        "efg_pct": 53.6, "opp_efg_pct": 57.8, "tov_pct": 13.2, "opp_tov_pct": 12.4,
        "oreb_pct": 26.2, "opp_oreb_pct": 27.1, "fta_rate": 27.7, "opp_fta_rate": 29.2,
    },
    {
        "team_name": "Sacramento Kings", "team_abbr": "SAC", "team_slug": "sacramento-kings",
        "conference": "West", "primary_color": "#5A2D81", "secondary_color": "#63727A",
        "wins": 22, "losses": 60, "adj_offensive_rating": 110.0, "adj_defensive_rating": 119.6,
        "adj_net_rating": -9.6, "ffi": 29.0, "pace": 101.9,
        "efg_pct": 52.5, "opp_efg_pct": 57.2, "tov_pct": 12.6, "opp_tov_pct": 12.3,
        "oreb_pct": 25.9, "opp_oreb_pct": 26.5, "fta_rate": 25.6, "opp_fta_rate": 27.4,
    },
    {
        "team_name": "Brooklyn Nets", "team_abbr": "BKN", "team_slug": "brooklyn-nets",
        "conference": "East", "primary_color": "#000000", "secondary_color": "#FFFFFF",
        "wins": 20, "losses": 62, "adj_offensive_rating": 107.1, "adj_defensive_rating": 117.8,
        "adj_net_rating": -10.8, "ffi": 22.6, "pace": 100.1,
        "efg_pct": 52.0, "opp_efg_pct": 57.1, "tov_pct": 14.3, "opp_tov_pct": 13.2,
        "oreb_pct": 23.6, "opp_oreb_pct": 26.0, "fta_rate": 27.2, "opp_fta_rate": 29.0,
    },
    {
        "team_name": "Washington Wizards", "team_abbr": "WAS", "team_slug": "washington-wizards",
        "conference": "East", "primary_color": "#002B5C", "secondary_color": "#E31837",
        "wins": 17, "losses": 65, "adj_offensive_rating": 109.5, "adj_defensive_rating": 121.3,
        "adj_net_rating": -11.8, "ffi": 24.2, "pace": 104.4,
        "efg_pct": 53.5, "opp_efg_pct": 56.3, "tov_pct": 13.6, "opp_tov_pct": 11.7,
        "oreb_pct": 24.1, "opp_oreb_pct": 29.8, "fta_rate": 23.5, "opp_fta_rate": 29.2,
    },
]


class Command(BaseCommand):
    help = "Seed TeamSeasonOutlook rows with 2025-26 final season data for all 30 NBA teams."

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            default=False,
            help="Skip teams that already have a TeamSeasonOutlook row (preserves editorial content).",
        )

    def handle(self, *args, **options):
        skip_existing = options["skip_existing"]
        created = updated = skipped = 0

        for data in TEAM_DATA:
            slug = data["team_slug"]
            exists = TeamSeasonOutlook.objects.filter(team_slug=slug).exists()

            if exists and skip_existing:
                self.stdout.write(f"  skip  {data['team_abbr']} (already exists)")
                skipped += 1
                continue

            _, was_created = TeamSeasonOutlook.objects.update_or_create(
                team_slug=slug,
                defaults=data,
            )
            if was_created:
                self.stdout.write(self.style.SUCCESS(f"  create {data['team_abbr']}"))
                created += 1
            else:
                self.stdout.write(f"  update {data['team_abbr']}")
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone — created={created}, updated={updated}, skipped={skipped}"
            )
        )
