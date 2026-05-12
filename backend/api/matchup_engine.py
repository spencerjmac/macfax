"""
Matchup Prediction Engine

Pure functions for game forecasting using our adjusted ratings and national averages.
No external data - everything from our database.
"""
import math
from typing import Dict, Tuple, Optional
from scipy import stats as scipy_stats


def compute_pace(tempo_a: float, tempo_b: float) -> float:
    """
    Compute expected game pace (possessions) from two teams' adjusted tempos.
    
    Formula: (2 * tempo_a * tempo_b) / (tempo_a + tempo_b)
    
    This is the harmonic mean weighted by 2, representing the interaction
    of both teams' pace preferences.
    """
    if tempo_a <= 0 or tempo_b <= 0:
        return 70.0  # Default college basketball pace
    
    return (2 * tempo_a * tempo_b) / (tempo_a + tempo_b)


def compute_expected_efficiency(
    adj_o: float,
    opp_adj_d: float,
    nat_avg_ortg: float
) -> float:
    """
    Compute expected offensive efficiency for a team vs an opponent.
    
    Formula: (adj_o * opp_adj_d) / nat_avg_ortg
    
    This multiplicative approach accounts for:
    - Team's offensive strength (adj_o)
    - Opponent's defensive strength (opp_adj_d)
    - National baseline (nat_avg_ortg)
    
    Returns: Expected points per 100 possessions
    """
    if nat_avg_ortg <= 0:
        nat_avg_ortg = 108.0  # Fallback
    
    return (adj_o * opp_adj_d) / nat_avg_ortg


def apply_hca_adjustment(
    pts_a: float,
    pts_b: float,
    site: str,
    hca_points: float
) -> Tuple[float, float]:
    """
    Apply home court advantage adjustment to projected scores.
    
    Args:
        pts_a: Team A's projected points (neutral site)
        pts_b: Team B's projected points (neutral site)
        site: 'home' (A home), 'away' (B home), or 'neutral'
        hca_points: Total HCA in points
    
    Returns:
        (adjusted_pts_a, adjusted_pts_b)
    
    Logic:
        - Home team gets +HCA/2
        - Away team gets -HCA/2
        - Neutral: no adjustment
    """
    hca_half = hca_points / 2
    
    if site == 'home':
        # Team A at home
        return pts_a + hca_half, pts_b - hca_half
    elif site == 'away':
        # Team B at home (Team A away)
        return pts_a - hca_half, pts_b + hca_half
    else:
        # Neutral site
        return pts_a, pts_b


def compute_win_probability(
    margin: float,
    sigma: float
) -> Tuple[float, float]:
    """
    Compute win probability using normal CDF.
    
    Args:
        margin: Expected margin (positive = Team A favored)
        sigma: Standard deviation of prediction errors
    
    Returns:
        (prob_a, prob_b) where each is in [0, 1]
    
    Formula: P(A wins) = Φ(margin / sigma)
    where Φ is the cumulative distribution function of standard normal
    """
    if sigma <= 0:
        sigma = 11.0  # Fallback
    
    # Standardize margin
    z_score = margin / sigma
    
    # Compute CDF
    prob_a = scipy_stats.norm.cdf(z_score)
    prob_b = 1 - prob_a
    
    return prob_a, prob_b


