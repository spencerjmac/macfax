"""
National Champion Checklist Logic

Computes the 15-item checklist for championship contenders based on 
historical champion thresholds.
"""

from typing import Dict, List, Optional, Any
from ncaa.models import TeamSeasonStats
from .trapezoid_views import compute_trapezoid_boundaries, is_inside_trapezoid
import numpy as np


def compute_national_champion_checklist(
    team_stats: TeamSeasonStats,
    season_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Compute the National Champion Checklist for a team.
    
    Args:
        team_stats: TeamSeasonStats instance for the team
        season_context: Pre-computed season-wide stats including:
            - max_adj_em: Maximum AdjEM in the season
            - trapezoid: Trapezoid boundaries
            - adj_o_ranks: Dict mapping team_id to AdjO rank
            - adj_d_ranks: Dict mapping team_id to AdjD rank
    
    Returns:
        Dictionary with checklist results
    """
    items = []
    passed_count = 0
    
    # 1) Trapezoid of Excellence
    item = _check_trapezoid(team_stats, season_context)
    items.append(item)
    if item['pass']:
        passed_count += 1
    
    # 2) KenPom Contender
    item = _check_kenpom_contender(team_stats)
    items.append(item)
    if item['pass']:
        passed_count += 1
    
    # 3) Predicted Efficiency "Title Favorite"
    item = _check_title_favorite(team_stats, season_context)
    items.append(item)
    if item['pass']:
        passed_count += 1
    
    # 4) Win%
    item = _check_win_pct(team_stats)
    items.append(item)
    if item['pass']:
        passed_count += 1
    
    # 5) Elite Off/Def ranks
    item = _check_elite_ranks(team_stats, season_context)
    items.append(item)
    if item['pass']:
        passed_count += 1
    
    # 6) 3P%
    item = _check_three_point_pct(team_stats)
    items.append(item)
    if item['pass']:
        passed_count += 1
    
    # 7) T-Rank
    item = _check_t_rank(team_stats)
    items.append(item)
    if item['pass']:
        passed_count += 1
    
    # 8) AP Poll Week 6
    item = _check_ap_poll_week6(team_stats)
    items.append(item)
    if item['pass']:
        passed_count += 1
    
    # 9) eFG Margin
    item = _check_efg_margin(team_stats, season_context)
    items.append(item)
    if item['pass']:
        passed_count += 1
    
    # 10) FTR Margin
    item = _check_ftr_margin(team_stats, season_context)
    items.append(item)
    if item['pass']:
        passed_count += 1
    
    # 11) Rebounding Edge
    item = _check_rebounding_edge(team_stats, season_context)
    items.append(item)
    if item['pass']:
        passed_count += 1
    
    # 12) Turnover Edge
    item = _check_turnover_edge(team_stats, season_context)
    items.append(item)
    if item['pass']:
        passed_count += 1
    
    # 13) Four Factor Index
    item = _check_four_factor_index(team_stats, season_context)
    items.append(item)
    if item['pass']:
        passed_count += 1
    
    # 14) WAB
    item = _check_wab(team_stats)
    items.append(item)
    if item['pass']:
        passed_count += 1
    
    # 15) FT%
    item = _check_ft_pct(team_stats)
    items.append(item)
    if item['pass']:
        passed_count += 1
    
    return {
        "passedCount": passed_count,
        "totalCount": 15,
        "items": items
    }


def compute_season_context(season) -> Dict[str, Any]:
    """
    Pre-compute season-wide statistics needed for checklist computation.
    This should be called once per season and cached/reused for all teams.
    
    Args:
        season: Season instance
    
    Returns:
        Dictionary with season context
    """
    # Get all teams in the season
    teams = TeamSeasonStats.objects.filter(season=season).select_related('team')
    
    if not teams:
        return {
            "max_adj_em": None,
            "trapezoid": None,
            "adj_o_ranks": {},
            "adj_d_ranks": {},
        }
    
    # Compute max AdjEM
    max_adj_em = max((t.adj_em for t in teams), default=None)
    
    # Compute trapezoid boundaries
    tempo_values = np.array([t.adj_tempo for t in teams])
    em_values = np.array([t.adj_em for t in teams])
    trapezoid = compute_trapezoid_boundaries(tempo_values, em_values)
    
    # Compute AdjO ranks (higher is better, rank 1 = highest AdjO)
    adj_o_sorted = sorted(teams, key=lambda t: t.adj_o, reverse=True)
    adj_o_ranks = {t.team_id: rank + 1 for rank, t in enumerate(adj_o_sorted)}
    
    # Compute AdjD ranks (lower is better, rank 1 = lowest AdjD)
    adj_d_sorted = sorted(teams, key=lambda t: t.adj_d)
    adj_d_ranks = {t.team_id: rank + 1 for rank, t in enumerate(adj_d_sorted)}
    
    # Fetch ratings to compute four factor stats
    # Determine if this is a pre-tournament snapshot
    is_pre = False
    if teams:
        first_team = teams[0]
        if hasattr(first_team, 'rating') and first_team.rating:
            is_pre = first_team.rating.is_pre_tournament

    from ncaa.models import TeamSeasonRatings
    qs = TeamSeasonRatings.objects.filter(season=season, team__is_d1=True, is_pre_tournament=is_pre)
    efgs = []
    ftrs = []
    rebs = []
    tovs = []
    ffis = []
    for r in qs:
        if r.adj_efg_margin is not None: efgs.append(r.adj_efg_margin)
        if r.adj_ftr_margin is not None: ftrs.append(r.adj_ftr_margin)
        if r.adj_reb_edge is not None: rebs.append(r.adj_reb_edge)
        if r.adj_tov_edge is not None: tovs.append(r.adj_tov_edge)
        if r.ffi_adj is not None: ffis.append(r.ffi_adj)
        
    stats = {
        "efg_mean": float(np.mean(efgs)) if efgs else 0,
        "efg_std": float(np.std(efgs)) if efgs else 1,
        "ftr_mean": float(np.mean(ftrs)) if ftrs else 0,
        "ftr_std": float(np.std(ftrs)) if ftrs else 1,
        "reb_mean": float(np.mean(rebs)) if rebs else 0,
        "reb_std": float(np.std(rebs)) if rebs else 1,
        "tov_mean": float(np.mean(tovs)) if tovs else 0,
        "tov_std": float(np.std(tovs)) if tovs else 1,
        "ffi_mean": float(np.mean(ffis)) if ffis else 0,
        "ffi_std": float(np.std(ffis)) if ffis else 1,
    }
    
    return {
        "max_adj_em": max_adj_em,
        "trapezoid": trapezoid,
        "adj_o_ranks": adj_o_ranks,
        "adj_d_ranks": adj_d_ranks,
        "stats": stats,
    }


# ==================== Individual Check Functions ====================

def _check_trapezoid(team_stats: TeamSeasonStats, context: Dict[str, Any]) -> Dict[str, Any]:
    """Check if team is inside the Trapezoid of Excellence"""
    trapezoid = context.get('trapezoid')
    
    if trapezoid is None:
        return {
            "key": "trapezoid",
            "label": "Trapezoid of Excellence",
            "pass": False,
            "value": "N/A",
            "threshold": "Inside trapezoid",
            "details": "Trapezoid data unavailable"
        }
    
    inside = is_inside_trapezoid(team_stats.adj_tempo, team_stats.adj_em, trapezoid)
    
    return {
        "key": "trapezoid",
        "label": "Trapezoid of Excellence",
        "pass": inside,
        "value": "Inside" if inside else "Outside",
        "threshold": "Inside trapezoid",
        "details": f"Tempo: {team_stats.adj_tempo:.1f}, AdjEM: {team_stats.adj_em:.1f}"
    }


def _check_kenpom_contender(team_stats: TeamSeasonStats) -> Dict[str, Any]:
    """Check KenPom contender thresholds"""
    adj_o = team_stats.adj_o
    adj_d = team_stats.adj_d
    adj_em = team_stats.adj_em
    
    # Pass if (AdjO ≥ 112.0 AND AdjD ≤ 96.5) OR (AdjEM > 30.0)
    condition1 = adj_o >= 112.0 and adj_d <= 96.5
    condition2 = adj_em > 30.0
    passes = condition1 or condition2
    
    return {
        "key": "kenpom_contender",
        "label": "KenPom Contender",
        "pass": passes,
        "value": f"O: {adj_o:.1f}, D: {adj_d:.1f}",
        "threshold": "(O ≥ 112.0 & D ≤ 96.5) OR EM > 30.0",
        "details": f"AdjO: {adj_o:.1f}, AdjD: {adj_d:.1f}, AdjEM: {adj_em:.1f}"
    }


def _check_title_favorite(team_stats: TeamSeasonStats, context: Dict[str, Any]) -> Dict[str, Any]:
    """Check if team is within 6 points of max AdjEM"""
    max_adj_em = context.get('max_adj_em')
    adj_em = team_stats.adj_em
    
    if max_adj_em is None:
        return {
            "key": "title_favorite",
            "label": "Title Favorite (AdjEM)",
            "pass": False,
            "value": "N/A",
            "threshold": "Within 6.0 of max",
            "details": "Season max unavailable"
        }
    
    threshold = max_adj_em - 6.0
    passes = adj_em >= threshold
    
    return {
        "key": "title_favorite",
        "label": "Title Favorite (AdjEM)",
        "pass": passes,
        "value": f"{adj_em:.1f}",
        "threshold": f"≥ {threshold:.1f} (max: {max_adj_em:.1f})",
        "details": f"AdjEM {adj_em:.1f}, needs ≥ {threshold:.1f} (max is {max_adj_em:.1f})"
    }


def _check_win_pct(team_stats: TeamSeasonStats) -> Dict[str, Any]:
    """Check win percentage > 74%"""
    if team_stats.games == 0:
        win_pct = 0.0
    else:
        win_pct = team_stats.wins / team_stats.games
    
    passes = win_pct >= 0.75
    
    return {
        "key": "win_pct",
        "label": "Win Percentage",
        "pass": passes,
        "value": f"{win_pct * 100:.1f}%",
        "expected": ">= 75.0%",
        "details": f"{team_stats.record} ({win_pct * 100:.1f}%)"
    }


def _check_elite_ranks(team_stats: TeamSeasonStats, context: Dict[str, Any]) -> Dict[str, Any]:
    """Check OffRtgRank <= 16 AND DefRtgRank <= 45"""
    adj_o_ranks = context.get('adj_o_ranks', {})
    adj_d_ranks = context.get('adj_d_ranks', {})
    
    off_rank = adj_o_ranks.get(team_stats.team_id)
    def_rank = adj_d_ranks.get(team_stats.team_id)
    
    if off_rank is None or def_rank is None:
        return {
            "key": "elite_ranks",
            "label": "Elite Off/Def Ranks",
            "pass": False,
            "value": "N/A",
            "threshold": "Off ≤ 16, Def ≤ 45",
            "details": "Rank data unavailable"
        }
    
    passes = off_rank <= 16 and def_rank <= 45
    
    return {
        "key": "elite_ranks",
        "label": "Elite Off/Def Ranks",
        "pass": passes,
        "value": f"Off: #{off_rank}, Def: #{def_rank}",
        "threshold": "Off ≤ 16, Def ≤ 45",
        "details": f"Offensive rank: #{off_rank}, Defensive rank: #{def_rank}"
    }


def _check_three_point_pct(team_stats: TeamSeasonStats) -> Dict[str, Any]:
    """Check 3P% > 32%"""
    fg3_pct = team_stats.fg3_pct
    
    if fg3_pct is None:
        return {
            "key": "three_point_pct",
            "label": "3-Point %",
            "pass": False,
            "value": "N/A",
            "threshold": "> 32%",
            "details": "3P% data unavailable"
        }
    
    # Assuming fg3_pct is stored as 0-100 scale (e.g., 34.5 for 34.5%)
    # If it's stored as 0-1 scale, adjust the threshold
    threshold = 32.0
    if fg3_pct < 1.0:  # Stored as decimal (0-1)
        threshold = 0.32
        passes = fg3_pct > threshold
        display_value = f"{fg3_pct * 100:.1f}%"
    else:  # Stored as percentage (0-100)
        passes = fg3_pct > threshold
        display_value = f"{fg3_pct:.1f}%"
    
    return {
        "key": "three_point_pct",
        "label": "3-Point %",
        "pass": passes,
        "value": display_value,
        "threshold": "> 32%",
        "details": f"Team 3P%: {display_value}"
    }


def _check_t_rank(team_stats: TeamSeasonStats) -> Dict[str, Any]:
    """Check T-Rank <= 7"""
    t_rank = team_stats.t_rank
    
    if t_rank is None:
        return {
            "key": "t_rank",
            "label": "T-Rank",
            "pass": False,
            "value": "N/A",
            "threshold": "≤ 7",
            "details": "T-Rank unavailable"
        }
    
    passes = t_rank <= 7
    
    return {
        "key": "t_rank",
        "label": "T-Rank",
        "pass": passes,
        "value": f"#{t_rank}",
        "threshold": "≤ 7",
        "details": f"T-Rank: #{t_rank}"
    }


def _check_ap_poll_week6(team_stats: TeamSeasonStats) -> Dict[str, Any]:
    """Check AP Poll Week 6 <= 12"""
    ap_rank = team_stats.ap_poll_week6
    
    if ap_rank is None:
        return {
            "key": "ap_poll_week6",
            "label": "AP Poll Week 6",
            "pass": False,
            "value": "N/A",
            "threshold": "≤ 12",
            "details": "AP Poll data unavailable"
        }
    
    passes = ap_rank <= 12
    
    return {
        "key": "ap_poll_week6",
        "label": "AP Poll Week 6",
        "pass": passes,
        "value": f"#{ap_rank}",
        "threshold": "≤ 12",
        "details": f"AP Poll Week 6: #{ap_rank}"
    }


def _check_efg_margin(team_stats: TeamSeasonStats, context: Dict[str, Any]) -> Dict[str, Any]:
    """Check eFG Margin >= Dynamic Z-Score Threshold"""
    efg_margin = team_stats.efg_margin
    stats = context.get("stats", {})
    MIN_Z_EFG = 1.36 # 1.3629
    threshold = stats.get("efg_mean", 0) + (MIN_Z_EFG * stats.get("efg_std", 1))
    passes = efg_margin >= threshold if efg_margin is not None else False
    
    return {
        "key": "efg_margin",
        "label": "eFG Margin",
        "pass": passes,
        "value": f"{efg_margin:.3f}" if efg_margin is not None else "N/A",
        "threshold": f"≥ {threshold:.3f}",
        "details": f"eFG Margin: {efg_margin:.3f}" if efg_margin is not None else "Unavailable"
    }


def _check_ftr_margin(team_stats: TeamSeasonStats, context: Dict[str, Any]) -> Dict[str, Any]:
    """Check FTR Margin >= Dynamic Z-Score Threshold"""
    ftr_margin = team_stats.ftr_margin
    stats = context.get("stats", {})
    MIN_Z_FTR = -0.58 # -0.5757
    threshold = stats.get("ftr_mean", 0) + (MIN_Z_FTR * stats.get("ftr_std", 1))
    passes = ftr_margin >= threshold if ftr_margin is not None else False
    
    return {
        "key": "ftr_margin",
        "label": "FTR Margin",
        "pass": passes,
        "value": f"{ftr_margin:.2f}" if ftr_margin is not None else "N/A",
        "threshold": f"≥ {threshold:.2f}",
        "details": f"FTR Margin: {ftr_margin:.2f}" if ftr_margin is not None else "Unavailable"
    }


def _check_rebounding_edge(team_stats: TeamSeasonStats, context: Dict[str, Any]) -> Dict[str, Any]:
    """Check Rebounding Edge >= Dynamic Z-Score Threshold"""
    reb_edge = team_stats.reb_edge
    stats = context.get("stats", {})
    MIN_Z_REB = 0.20 # 0.1987
    threshold = stats.get("reb_mean", 0) + (MIN_Z_REB * stats.get("reb_std", 1))
    passes = reb_edge >= threshold if reb_edge is not None else False
    
    return {
        "key": "rebounding_edge",
        "label": "Rebounding Edge",
        "pass": passes,
        "value": f"{reb_edge:.2f}" if reb_edge is not None else "N/A",
        "threshold": f"≥ {threshold:.2f}",
        "details": f"Rebounding Edge: {reb_edge:.2f}" if reb_edge is not None else "Unavailable"
    }


def _check_turnover_edge(team_stats: TeamSeasonStats, context: Dict[str, Any]) -> Dict[str, Any]:
    """Check Turnover Edge >= Dynamic Z-Score Threshold"""
    to_edge = team_stats.tov_edge
    stats = context.get("stats", {})
    MIN_Z_TOV = 0.12 # 0.1225
    threshold = stats.get("tov_mean", 0) + (MIN_Z_TOV * stats.get("tov_std", 1))
    passes = to_edge >= threshold if to_edge is not None else False
    
    return {
        "key": "turnover_edge",
        "label": "Turnover Edge",
        "pass": passes,
        "value": f"{to_edge:.2f}" if to_edge is not None else "N/A",
        "threshold": f"≥ {threshold:.2f}",
        "details": f"Turnover Edge: {to_edge:.2f}" if to_edge is not None else "Unavailable"
    }


def _check_four_factor_index(team_stats: TeamSeasonStats, context: Dict[str, Any]) -> Dict[str, Any]:
    """Check Four Factor Index >= Dynamic Z-Score Threshold"""
    ffi = team_stats.four_factor_index_100
    stats = context.get("stats", {})
    MIN_Z_FFI = 2.01 # 2.0141
    threshold = stats.get("ffi_mean", 0) + (MIN_Z_FFI * stats.get("ffi_std", 1))
    
    if ffi is None:
        return {
            "key": "four_factor_index",
            "label": "Four Factor Index",
            "pass": False,
            "value": "N/A",
            "threshold": f"≥ {threshold:.1f}",
            "details": "Four Factor Index unavailable"
        }
    
    passes = ffi >= threshold
    
    return {
        "key": "four_factor_index",
        "label": "Four Factor Index",
        "pass": passes,
        "value": f"{ffi:.1f}",
        "threshold": f"≥ {threshold:.1f}",
        "details": f"Four Factor Index: {ffi:.1f}"
    }


def _check_wab(team_stats: TeamSeasonStats) -> Dict[str, Any]:
    """Check WAB > 5"""
    # Try to get WAB from TeamSeasonStats first, then from TeamSeasonRatings
    wab = team_stats.wab
    
    if wab is None:
        # Fallback to TeamSeasonRatings
        try:
            from ncaa.models import TeamSeasonRatings
            ratings = TeamSeasonRatings.objects.get(
                team=team_stats.team,
                season=team_stats.season
            )
            wab = ratings.wab
        except (TeamSeasonRatings.DoesNotExist, AttributeError):
            pass
    
    if wab is None:
        return {
            "key": "wab",
            "label": "WAB (Wins Above Bubble)",
            "pass": False,
            "value": "N/A",
            "threshold": "> 5",
            "details": "WAB unavailable"
        }
    
    threshold = 5.0
    passes = wab > threshold
    
    return {
        "key": "wab",
        "label": "WAB (Wins Above Bubble)",
        "pass": passes,
        "value": f"{wab:.1f}",
        "threshold": "> 5",
        "details": f"WAB: {wab:.1f}"
    }


def _check_ft_pct(team_stats: TeamSeasonStats) -> Dict[str, Any]:
    """Check FT% ≥ 68.0%"""
    ft_pct = team_stats.ft_pct
    
    if ft_pct is None:
        return {
            "key": "ft_pct",
            "label": "Free Throw %",
            "pass": False,
            "value": "N/A",
            "threshold": "≥ 68.0%",
            "details": "FT% data unavailable"
        }
    
    # Assuming ft_pct is stored as 0-100 scale (e.g., 72.5 for 72.5%)
    # If it's stored as 0-1 scale, adjust the threshold
    threshold = 68.0
    if ft_pct < 1.0:  # Stored as decimal (0-1)
        threshold = 0.68
        passes = ft_pct >= threshold
        display_value = f"{ft_pct * 100:.1f}%"
    else:  # Stored as percentage (0-100)
        passes = ft_pct >= threshold
        display_value = f"{ft_pct:.1f}%"
    
    return {
        "key": "ft_pct",
        "label": "Free Throw %",
        "pass": passes,
        "value": display_value,
        "threshold": "> 70%",
        "details": f"Team FT%: {display_value}"
    }
