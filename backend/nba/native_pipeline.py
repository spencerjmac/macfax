"""
Daily-pipeline helpers for the native BPR path (Phase 5, task 5.9).

update_nba_all and update_nba_players pick their rating steps by data: when the season
before Y holds native ratings (bpr_model 'native-1'), Y runs the native steps
(nba_fit_box_pooled --write, nba_compute_native_bpr --write); otherwise the earlier
steps run unchanged (nba_compute_box_bpr, nba_compute_final_bpr). So main stays safe to
deploy to a database that has no native seasons yet.

Before the rating steps the native path checks every player's season-row games and
minutes against his game logs (the games-played bug of task 5.4d). Any mismatch is
logged; when more than MAX_MISMATCH_SHARE of the players mismatch, the rating steps are
skipped and yesterday's ratings stay.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from nba.management.commands.nba_compute_native_bpr import NATIVE_MODEL

# Share of players whose season rows disagree with their game logs above which the
# rating steps are skipped.
MAX_MISMATCH_SHARE = 0.01
# Minutes tolerance per player: season rows store mpg as a float, so mpg x gp matches the
# game-log total to rounding error when the rollup is right.
MINUTES_TOLERANCE = 0.1


def last_season_is_native(season_year: int) -> bool:
    """True when Y-1 has any regular-season row written by the native model."""
    from nba.models import NBAPlayerSeasonStats

    return NBAPlayerSeasonStats.objects.filter(
        season__year=season_year - 1, season_type="regular", bpr_model=NATIVE_MODEL,
    ).exists()


@dataclass
class MinutesCheck:
    players: int = 0
    mismatches: list[dict] = field(default_factory=list)

    @property
    def share(self) -> float:
        return len(self.mismatches) / self.players if self.players else 0.0

    @property
    def too_many(self) -> bool:
        return self.share > MAX_MISMATCH_SHARE


def minutes_check(season_year: int) -> MinutesCheck:
    """
    Regular season of Y: per player (summed over his team rows), season-row games (gp) and
    minutes (mpg x gp) against his game logs (rows with seconds played, in games that count
    toward the regular season, as nba_compute_player_stats rolls them up). A player present on
    one side only counts as a mismatch.
    """
    from django.db.models import Count, Sum
    from nba.models import NBAPlayerGameStats, NBAPlayerSeasonStats

    logs = {r["player__player_id"]: (r["n"], (r["sec"] or 0) / 60.0) for r in NBAPlayerGameStats.objects.filter(
        game__season__year=season_year, game__counts_toward_regular_season=True, seconds_played__gt=0,
    ).values("player__player_id").annotate(n=Count("id"), sec=Sum("seconds_played"))}
    rows: dict[int, list[float]] = defaultdict(lambda: [0, 0.0])
    names: dict[int, str] = {}
    for nba_id, name, gp, mpg in NBAPlayerSeasonStats.objects.filter(
            season__year=season_year, season_type="regular").values_list(
            "player__player_id", "player__name", "gp", "mpg"):
        rows[nba_id][0] += gp or 0
        rows[nba_id][1] += (mpg or 0.0) * (gp or 0)
        names[nba_id] = name
    check = MinutesCheck(players=len(rows.keys() | logs.keys()))
    for nba_id in sorted(rows.keys() | logs.keys()):
        row_gp, row_min = rows.get(nba_id, (0, 0.0))
        log_gp, log_min = logs.get(nba_id, (0, 0.0))
        if row_gp != log_gp or abs(row_min - log_min) > MINUTES_TOLERANCE:
            check.mismatches.append({"nba_id": nba_id, "name": names.get(nba_id, ""), "row_gp": row_gp,
                                     "log_gp": log_gp, "row_min": round(row_min, 1),
                                     "log_min": round(log_min, 1)})
    return check
