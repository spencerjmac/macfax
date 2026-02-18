"""
Efficiency Landscape API View

Provides data for the Efficiency Landscape visualization showing team positioning
by offensive rating (O-Rate/AOR), defensive rating (D-Rate/ADR), and net rating (AEM).
Teams are categorized into tiers based on their net rating relative to the best team.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from core.models import Season, TeamSeasonStats


# Default tier deltas (can be made configurable later)
TITLE_FAVORITES_DELTA = 6
FINAL_FOUR_DELTA = 12
HIT_OR_MISS_DELTA = 18


class EfficiencyLandscapeView(APIView):
    """
    GET /api/viz/landscape?season=2026&conference=ALL&top=365
    
    Returns efficiency landscape visualization data.
    
    Query Parameters:
    - season: year (default: current season)
    - conference: conference code or "ALL" (default: "ALL")
    - top: number of top teams to include by net rating (default: 365)
    
    Response:
    {
        "season": 2026,
        "season_display": "2025-26",
        "conference": "ALL",
        "top": 365,
        "max_net": 25.5,
        "defaults": {
            "title_delta": 6,
            "final4_delta": 12,
            "hit_miss_delta": 18
        },
        "teams": [
            {
                "team_name": "Duke",
                "team_slug": "duke",
                "conference": "ACC",
                "conference_name": "Atlantic Coast Conference",
                "o_rate": 122.5,
                "d_rate": 97.2,
                "net": 25.3,
                "logo_url": "...",
                "rank": 1,
                "record": "25-2"
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
        
        # Build base queryset
        queryset = TeamSeasonStats.objects.filter(
            season=season,
            em_o_rate__isnull=False,  # Only include teams with Evan Miya ratings
            em_d_rate__isnull=False,
            em_rating__isnull=False,
        ).select_related('team', 'conference')
        
        # Apply conference filter
        if conference_filter and conference_filter.upper() != 'ALL':
            queryset = queryset.filter(conference__code=conference_filter)
        
        # Order by Evan Miya relative rating descending
        queryset = queryset.order_by('-em_rating')
        
        # Limit to top N
        if top_n and top_n > 0:
            queryset = queryset[:top_n]
        
        # Convert to list to compute max_net
        teams_data = list(queryset)
        
        if not teams_data:
            return Response(
                {'error': 'No teams found with computed ratings for this season'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Compute max_net from the filtered dataset (Evan Miya Relative Rating)
        max_net = max(team.em_rating for team in teams_data)
        
        # Build response
        teams_list = []
        for team_stats in teams_data:
            teams_list.append({
                'team_name': team_stats.team.name,
                'team_slug': team_stats.team.slug,
                'conference': team_stats.conference.code if team_stats.conference else 'N/A',
                'conference_name': team_stats.conference.name if team_stats.conference else 'N/A',
                'o_rate': round(team_stats.em_o_rate, 1),
                'd_rate': round(team_stats.em_d_rate, 1),
                'net': round(team_stats.em_rating, 1),
                'logo_url': team_stats.team.logo_url,
                'rank': team_stats.rank,
                'record': team_stats.record,
            })
        
        response_data = {
            'season': season.year,
            'season_display': season.display_name,
            'conference': conference_filter,
            'top': top_n,
            'max_net': round(max_net, 1),
            'defaults': {
                'title_delta': TITLE_FAVORITES_DELTA,
                'final4_delta': FINAL_FOUR_DELTA,
                'hit_miss_delta': HIT_OR_MISS_DELTA,
            },
            'teams': teams_list,
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