def compute_win_probability_with_confidence(
    margin: float,
    sigma: float,
    model_margin_error: float = 1.5,
) -> Dict[str, float]:
    """
    Compute win probability with two distinct bands.

    margin_low / margin_high  — score projection range (±1 sigma).
        Shows the spread of plausible game outcomes in raw points.
        e.g. "game could end anywhere from -7 to +17"

    prob_a_low / prob_a_high  — model confidence band.
        How much the win probability shifts if our margin estimate is
        off by ±model_margin_error points (default ±1.5 pts).
        This is the uncertainty in the prediction, not game variance.
        e.g. for a 5-pt favorite: [0.61, 0.71] — tight and honest.

    The old approach used margin ± sigma for both, producing enormous
    probability bands (e.g. [0.28, 0.92]) that misrepresent model
    uncertainty as if the model could predict a swing of ±1 sigma.
    """
    if sigma <= 0:
        sigma = 11.0

    prob_a, prob_b = compute_win_probability(margin, sigma)

    # Score projection range: ±1 sigma in raw points
    margin_low = margin - sigma
    margin_high = margin + sigma

    # Model confidence band: prob shift from ±model_margin_error on the spread
    prob_a_low, _ = compute_win_probability(margin - model_margin_error, sigma)
    prob_a_high, _ = compute_win_probability(margin + model_margin_error, sigma)

    return {
        'prob_a': prob_a,
        'prob_b': prob_b,
        'margin_low': margin_low,
        'margin_high': margin_high,
        'prob_a_low': prob_a_low,
        'prob_a_high': prob_a_high,
    }


def forecast_game(
    adj_o_a: float,
    adj_d_a: float,
    adj_em_a: float,
    tempo_a: float,
    adj_o_b: float,
    adj_d_b: float,
    adj_em_b: float,
    tempo_b: float,
    nat_avg_ortg: float,
    hca_points: float,
    sigma: float,
    site: str = 'neutral'
) -> Dict:
    """
    Complete game forecast using multiplicative efficiency model.
    
    Args:
        adj_o_a, adj_d_a, adj_em_a, tempo_a: Team A's adjusted ratings
        adj_o_b, adj_d_b, adj_em_b, tempo_b: Team B's adjusted ratings
        nat_avg_ortg: National average offensive rating
        hca_points: Home court advantage in points
        sigma: Prediction error standard deviation
        site: 'home', 'away', or 'neutral'
    
    Returns:
        {
            'pace': float,
            'pts_a_neutral': float,
            'pts_b_neutral': float,
            'pts_a': float,
            'pts_b': float,
            'margin': float,
            'spread': float,
            'total': float,
            'prob_a': float,
            'prob_b': float,
            'confidence': dict (optional confidence bands)
        }
    """
    # 1. Compute expected pace
    pace = compute_pace(tempo_a, tempo_b)
    
    # 2. Compute expected efficiencies (per 100 possessions)
    exp_oe_a = compute_expected_efficiency(adj_o_a, adj_d_b, nat_avg_ortg)
    exp_oe_b = compute_expected_efficiency(adj_o_b, adj_d_a, nat_avg_ortg)
    
    # 3. Convert to points (neutral site)
    pts_a_neutral = exp_oe_a * (pace / 100)
    pts_b_neutral = exp_oe_b * (pace / 100)
    
    # 4. Apply HCA adjustment
    pts_a, pts_b = apply_hca_adjustment(pts_a_neutral, pts_b_neutral, site, hca_points)
    
    # 5. Compute margin and spread
    margin = pts_a - pts_b
    
    # Spread convention: negative for favorite
    if margin > 0:
        spread = -abs(margin)  # Team A favored
        spread_team = 'a'
    else:
        spread = abs(margin)  # Team B favored
        spread_team = 'b'
    
    total = pts_a + pts_b
    
    # 6. Win probability
    win_prob = compute_win_probability_with_confidence(margin, sigma)
    
    return {
        'pace': round(pace, 1),
        'pts_a_neutral': round(pts_a_neutral, 1),
        'pts_b_neutral': round(pts_b_neutral, 1),
        'pts_a': round(pts_a, 1),
        'pts_b': round(pts_b, 1),
        'margin': round(margin, 1),
        'spread': round(spread, 1),
        'spread_team': spread_team,
        'total': round(total, 1),
        'prob_a': round(win_prob['prob_a'], 3),
        'prob_b': round(win_prob['prob_b'], 3),
        'prob_a_low': round(win_prob['prob_a_low'], 3),
        'prob_a_high': round(win_prob['prob_a_high'], 3),
        'margin_low': round(win_prob['margin_low'], 1),
        'margin_high': round(win_prob['margin_high'], 1),
    }


