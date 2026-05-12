"""
NBA Matchup Engine — NBA-specific helpers for game forecasting.

Sport-agnostic math (forecast_game, compute_matchup_four_factors, etc.) lives in
api.matchup_engine and is imported directly. This module handles NBA model
structure, data access, and NBA-specific features (series probability).

Scale difference: NBA four-factor fields are stored as decimals (0.54 = 54%).
All functions here return/accept percentage-point scale (54.0) for API consistency
with the NCAA matchup response.
"""
import logging
import statistics
from typing import Dict, List, Optional

from django.db.models import Avg, Count

logger = logging.getLogger(__name__)

NBA_PACE_DEFAULT = 98.0
NBA_ORTG_DEFAULT = 115.0
NBA_HCA_DEFAULT = 2.5
NBA_SIGMA_DEFAULT = 12.0

# National average four-factor defaults in percentage-point scale
NBA_NAT_EFG = 53.5
NBA_NAT_TOV = 13.5
NBA_NAT_ORB = 27.0
NBA_NAT_FTR = 23.0


def get_nba_model_params(season) -> Dict:
    """
    Load HCA, sigma, and nat_avg_ortg for a season from NBAModelCalibration.
    Falls back to NBA-appropriate defaults if calibration not available.
    """
    from nba.models import NBAModelCalibration, NBATeamSeasonRatings

    hca_points = NBA_HCA_DEFAULT
    sigma = NBA_SIGMA_DEFAULT
    ols_r_squared = None

    try:
        cal = NBAModelCalibration.objects.get(season=season)
        if cal.empirical_hca is not None:
            hca_points = cal.empirical_hca
        # prediction_sigma = std dev of OLS residuals in game points (correct unit for CDF)
        # ols_model_scale is the β₁ slope coefficient — NOT sigma — do not use it here
        if cal.prediction_sigma is not None:
            sigma = cal.prediction_sigma
        ols_r_squared = cal.ols_r_squared
    except NBAModelCalibration.DoesNotExist:
        pass

    # nat_avg_ortg from average of all teams' adj_off for the season
    agg = NBATeamSeasonRatings.objects.filter(
        season=season, season_type="regular", adj_off__isnull=False
    ).aggregate(v=Avg("adj_off"), n=Count("id"))

    rated_teams = agg["n"] or 0
    avg_off = agg["v"]

    if avg_off is not None and 105.0 < avg_off < 130.0:
        nat_avg_ortg = round(avg_off, 1)
    else:
        nat_avg_ortg = NBA_ORTG_DEFAULT
        if avg_off is not None:
            logger.error(
                "[NBA matchup] nat_avg_ortg=%.1f out of expected range 105-130 "
                "(rated_teams=%d). Using fallback %.1f.",
                avg_off, rated_teams, NBA_ORTG_DEFAULT,
            )

    if rated_teams < 20:
        logger.warning(
            "[NBA matchup] Only %d teams have adj_off ratings for season %s — "
            "nat_avg_ortg may be unreliable. Run nba_compute_ratings.",
            rated_teams, season,
        )

    if not (8.0 < sigma < 20.0):
        logger.error(
            "[NBA matchup] sigma=%.2f outside expected range 8-20. "
            "Run nba_eval_model to compute prediction_sigma.",
            sigma,
        )

    logger.debug(
        "[NBA matchup params] season=%s hca=%.2f sigma=%.2f nat_avg_ortg=%.1f rated_teams=%d",
        season, hca_points, sigma, nat_avg_ortg, rated_teams,
    )

    return {
        "hca_points": hca_points,
        "sigma": sigma,
        "nat_avg_ortg": nat_avg_ortg,
        "ols_r_squared": ols_r_squared,
    }


