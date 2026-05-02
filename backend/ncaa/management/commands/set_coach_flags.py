"""
Management command: set_coach_flags

Manually set is_first_year_coach on TeamSeasonStats rows for a season.
This is an intentionally simple tool — a human reviews new head coaches
each offseason and runs this once.

Usage:
    python manage.py set_coach_flags --season 2027 --list
    python manage.py set_coach_flags --season 2027 --team-id 123 --is-first-year true
    python manage.py set_coach_flags --season 2027 --clear
"""

from django.core.management.base import BaseCommand, CommandError

from ncaa.models import Season, Team, TeamSeasonStats


class Command(BaseCommand):
    help = "Manually set is_first_year_coach flags on TeamSeasonStats for a season."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True, metavar="YEAR")
        parser.add_argument("--list", action="store_true",
                            help="List all teams and their current is_first_year_coach value.")
        parser.add_argument("--team-id", type=int, default=None, metavar="ID",
                            help="Team ID to update (use with --is-first-year).")
        parser.add_argument("--is-first-year", type=str, default=None, metavar="true|false",
                            help="Set is_first_year_coach to true or false for --team-id.")
        parser.add_argument("--clear", action="store_true",
                            help="Reset all is_first_year_coach flags to False for the season.")

    def handle(self, *args, **options):
        season_year = options["season"]
        do_list     = options["list"]
        team_id     = options["team_id"]
        is_first_year_str = options["is_first_year"]
        do_clear    = options["clear"]

        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            raise CommandError(f"Season {season_year} not found.")

        if do_list:
            rows = TeamSeasonStats.objects.filter(season=season).select_related("team").order_by("team__name")
            self.stdout.write(f"\nis_first_year_coach flags — season {season_year}")
            self.stdout.write(f"{'Team':<35}  is_first_year_coach")
            self.stdout.write("-" * 55)
            for row in rows:
                flag = "True" if row.is_first_year_coach else "False"
                style = self.style.SUCCESS if row.is_first_year_coach else str
                self.stdout.write(style(f"{row.team.name:<35}  {flag}"))
            self.stdout.write("")
            return

        if do_clear:
            count = TeamSeasonStats.objects.filter(season=season).update(is_first_year_coach=False)
            self.stdout.write(self.style.SUCCESS(f"Cleared is_first_year_coach for {count} teams in {season_year}."))
            return

        if team_id is not None and is_first_year_str is not None:
            # Validate boolean string
            if is_first_year_str.lower() not in ("true", "false"):
                raise CommandError("--is-first-year must be 'true' or 'false'.")
            flag_value = is_first_year_str.lower() == "true"

            try:
                team = Team.objects.get(id=team_id)
            except Team.DoesNotExist:
                raise CommandError(f"Team with id={team_id} not found.")

            try:
                stats = TeamSeasonStats.objects.get(team=team, season=season)
            except TeamSeasonStats.DoesNotExist:
                raise CommandError(
                    f"No TeamSeasonStats found for team {team.name} (id={team_id}) in season {season_year}."
                )

            stats.is_first_year_coach = flag_value
            stats.save(update_fields=["is_first_year_coach"])
            self.stdout.write(self.style.SUCCESS(
                f"Set {team.name} (id={team_id}) is_first_year_coach={flag_value} for season {season_year}."
            ))
            return

        self.stdout.write("Specify one of: --list, --clear, or --team-id + --is-first-year.")
        self.stdout.write("Use --help for usage details.")
