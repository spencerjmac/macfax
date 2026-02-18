"""
API Views for Viz Builder

Endpoints:
- GET /api/viz/stats - Returns stat catalog
- GET /api/viz/scatter - Returns scatter plot data with correlation/regression
"""

import numpy as np
from scipy import stats as scipy_stats
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.core.cache import cache

from core.models import Season, TeamSeasonStats
from .stat_catalog import get_stat_catalog, get_stat_metadata, is_valid_stat_key, get_stats_by_group


class VizStatsView(APIView):
    """
    GET /api/viz/stats?season=2026
    
    Returns the stat catalog with metadata for building the viz builder UI.
    Optionally filtered by season to only include stats with data.
    
    Response:
    {
        "groups": {
            "KenPom": [
                {
                    "key": "adj_o",
                    "label": "Adj Offensive Efficiency",
                    "description": "...",
                    "format": "rating",
                    "decimals": 1
                },
                ...
            ],
            ...
        },
        "count": 42
    }
    """
    
    def get(self, request):
        # Get season parameter (optional)
        season_year = request.query_params.get('season')
        
        # Get grouped stats
        grouped_stats = get_stats_by_group()
        
        # Format response
        response_data = {
            'groups': grouped_stats,
            'count': sum(len(stats) for stats in grouped_stats.values()),
        }
        
        if season_year:
            try:
                season = Season.objects.get(year=season_year)
                response_data['season'] = season.display_name
            except Season.DoesNotExist:
                pass
        
        return Response(response_data)


class VizScatterView(APIView):
    """
    GET /api/viz/scatter?season=2026&x=adj_o&y=adj_d&colorBy=conference
    
    Returns scatter plot data with correlation and regression statistics.
    
    Query params:
    - season: year (default: current season)
    - x: stat key for x-axis (required)
    - y: stat key for y-axis (required)
    - colorBy: 'conference' or None (default: None)
    
    Response:
    {
        "season": "2025-26",
        "x": { "key": "adj_o", "label": "...", "format": "rating", "decimals": 1 },
        "y": { "key": "adj_d", "label": "...", "format": "rating", "decimals": 1 },
        "stats": {
            "n": 362,
            "pearson_r": 0.123,
            "r2": 0.015,
            "slope": -0.234,
            "intercept": 125.6,
            "p_value": 0.023
        },
        "points": [
            {
                "team": "Utah State",
                "slug": "utah-state",
                "conference": "MWC",
                "x": 118.5,
                "y": 95.2
            },
            ...
        ],
        "last_updated": "2026-02-17T12:34:56Z"
    }
    """
    
    def get(self, request):
        # Validate required parameters
        x_key = request.query_params.get('x')
        y_key = request.query_params.get('y')
        
        if not x_key or not y_key:
            return Response(
                {'error': 'Both x and y parameters are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate stat keys
        if not is_valid_stat_key(x_key):
            return Response(
                {'error': f'Invalid stat key: {x_key}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not is_valid_stat_key(y_key):
            return Response(
                {'error': f'Invalid stat key: {y_key}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get season
        season_year = request.query_params.get('season')
        if season_year:
            season = get_object_or_404(Season, year=season_year)
        else:
            season = Season.objects.filter(is_current=True).first()
            if not season:
                return Response(
                    {'error': 'No current season found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Get color_by parameter
        color_by = request.query_params.get('colorBy')
        
        # Build cache key
        cache_key = f'viz_scatter:{season.year}:{x_key}:{y_key}:{color_by or "none"}'
        
        # Try to get from cache
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)
        
        # Query database
        queryset = TeamSeasonStats.objects.filter(season=season).select_related(
            'team', 'conference'
        ).only(
            'team__name', 'team__slug', 'team__logo_url', 'conference__code',
            x_key, y_key, 'last_updated'
        )
        
        # Extract data
        points = []
        x_values = []
        y_values = []
        last_updated = None
        
        for stat in queryset:
            x_val = getattr(stat, x_key, None)
            y_val = getattr(stat, y_key, None)
            
            # Skip if either value is None
            if x_val is None or y_val is None:
                continue
            
            point = {
                'team': stat.team.name,
                'slug': stat.team.slug,
                'conference': stat.conference.code if stat.conference else 'IND',
                'logo_url': stat.team.logo_url,
                'x': float(x_val),
                'y': float(y_val),
            }
            
            points.append(point)
            x_values.append(float(x_val))
            y_values.append(float(y_val))
            
            # Track most recent update
            if last_updated is None or stat.last_updated > last_updated:
                last_updated = stat.last_updated
        
        # Compute statistics
        stats_data = {}
        if len(x_values) >= 2:
            # Convert to numpy arrays
            x_array = np.array(x_values)
            y_array = np.array(y_values)
            
            # Pearson correlation
            pearson_r, p_value = scipy_stats.pearsonr(x_array, y_array)
            
            # Linear regression
            slope, intercept, r_value, p_val_reg, std_err = scipy_stats.linregress(x_array, y_array)
            
            stats_data = {
                'n': len(x_values),
                'pearson_r': float(pearson_r),
                'r2': float(r_value ** 2),
                'slope': float(slope),
                'intercept': float(intercept),
                'p_value': float(p_value),
            }
        else:
            stats_data = {
                'n': len(x_values),
                'pearson_r': None,
                'r2': None,
                'slope': None,
                'intercept': None,
                'p_value': None,
            }
        
        # Get metadata
        x_meta = get_stat_metadata(x_key)
        y_meta = get_stat_metadata(y_key)
        
        # Build response
        response_data = {
            'season': season.display_name,
            'x': {
                'key': x_meta['key'],
                'label': x_meta['label'],
                'format': x_meta['format'],
                'decimals': x_meta['decimals'],
            } if x_meta else {'key': x_key, 'label': x_key},
            'y': {
                'key': y_meta['key'],
                'label': y_meta['label'],
                'format': y_meta['format'],
                'decimals': y_meta['decimals'],
            } if y_meta else {'key': y_key, 'label': y_key},
            'stats': stats_data,
            'points': points,
            'last_updated': last_updated.isoformat() if last_updated else None,
        }
        
        # Cache for 5 minutes
        cache.set(cache_key, response_data, 300)
        
        return Response(response_data)
