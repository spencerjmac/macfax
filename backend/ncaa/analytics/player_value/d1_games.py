"""
D-I v D-I games for player impact and MPR.

Player impact (compute_ncaa_player_impact) and MPR (bpr pipeline: RAPM stints and the box rates the box
model reads) use only games between two teams that were D-I that season (TeamSeasonMembership). Games
against non-D-I opponents are mostly lopsided wins; RAPM shrinks the non-D-I players toward an average
D-I level, so those games credited every D-I player: syncing 2025-26's missing D-I v non-D-I games on
2026-11-27 lifted every D-I player's MPR by about 0.47 and the D-I dollar total by 17%. The team-ratings
solver (compute_adjusted_ratings) already fits efficiencies on D-I v D-I games only.

Season stat lines (PlayerSeasonStats box columns) keep every game; MPR reads its box rates from
d1_box_lines instead.
"""
from __future__ import annotations

from functools import reduce
from operator import or_

from django.db.models import Count, F, FloatField, Q, Sum
from django.db.models.functions import Cast

from ncaa.utils.d1 import d1_q

# PlayerSeasonStats box columns the box model and MPIR read, recomputed over D-I v D-I games
BOX_FIELDS = ("gp", "mpg", "pts", "ast", "tov", "stl", "blk", "pf", "reb", "oreb_pg", "dreb_pg",
              "fga_pg", "fg3a_pg", "fta_pg", "ftm_pg", "efg_pct", "ts_pct")


def d1_vs_d1_games_q(years, prefix: str = "") -> Q:
    """Q for games (prefix "") or rows with a game FK (prefix "game__") between two D-I teams that season."""
    years = sorted({int(y) for y in years})
    if not years:
        return Q(**{f"{prefix}pk__in": []})
    return reduce(or_, (Q(**{f"{prefix}season_year": y}) & d1_q(y, f"{prefix}home_team")
                        & d1_q(y, f"{prefix}away_team") for y in years))


def d1_box_lines(year: int) -> dict:
    """
    (player_id, team_id) -> PlayerSeasonStats-style box line over the season's D-I v D-I games (same
    formulas as compute_ncaa_player_season_stats), plus "d1_minutes_share": D-I v D-I minutes over all
    minutes. A player-team with no D-I v D-I game is absent.
    """
    from ncaa.models import PlayerGameStats

    agg = dict(gp=Count("id"), mins=Sum("minutes"), pts=Sum("points"), reb=Sum("rebounds"),
               oreb=Sum("offensive_rebounds"), dreb=Sum("defensive_rebounds"), ast=Sum("assists"),
               stl=Sum("steals"), blk=Sum("blocks"), tov=Sum("turnovers"), pf=Sum("fouls"),
               fgm=Sum("fg_made"), fga=Sum("fg_attempted"), fg3m=Sum("fg3_made"), fg3a=Sum("fg3_attempted"),
               ftm=Sum("ft_made"), fta=Sum("ft_attempted"))
    base = PlayerGameStats.objects.filter(game__season_year=year, did_not_play=False)
    all_mins = {(r["player_id"], r["team_id"]): r["mins"] or 0
                for r in base.values("player_id", "team_id").annotate(mins=Sum("minutes"))}
    out = {}
    for r in base.filter(d1_vs_d1_games_q([year], "game__")).values("player_id", "team_id").annotate(**agg):
        gp = r["gp"]
        if not gp:
            continue
        v = {k: (r[k] or 0) for k in agg}
        avg = lambda t: round(t / gp, 2)  # noqa: E731
        tsa = 2 * (v["fga"] + 0.44 * v["fta"])
        key = (r["player_id"], r["team_id"])
        out[key] = {
            "gp": gp, "mpg": avg(v["mins"]), "pts": avg(v["pts"]), "ast": avg(v["ast"]), "tov": avg(v["tov"]),
            "stl": avg(v["stl"]), "blk": avg(v["blk"]), "pf": avg(v["pf"]), "reb": avg(v["reb"]),
            "oreb_pg": avg(v["oreb"]), "dreb_pg": avg(v["dreb"]), "fga_pg": avg(v["fga"]),
            "fg3a_pg": avg(v["fg3a"]), "fta_pg": avg(v["fta"]), "ftm_pg": avg(v["ftm"]),
            "efg_pct": round((v["fgm"] + 0.5 * v["fg3m"]) / v["fga"], 4) if v["fga"] else None,
            "ts_pct": round(v["pts"] / tsa, 4) if tsa > 0 else None,
            "d1_minutes_share": (v["mins"] / all_mins[key]) if all_mins.get(key) else 1.0,
        }
    return out


def d1_stint_possessions(year: int) -> dict:
    """
    (player_id, team_id) -> (offensive, defensive) possessions on court in the season's D-I v D-I games,
    from the stints' box events with the RAPM dataset's estimate (FGA + 0.44 FTA + TOV - ORB).
    """
    from ncaa.models import PlayerGameStint

    def poss(side):
        return (Cast(F(f"{side}_fga"), FloatField()) + 0.44 * F(f"{side}_fta") + F(f"{side}_tov")
                - F(f"{side}_oreb"))

    rows = (PlayerGameStint.objects.filter(d1_vs_d1_games_q([year], "game__"))
            .values("player_id", "team_id").annotate(off=Sum(poss("team")), deff=Sum(poss("opp"))))
    return {(r["player_id"], r["team_id"]): (max(r["off"] or 0.0, 0.0), max(r["deff"] or 0.0, 0.0)) for r in rows}


def overlay_d1_box(rows: list[dict], year: int | None = None, year_key: str = "season__year",
                   replace_poss: bool = False) -> list[dict]:
    """
    PlayerSeasonStats .values() rows with their box columns replaced by the D-I v D-I line; rows with no
    D-I v D-I game are dropped. `year` for single-season rows, else each row's `year_key`.

    replace_poss: also replace the row's stored off_poss/def_poss (the box rates divide by them) with
    its D-I v D-I stint possessions. Stored possessions of seasons computed before this change count
    every game; recomputing them from the stints is right whichever way a season was stored.
    """
    lines: dict[int, dict] = {}
    poss: dict[int, dict] = {}
    out = []
    for r in rows:
        y = int(year if year is not None else r[year_key])
        if y not in lines:
            lines[y] = d1_box_lines(y)
            if replace_poss:
                poss[y] = d1_stint_possessions(y)
        key = (r.get("player_id"), r.get("team_id"))
        line = lines[y].get(key)
        if line is None:
            continue
        new = dict(r)
        new.update({k: line[k] for k in BOX_FIELDS})
        if replace_poss:
            off, deff = poss[y].get(key, (0.0, 0.0))
            new["off_poss"], new["def_poss"] = off, deff
        out.append(new)
    return out
