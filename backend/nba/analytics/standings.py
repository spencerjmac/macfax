"""
Standings computation from NBAGame results.

Pure derived data — no new ingestion. Used by the playoff-results sync
command, the Efficiency Landscape backtest, and the future Crystal Ball.
"""

from nba.models import NBAGame, NBATeam


def compute_standings(season_year: int, season_type: str = "regular") -> list[dict]:
    """
    Return one dict per team with wins/losses/win_pct and a 1-15 rank
    within its conference, sorted by win_pct (then wins) descending.

    For season_type='regular', only games where counts_toward_regular_season
    is True are tallied (excludes the NBA Cup Championship game). For other
    season types (e.g. 'playoffs'), all 'Final' games of that type count.
    """
    games_qs = NBAGame.objects.filter(season__year=season_year, status="Final")
    if season_type == "regular":
        games_qs = games_qs.filter(counts_toward_regular_season=True)
    else:
        games_qs = games_qs.filter(season_type=season_type)

    records: dict[int, dict] = {}

    def _record(team_id: int) -> dict:
        return records.setdefault(team_id, {"wins": 0, "losses": 0})

    for game in games_qs.only(
        "home_team_id", "away_team_id", "home_score", "away_score"
    ):
        if game.home_score is None or game.away_score is None:
            continue
        if game.home_score > game.away_score:
            _record(game.home_team_id)["wins"] += 1
            _record(game.away_team_id)["losses"] += 1
        elif game.away_score > game.home_score:
            _record(game.away_team_id)["wins"] += 1
            _record(game.home_team_id)["losses"] += 1

    team_conference = {
        t.id: t.conference for t in NBATeam.objects.only("id", "conference")
    }

    standings: list[dict] = []
    for team_id, record in records.items():
        wins, losses = record["wins"], record["losses"]
        games = wins + losses
        win_pct = wins / games if games else 0.0
        standings.append({
            "team_id": team_id,
            "conference": team_conference.get(team_id),
            "wins": wins,
            "losses": losses,
            "win_pct": win_pct,
        })

    # Rank within conference, best record first.
    by_conference: dict[str, list[dict]] = {}
    for row in standings:
        by_conference.setdefault(row["conference"], []).append(row)

    for conference_rows in by_conference.values():
        conference_rows.sort(key=lambda r: (r["win_pct"], r["wins"]), reverse=True)
        for rank, row in enumerate(conference_rows, start=1):
            row["conference_rank"] = rank

    return [
        {
            "team_id": row["team_id"],
            "wins": row["wins"],
            "losses": row["losses"],
            "win_pct": row["win_pct"],
            "conference_rank": row["conference_rank"],
        }
        for row in standings
    ]
