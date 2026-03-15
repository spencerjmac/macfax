"""
Cinderella Index API View

Computes a two-part Cinderella dangerness score for tournament-eligible teams:

  Profile Score (0-100) — team-only, available before the bracket:
    28% Underseeded Strength  (AdjEM percentile; + seed residual when bracket is set)
    27% Defense Score         (AdjD, opp eFG%, forced TOV%)
    21% Possession Score      (TOV% avoided, forced TOV%, ORB%)
    14% Variance Score        (3PA rate, 3P%, slow tempo)
    10% Resume Legitimacy     (WAB, SOS difficulty)

  (Experience component dropped — weight redistributed 3% each to Defense + Possession)

All percentiles are computed against the full D1 field so scores remain
stable regardless of what seed-range filter the user selects.
"""

import math
import numpy as np
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from core.models import Season, TeamSeasonRatings, TeamSeasonMetrics
from .serializers import RankingsSerializer


# ---------------------------------------------------------------------------
# Percentile helpers
# ---------------------------------------------------------------------------

def _pct_higher(val: float, arr: np.ndarray) -> float:
    """Fraction of teams with value ≤ val (higher is better → higher = better pct)."""
    if arr.size <= 1:
        return 0.5
    return float(np.mean(arr <= val))


def _pct_lower(val: float, arr: np.ndarray) -> float:
    """Fraction of teams with value ≥ val (lower is better → lower = better pct)."""
    if arr.size <= 1:
        return 0.5
    return float(np.mean(arr >= val))


# ---------------------------------------------------------------------------
# Context builder — arrays for percentile computation across all D1 teams
# ---------------------------------------------------------------------------

def _build_context(all_ratings, metrics_map):
    # Sort by AdjEM for expected-seed computation
    sorted_by_em = sorted(all_ratings, key=lambda r: r.adj_em, reverse=True)
    adj_em_ranks = {r.team_id: idx + 1 for idx, r in enumerate(sorted_by_em)}

    fg3_rates, fg3_pcts = [], []
    for r in all_ratings:
        m = metrics_map.get(r.team_id)
        if m:
            if m.total_fga and m.total_fga > 0:
                fg3_rates.append(m.total_fg3a / m.total_fga)
            if m.total_fg3a and m.total_fg3a > 0:
                fg3_pcts.append(m.total_fg3m / m.total_fg3a)

    wab_vals  = [r.wab        for r in all_ratings if r.wab        is not None]
    sos_vals  = [r.sos_win_pct for r in all_ratings if r.sos_win_pct is not None]

    ctx = {
        'adj_em_ranks':    adj_em_ranks,
        'n_teams':         len(all_ratings),
        'all_adj_em':      np.array([r.adj_em            for r in all_ratings]),
        'all_adj_d':       np.array([r.adj_d             for r in all_ratings]),
        'all_adj_opp_efg': np.array([r.adj_opp_efg_pct   for r in all_ratings]),
        'all_adj_opp_tov': np.array([r.adj_opp_tov_pct   for r in all_ratings]),
        'all_adj_tov':     np.array([r.adj_tov_pct       for r in all_ratings]),
        'all_adj_orb':     np.array([r.adj_orb_pct       for r in all_ratings]),
        'all_adj_tempo':   np.array([r.adj_tempo         for r in all_ratings]),
        'all_wab':         np.array(wab_vals)  if wab_vals  else np.array([]),
        'all_sos':         np.array(sos_vals)  if sos_vals  else np.array([]),
        'all_fg3_rate':    np.array(fg3_rates) if fg3_rates else np.array([]),
        'all_fg3_pct':     np.array(fg3_pcts)  if fg3_pcts  else np.array([]),
    }

    # Pre-compute seed residuals if bracket data exists
    seeded = [
        (r.team_id, r.tournament_seed, adj_em_ranks[r.team_id])
        for r in all_ratings if r.tournament_seed is not None
    ]
    if seeded:
        residuals = {
            tid: seed - min(16, max(1, math.ceil(rank / 4)))
            for tid, seed, rank in seeded
        }
        ctx['seed_residuals']     = residuals
        ctx['all_seed_residuals'] = np.array(list(residuals.values()), dtype=float)

    return ctx


