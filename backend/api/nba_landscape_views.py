"""
NBA Efficiency Landscape API View

Provides data for the NBA Efficiency Landscape visualization: team
positioning by Adjusted Offensive (Adj Off) and Adjusted Defensive (Adj Def)
rating, plus three tier lines (Champion / Contender / Playoff), each a
constant-Adj-Net diagonal halfway between the Nth and (N+1)th team (top 7 /
top 10 / top 15). Ranks and calibration: backend/api/nba_landscape_config.py.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from nba.analytics.standings import compute_standings
from nba.models import NBASeason, NBATeamSeasonRatings

from . import nba_landscape_config as cfg


class NBAEfficiencyLandscapeView(APIView):
    """
    GET /api/viz/nba-landscape/?season=2026

    Response:
    {
        "season": 2026,
        "season_display": "2025-26",
        "max_net": 9.31,
        "lines": {
            "champion": {"n": 7, "net": 2.515},
            "contender": {"n": 10, "net": 1.173},
            "playoff": {"n": 15, "net": 0.171}
        },
        "teams": [
            {
                "team_name": "Oklahoma City Thunder",
                "team_slug": "oklahoma-city-thunder",
                "team_abbreviation": "OKC",
                "conference": "West",
                "logo_url": "...",
                "o_rate": 118.4123,
                "d_rate": 109.1047,
                "net": 9.31,
                "rank": 1,
                "record": "12-3",
                "playoff_finish": null
            },
            ...
        ]
    }
    """

    def get(self, request):
        season_year = request.query_params.get('season')

        if season_year:
            season = get_object_or_404(NBASeason, year=season_year)
        else:
            season = NBASeason.objects.filter(is_current=True).first()
            if not season:
                return Response(
                    {'error': 'No current season found'},
                    status=status.HTTP_404_NOT_FOUND
                )

        ratings = list(
            NBATeamSeasonRatings.objects.filter(
                season=season,
                season_type='regular',
                adj_net__isnull=False,
            )
            .select_related('team')
            .order_by('-adj_net')
        )

        if not ratings:
            return Response(
                {'error': 'No teams found with computed ratings for this season'},
                status=status.HTTP_404_NOT_FOUND
            )

        max_net = ratings[0].adj_net
        lines = cfg.landscape_lines(r.adj_net for r in ratings)

        standings_by_team = {
            row['team_id']: row for row in compute_standings(season.year, season_type='regular')
        }

        teams_list = []
        for rating in ratings:
            record = standings_by_team.get(rating.team_id)
            record_str = f"{record['wins']}-{record['losses']}" if record else "0-0"
            teams_list.append({
                'team_name': rating.team.name,
                'team_slug': rating.team.slug,
                'team_abbreviation': rating.team.abbreviation,
                'conference': rating.team.conference,
                'logo_url': rating.team.logo_url,
                # Full precision so each dot sits on the correct side of the tier lines
                # (rounding o and d separately moved dots up to 0.1); pages format to 0.1.
                'o_rate': rating.adj_off,
                'd_rate': rating.adj_def,
                'net': round(rating.adj_net, 1),
                'rank': rating.rank_adj_net,
                'record': record_str,
                'playoff_finish': rating.playoff_finish,
            })

        response_data = {
            'season': season.year,
            'season_display': season.display_name,
            'max_net': round(max_net, 1),
            'lines': lines,
            'teams': teams_list,
        }

        return Response(response_data, status=status.HTTP_200_OK)
