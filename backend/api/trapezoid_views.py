"""
Trapezoid of Excellence API View

Provides data for the Trapezoid of Excellence visualization with dynamically
calculated trapezoid boundaries based on the filtered dataset.
"""

import numpy as np
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from ncaa.models import Season, TeamSeasonRatings, TeamSeasonStats
from .trapezoid_config import (
    Q_BOT_EM, Q_X_LEFT_TOP, Q_X_RIGHT_TOP,
    Q_X_LEFT_BOT, Q_X_RIGHT_BOT,
    Y_PAD_MIN, Y_PAD_RATE, PACE_PAD,
    QUANTILE_METHOD
)


def calculate_quantile(values, q, method='linear'):
    """Calculate quantile using numpy with specified interpolation method"""
    return np.quantile(values, q, method=method)


def compute_trapezoid_boundaries(tempo_values, em_values):
    """
    Compute trapezoid boundaries using NATIONAL BASELINE approach.
    
    Algorithm (Ryan Hammer's method):
    1. Compute y_bot from national EM distribution (elite floor)
    2. Compute y_top to be ABOVE the best team nationally
    3. Define elite subset C = teams where adj_em >= y_bot
    4. Compute x-bounds from tempo distribution of elite subset C
    
    Args:
        tempo_values: numpy array of ALL D1 adj_tempo values (national)
        em_values: numpy array of ALL D1 adj_em values (national)
    
    Returns:
        dict: Dictionary with trapezoid boundary coordinates
    """
    # Step 1: Compute y_bot from national EM distribution (elite floor)
    y_bot = calculate_quantile(em_values, Q_BOT_EM, QUANTILE_METHOD)
    
    # Step 2: Compute y_top so it's ALWAYS above the best team
    y_max = float(np.max(em_values))
    y_range = y_max - y_bot
    y_pad = max(Y_PAD_MIN, Y_PAD_RATE * y_range)
    y_top = y_max + y_pad
    
    # Step 3: Define elite subset C (teams with adj_em >= y_bot)
    elite_mask = em_values >= y_bot
    elite_tempo_values = tempo_values[elite_mask]
    
    # Step 4: Compute x-bounds from tempo distribution of elite subset C
    # Top edge: Use MIN/MAX to capture full elite pace range
    # Bottom edge: Use 25th/75th percentiles for control band
    # If elite subset is too small, fall back to all teams
    if len(elite_tempo_values) < 10:
        elite_tempo_values = tempo_values
    
    x_left_top = float(np.min(elite_tempo_values)) - PACE_PAD
    x_right_top = float(np.max(elite_tempo_values)) + PACE_PAD
    x_left_bot = calculate_quantile(elite_tempo_values, Q_X_LEFT_BOT, QUANTILE_METHOD)
    x_right_bot = calculate_quantile(elite_tempo_values, Q_X_RIGHT_BOT, QUANTILE_METHOD)
    
    # Validate X-axis ordering
    if not (x_left_top < x_left_bot < x_right_bot < x_right_top):
        # Fallback: recompute from all teams if elite subset creates invalid ordering
        x_left_top = float(np.min(tempo_values)) - PACE_PAD
        x_right_top = float(np.max(tempo_values)) + PACE_PAD
        x_left_bot = calculate_quantile(tempo_values, Q_X_LEFT_BOT, QUANTILE_METHOD)
        x_right_bot = calculate_quantile(tempo_values, Q_X_RIGHT_BOT, QUANTILE_METHOD)
    
    return {
        'x_left_top': float(x_left_top),
        'x_right_top': float(x_right_top),
        'x_left_bot': float(x_left_bot),
        'x_right_bot': float(x_right_bot),
        'y_top': float(y_top),
        'y_bot': float(y_bot),
    }


def is_inside_trapezoid(x, y, trapezoid):
    """
    Test if a point (x=tempo, y=em) is inside the trapezoid.
    
    Args:
        x: adj_tempo value
        y: adj_em value
        trapezoid: dict with boundary coordinates
    
    Returns:
        bool: True if inside trapezoid
    """
    x_left_top = trapezoid['x_left_top']
    x_right_top = trapezoid['x_right_top']
    x_left_bot = trapezoid['x_left_bot']
    x_right_bot = trapezoid['x_right_bot']
    y_top = trapezoid['y_top']
    y_bot = trapezoid['y_bot']
    
    # Must be within X bounds
    if x < x_left_top or x > x_right_top:
        return False
    
    # Must be below top boundary
    if y > y_top:
        return False
    
    # Calculate bottom boundary y_min at this x position
    if x <= x_left_bot:
        # Left slant: interpolate between (x_left_top, y_top) and (x_left_bot, y_bot)
        if x_left_bot == x_left_top:
            y_min = y_bot
        else:
            slope = (y_bot - y_top) / (x_left_bot - x_left_top)
            y_min = y_top + slope * (x - x_left_top)
    elif x < x_right_bot:
        # Flat bottom
        y_min = y_bot
    else:
        # Right slant: interpolate between (x_right_bot, y_bot) and (x_right_top, y_top)
        if x_right_top == x_right_bot:
            y_min = y_bot
        else:
            slope = (y_top - y_bot) / (x_right_top - x_right_bot)
            y_min = y_bot + slope * (x - x_right_bot)
    
    # Must be above bottom boundary
    return y >= y_min