# ---------------------------------------------------------------------------
# Scoring engine
# ---------------------------------------------------------------------------

def _score(rating, ctx, metrics):
    r   = rating
    m   = metrics  # TeamSeasonMetrics or None
    p_h = _pct_higher
    p_l = _pct_lower

    # ── Underseeded Strength ──────────────────────────────────────────────
    adj_em_pct = p_h(r.adj_em, ctx['all_adj_em'])

    seed_residual = None
    if r.tournament_seed is not None and 'seed_residuals' in ctx:
        residuals     = ctx['seed_residuals']
        residual_arr  = ctx['all_seed_residuals']
        raw_residual  = residuals.get(r.team_id, 0.0)
        seed_res_pct  = p_h(raw_residual, residual_arr)
        seed_residual = raw_residual
        underseeded   = 0.70 * adj_em_pct + 0.30 * seed_res_pct
    else:
        underseeded = adj_em_pct

    # ── Defense Score ─────────────────────────────────────────────────────
    adj_d_pct       = p_l(r.adj_d,          ctx['all_adj_d'])
    opp_efg_pct     = p_l(r.adj_opp_efg_pct, ctx['all_adj_opp_efg'])
    opp_tov_pct     = p_h(r.adj_opp_tov_pct, ctx['all_adj_opp_tov'])
    defense         = 0.50 * adj_d_pct + 0.30 * opp_efg_pct + 0.20 * opp_tov_pct

    # ── Possession Score ──────────────────────────────────────────────────
    tov_avoid_pct   = p_l(r.adj_tov_pct,  ctx['all_adj_tov'])
    orb_pct         = p_h(r.adj_orb_pct,  ctx['all_adj_orb'])
    possession      = 0.40 * tov_avoid_pct + 0.35 * opp_tov_pct + 0.25 * orb_pct

    # ── Variance Score ────────────────────────────────────────────────────
    fg3_rate_val = fg3_pct_val = None
    if m:
        if m.total_fga and m.total_fga > 0:
            fg3_rate_val = m.total_fg3a / m.total_fga
        if m.total_fg3a and m.total_fg3a > 0:
            fg3_pct_val = m.total_fg3m / m.total_fg3a

    fg3_rate_p   = p_h(fg3_rate_val, ctx['all_fg3_rate']) if (fg3_rate_val is not None and ctx['all_fg3_rate'].size > 0) else 0.5
    fg3_pct_p    = p_h(fg3_pct_val,  ctx['all_fg3_pct'])  if (fg3_pct_val  is not None and ctx['all_fg3_pct'].size  > 0) else 0.5
    slow_pct     = p_l(r.adj_tempo,  ctx['all_adj_tempo'])
    variance     = 0.45 * fg3_rate_p + 0.25 * fg3_pct_p + 0.30 * slow_pct

    # ── Resume Legitimacy ─────────────────────────────────────────────────
    wab_p   = p_h(r.wab,          ctx['all_wab']) if (r.wab          is not None and ctx['all_wab'].size  > 0) else 0.5
    sos_p   = p_l(r.sos_win_pct,  ctx['all_sos']) if (r.sos_win_pct  is not None and ctx['all_sos'].size   > 0) else 0.5
    resume  = 0.60 * wab_p + 0.40 * sos_p

    # ── Combined Profile ──────────────────────────────────────────────────
    profile = (
        0.28 * underseeded +
        0.27 * defense     +
        0.21 * possession  +
        0.14 * variance    +
        0.10 * resume
    )

    return {
        'profile_score':       round(profile     * 100, 1),
        'underseeded_strength': round(underseeded * 100, 1),
        'defense_score':        round(defense     * 100, 1),
        'possession_score':     round(possession  * 100, 1),
        'variance_score':       round(variance    * 100, 1),
        'resume_score':         round(resume      * 100, 1),
        'seed_residual':        seed_residual,
        # Raw component percentiles for tooltip detail
        'components': {
            'adj_em_pct':    round(adj_em_pct    * 100, 1),
            'adj_d_pct':     round(adj_d_pct     * 100, 1),
            'opp_efg_pct':   round(opp_efg_pct   * 100, 1),
            'opp_tov_pct':   round(opp_tov_pct   * 100, 1),
            'tov_avoid_pct': round(tov_avoid_pct * 100, 1),
            'orb_pct':       round(orb_pct       * 100, 1),
            'fg3_rate_pct':  round(fg3_rate_p    * 100, 1),
            'fg3_pct_pct':   round(fg3_pct_p     * 100, 1),
            'slow_tempo_pct': round(slow_pct     * 100, 1),
            'wab_pct':       round(wab_p         * 100, 1),
            'sos_pct':       round(sos_p         * 100, 1),
        },
    }


