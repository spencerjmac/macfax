"""
Traditional per-game team stats for the NBA ratings table (Traditional tab).

Built from NBATeamGameStats for one season and season type (final games only).
Each stat divides by the games that have it, so a game missing a value (for
example AST before the post-0034 re-sync) drops out of that stat only, and a
stat no game has is None, not 0. Fouls drawn (PFD) are the opponent's PF in the
same game. Percentages are 0-100, as on the NCAA rankings.
"""

from collections import defaultdict

from .models import NBATeamGameStats

# Per-game averages: output field -> NBATeamGameStats field(s) summed per game.
PER_GAME = {
    "ppg": ("pts",),
    "papg": ("opp_pts",),
    "fgm_pg": ("fgm",),
    "fga_pg": ("fga",),
    "fg3m_pg": ("fg3m",),
    "fg3a_pg": ("fg3a",),
    "ftm_pg": ("ftm",),
    "fta_pg": ("fta",),
    "orpg": ("oreb",),
    "drpg": ("dreb",),
    "rpg": ("oreb", "dreb"),
    "apg": ("ast",),
    "spg": ("stl",),
    "bpg": ("blk",),
    "topg": ("tov",),
    "pfpg": ("pf",),
}

# Shooting percentages: output field -> (makes, attempts), over games that have both.
PERCENT = {
    "fg_pct": ("fgm", "fga"),
    "fg3_pct": ("fg3m", "fg3a"),
    "ft_pct": ("ftm", "fta"),
}

FIELDS = ["gp", *PER_GAME, "pfdpg", "fg_pct", "fg2_pct", "fg3_pct", "ft_pct"]

_STAT_FIELDS = sorted({f for fs in PER_GAME.values() for f in fs} | {"pf"})


def _per_game(total, games):
    return round(total / games, 1) if games else None


def _pct(makes, attempts):
    return round(makes / attempts * 100, 1) if attempts else None


def team_traditional_stats(season, season_type: str) -> dict[int, dict]:
    """{team_id: {field: value}} for every team with a final game of this season type."""
    rows = list(
        NBATeamGameStats.objects.filter(
            game__season=season, game__season_type=season_type, game__status="Final",
        ).values("game_id", "team_id", *_STAT_FIELDS)
    )
    by_game = defaultdict(list)
    for r in rows:
        by_game[r["game_id"]].append(r)

    # team_id -> field -> [sum, games]
    acc = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for r in rows:
        a = acc[r["team_id"]]
        if r["pts"] is not None:
            a["gp"][1] += 1
        for out, fields in PER_GAME.items():
            vals = [r[f] for f in fields]
            if None not in vals:
                a[out][0] += sum(vals)
                a[out][1] += 1
        for out, (made, att) in PERCENT.items():
            if r[made] is not None and r[att] is not None:
                a[out][0] += r[made]
                a[out][1] += r[att]
        vals = [r["fgm"], r["fga"], r["fg3m"], r["fg3a"]]
        if None not in vals:
            a["fg2_pct"][0] += r["fgm"] - r["fg3m"]
            a["fg2_pct"][1] += r["fga"] - r["fg3a"]
        opp = [o for o in by_game[r["game_id"]] if o["team_id"] != r["team_id"]]
        if len(opp) == 1 and opp[0]["pf"] is not None:
            a["pfdpg"][0] += opp[0]["pf"]
            a["pfdpg"][1] += 1

    out = {}
    for team_id, a in acc.items():
        stats = {"gp": a["gp"][1] or None}
        for f in [*PER_GAME, "pfdpg"]:
            stats[f] = _per_game(*a[f])
        for f in ["fg_pct", "fg2_pct", "fg3_pct", "ft_pct"]:
            stats[f] = _pct(*a[f])
        out[team_id] = stats
    return out