def compute_nba_national_four_factors(season, season_type: str = "regular") -> Dict:
    """
    Compute national average four factors from all teams in the season.
    NBA stores these as decimals; returns percentage-point scale (×100).
    """
    from nba.models import NBATeamSeasonRatings

    agg = NBATeamSeasonRatings.objects.filter(
        season=season, season_type=season_type
    ).aggregate(
        avg_efg=Avg("efg_pct"),
        avg_tov=Avg("tov_rate"),
        avg_orb=Avg("oreb_pct"),
        avg_ftr=Avg("fta_rate"),
    )

    def _pct(val, default):
        return round(val * 100.0, 1) if val is not None else default

    return {
        "nat_efg": _pct(agg["avg_efg"], NBA_NAT_EFG),
        "nat_tov": _pct(agg["avg_tov"], NBA_NAT_TOV),
        "nat_orb": _pct(agg["avg_orb"], NBA_NAT_ORB),
        "nat_ftr": _pct(agg["avg_ftr"], NBA_NAT_FTR),
    }


def get_nba_four_factors_pct(ratings) -> Dict:
    """
    Extract four-factor fields from NBATeamSeasonRatings and convert to
    percentage points (NBA stores decimals, engine expects percentage points).
    """
    def _p(v, default):
        return round(v * 100.0, 2) if v is not None else default

    return {
        "efg":     _p(ratings.efg_pct,      NBA_NAT_EFG),
        "tov":     _p(ratings.tov_rate,     NBA_NAT_TOV),
        "orb":     _p(ratings.oreb_pct,     NBA_NAT_ORB),
        "ftr":     _p(ratings.fta_rate,     NBA_NAT_FTR),
        "opp_efg": _p(ratings.opp_efg_pct,  NBA_NAT_EFG),
        "opp_tov": _p(ratings.opp_tov_rate, NBA_NAT_TOV),
        "opp_orb": _p(ratings.opp_oreb_pct, NBA_NAT_ORB),
        "opp_ftr": _p(ratings.opp_fta_rate, NBA_NAT_FTR),
    }


def _build_game_map(stats_list) -> Dict:
    """Build {game_pk: {team_pk: stat}} lookup from a list of NBATeamGameStats."""
    game_map: Dict = {}
    for s in stats_list:
        gid = s.game_id  # integer FK PK
        if gid not in game_map:
            game_map[gid] = {}
        game_map[gid][s.team_id] = s
    return game_map


def compute_nba_record(team, season) -> str:
    """Compute W-L record from NBATeamGameStats for the regular season."""
    from nba.models import NBATeamGameStats

    stats = NBATeamGameStats.objects.filter(
        team=team,
        game__season=season,
        game__counts_toward_regular_season=True,
        pts__isnull=False,
        opp_pts__isnull=False,
    )
    wins = sum(1 for s in stats if s.pts > s.opp_pts)
    losses = sum(1 for s in stats if s.pts <= s.opp_pts)
    return f"{wins}-{losses}"