def compute_matchup_four_factors(
    efg_a: float, tov_a: float, orb_a: float, ftr_a: float,
    efg_d_a: float, tov_d_a: float, orb_d_a: float, ftr_d_a: float,
    efg_b: float, tov_b: float, orb_b: float, ftr_b: float,
    efg_d_b: float, tov_d_b: float, orb_d_b: float, ftr_d_b: float,
    nat_efg: float, nat_tov: float, nat_orb: float, nat_ftr: float
) -> Dict:
    """
    Compute matchup-specific four factor edges.
    
    Uses multiplicative adjustment relative to national average.
    
    Formula for Team A expected eFG%:
        exp_efg_a = efg_a * (efg_d_b / nat_efg)
    
    This accounts for:
        - Team A's offensive eFG% (efg_a)
        - Team B's defensive eFG% allowed (efg_d_b)
        - National baseline (nat_efg)
    
    Returns edges oriented positive = Team A advantage.
    """
    # Prevent division by zero
    if nat_efg <= 0: nat_efg = 51.0
    if nat_tov <= 0: nat_tov = 17.0
    if nat_orb <= 0: nat_orb = 30.0
    if nat_ftr <= 0: nat_ftr = 35.0
    
    # Expected values for Team A
    exp_efg_a = efg_a * (efg_d_b / nat_efg)
    exp_tov_a = tov_a * (tov_d_b / nat_tov)
    exp_orb_a = orb_a * (orb_d_b / nat_orb)  # Team A offense vs Team B defense
    exp_ftr_a = ftr_a * (ftr_d_b / nat_ftr)
    
    # Expected values for Team B
    exp_efg_b = efg_b * (efg_d_a / nat_efg)
    exp_tov_b = tov_b * (tov_d_a / nat_tov)
    exp_orb_b = orb_b * (orb_d_a / nat_orb)  # Team B offense vs Team A defense
    exp_ftr_b = ftr_b * (ftr_d_a / nat_ftr)
    
    # Compute edges (positive = Team A advantage)
    efg_edge = exp_efg_a - exp_efg_b
    tov_edge = exp_tov_b - exp_tov_a  # Lower TOV is better
    orb_edge = exp_orb_a - exp_orb_b
    ftr_edge = exp_ftr_a - exp_ftr_b
    
    return {
        'efg_edge': round(efg_edge, 3),
        'tov_edge': round(tov_edge, 3),
        'orb_edge': round(orb_edge, 3),
        'ftr_edge': round(ftr_edge, 3),
        'exp_efg_a': round(exp_efg_a, 1),
        'exp_efg_b': round(exp_efg_b, 1),
        'exp_tov_a': round(exp_tov_a, 1),
        'exp_tov_b': round(exp_tov_b, 1),
        'exp_orb_a': round(exp_orb_a, 1),
        'exp_orb_b': round(exp_orb_b, 1),
        'exp_ftr_a': round(exp_ftr_a, 1),
        'exp_ftr_b': round(exp_ftr_b, 1),
    }


