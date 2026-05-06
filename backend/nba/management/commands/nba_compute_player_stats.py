"""
nba_compute_player_stats — roll up NBAPlayerGameStats into NBAPlayerSeasonStats.

Aggregates per-game box scores into per-game averages for each player/team/season
combination.  Safe to re-run (uses update_or_create).

Usage:
    python manage.py nba_compute_player_stats --season 2026
"""

import logging
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nba.models import (
    NBASeason,
    NBAPlayer,
    NBATeam,
    NBAPlayerGameStats,
    NBAPlayerSeasonStats,
)

logger = logging.getLogger(__name__)


def _safe_pct(made, attempted):
    """Return made/attempted as float, or None if attempted == 0."""
    if attempted and attempted > 0:
        return made / attempted
    return None


class Command(BaseCommand):
    help = "Aggregate NBAPlayerGameStats into per-season averages (NBAPlayerSeasonStats)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season", type=int, required=True,
            help="Ending season year (e.g., 2026)",
        )
        parser.add_argument(
            "--season-type", default="regular", choices=["regular", "playoffs"],
            help="Which game type to aggregate (default: regular)",
        )

    def handle(self, *args, **options):
        season_year: int = options["season"]
        season_type: str = options["season_type"]

        try:
            season = NBASeason.objects.get(year=season_year)
        except NBASeason.DoesNotExist:
            raise CommandError(
                f"Season {season_year} not found. Run nba_sync_teams first."
            )

        game_filter: dict = {"game__season": season}
        if season_type == "playoffs":
            game_filter["game__season_type"] = "playoffs"
        else:
            game_filter["game__counts_toward_regular_season"] = True

        rows = (
            NBAPlayerGameStats.objects
            .filter(**game_filter)
            .select_related("player", "team")
        )

        total_game_rows = rows.count()
        if total_game_rows == 0:
            self.stdout.write(
                self.style.WARNING(
                    f"No NBAPlayerGameStats found for {season.display_name} ({season_type}). "
                    "Run: python manage.py nba_sync_team_logs --season "
                    f"{season_year}"
                )
            )
            return

        self.stdout.write(
            f"Aggregating {total_game_rows} game rows for {season.display_name}..."
        )

        # Group by (player_id, team_id)
        # A player who was traded will have two groups — one per team.
        groups: dict[tuple[int, int | None], list[NBAPlayerGameStats]] = defaultdict(list)
        player_map: dict[int, NBAPlayer] = {}
        team_map: dict[int | None, NBATeam | None] = {None: None}

        for row in rows:
            pid = row.player_id
            tid = row.team_id if row.team else None
            groups[(pid, tid)].append(row)
            player_map[pid] = row.player
            if tid and tid not in team_map:
                team_map[tid] = row.team

        written = 0
        with transaction.atomic():
            for (pid, tid), game_rows in groups.items():
                player = player_map[pid]
                team = team_map.get(tid)
                gp = len(game_rows)

                # Accumulators
                total_seconds = 0
                sec_count = 0
                pts = reb = ast = stl = blk = tov = pm = 0
                fgm = fga = fg3m = fg3a = ftm = fta = 0

                for gr in game_rows:
                    if gr.seconds_played is not None:
                        total_seconds += gr.seconds_played
                        sec_count += 1
                    pts += gr.pts or 0
                    reb += gr.reb or 0
                    ast += gr.ast or 0
                    stl += gr.stl or 0
                    blk += gr.blk or 0
                    tov += gr.tov or 0
                    pm += gr.plus_minus or 0
                    fgm += gr.fgm or 0
                    fga += gr.fga or 0
                    fg3m += gr.fg3m or 0
                    fg3a += gr.fg3a or 0
                    ftm += gr.ftm or 0
                    fta += gr.fta or 0

                mpg = (total_seconds / sec_count / 60.0) if sec_count > 0 else None

                NBAPlayerSeasonStats.objects.update_or_create(
                    player=player,
                    season=season,
                    team=team,
                    season_type=season_type,
                    defaults={
                        "gp": gp,
                        "mpg": mpg,
                        "pts": round(pts / gp, 1),
                        "reb": round(reb / gp, 1),
                        "ast": round(ast / gp, 1),
                        "stl": round(stl / gp, 1),
                        "blk": round(blk / gp, 1),
                        "tov": round(tov / gp, 1),
                        "plus_minus": round(pm / gp, 1),
                        "fg_pct": _safe_pct(fgm, fga),
                        "fg3_pct": _safe_pct(fg3m, fg3a),
                        "ft_pct": _safe_pct(ftm, fta),
                        "fga_pg": round(fga / gp, 1),
                        "fg3a_pg": round(fg3a / gp, 1),
                    },
                )
                written += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {written} player-team-season rows written for "
                f"{season.display_name}."
            )
        )
