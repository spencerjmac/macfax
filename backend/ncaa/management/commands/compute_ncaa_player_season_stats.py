"""
Aggregate PlayerGameStats → PlayerSeasonStats for each player-team-season combo.

Usage:
    python manage.py compute_ncaa_player_season_stats --season 2025
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Sum, Count, F, FloatField, ExpressionWrapper, Q
from django.db import transaction

from ncaa.models import Game, Player, PlayerGameStats, PlayerSeasonStats, Season, Team, TeamGameStats


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

        # Build team game stats lookup: (game_id, team_id) -> stats dict.
        # Used to compute minutes-adjusted rate stats (USG%, ORB%, etc.).
        tgs_lookup = {}
        for tgs in (
            TeamGameStats.objects
            .filter(game_id__in=game_ids)
            .values(
                "game_id", "team_id", "opponent_id",
                "fga", "fta", "fg3a", "tov", "oreb", "dreb",
                "minutes", "game__went_to_ot",
            )
        ):
            gm = tgs["minutes"] if tgs["minutes"] else (45 if tgs["game__went_to_ot"] else 40)
            tgs_lookup[(tgs["game_id"], tgs["team_id"])] = {
                "fga": tgs["fga"],
                "fta": tgs["fta"],
                "fg3a": tgs["fg3a"],
                "tov": tgs["tov"],
                "oreb": tgs["oreb"],
                "dreb": tgs["dreb"],
                "game_minutes": gm,
                "opponent_id": tgs["opponent_id"],
            }

        # For each (player_id, team_id), accumulate team and opponent totals
        # across only the games that player appeared in.
        acc = defaultdict(lambda: {
            "sum_tm_fga": 0, "sum_tm_fta": 0, "sum_tm_fg3a": 0, "sum_tm_tov": 0,
            "sum_tm_oreb": 0, "sum_tm_dreb": 0, "sum_tm_mp": 0,
            "sum_opp_oreb": 0, "sum_opp_dreb": 0, "sum_opp_fga": 0,
            "sum_opp_fg3a": 0, "sum_opp_tov": 0, "sum_opp_fta": 0,
        })

        for pg in (
            PlayerGameStats.objects
            .filter(game_id__in=game_ids, did_not_play=False, team_id__isnull=False)
            .values("player_id", "team_id", "game_id")
        ):
            team_key = (pg["game_id"], pg["team_id"])
            tgs = tgs_lookup.get(team_key)
            if not tgs:
                continue
            opp_tgs = tgs_lookup.get((pg["game_id"], tgs["opponent_id"]))

            a = acc[(pg["player_id"], pg["team_id"])]
            a["sum_tm_fga"]  += tgs["fga"]
            a["sum_tm_fta"]  += tgs["fta"]
            a["sum_tm_fg3a"] += tgs["fg3a"]
            a["sum_tm_tov"]  += tgs["tov"]
            a["sum_tm_oreb"] += tgs["oreb"]
            a["sum_tm_dreb"] += tgs["dreb"]
            a["sum_tm_mp"]   += 5 * tgs["game_minutes"]

            if opp_tgs:
                a["sum_opp_oreb"]  += opp_tgs["oreb"]
                a["sum_opp_dreb"]  += opp_tgs["dreb"]
                a["sum_opp_fga"]   += opp_tgs["fga"]
                a["sum_opp_fg3a"]  += opp_tgs["fg3a"]
                a["sum_opp_tov"]   += opp_tgs["tov"]
                a["sum_opp_fta"]   += opp_tgs["fta"]

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

                # ── Rate stats (minutes-adjusted where required) ──────────────
                sum_oreb = row["total_oreb"] or 0
                sum_dreb = row["total_dreb"] or 0
                sum_stl  = row["total_stl"] or 0
                sum_blk  = row["total_blk"] or 0
                sum_mp   = row["total_minutes"] or 0

                a = acc.get((row["player_id"], row["team_id"]), {})
                sum_tm_fga   = a.get("sum_tm_fga", 0)
                sum_tm_fta   = a.get("sum_tm_fta", 0)
                sum_tm_fg3a  = a.get("sum_tm_fg3a", 0)
                sum_tm_tov   = a.get("sum_tm_tov", 0)
                sum_tm_oreb  = a.get("sum_tm_oreb", 0)
                sum_tm_dreb  = a.get("sum_tm_dreb", 0)
                sum_tm_mp    = a.get("sum_tm_mp", 0)
                sum_opp_oreb = a.get("sum_opp_oreb", 0)
                sum_opp_dreb = a.get("sum_opp_dreb", 0)
                sum_opp_fga  = a.get("sum_opp_fga", 0)
                sum_opp_fg3a = a.get("sum_opp_fg3a", 0)
                sum_opp_tov  = a.get("sum_opp_tov", 0)
                sum_opp_fta  = a.get("sum_opp_fta", 0)

                if gp < 3 or not sum_tm_mp or not sum_mp:
                    usg_pct = tov_pct = orb_pct = drb_pct = None
                    fta_rate = fg3_rate = blk_pct = stl_pct = ast_usg = None
                else:
                    # USG% (minutes-adjusted)
                    usg_num = (fga + 0.44 * fta + tov) * (sum_tm_mp / 5)
                    usg_den = sum_mp * (sum_tm_fga + 0.44 * sum_tm_fta + sum_tm_tov)
                    usg_pct = round(100 * usg_num / usg_den, 2) if usg_den else None

                    # TOV% (possession-based denominator, no minutes adjustment)
                    tov_den = fga + 0.44 * fta + tov
                    tov_pct = round(100 * tov / tov_den, 2) if tov_den else None

                    # ORB% (minutes-adjusted)
                    orb_den = sum_mp * (sum_tm_oreb + sum_opp_dreb)
                    orb_pct = round(100 * sum_oreb * (sum_tm_mp / 5) / orb_den, 2) if orb_den else None

                    # DRB% (minutes-adjusted)
                    drb_den = sum_mp * (sum_tm_dreb + sum_opp_oreb)
                    drb_pct = round(100 * sum_dreb * (sum_tm_mp / 5) / drb_den, 2) if drb_den else None

                    # FTA rate (no minutes adjustment)
                    fta_rate = round(fta / fga, 4) if fga else None

                    # 3PA rate (no minutes adjustment)
                    fg3_rate = round(fg3a / fga, 4) if fga else None

                    # BLK% (minutes-adjusted, vs opp 2-point attempts only)
                    opp_fg2a = sum_opp_fga - sum_opp_fg3a
                    blk_den  = sum_mp * opp_fg2a
                    blk_pct  = round(100 * sum_blk * (sum_tm_mp / 5) / blk_den, 2) if blk_den else None

                    # STL% (minutes-adjusted, vs opp possessions)
                    opp_poss = sum_opp_fga - sum_opp_oreb + sum_opp_tov + 0.44 * sum_opp_fta
                    stl_den  = sum_mp * opp_poss
                    stl_pct  = round(100 * sum_stl * (sum_tm_mp / 5) / stl_den, 2) if stl_den else None

                    # AST/USG
                    ast_usg = round((ast / gp) / usg_pct, 4) if (usg_pct and usg_pct > 0) else None

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
                        "usg_pct": usg_pct,
                        "tov_pct": tov_pct,
                        "orb_pct": orb_pct,
                        "drb_pct": drb_pct,
                        "fta_rate": fta_rate,
                        "fg3_rate": fg3_rate,
                        "blk_pct": blk_pct,
                        "stl_pct": stl_pct,
                        "ast_usg": ast_usg,
                    },
                )
                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Season {season_year}: wrote {created_count} player-season stat rows."
            )
        )