def compute_nba_adjusted_variance(
    team,
    season,
    recent_stats: List,
    nat_avg_ortg: float,
    hca_points: float,
    sigma: float,
) -> Optional[float]:
    """
    Variance of (actual_margin - expected_margin) for recent NBA games.
    NBATeamGameStats uses is_home bool (not home_away string like NCAA).
    """
    from api.matchup_engine import forecast_game
    from nba.models import NBATeamGameStats, NBATeamSeasonRatings

    if len(recent_stats) < 2:
        return None

    # Load all stats for these games to find opponents
    game_pks = [s.game_id for s in recent_stats]
    all_stats = NBATeamGameStats.objects.filter(
        game_id__in=game_pks
    ).select_related("team")
    game_map = _build_game_map(all_stats)

    try:
        team_ratings = NBATeamSeasonRatings.objects.get(
            team=team, season=season, season_type="regular"
        )
    except NBATeamSeasonRatings.DoesNotExist:
        return None

    residuals = []
    for stat in recent_stats:
        if stat.pts is None or stat.opp_pts is None:
            continue
        actual_margin = stat.pts - stat.opp_pts

        opp_stat = next(
            (s for tid, s in game_map.get(stat.game_id, {}).items() if tid != stat.team_id),
            None,
        )
        if opp_stat is None:
            continue

        try:
            opp_ratings = NBATeamSeasonRatings.objects.get(
                team=opp_stat.team, season=season, season_type="regular"
            )
        except NBATeamSeasonRatings.DoesNotExist:
            continue

        site = "home" if stat.is_home else "away"
        fc = forecast_game(
            adj_o_a=team_ratings.adj_off or nat_avg_ortg,
            adj_d_a=team_ratings.adj_def or nat_avg_ortg,
            adj_em_a=team_ratings.adj_net or 0.0,
            tempo_a=team_ratings.pace or NBA_PACE_DEFAULT,
            adj_o_b=opp_ratings.adj_off or nat_avg_ortg,
            adj_d_b=opp_ratings.adj_def or nat_avg_ortg,
            adj_em_b=opp_ratings.adj_net or 0.0,
            tempo_b=opp_ratings.pace or NBA_PACE_DEFAULT,
            nat_avg_ortg=nat_avg_ortg,
            hca_points=hca_points,
            sigma=sigma,
            site=site,
        )
        residuals.append(actual_margin - fc["margin"])

    if len(residuals) < 2:
        return None
    return statistics.stdev(residuals)


def compute_nba_recent_form(team, season, nat_avg_ortg: float, hca_points: float, sigma: float) -> Dict:
    """
    Pull last 10 regular-season NBATeamGameStats and compute recent form summary.
    Returns adjusted variance (opponent-adjusted residuals) where possible.
    """
    from nba.models import NBATeamGameStats

    recent_stats = list(
        NBATeamGameStats.objects.filter(
            team=team,
            game__season=season,
            game__counts_toward_regular_season=True,
            pts__isnull=False,
            opp_pts__isnull=False,
        )
        .select_related("game", "team")
        .order_by("-game__date")[:10]
    )

    if not recent_stats:
        return {"games_analyzed": 0, "record": "0-0", "avg_margin": 0.0, "variance": 0.0, "games": []}

    # Load all sides for these games (to find opponent names)
    game_pks = [s.game_id for s in recent_stats]
    all_stats = NBATeamGameStats.objects.filter(
        game_id__in=game_pks
    ).select_related("team")
    game_map = _build_game_map(all_stats)

    margins = []
    form_data = []
    for stat in recent_stats:
        opp_stat = next(
            (s for tid, s in game_map.get(stat.game_id, {}).items() if tid != stat.team_id),
            None,
        )
        opp_name = opp_stat.team.name if opp_stat else "Unknown"
        opp_pts = stat.opp_pts or 0
        margin = stat.pts - opp_pts
        margins.append(margin)
        form_data.append({
            "date": stat.game.date.isoformat(),
            "opponent": opp_name,
            "result": "W" if margin > 0 else "L",
            "score": f"{stat.pts}-{opp_pts}",
            "margin": margin,
        })

    wins = sum(1 for m in margins if m > 0)
    losses = len(margins) - wins

    adj_var = compute_nba_adjusted_variance(team, season, recent_stats, nat_avg_ortg, hca_points, sigma)
    if adj_var is None and len(margins) >= 2:
        adj_var = statistics.stdev(margins)

    return {
        "games_analyzed": len(recent_stats),
        "record": f"{wins}-{losses}",
        "avg_margin": round(statistics.mean(margins), 1) if margins else 0.0,
        "variance": round(adj_var, 1) if adj_var is not None else 0.0,
        "games": form_data[:5],
    }


