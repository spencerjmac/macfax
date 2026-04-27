"""
Aggregate PlayerGameStats → PlayerSeasonStats for each player-team-season combo.

Usage:
    python manage.py compute_ncaa_player_season_stats --season 2025
"""
from django.core.management.base import BaseCommand
from django.db.models import Sum, Count, F, FloatField, ExpressionWrapper, Q
from django.db import transaction

from ncaa.models import Game, Player, PlayerGameStats, PlayerSeasonStats, Season, Team


class Command(BaseCommand):
    help = "Aggregate NCAA player game stats into per-season averages."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=int,
            default=2025,
            help="Season year (ending year, e.g. 2025 for 2024-25)",
        )

    def handle(self, *args, **options):
        season_year = options["season"]

        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            self.stderr.write(f"Season {season_year} not found in database.")
            return

        # All games in this season that have player stats ingested
        game_ids = set(
            Game.objects.filter(season_year=season_year)
            .values_list("id", flat=True)
        )

        if not game_ids:
            self.stderr.write(f"No games found for season {season_year}.")
            return

        # Aggregate by player + team
        from django.db.models import Avg
        rows = (
            PlayerGameStats.objects.filter(game_id__in=game_ids, did_not_play=False)
            .values("player_id", "team_id")
            .annotate(
                gp=Count("id"),
                total_minutes=Sum("minutes"),
                total_pts=Sum("points"),
                total_reb=Sum("rebounds"),
                total_oreb=Sum("offensive_rebounds"),
                total_dreb=Sum("defensive_rebounds"),
                total_ast=Sum("assists"),
                total_stl=Sum("steals"),
                total_blk=Sum("blocks"),
                total_tov=Sum("turnovers"),
                total_pf=Sum("fouls"),
                total_fgm=Sum("fg_made"),
                total_fga=Sum("fg_attempted"),
                total_fg3m=Sum("fg3_made"),
                total_fg3a=Sum("fg3_attempted"),
                total_ftm=Sum("ft_made"),
                total_fta=Sum("ft_attempted"),
            )
        )

        def safe_pct(made, attempted):
            return round(made / attempted, 4) if attempted else None

        def avg(total, gp):
            return round(total / gp, 2) if gp else 0.0

        def safe_div(a, b):
            return round(a / b, 2) if b else None

        created_count = 0
        updated_count = 0

        with transaction.atomic():
            PlayerSeasonStats.objects.filter(season=season).delete()

            for row in rows:
                gp = row["gp"]
                fgm = row["total_fgm"] or 0
                fga = row["total_fga"] or 0
                fg3m = row["total_fg3m"] or 0
                fg3a = row["total_fg3a"] or 0
                ftm = row["total_ftm"] or 0
                fta = row["total_fta"] or 0
                pts = row["total_pts"] or 0
                ast = row["total_ast"] or 0
                tov = row["total_tov"] or 0

                # eFG% = (FGM + 0.5*FG3M) / FGA
                efg_pct = round((fgm + 0.5 * fg3m) / fga, 4) if fga else None
                # TS% = PTS / (2 * (FGA + 0.44*FTA))
                tsa = 2 * (fga + 0.44 * fta)
                ts_pct = round(pts / tsa, 4) if tsa > 0 else None
                # AST/TO
                ast_to = safe_div(ast, tov)

                team = Team.objects.filter(pk=row["team_id"]).first() if row["team_id"] else None

                PlayerSeasonStats.objects.update_or_create(
                    player_id=row["player_id"],
                    season=season,
                    team=team,
                    defaults={
                        "gp": gp,
                        "mpg": avg(row["total_minutes"] or 0, gp),
                        "pts": avg(pts, gp),
                        "reb": avg(row["total_reb"] or 0, gp),
                        "ast": avg(ast, gp),
                        "stl": avg(row["total_stl"] or 0, gp),
                        "blk": avg(row["total_blk"] or 0, gp),
                        "tov": avg(tov, gp),
                        "pf": avg(row["total_pf"] or 0, gp),
                        "fg_pct": safe_pct(fgm, fga),
                        "fg3_pct": safe_pct(fg3m, fg3a),
                        "ft_pct": safe_pct(ftm, fta),
                        "fga_pg": avg(fga, gp),
                        "fg3a_pg": avg(fg3a, gp),
                        "ftm_pg": avg(ftm, gp),
                        "fta_pg": avg(fta, gp),
                        "oreb_pg": avg(row["total_oreb"] or 0, gp),
                        "dreb_pg": avg(row["total_dreb"] or 0, gp),
                        "efg_pct": efg_pct,
                        "ts_pct": ts_pct,
                        "ast_to": ast_to,
                    },
                )
                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Season {season_year}: wrote {created_count} player-season stat rows."
            )
        )