def compute_points_from_four_factors(
    efg_edge: float,
    tov_edge: float,
    orb_edge: float,
    ftr_edge: float,
    coef_efg: float,
    coef_tov: float,
    coef_orb: float,
    coef_ftr: float,
    coef_intercept: float,
    pace: float
) -> Dict:
    """
    Compute predicted margin contribution from four factor edges using regression coefficients.
    
    Formula: 
        efficiency_margin_100 = coef_efg*efg_edge + coef_tov*tov_edge + coef_orb*orb_edge + coef_ftr*ftr_edge + intercept
        game_margin = efficiency_margin_100 * (pace / 100)
    
    This uses learned coefficients from historical games to weight each four factor's
    contribution to the final score, then scales by game pace.
    
    Args:
        efg_edge: eFG% edge (Team A - Team B)
        tov_edge: TOV% edge (Team B - Team A, since lower is better)
        orb_edge: ORB% edge (Team A - Team B)
        ftr_edge: FTR edge (Team A - Team B)
        coef_efg: Efficiency points per 100 poss per 1% eFG edge
        coef_tov: Efficiency points per 100 poss per 1% TOV edge
        coef_orb: Efficiency points per 100 poss per 1% ORB edge
        coef_ftr: Efficiency points per 100 poss per 1% FTR edge
        coef_intercept: Baseline efficiency margin per 100 poss
        pace: Expected game pace (possessions per game)
    
    Returns:
        Dict with margin breakdown and total (scaled by pace)
    """
    # Compute contribution from each factor (per 100 possessions)
    eff_from_efg = efg_edge * coef_efg
    eff_from_tov = tov_edge * coef_tov
    eff_from_orb = orb_edge * coef_orb
    eff_from_ftr = ftr_edge * coef_ftr
    
    # Total predicted efficiency margin (per 100 possessions)
    efficiency_margin_100 = eff_from_efg + eff_from_tov + eff_from_orb + eff_from_ftr + coef_intercept
    
    # Scale by pace to get game margin
    pace_factor = pace / 100
    pts_from_efg = eff_from_efg * pace_factor
    pts_from_tov = eff_from_tov * pace_factor
    pts_from_orb = eff_from_orb * pace_factor
    pts_from_ftr = eff_from_ftr * pace_factor
    baseline = coef_intercept * pace_factor
    total_margin = efficiency_margin_100 * pace_factor
    
    return {
        'pts_from_efg': round(pts_from_efg, 2),
        'pts_from_tov': round(pts_from_tov, 2),
        'pts_from_orb': round(pts_from_orb, 2),
        'pts_from_ftr': round(pts_from_ftr, 2),
        'baseline': round(baseline, 2),
        'total_margin': round(total_margin, 2),
    }


def identify_top_drivers(
    efg_edge: float,
    tov_edge: float,
    orb_edge: float,
    ftr_edge: float,
    coef_efg: float,
    coef_tov: float,
    coef_orb: float,
    coef_ftr: float,
    pace: float
) -> list:
    """
    Identify the top 3 four factor drivers of the matchup.
    
    Returns factors sorted by their contribution to the margin (absolute value),
    with sign indicating which team has the advantage.
    
    Args:
        Four factor edges and their coefficients (per 100 poss)
        pace: Game pace (possessions per game) for scaling to game points
    
    Returns:
        List of dicts with factor name, edge, contribution, and team advantage
        Example: [
            {'factor': 'eFG%', 'edge': 3.7, 'points': 3.7, 'team': 'a'},
            {'factor': 'ORB%', 'edge': 2.5, 'points': 1.2, 'team': 'a'},
            {'factor': 'TOV%', 'edge': -1.3, 'points': -1.2, 'team': 'b'}
        ]
    """
    # Scale coefficients by pace to get game impact (not per-100-poss)
    pace_factor = pace / 100
    
    drivers = [
        {
            'factor': 'eFG%',
            'edge': efg_edge,
            'points': efg_edge * coef_efg * pace_factor,
            'team': 'a' if efg_edge > 0 else 'b'
        },
        {
            'factor': 'TOV%',
            'edge': tov_edge,
            'points': tov_edge * coef_tov * pace_factor,
            'team': 'a' if tov_edge > 0 else 'b'  # Already flipped (lower is better)
        },
        {
            'factor': 'ORB%',
            'edge': orb_edge,
            'points': orb_edge * coef_orb * pace_factor,
            'team': 'a' if orb_edge > 0 else 'b'
        },
        {
            'factor': 'FTR',
            'edge': ftr_edge,
            'points': ftr_edge * coef_ftr * pace_factor,
            'team': 'a' if ftr_edge > 0 else 'b'
        }
    ]
    
    # Sort by absolute contribution (most impactful first)
    drivers.sort(key=lambda x: abs(x['points']), reverse=True)
    
    # Round values and take top 3
    top_3 = []
    for driver in drivers[:3]:
        top_3.append({
            'factor': driver['factor'],
            'edge': round(driver['edge'], 2),
            'points': round(driver['points'], 2),
            'team': driver['team']
        })
    
    return top_3


