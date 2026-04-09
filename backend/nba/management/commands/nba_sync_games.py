"""
nba_sync_games — ingest a season's game log from NBA.com.

Uses LeagueGameLog which returns one row per team per game. The command pairs
rows by game_id to reconstruct each full game, then writes:
  - NBAGame (metadata, scores, rest context)
  - NBATeamGameStats (box score stats + possessions + raw ratings)

This single sync gives us everything needed for nba_compute_ratings.
No separate BoxScoreTraditionalV3 call is needed for team-level four factors.

Usage:
    uv run python manage.py nba_sync_games --season 2026
    uv run python manage.py nba_sync_games --season 2026 --season-type playoffs
    uv run python manage.py nba_sync_games --season 2026 --dry-run
"""

import logging
from collections import defaultdict
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nba.models import NBASeason, NBATeam, NBAGame, NBATeamGameStats
from nba.providers.nba_api_provider import NBAApiProvider

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Sync NBA game log for a given season from NBA.com. Idempotent."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season", type=int, required=True,
            help="Ending season year (e.g., 2026 for the 2025-26 season)",
        )
        parser.add_argument(
            "--season-type", default="Regular Season",
            choices=["Regular Season", "Pre Season", "Playoffs", "PlayIn"],
        )
        parser.add_argument(
            "--sleep", type=float, default=0.6,
            help="Seconds to sleep between API calls",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        season_year: int = options["season"]
        season_type_str: str = options["season_type"]
        dry_run: bool = options["dry_run"]

        # ── Ensure season record exists ─────────────────────────────────────
        season, created = NBASeason.objects.get_or_create(
            year=season_year,
            defaults={
                "display_name": f"{season_year - 1}-{str(season_year)[2:]}",
                "is_current": True,
            },
        )
        if created:
            self.stdout.write(f"Created NBASeason: {season.display_name}")

        # ── Build team lookup by nba_team_id ─────────────────────────────────
        team_map: dict[int, NBATeam] = {
            t.nba_team_id: t for t in NBATeam.objects.all()
        }
        if not team_map:
            raise CommandError(
                "No NBA teams found in DB. Run 'python manage.py nba_sync_teams' first."
            )

        # ── Fetch from NBA.com ────────────────────────────────────────────────
        provider = NBAApiProvider(sleep_seconds=options["sleep"])
        self.stdout.write(
            f"Fetching {season_type_str} game log for {season.display_name} …"
        )
        rows = provider.get_league_game_log(season_year, season_type=season_type_str)
        self.stdout.write(f"Received {len(rows)} team-game rows from LeagueGameLog.")

        # ── Group rows by game_id ─────────────────────────────────────────────
        by_game: dict[str, list] = defaultdict(list)
        for row in rows:
            by_game[row.game_id].append(row)

        # ── Process each game ─────────────────────────────────────────────────
        games_payload = []  # list of (home_row, away_row, nba_game_kwargs)
        skipped = 0

        for game_id, game_rows in by_game.items():
            # Only process completed pairs (2 rows = both teams present)
            home_rows = [r for r in game_rows if r.is_home]
            away_rows = [r for r in game_rows if not r.is_home]

            if len(home_rows) != 1 or len(away_rows) != 1:
                logger.warning(
                    "game_id=%s has unexpected row count (home=%d, away=%d) — skipping",
                    game_id, len(home_rows), len(away_rows),
                )
                skipped += 1
                continue

            home_row = home_rows[0]
            away_row = away_rows[0]

            home_team = team_map.get(home_row.team_id)
            away_team = team_map.get(away_row.team_id)
            if not home_team or not away_team:
                logger.warning(
                    "game_id=%s unknown team(s) home=%s away=%s — skipping",
                    game_id, home_row.team_id, away_row.team_id,
                )
                skipped += 1
                continue

            try:
                game_date = date.fromisoformat(home_row.date) if home_row.date else None
            except ValueError:
                logger.warning("game_id=%s bad date %r — skipping", game_id, home_row.date)
                skipped += 1
                continue

            status = "Final" if home_row.is_final else "Scheduled"
            games_payload.append((home_row, away_row, home_team, away_team, game_date, status))

        self.stdout.write(
            f"Parsed {len(games_payload)} valid paired games "
            f"(skipped {skipped} incomplete)."
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no DB writes."))
            return

        # ── Pass 1: upsert NBAGame + NBATeamGameStats ──────────────────────
        created_games = updated_games = 0

        with transaction.atomic():
            for (home_row, away_row, home_team, away_team, game_date, status) in games_payload:
                season_type_key = home_row.season_type  # "regular", "playoffs", etc.

                game_defaults = {
                    "season": season,
                    "date": game_date,
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_score": home_row.pts,
                    "away_score": away_row.pts,
                    "season_type": season_type_key,
                    "status": status,
                    # rest fields filled in Pass 2
                }

                game_obj, is_new = NBAGame.objects.update_or_create(
                    game_id=home_row.game_id,
                    defaults=game_defaults,
                )
                if is_new:
                    created_games += 1
                else:
                    updated_games += 1

                # Upsert team game stats for each side
                for row, is_home, opp_pts in [
                    (home_row, True, away_row.pts),
                    (away_row, False, home_row.pts),
                ]:
                    team = home_team if is_home else away_team
                    poss = _compute_poss(row)
                    raw_ortg = raw_drtg = None

                    # raw_drtg for this team = opponent's raw_ortg (computed from opp row)
                    opp_row = away_row if is_home else home_row
                    opp_poss = _compute_poss(opp_row)

                    if poss and poss > 0 and row.pts is not None:
                        raw_ortg = 100.0 * row.pts / poss
                    if opp_poss and opp_poss > 0 and opp_pts is not None:
                        raw_drtg = 100.0 * opp_pts / opp_poss

                    NBATeamGameStats.objects.update_or_create(
                        game=game_obj,
                        team=team,
                        defaults={
                            "is_home": is_home,
                            "pts": row.pts,
                            "opp_pts": opp_pts,
                            "fgm": row.fgm,
                            "fga": row.fga,
                            "fg3m": row.fg3m,
                            "fg3a": row.fg3a,
                            "ftm": row.ftm,
                            "fta": row.fta,
                            "oreb": row.oreb,
                            "dreb": row.dreb,
                            "tov": row.tov,
                            "poss": poss,
                            "raw_ortg": raw_ortg,
                            "raw_drtg": raw_drtg,
                        },
                    )

        self.stdout.write(
            f"Games: {created_games} created, {updated_games} updated."
        )

        # ── Pass 2: compute rest days + B2B for each team ──────────────────
        self.stdout.write("Computing rest days / back-to-back flags …")
        _compute_rest_context(season)
        self.stdout.write(self.style.SUCCESS("Done."))


# ── Helpers ──────────────────────────────────────────────────────────────────


def _compute_poss(row) -> float | None:
    """Estimate possessions from LeagueGameLog box score row."""
    # poss = FGA - OREB + TO + 0.44 * FTA
    if any(v is None for v in (row.fga, row.oreb, row.tov, row.fta)):
        return None
    poss = row.fga - row.oreb + row.tov + 0.44 * row.fta
    return max(poss, 1.0)  # floor at 1 to avoid division-by-zero downstream


def _compute_rest_context(season: NBASeason) -> None:
    """
    For every team, sort their games in this season by date and compute:
      - rest_days_home / rest_days_away  (days since previous game)
      - home_b2b / away_b2b             (rest_days == 1)

    Only updates NBAGame records that belong to this season.
    Idempotent — safe to re-run.
    """
    # Build per-team sorted game dates
    games_qs = NBAGame.objects.filter(season=season, date__isnull=False).order_by("date")

    # team_id (DB PK) -> sorted list of (date, game_id, is_home)
    team_games: dict[int, list[tuple[date, str, bool]]] = defaultdict(list)
    for game in games_qs:
        team_games[game.home_team_id].append((game.date, game.game_id, True))
        team_games[game.away_team_id].append((game.date, game.game_id, False))

    # Compute rest_days for each (team, game)
    # rest_days_map: game_id -> {'home': days, 'away': days}
    rest_map: dict[str, dict[str, int | None]] = defaultdict(lambda: {"home": None, "away": None})

    for team_pk, appearances in team_games.items():
        appearances.sort(key=lambda x: x[0])
        for i, (game_date, game_id, is_home) in enumerate(appearances):
            if i == 0:
                days = None  # first game of season — no prior game
            else:
                prev_date = appearances[i - 1][0]
                days = (game_date - prev_date).days
            key = "home" if is_home else "away"
            rest_map[game_id][key] = days

    # Bulk update
    updates = []
    for game in games_qs:
        rest = rest_map.get(game.game_id, {})
        home_days = rest.get("home")
        away_days = rest.get("away")
        game.rest_days_home = home_days
        game.rest_days_away = away_days
        game.home_b2b = home_days == 1
        game.away_b2b = away_days == 1
        updates.append(game)

    NBAGame.objects.bulk_update(
        updates, ["rest_days_home", "rest_days_away", "home_b2b", "away_b2b"]
    )
