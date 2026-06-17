"""
nba_sync_playoff_results — fill conference_seed + playoff_finish on
NBATeamSeasonRatings (season_type='regular').

conference_seed is derived from compute_standings() (pure computation from
NBAGame results — no ingestion needed). playoff_finish comes from a small
hardcoded table of public-record playoff results for 2016-2025 (16 playoff
teams/season: champion, runner-up, 2 conference-finals losers, 4 conference-
semifinals losers, 8 first-round losers). Teams not in the table for a given
season missed the playoffs and keep playoff_finish=None.

Usage:
    uv run python manage.py nba_sync_playoff_results
    uv run python manage.py nba_sync_playoff_results --season 2025
"""

from django.core.management.base import BaseCommand, CommandError

from nba.analytics.standings import compute_standings
from nba.models import NBASeason, NBATeam, NBATeamSeasonRatings

# Public-record playoff results, by ending season year (e.g. 2016 = the
# 2015-16 season's playoffs, decided in June 2016).
PLAYOFF_RESULTS: dict[int, dict[str, list[str]]] = {
    2016: {
        "Champion": ["CLE"],
        "Runner-Up": ["GSW"],
        "Conf Finals": ["TOR", "OKC"],
        "Conf Semis": ["ATL", "MIA", "POR", "SAS"],
        "Round 1": ["DET", "IND", "CHA", "BOS", "HOU", "MEM", "DAL", "LAC"],
    },
    2017: {
        "Champion": ["GSW"],
        "Runner-Up": ["CLE"],
        "Conf Finals": ["BOS", "SAS"],
        "Conf Semis": ["WAS", "TOR", "UTA", "HOU"],
        "Round 1": ["CHI", "IND", "MIL", "ATL", "POR", "MEM", "OKC", "LAC"],
    },
    2018: {
        "Champion": ["GSW"],
        "Runner-Up": ["CLE"],
        "Conf Finals": ["BOS", "HOU"],
        "Conf Semis": ["TOR", "PHI", "UTA", "NOP"],
        "Round 1": ["WAS", "MIL", "IND", "MIA", "MIN", "SAS", "POR", "OKC"],
    },
    2019: {
        "Champion": ["TOR"],
        "Runner-Up": ["GSW"],
        "Conf Finals": ["MIL", "POR"],
        "Conf Semis": ["BOS", "PHI", "HOU", "DEN"],
        "Round 1": ["DET", "ORL", "BKN", "IND", "LAC", "SAS", "OKC", "UTA"],
    },
    2020: {
        "Champion": ["LAL"],
        "Runner-Up": ["MIA"],
        "Conf Finals": ["BOS", "DEN"],
        "Conf Semis": ["MIL", "TOR", "HOU", "LAC"],
        "Round 1": ["ORL", "BKN", "PHI", "IND", "POR", "DAL", "UTA", "OKC"],
    },
    2021: {
        "Champion": ["MIL"],
        "Runner-Up": ["PHX"],
        "Conf Finals": ["ATL", "LAC"],
        "Conf Semis": ["PHI", "BKN", "UTA", "DEN"],
        "Round 1": ["WAS", "BOS", "MIA", "NYK", "MEM", "LAL", "POR", "DAL"],
    },
    2022: {
        "Champion": ["GSW"],
        "Runner-Up": ["BOS"],
        "Conf Finals": ["MIA", "DAL"],
        "Conf Semis": ["PHI", "MIL", "PHX", "MEM"],
        "Round 1": ["ATL", "BKN", "CHI", "TOR", "NOP", "MIN", "DEN", "UTA"],
    },
    2023: {
        "Champion": ["DEN"],
        "Runner-Up": ["MIA"],
        "Conf Finals": ["BOS", "LAL"],
        "Conf Semis": ["NYK", "PHI", "PHX", "GSW"],
        "Round 1": ["MIL", "ATL", "BKN", "CLE", "MIN", "MEM", "SAC", "LAC"],
    },
    2024: {
        "Champion": ["BOS"],
        "Runner-Up": ["DAL"],
        "Conf Finals": ["IND", "MIN"],
        "Conf Semis": ["CLE", "NYK", "OKC", "DEN"],
        "Round 1": ["MIA", "PHI", "MIL", "ORL", "NOP", "LAL", "PHX", "LAC"],
    },
    2025: {
        "Champion": ["OKC"],
        "Runner-Up": ["IND"],
        "Conf Finals": ["NYK", "MIN"],
        "Conf Semis": ["CLE", "BOS", "DEN", "GSW"],
        "Round 1": ["MIA", "ORL", "DET", "MIL", "MEM", "HOU", "LAL", "LAC"],
    },
}


class Command(BaseCommand):
    help = "Fill conference_seed (from standings) and playoff_finish (hardcoded 2016-2025) on NBATeamSeasonRatings."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season", type=int, default=None,
            help="Single season year. Default: all seasons 2016-2025.",
        )

    def handle(self, *args, **options):
        season_year = options["season"]
        years = [season_year] if season_year else sorted(PLAYOFF_RESULTS.keys())

        teams_by_abbr = {t.abbreviation: t for t in NBATeam.objects.all()}

        for year in years:
            try:
                season = NBASeason.objects.get(year=year)
            except NBASeason.DoesNotExist:
                raise CommandError(f"NBASeason year={year} not found.")

            ratings_by_team = {
                r.team_id: r
                for r in NBATeamSeasonRatings.objects.filter(
                    season=season, season_type="regular",
                )
            }

            # ── conference_seed from standings ──────────────────────────────
            standings = compute_standings(year, season_type="regular")
            for row in standings:
                rating = ratings_by_team.get(row["team_id"])
                if rating is None:
                    continue
                rating.conference_seed = row["conference_rank"]
                rating.save(update_fields=["conference_seed"])

            # ── playoff_finish from hardcoded table ─────────────────────────
            results = PLAYOFF_RESULTS.get(year, {})
            updated = 0
            for finish, abbrs in results.items():
                for abbr in abbrs:
                    team = teams_by_abbr.get(abbr)
                    if team is None:
                        self.stdout.write(self.style.WARNING(
                            f"  {year}: unknown team abbreviation {abbr!r}"
                        ))
                        continue
                    rating = ratings_by_team.get(team.id)
                    if rating is None:
                        self.stdout.write(self.style.WARNING(
                            f"  {year}: no NBATeamSeasonRatings for {abbr}"
                        ))
                        continue
                    rating.playoff_finish = finish
                    rating.save(update_fields=["playoff_finish"])
                    updated += 1

            self.stdout.write(self.style.SUCCESS(
                f"{year}: seeded {len(standings)} teams, "
                f"set playoff_finish for {updated}/16 playoff teams"
            ))
