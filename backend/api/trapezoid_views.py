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

from core.models import Season, TeamSeasonStats
from .trapezoid_config import (
    X_LEFT_TOP_QUANTILE, X_RIGHT_TOP_QUANTILE,
    X_LEFT_BOT_QUANTILE, X_RIGHT_BOT_QUANTILE,
    Y_TOP_QUANTILE, Y_BOT_QUANTILE,
    X_LEFT_BOT_FALLBACK, X_RIGHT_BOT_FALLBACK,
    Y_BOT_FALLBACK, QUANTILE_METHOD
)


def calculate_quantile(values, q, method='linear'):
    """Calculate quantile using numpy with specified interpolation method"""
    return np.quantile(values, q, method=method)


def compute_trapezoid_boundaries(tempo_values, em_values):
    """
    Compute trapezoid boundaries from tempo and em arrays using quantiles.
    
    Returns:
        dict: Dictionary with trapezoid boundary coordinates
    """
    # Calculate initial quantiles
    x_left_top = calculate_quantile(tempo_values, X_LEFT_TOP_QUANTILE, QUANTILE_METHOD)
    x_right_top = calculate_quantile(tempo_values, X_RIGHT_TOP_QUANTILE, QUANTILE_METHOD)
    x_left_bot = calculate_quantile(tempo_values, X_LEFT_BOT_QUANTILE, QUANTILE_METHOD)
    x_right_bot = calculate_quantile(tempo_values, X_RIGHT_BOT_QUANTILE, QUANTILE_METHOD)
    
    y_top = calculate_quantile(em_values, Y_TOP_QUANTILE, QUANTILE_METHOD)
    y_bot = calculate_quantile(em_values, Y_BOT_QUANTILE, QUANTILE_METHOD)
    
    # Validate and fix X-axis ordering
    if not (x_left_top < x_left_bot < x_right_bot < x_right_top):
        # Fallback: use min/max for top, fallback quantiles for bottom
        x_left_top = float(np.min(tempo_values))
        x_right_top = float(np.max(tempo_values))
        x_left_bot = calculate_quantile(tempo_values, X_LEFT_BOT_FALLBACK, QUANTILE_METHOD)
        x_right_bot = calculate_quantile(tempo_values, X_RIGHT_BOT_FALLBACK, QUANTILE_METHOD)
    
    # Validate and fix Y-axis ordering
    if y_bot >= y_top:
        y_bot = calculate_quantile(em_values, Y_BOT_FALLBACK, QUANTILE_METHOD)
        # If still invalid, use a fixed offset
        if y_bot >= y_top:
            y_bot = y_top - 1.0
    
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
            slope = (y_bot - y_top) / (x_right_top - x_right_bot)
            y_min = y_top + slope * (x - x_right_bot)
    
    # Must be above bottom boundary
    return y >= y_min


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
        all_teams_queryset = TeamSeasonStats.objects.filter(
            season=season
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
        
        # Now build filtered queryset for display
        display_queryset = TeamSeasonStats.objects.filter(
            season=season
        ).select_related('team', 'conference')
        
        # Apply conference filter to display queryset only
        if conference_filter and conference_filter != 'ALL':
            display_queryset = display_queryset.filter(conference__code=conference_filter)
        
        # Get top N teams by adj_em (descending)
        display_queryset = display_queryset.order_by('-adj_em')[:top_n]
        
        # Convert to list for processing
        teams_data = list(display_queryset.values(
            'team_id',
            'team__name',
            'team__slug',
            'team__logo_url',
            'adj_tempo',
            'adj_em',
            'conference__code',
            'conference__name',
            'rank',
            'wins',
            'losses',
        ))
        
        if not teams_data:
            return Response(
                {'error': 'No teams found matching criteria'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Build team list with inside_trapezoid flag
        teams = []
        for t in teams_data:
            inside = is_inside_trapezoid(t['adj_tempo'], t['adj_em'], trapezoid)
            teams.append({
                'team_id': t['team_id'],
                'team_name': t['team__name'],
                'team_slug': t['team__slug'],
                'adj_tempo': round(t['adj_tempo'], 2),
                'adj_em': round(t['adj_em'], 2),
                'conference': t['conference__code'],
                'conference_name': t['conference__name'],
                'logo_url': t['team__logo_url'],
                'rank': t['rank'],
                'record': f"{t['wins']}-{t['losses']}",
                'inside_trapezoid': inside,
            })
        
        # Build response
        response_data = {
            'meta': {
                'season': season.year,
                'season_display': season.display_name,
                'conference': conference_filter,
                'top': top_n,
                'total_teams': len(teams),
                'quantiles_used': {
                    'x_left_top': X_LEFT_TOP_QUANTILE,
                    'x_right_top': X_RIGHT_TOP_QUANTILE,
                    'x_left_bot': X_LEFT_BOT_QUANTILE,
                    'x_right_bot': X_RIGHT_BOT_QUANTILE,
                    'y_top': Y_TOP_QUANTILE,
                    'y_bot': Y_BOT_QUANTILE,
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
