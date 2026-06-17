"""
NBA Luck Chart API View

For each team: computes Pythagorean expected wins (exponent=14, NBA-standard)
from adj_off/adj_def, then derives wins_above_expected = actual_wins - expected_wins.
Returns all 30 teams plus the season's league_avg_net_rating (used as the scatter
chart's vertical divider — NOT hardcoded 0).
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from nba.analytics.standings import compute_standings
from nba.models import NBASeason, NBATeamSeasonRatings


class NBALuckChartView(APIView):
    """
    GET /api/viz/nba-luck-chart/?season=2026

    Response:
    {
        "season": 2026,
        "season_display": "2025-26",
        "league_avg_net_rating": 0.03,
        "teams": [
            {
                "team_name": "...", "team_slug": "...", "team_abbreviation": "OKC",
                "conference": "West", "logo_url": "...",
                "net_rating": 9.3, "ortg": 116.6, "drtg": 107.3,
                "actual_wins": 68, "actual_losses": 14, "games_played": 82,
                "expected_wins": 65.4, "wins_above_expected": 2.6,
                "quadrant": "hot"
            }, ...
        ]
    }

    Sorted by wins_above_expected descending.
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
                    status=status.HTTP_404_NOT_FOUND,
                )

        ratings = list(
            NBATeamSeasonRatings.objects.filter(
                season=season,
                season_type='regular',
                adj_net__isnull=False,
                adj_off__isnull=False,
                adj_def__isnull=False,
            )
            .select_related('team')
        )

        if not ratings:
            return Response(
                {'error': 'No teams found with computed ratings for this season'},
                status=status.HTTP_404_NOT_FOUND,
            )

        league_avg_net_rating = round(
            sum(r.adj_net for r in ratings) / len(ratings), 2
        )

        standings_by_team = {
            row['team_id']: row
            for row in compute_standings(season.year, season_type='regular')
        }

        teams_list = []
        for r in ratings:
            record = standings_by_team.get(r.team_id)
            actual_wins = record['wins'] if record else 0
            actual_losses = record['losses'] if record else 0
            games_played = actual_wins + actual_losses

            ortg = r.adj_off
            drtg = r.adj_def
            # NBA Pythagorean formula — exponent 14, not a linear approximation
            if games_played > 0 and ortg > 0 and drtg > 0:
                denom = ortg ** 14 + drtg ** 14
                expected_wins = (ortg ** 14 / denom) * games_played
            else:
                expected_wins = games_played / 2.0

            wins_above_expected = round(actual_wins - expected_wins, 1)
            expected_wins_rounded = round(expected_wins, 1)

            adj_net = r.adj_net
            wae = wins_above_expected
            if adj_net > league_avg_net_rating:
                quadrant = 'hot' if wae >= 0 else 'hidden_value'
            else:
                quadrant = 'overachieving' if wae >= 0 else 'struggling'

            teams_list.append({
                'team_name':           r.team.name,
                'team_slug':           r.team.slug,
                'team_abbreviation':   r.team.abbreviation,
                'conference':          r.team.conference,
                'logo_url':            r.team.logo_url,
                'net_rating':          round(adj_net, 1),
                'ortg':                round(ortg, 1),
                'drtg':                round(drtg, 1),
                'actual_wins':         actual_wins,
                'actual_losses':       actual_losses,
                'games_played':        games_played,
                'expected_wins':       expected_wins_rounded,
                'wins_above_expected': wins_above_expected,
                'quadrant':            quadrant,
            })

        teams_list.sort(key=lambda t: -t['wins_above_expected'])

        return Response({
            'season':                season.year,
            'season_display':        season.display_name,
            'league_avg_net_rating': league_avg_net_rating,
            'teams':                 teams_list,
        })
