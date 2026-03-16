"""
Bracket Simulator API View

GET /api/viz/bracket/?season=2026&n_sims=2000

Returns the full tournament bracket with Monte Carlo win probabilities
for each team reaching each round.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from core.models import Season, TeamSeasonRatings, NationalAverages

from .bracket_engine import (
    BRACKET_REGIONS,
    R64_PODS,
    FF_PAIRINGS,
    build_bracket_from_ratings,
    simulate_tournament,
)

_DEFAULT_SIGMA = 11.08
_DEFAULT_NAT_AVG = 108.0
_DEFAULT_HCA = 3.5


class BracketView(APIView):
    """
    GET /api/viz/bracket/?season=2026&n_sims=2000

    Query params:
      season  – season year (default: current)
      n_sims  – Monte Carlo simulation count (default: 2000, max: 10000)
    """

    def get(self, request):
        season_year = request.query_params.get('season')
        n_sims = min(int(request.query_params.get('n_sims', 2000)), 10000)

        if season_year:
            season = get_object_or_404(Season, year=season_year)
        else:
            season = Season.objects.filter(is_current=True).first()
            if not season:
                return Response({'error': 'No current season found'},
                                status=status.HTTP_404_NOT_FOUND)

        # National averages
        try:
            nat = NationalAverages.objects.get(season=season)
            nat_avg_ortg = nat.avg_ortg or _DEFAULT_NAT_AVG
            sigma = nat.prediction_sigma or _DEFAULT_SIGMA
        except NationalAverages.DoesNotExist:
            nat_avg_ortg = _DEFAULT_NAT_AVG
            sigma = _DEFAULT_SIGMA

        # Load tournament teams
        all_ratings = list(
            TeamSeasonRatings.objects
            .filter(season=season, tournament_seed__isnull=False)
            .select_related('team')
        )

        if not all_ratings:
            return Response(
                {'error': 'No tournament bracket data found for this season'},
                status=status.HTTP_404_NOT_FOUND,
            )

        bracket = build_bracket_from_ratings(all_ratings)
        if not bracket:
            return Response(
                {'error': 'Could not build bracket from tournament data'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Run simulation
        probs = simulate_tournament(bracket, nat_avg_ortg, sigma, n_sims)

        # Build region payloads: list of slots in R64_PODS order
        regions_payload: dict = {}
        for region in BRACKET_REGIONS:
            region_seeds = bracket.get(region, {})
            slots = []
            seen_seeds = set()
            for s_high, s_low in R64_PODS:
                for seed in (s_high, s_low):
                    if seed in seen_seeds:
                        continue
                    seen_seeds.add(seed)
                    teams_in_slot = region_seeds.get(seed, [])
                    slots.append({
                        'seed': seed,
                        'is_first_four': len(teams_in_slot) == 2,
                        'teams': [
                            {
                                'team_id':   t.team_id,
                                'name':      t.name,
                                'slug':      t.slug,
                                'logo_url':  t.logo_url,
                                'seed':      t.seed,
                                'region':    t.region,
                                'adj_em':    round(t.adj_em, 1),
                                'record':    f'{t.wins}-{t.losses}',
                                'is_first_four': t.is_first_four,
                            }
                            for t in teams_in_slot
                        ],
                    })
            regions_payload[region] = slots

        return Response({
            'season':       season.year,
            'season_label': getattr(season, 'display_name', str(season.year)),
            'n_sims':       n_sims,
            'ff_pairings':  [[a, b] for a, b in FF_PAIRINGS],
            'r64_pods':     [[a, b] for a, b in R64_PODS],
            'regions':      regions_payload,
            'probabilities': probs,
        })