def compute_shot_profile_edges(
    fg3_rate_a: float,
    fg3_pct_a: float,
    fg2_pct_a: float,
    fg3_rate_b: float,
    fg3_pct_b: float,
    fg2_pct_b: float
) -> Dict:
    """
    Compute shot profile edges between two teams.
    
    Compares:
    - 3-point attempt rate (% of FGA that are 3PA)
    - 3-point shooting percentage
    - 2-point shooting percentage
    
    Args:
        fg3_rate_a: Team A's 3-point attempt rate (%)
        fg3_pct_a: Team A's 3-point percentage (%)
        fg2_pct_a: Team A's 2-point percentage (%)
        fg3_rate_b: Team B's 3-point attempt rate (%)
        fg3_pct_b: Team B's 3-point percentage (%)
        fg2_pct_b: Team B's 2-point percentage (%)
    
    Returns:
        Dict with edges (positive = Team A advantage)
    """
    # Compute edges (Team A - Team B)
    fg3_rate_edge = fg3_rate_a - fg3_rate_b
    fg3_pct_edge = fg3_pct_a - fg3_pct_b
    fg2_pct_edge = fg2_pct_a - fg2_pct_b
    
    return {
        'fg3_rate_edge': round(fg3_rate_edge, 2),
        'fg3_pct_edge': round(fg3_pct_edge, 2),
        'fg2_pct_edge': round(fg2_pct_edge, 2),
        'fg3_rate_a': round(fg3_rate_a, 1),
        'fg3_rate_b': round(fg3_rate_b, 1),
        'fg3_pct_a': round(fg3_pct_a, 1),
        'fg3_pct_b': round(fg3_pct_b, 1),
        'fg2_pct_a': round(fg2_pct_a, 1),
        'fg2_pct_b': round(fg2_pct_b, 1),
    }


def compute_volatility_ranges(tempo_values, fg3_rate_values, variance_values=None):
    """
    Compute dynamic volatility ranges from current season distribution.
    Uses P5 and P95 to capture the practical range of D1 basketball.
    
    Args:
        tempo_values: Array-like of adj_tempo values (all teams in season)
        fg3_rate_values: Array-like of fg3_rate values (all teams in season)
        variance_values: Optional array-like of recent variance values
    
    Returns:
        Dict with ranges: {
            'tempo_range': (p5, p95),
            'fg3_rate_range': (p5, p95),
            'variance_range': (p5, p95) or default (5, 20)
        }
    """
    import numpy as np
    
    # Convert to numpy arrays if not already
    tempo_arr = np.array(tempo_values)
    fg3_arr = np.array(fg3_rate_values)
    
    # Calculate P5 and P95 for tempo and fg3_rate
    tempo_p5 = float(np.percentile(tempo_arr, 5))
    tempo_p95 = float(np.percentile(tempo_arr, 95))
    fg3_p5 = float(np.percentile(fg3_arr, 5))
    fg3_p95 = float(np.percentile(fg3_arr, 95))
    
    # Variance range (if provided, otherwise use sensible defaults)
    if variance_values is not None and len(variance_values) > 0:
        var_arr = np.array(variance_values)
        var_p5 = float(np.percentile(var_arr, 5))
        var_p95 = float(np.percentile(var_arr, 95))
    else:
        # Default variance range based on typical D1 game variance
        var_p5 = 5.0
        var_p95 = 20.0
    
    return {
        'tempo_range': (tempo_p5, tempo_p95),
        'fg3_rate_range': (fg3_p5, fg3_p95),
        'variance_range': (var_p5, var_p95),
    }


