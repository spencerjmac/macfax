"""
Efficiency Landscape API View

Provides data for the Efficiency Landscape visualization showing team positioning
by our computed Adjusted Offensive (Adj O), Adjusted Defensive (Adj D), and 
Adjusted Efficiency Margin (Adj EM) ratings.
Teams are categorized into tiers based on their Adj EM relative to the best team.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from core.models import Season, TeamSeasonRatings


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
        
        # Build base queryset - use our computed ratings from TeamSeasonRatings
        # CRITICAL: Only include D1 teams
        queryset = TeamSeasonRatings.objects.filter(
            season=season,
            team__is_d1=True  # Only D1 teams
        ).select_related('team')
        
        # Order by Adj EM descending
        queryset = queryset.order_by('-adj_em')
        
        # Get all teams for conference filtering
        all_ratings = list(queryset)
        
        if not all_ratings:
            return Response(
                {'error': 'No teams found with computed ratings for this season'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Use RankingsSerializer for conference lookup (same as trapezoid)
        from .serializers import RankingsSerializer
        serializer = RankingsSerializer()
        
        # Build team data with conference info
        all_teams_data = []
        for rating in all_ratings:
            conference_code = serializer.get_conference(rating)
            # Get conference name from code
            from core.models import Conference as ConfModel
            try:
                conf_obj = ConfModel.objects.get(code=conference_code)
                conference_name = conf_obj.name
            except ConfModel.DoesNotExist:
                conference_name = conference_code
            
            all_teams_data.append({
                'rating': rating,
                'conference_code': conference_code,
                'conference_name': conference_name,
            })
        
        # NATIONAL BASELINE: Calculate max_net from ALL D1 teams (before conference filter)
        # This ensures tier boundaries stay constant regardless of conference selection
        max_net = max(t['rating'].adj_em for t in all_teams_data)
        
        # Filter by conference AFTER computing national baseline
        if conference_filter and conference_filter.upper() != 'ALL':
            teams_data = [t for t in all_teams_data if t['conference_code'] == conference_filter]
        else:
            teams_data = all_teams_data
        
        # Take top N teams
        teams_data = teams_data[:top_n]
        
        if not teams_data:
            return Response(
                {'error': 'No teams found matching criteria'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Build response
        teams_list = []
        for team_data in teams_data:
            rating = team_data['rating']
            teams_list.append({
                'team_name': rating.team.name,
                'team_slug': rating.team.slug,
                'conference': team_data['conference_code'],
                'conference_name': team_data['conference_name'],
                'o_rate': round(rating.adj_o, 1),
                'd_rate': round(rating.adj_d, 1),
                'net': round(rating.adj_em, 1),
                'logo_url': rating.team.logo_url,
                'rank': rating.rank_adj_em,
                'record': f"{rating.wins}-{rating.losses}",
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