# ---------------------------------------------------------------------------
# API View
# ---------------------------------------------------------------------------

class CinderellaView(APIView):
    """
    GET /api/viz/cinderella/?season=2026&min_seed=9&max_seed=16

    Query params:
      season    – season year (default: current)
      min_seed  – minimum tournament seed to include (default: 9 if bracket loaded, else ignored)
      max_seed  – maximum tournament seed to include (default: 16)
      show_all  – "true" to include all D1 teams regardless of seed
    """

    def get(self, request):
        season_year = request.query_params.get('season')
        min_seed    = request.query_params.get('min_seed')
        max_seed    = request.query_params.get('max_seed')
        show_all    = request.query_params.get('show_all', 'false').lower() == 'true'

        if season_year:
            season = get_object_or_404(Season, year=season_year)
        else:
            season = Season.objects.filter(is_current=True).first()
            if not season:
                return Response({'error': 'No current season found'},
                                status=status.HTTP_404_NOT_FOUND)

        all_ratings = list(
            TeamSeasonRatings.objects
            .filter(season=season, team__is_d1=True)
            .select_related('team')
        )
        if not all_ratings:
            return Response({'error': 'No ratings found for this season'},
                            status=status.HTTP_404_NOT_FOUND)

        metrics_map = {
            m.team_id: m
            for m in TeamSeasonMetrics.objects.filter(season=season)
        }

        ctx           = _build_context(all_ratings, metrics_map)
        has_tournament = bool(ctx.get('seed_residuals'))
        conf_ser      = RankingsSerializer()

        # Decide which teams to show in the response
        if show_all:
            display_ratings = all_ratings
        elif has_tournament:
            lo = int(min_seed) if min_seed else 9
            hi = int(max_seed) if max_seed else 16
            display_ratings = [
                r for r in all_ratings
                if r.tournament_seed is not None and lo <= r.tournament_seed <= hi
            ]
        else:
            # No bracket yet — show all D1 teams so the page is still useful
            display_ratings = all_ratings

        results = []
        for r in display_ratings:
            cin = _score(r, ctx, metrics_map.get(r.team_id))
            results.append({
                'team_name':         r.team.name,
                'team_slug':         r.team.slug,
                'team_logo':         r.team.logo_url,
                'conference':        conf_ser.get_conference(r),
                'record':            f'{r.wins}-{r.losses}',
                'rank':              ctx['adj_em_ranks'].get(r.team_id),
                'adj_em':            round(r.adj_em,    1),
                'adj_d':             round(r.adj_d,     1),
                'adj_tempo':         round(r.adj_tempo, 1),
                'tournament_seed':   r.tournament_seed,
                'tournament_region': r.tournament_region,
                'cinderella':        cin,
            })

        # Sort by profile_score descending
        results.sort(key=lambda x: -x['cinderella']['profile_score'])

        return Response({
            'season':           season.year,
            'season_display':   season.display_name,
            'has_tournament':   has_tournament,
            'total_teams':      len(results),
            'teams':            results,
        })