def compute_volatility_score(
    tempo_a: float,
    tempo_b: float,
    fg3_rate_a: float,
    fg3_rate_b: float,
    recent_variance_a: Optional[float] = None,
    recent_variance_b: Optional[float] = None,
    tempo_range: Optional[Tuple[float, float]] = None,
    fg3_rate_range: Optional[Tuple[float, float]] = None,
    variance_range: Optional[Tuple[float, float]] = None,
    weights: Optional[Tuple[float, float, float]] = None,
) -> Dict:
    """
    Compute game volatility score (0-100) based on factors that increase upset potential.
    
    Higher volatility = more unpredictable outcome, higher upset potential.
    
    Factors:
    1. Pace (SLOWER = more variance, fewer possessions for talent to prevail): 30% weight
    2. 3-point volume (more 3s = more variance): 40% weight
    3. Recent performance variance (inconsistency): 30% weight
    
    Score interpretation:
    - 0-30: Low volatility (predictable, fast pace settling to talent)
    - 31-60: Medium volatility (typical game)
    - 61-80: High volatility (slow pace + lots of 3s = upset potential)
    - 81-100: Extreme volatility (chaos game, anything can happen)
    
    Args:
        tempo_a: Team A's adjusted tempo
        tempo_b: Team B's adjusted tempo
        fg3_rate_a: Team A's 3-point attempt rate (%)
        fg3_rate_b: Team B's 3-point attempt rate (%)
        recent_variance_a: Team A's recent margin variance (optional)
        recent_variance_b: Team B's recent margin variance (optional)
        tempo_range: (P5, P95) tuple for tempo. If None, uses default (63.9, 75.2)
        fg3_rate_range: (P5, P95) tuple for fg3_rate. If None, uses default (27.9, 51.9)
        variance_range: (P5, P95) tuple for variance. If None, uses default (5, 20)
    
    Returns:
        Dict with volatility score and breakdown
    """
    # weights = (pace_weight, three_pt_weight, variance_weight)
    # NCAA defaults: 30/40/30 — NBA callers pass 40/20/40 (compressed 3P range)
    w_pace, w_3pt, w_var = weights if weights else (0.30, 0.40, 0.30)

    # Helper function to normalize to 0-100 range with clamping
    def norm_to_100(x: float, lo: float, hi: float) -> float:
        """Normalize x from range [lo, hi] to [0, 100], clamped to bounds"""
        return max(0, min(100, ((x - lo) / (hi - lo)) * 100))
    
    # Use provided ranges or fall back to historical defaults
    tempo_lo, tempo_hi = tempo_range if tempo_range else (63.9, 75.2)
    fg3_lo, fg3_hi = fg3_rate_range if fg3_rate_range else (27.9, 51.9)
    var_lo, var_hi = variance_range if variance_range else (5.0, 20.0)
    
    # 1. PACE SCORE (0-100)
    # INVERTED: Slower pace = higher volatility (fewer possessions = more random outcome)
    # tempo_range is dynamically calculated from current season (P5 to P95)
    avg_tempo = (tempo_a + tempo_b) / 2
    pace_percentile = norm_to_100(avg_tempo, tempo_lo, tempo_hi)
    pace_score = 100 - pace_percentile  # Invert: slow = volatile, fast = less volatile
    
    # 2. THREE-POINT VOLUME SCORE (0-100)
    # fg3_rate_range is dynamically calculated from current season (P5 to P95)
    avg_fg3_rate = (fg3_rate_a + fg3_rate_b) / 2
    three_pt_score = norm_to_100(avg_fg3_rate, fg3_lo, fg3_hi)
    
    # 3. VARIANCE SCORE (0-100)
    # If recent variance provided, use it; otherwise default to 50
    if recent_variance_a is not None and recent_variance_b is not None:
        # variance_range is dynamically calculated from current season (P5 to P95)
        avg_variance = (recent_variance_a + recent_variance_b) / 2
        variance_score = norm_to_100(avg_variance, var_lo, var_hi)
    else:
        variance_score = 50  # Default (no data)
    
    # WEIGHTED VOLATILITY SCORE
    volatility = (
        w_pace * pace_score +
        w_3pt  * three_pt_score +
        w_var  * variance_score
    )
    volatility = round(volatility, 1)
    
    # Calculate thresholds for reasons (approximate P10 and P90)
    tempo_p10 = tempo_lo + 0.05 * (tempo_hi - tempo_lo)  # ~10th percentile
    tempo_p90 = tempo_lo + 0.95 * (tempo_hi - tempo_lo)  # ~90th percentile
    fg3_p10 = fg3_lo + 0.05 * (fg3_hi - fg3_lo)  # ~10th percentile
    fg3_p90 = fg3_lo + 0.95 * (fg3_hi - fg3_lo)  # ~90th percentile
    
    # Generate reasons
    reasons = []
    
    if avg_tempo <= tempo_p10:  # ~10th percentile (SLOW)
        reasons.append(f"Slow pace increases upset potential ({avg_tempo:.1f} possessions)")
    elif avg_tempo >= tempo_p90:  # ~90th percentile (FAST)
        reasons.append(f"Fast pace favors the better team ({avg_tempo:.1f} possessions)")
    
    if avg_fg3_rate >= fg3_p90:  # ~90th percentile
        reasons.append(f"Heavy 3-point volume ({avg_fg3_rate:.1f}% of shots)")
    elif avg_fg3_rate <= fg3_p10:  # ~10th percentile
        reasons.append(f"Low 3-point rate ({avg_fg3_rate:.1f}% of shots)")
    
    if recent_variance_a and recent_variance_b:
        avg_var = (recent_variance_a + recent_variance_b) / 2
        if avg_var >= 15:
            reasons.append(f"High recent variance (±{avg_var:.1f} pts)")
        elif avg_var <= 8:
            reasons.append(f"Consistent recent performance (±{avg_var:.1f} pts)")
    
    # Style contrast
    tempo_diff = abs(tempo_a - tempo_b)
    if tempo_diff >= 5:  # ~2 standard deviations (std = 2.2)
        reasons.append(f"Major pace mismatch ({tempo_diff:.1f} possession gap)")
    
    fg3_diff = abs(fg3_rate_a - fg3_rate_b)
    if fg3_diff >= 15:  # ~2 standard deviations (std = 7.6)
        reasons.append(f"Contrasting shot styles ({fg3_diff:.1f}% 3P rate gap)")
    
    # Upset potential — check higher threshold first (elif 85 was unreachable before)
    upset_warning = None
    if volatility >= 85:
        upset_warning = "Extreme upset potential - anything can happen"
    elif volatility >= 70:
        upset_warning = "High upset potential"
    
    return {
        'volatility_score': volatility,
        'pace_component': round(pace_score, 1),
        'three_pt_component': round(three_pt_score, 1),
        'variance_component': round(variance_score, 1),
        'reasons': reasons[:3],  # Max 3 reasons
        'upset_warning': upset_warning,
    }