def compute_nba_shot_profile(team, season) -> Optional[Dict]:
    """
    Compute shot profile from season NBATeamGameStats aggregates.
    Returns percentage-point scale for API consistency with NCAA.
    """
    from nba.models import NBATeamGameStats

    rows = list(
        NBATeamGameStats.objects.filter(
            team=team,
            game__season=season,
            game__counts_toward_regular_season=True,
            fga__gt=0,
        ).values_list("fgm", "fga", "fg3m", "fg3a")
    )

    if not rows:
        return None

    tot_fgm = sum(r[0] or 0 for r in rows)
    tot_fga = sum(r[1] or 0 for r in rows)
    tot_fg3m = sum(r[2] or 0 for r in rows)
    tot_fg3a = sum(r[3] or 0 for r in rows)

    if tot_fga == 0:
        return None

    fg3_rate = (tot_fg3a / tot_fga * 100) if tot_fga else 42.0
    fg3_pct = (tot_fg3m / tot_fg3a * 100) if tot_fg3a else 36.0
    fg2m = tot_fgm - tot_fg3m
    fg2a = tot_fga - tot_fg3a
    fg2_pct = (fg2m / fg2a * 100) if fg2a else 51.0

    return {
        "fg3_rate": round(fg3_rate, 1),
        "fg3_pct": round(fg3_pct, 1),
        "fg2_pct": round(fg2_pct, 1),
    }


def compute_series_probability(
    prob_a_home: float,
    prob_a_away: float,
    series_home: str = "a",
) -> Dict:
    """
    Compute 7-game series win probabilities using DP over 2-2-1-1-1 format.

    series_home: 'a' = Team A has home court (G1,G2,G6,G7 at A).
                 'b' = Team B has home court.
    """
    if series_home == "a":
        game_sites = ["home", "home", "away", "away", "away", "home", "home"]
    else:
        game_sites = ["away", "away", "home", "home", "home", "away", "away"]

    def p_a(g: int) -> float:
        return prob_a_home if game_sites[g] == "home" else prob_a_away

    # dp[a_wins][b_wins] = P(series reaches this state, ongoing)
    dp = [[0.0] * 5 for _ in range(5)]
    dp[0][0] = 1.0

    prob_a_in = [0.0] * 8   # index = total games played when A clinches
    prob_b_in = [0.0] * 8

    for g in range(7):
        pa = p_a(g)
        new_dp = [[0.0] * 5 for _ in range(5)]
        for a in range(5):
            for b in range(5):
                if dp[a][b] == 0.0 or a == 4 or b == 4:
                    continue
                # A wins game g+1
                p_a_win = dp[a][b] * pa
                if a + 1 == 4:
                    prob_a_in[g + 1] += p_a_win
                else:
                    new_dp[a + 1][b] += p_a_win
                # B wins game g+1
                p_b_win = dp[a][b] * (1 - pa)
                if b + 1 == 4:
                    prob_b_in[g + 1] += p_b_win
                else:
                    new_dp[a][b + 1] += p_b_win
        dp = new_dp

    prob_a_series = sum(prob_a_in[4:8])
    prob_b_series = sum(prob_b_in[4:8])

    schedule = [
        {
            "game": i + 1,
            "site": game_sites[i],
            "label": f"Team {'A' if game_sites[i] == 'home' else 'B'} home",
        }
        for i in range(7)
    ]

    return {
        "prob_a_series": round(prob_a_series, 3),
        "prob_b_series": round(prob_b_series, 3),
        "prob_sweep_a": round(prob_a_in[4], 3),
        "prob_a_in_5": round(prob_a_in[5], 3),
        "prob_a_in_6": round(prob_a_in[6], 3),
        "prob_a_in_7": round(prob_a_in[7], 3),
        "prob_sweep_b": round(prob_b_in[4], 3),
        "prob_b_in_5": round(prob_b_in[5], 3),
        "prob_b_in_6": round(prob_b_in[6], 3),
        "prob_b_in_7": round(prob_b_in[7], 3),
        "series_home": series_home,
        "game_schedule": schedule,
    }