def trapezoid_margin(x, y, trapezoid):
    """
    Signed distance (in EM points) from a point (x=tempo, y=em) to the
    trapezoid's bottom boundary at that x position.

    Positive: inside, value = how far above the boundary.
    Negative: outside, value = how far short of the boundary.
    None: x is outside the trapezoid's x-range entirely (no boundary defined).
    """
    x_left_top = trapezoid['x_left_top']
    x_right_top = trapezoid['x_right_top']
    x_left_bot = trapezoid['x_left_bot']
    x_right_bot = trapezoid['x_right_bot']
    y_top = trapezoid['y_top']
    y_bot = trapezoid['y_bot']

    if x < x_left_top or x > x_right_top:
        return None

    if x <= x_left_bot:
        if x_left_bot == x_left_top:
            y_min = y_bot
        else:
            slope = (y_bot - y_top) / (x_left_bot - x_left_top)
            y_min = y_top + slope * (x - x_left_top)
    elif x < x_right_bot:
        y_min = y_bot
    else:
        if x_right_top == x_right_bot:
            y_min = y_bot
        else:
            slope = (y_top - y_bot) / (x_right_top - x_right_bot)
            y_min = y_bot + slope * (x - x_right_bot)

    return y - y_min


class TrapezoidView(APIView):
    """
    GET /api/viz/trapezoid?season=2026&conference=ALL&top=365
    
    Returns trapezoid visualization data with dynamically computed boundaries.
    
    Query Parameters:
    - season: year (default: current season)
    - conference: conference code or "ALL" (default: "ALL")
    - top: number of top teams to include by adj_em (default: 365)
    
    IMPORTANT: The trapezoid boundaries are ALWAYS computed from ALL teams in the 
    season, regardless of conference or top filters. This ensures the trapezoid 
    shape remains constant when switching conferences. Only the displayed teams 
    are filtered.
    
    Response:
    {
        "meta": {
            "season": 2026,
            "conference": "ALL",
            "top": 365,
            "total_teams": 365,
            "quantiles_used": {...}
        },
        "trapezoid": {
            "x_left_top": 62.5,
            "x_right_top": 72.8,
            ...
        },
        "averages": {
            "avg_tempo": 67.2,
            "avg_em": 5.3
        },
        "teams": [
            {
                "team_id": 1,
                "team_name": "Duke",
                "team_slug": "duke",
                "adj_tempo": 68.5,
                "adj_em": 28.3,
                "conference": "ACC",
                "logo_url": "...",
                "rank": 1,
                "record": "25-2",
                "inside_trapezoid": true
            },
            ...
        ]
    }
    """
    
    def get(self, request):
        # Parse query parameters
        season_year = request.query_params.get('season')
        conference_filter = request.query_params.get('conference', 'ALL')
        top_n = int(request.query_params.get('top', 365))
        
        # Get season
        if season_year:
            season = get_object_or_404(Season, year=season_year)
        else:
            season = Season.objects.filter(is_current=True).first()
            if not season:
                return Response(
                    {'error': 'No current season found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Build queryset for ALL teams (for trapezoid boundary calculation)
        # CRITICAL: Only include D1 teams
        all_teams_queryset = TeamSeasonRatings.all_objects.filter(
            season=season,
            team__is_d1=True,  # Only D1 teams
            games_played__gt=0,  # Exclude stubs (teams not D1 in this season)
            is_pre_tournament=True,
        ).values('adj_tempo', 'adj_em')
        
        # Extract tempo and em values from ALL teams for trapezoid boundaries
        all_teams_data = list(all_teams_queryset)
        if not all_teams_data:
            return Response(
                {'error': 'No teams found for season'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        all_tempo_values = np.array([t['adj_tempo'] for t in all_teams_data])
        all_em_values = np.array([t['adj_em'] for t in all_teams_data])
        
        # Compute trapezoid boundaries based on ALL teams
        trapezoid = compute_trapezoid_boundaries(all_tempo_values, all_em_values)
        
        # Calculate averages based on ALL teams (not filtered)
        avg_tempo = float(np.mean(all_tempo_values))
        avg_em = float(np.mean(all_em_values))
        
        # Now build queryset for display (get all teams first)
        # CRITICAL: Only include D1 teams
        display_queryset = TeamSeasonRatings.all_objects.filter(
            season=season,
            team__is_d1=True,  # Only D1 teams
            games_played__gt=0,  # Exclude stubs (teams not D1 in this season)
            is_pre_tournament=True,
        ).select_related('team').order_by('-adj_em')
        
        # Use the same serializer to get conference data (it has comprehensive mapping)
        # Import locally to avoid circular import
        from .serializers import RankingsSerializer
        serializer = RankingsSerializer()
        
        # For each rating, get the conference using the serializer
        all_teams_data = []
        for rating in display_queryset:
            conference_code = serializer.get_conference(rating)
            # Get conference name from code
            from ncaa.models import Conference as ConfModel
            try:
                conf_obj = ConfModel.objects.get(code=conference_code)
                conference_name = conf_obj.name
            except ConfModel.DoesNotExist:
                conference_name = conference_code
            
            all_teams_data.append({
                'team_id': rating.team_id,
                'team__name': rating.team.name,
                'team__slug': rating.team.slug,
                'team__logo_url': rating.team.logo_url,
                'adj_tempo': rating.adj_tempo,
                'adj_em': rating.adj_em,
                'conference__code': conference_code,
                'conference__name': conference_name,
                'rank_adj_em': rating.rank_adj_em,
                'wins': rating.wins,
                'losses': rating.losses,
                'net_100': rating.adj_em,
                'tournament_seed': rating.tournament_seed,
                'tournament_finish': rating.tournament_finish,
                'tournament_region': rating.tournament_region,
            })
        
        # Filter by conference / tournament AFTER getting conference data
        _TOURNAMENT_REGIONS = {'SOUTH', 'EAST', 'WEST', 'MIDWEST'}
        if not conference_filter or conference_filter == 'ALL':
            teams_data = all_teams_data
        elif conference_filter == 'NCAA_TOURNAMENT':
            teams_data = [t for t in all_teams_data if t['tournament_seed'] is not None]
        elif conference_filter in _TOURNAMENT_REGIONS:
            teams_data = [
                t for t in all_teams_data
                if t['tournament_region'] and t['tournament_region'].upper() == conference_filter
            ]
        else:
            teams_data = [t for t in all_teams_data if t['conference__code'] == conference_filter]
        
        # Take top N teams
        teams_data = teams_data[:top_n]
        
        if not teams_data:
            teams_data = []
        
        # Build team list with inside_trapezoid flag
        teams = []
        for t in teams_data:
            inside = is_inside_trapezoid(t['adj_tempo'], t['adj_em'], trapezoid)
            margin = trapezoid_margin(t['adj_tempo'], t['adj_em'], trapezoid)
            teams.append({
                'team_id': t['team_id'],
                'team_name': t['team__name'],
                'team_slug': t['team__slug'],
                'adj_tempo': round(t['adj_tempo'], 2),
                'adj_em': round(t['adj_em'], 2),
                'conference': t['conference__code'],
                'conference_name': t['conference__name'],
                'logo_url': t['team__logo_url'],
                'rank': t['rank_adj_em'],
                'record': f"{t['wins']}-{t['losses']}",
                'inside_trapezoid': inside,
                'trapezoid_margin': round(margin, 2) if margin is not None else None,
                'tournament_finish': t['tournament_finish'],
            })
        
        # Build response
        response_data = {
            'meta': {
                'season': season.year,
                'season_display': season.display_name,
                'conference': conference_filter,
                'top': top_n,
                'total_teams': len(teams),
                'trapezoid_basis': 'NATIONAL_D1',
                'quantiles_used': {
                    'q_bot_em': Q_BOT_EM,
                    'q_x_left_top': Q_X_LEFT_TOP,
                    'q_x_right_top': Q_X_RIGHT_TOP,
                    'q_x_left_bot': Q_X_LEFT_BOT,
                    'q_x_right_bot': Q_X_RIGHT_BOT,
                    'y_pad_min': Y_PAD_MIN,
                    'y_pad_rate': Y_PAD_RATE,
                    'pace_pad': PACE_PAD,
                    'method': QUANTILE_METHOD,
                }
            },
            'trapezoid': trapezoid,
            'averages': {
                'avg_tempo': round(avg_tempo, 2),
                'avg_em': round(avg_em, 2),
            },
            'teams': teams,
        }
        
        return Response(response_data)