def format_recent_form(recent_games: list) -> Dict:
    """
    Format recent game results for API response.
    
    Args:
        recent_games: List of TeamGameStats objects (most recent first)
    
    Returns:
        Dict with recent performance summary
    """
    if not recent_games or len(recent_games) == 0:
        return {
            'games_analyzed': 0,
            'record': '0-0',
            'avg_margin': 0.0,
            'avg_ortg': 0.0,
            'variance': 0.0,
            'games': []
        }
    
    wins = 0
    losses = 0
    margins = []
    ortgs = []
    games_data = []
    
    for game_stat in recent_games:
        # Margin (positive = won, negative = lost)
        margin = game_stat.pts - game_stat.opponent_pts if hasattr(game_stat, 'opponent_pts') else 0
        
        # Determine W/L
        if game_stat.pts > getattr(game_stat, 'opponent_pts', 0):
            wins += 1
            result = 'W'
        else:
            losses += 1
            result = 'L'
        
        margins.append(margin)
        
        # Offensive rating (points per 100 possessions)
        if hasattr(game_stat, 'ortg_team') and game_stat.ortg_team:
            ortgs.append(game_stat.ortg_team)
        
        # Game data
        games_data.append({
            'date': game_stat.game.game_date.isoformat() if game_stat.game else None,
            'opponent': game_stat.opponent.name if game_stat.opponent else 'Unknown',
            'result': result,
            'score': f"{game_stat.pts}-{getattr(game_stat, 'opponent_pts', 0)}",
            'margin': margin,
        })
    
    # Calculate stats
    import statistics
    avg_margin = statistics.mean(margins) if margins else 0.0
    variance = statistics.stdev(margins) if len(margins) >= 2 else 0.0
    avg_ortg = statistics.mean(ortgs) if ortgs else 0.0
    
    return {
        'games_analyzed': len(recent_games),
        'record': f"{wins}-{losses}",
        'avg_margin': round(avg_margin, 1),
        'avg_ortg': round(avg_ortg, 1) if ortgs else None,
        'variance': round(variance, 1),
        'games': games_data[:5],  # Return max 5 games for display
    }


def compute_wab_for_team(
    team_ratings,
    bubble_ratings,
    team_games,
    nat_avg_ortg: float,
    hca_points: float,
    sigma: float
) -> float:
    """
    Compute WAB (Wins Above Bubble) for a team.
    
    WAB_T = Σ (Result_g - pBubble_g)
    where:
    - Result_g = 1 if team won game g, else 0
    - pBubble_g = probability that Bubble Team (#45 ranked) would win that same game
    
    Args:
        team_ratings: TeamSeasonRatings for the team
        bubble_ratings: TeamSeasonRatings for the Bubble Team (#45 ranked)
        team_games: QuerySet of TeamGameStats for the team (completed games only)
        nat_avg_ortg: National average offensive rating
        hca_points: Home court advantage in points
        sigma: Prediction standard deviation
    
    Returns:
        WAB value (float)
    """
    wab = 0.0
    
    for game_stat in team_games:
        # Get opponent ratings
        from ncaa.models import TeamSeasonRatings
        try:
            opp_ratings = TeamSeasonRatings.objects.get(
                team=game_stat.opponent,
                season=team_ratings.season
            )
        except TeamSeasonRatings.DoesNotExist:
            # Skip non-D1 opponents or opponents without ratings
            continue
        
        # Determine result (1 if won, 0 if lost)
        try:
            from ncaa.models import TeamGameStats
            opp_stat = TeamGameStats.objects.get(
                game=game_stat.game,
                team=game_stat.opponent
            )
            result = 1.0 if game_stat.pts > opp_stat.pts else 0.0
        except TeamGameStats.DoesNotExist:
            continue
        
        # Determine site from team perspective
        if game_stat.home_away == 'H':
            site = 'home'  # Team at home
        elif game_stat.home_away == 'A':
            site = 'away'  # Team away
        else:
            site = 'neutral'
        
        # Compute pBubble_g: probability that Bubble Team would win
        # Treat Bubble Team as if it were the actual team in this game
        forecast = forecast_game(
            adj_o_a=bubble_ratings.adj_o,
            adj_d_a=bubble_ratings.adj_d,
            adj_em_a=bubble_ratings.adj_em,
            tempo_a=bubble_ratings.adj_tempo,
            adj_o_b=opp_ratings.adj_o,
            adj_d_b=opp_ratings.adj_d,
            adj_em_b=opp_ratings.adj_em,
            tempo_b=opp_ratings.adj_tempo,
            nat_avg_ortg=nat_avg_ortg,
            hca_points=hca_points,
            sigma=sigma,
            site=site
        )
        
        # Extract bubble win probability
        p_bubble = forecast['prob_a']  # Bubble team is "Team A" in forecast
        
        # Add contribution to WAB
        wab += (result - p_bubble)
    
    return wab


