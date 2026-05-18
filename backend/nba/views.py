"""
NBA API Views — macfax NBA app

Phase 1: Stub views that return empty/minimal data.
Phase 2: Populated by nba_sync_* management commands + real ingestion.
"""

import logging

from django.core.cache import cache
from django.db.models import Q
from rest_framework import viewsets, status

_log = logging.getLogger(__name__)
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    NBASeason,
    NBATeam,
    NBAGame,
    NBATeamGameStats,
    NBAPlayer,
    NBAPlayerSeasonStats,
    NBATeamSeasonRatings,
    NBAModelCalibration,
)
from .serializers import (
    NBASeasonSerializer,
    NBATeamSerializer,
    NBAGameSerializer,
    NBATeamGameStatsSerializer,
    NBAPlayerSerializer,
    NBAPlayerSeasonStatsSerializer,
    NBATeamSeasonRatingsSerializer,
    NBAModelCalibrationSerializer,
)


class NBASeasonViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/nba/seasons/"""

    queryset = NBASeason.objects.all()
    serializer_class = NBASeasonSerializer
    pagination_class = None


class NBATeamViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/nba/teams/ and /api/nba/teams/<slug>/"""

    serializer_class = NBATeamSerializer
    lookup_field = "slug"

    def get_queryset(self):
        qs = NBATeam.objects.all()
        conf = self.request.query_params.get("conference")
        if conf:
            qs = qs.filter(conference=conf)
        return qs


class NBARankingsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/nba/rankings/?season=2026

    Returns NBATeamSeasonRatings ordered by adj_net.
    Defaults to the current season if no season param is provided.
    """

    serializer_class = NBATeamSeasonRatingsSerializer

    def get_queryset(self):
        qs = NBATeamSeasonRatings.objects.select_related("team", "season")

        season_year = self.request.query_params.get("season")
        if season_year:
            qs = qs.filter(season__year=season_year)
        else:
            try:
                current = NBASeason.objects.get(is_current=True)
                qs = qs.filter(season=current)
            except NBASeason.DoesNotExist:
                return qs.none()

        season_type = self.request.query_params.get("season_type", "regular")
        qs = qs.filter(season_type=season_type)

        return qs.order_by("rank_adj_net", "-adj_net")


class NBAGameViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/nba/games/?season=2026&team=<slug>&season_type=regular
    """

    serializer_class = NBAGameSerializer

    def get_queryset(self):
        qs = NBAGame.objects.select_related("home_team", "away_team", "season")

        season_year = self.request.query_params.get("season")
        if season_year:
            qs = qs.filter(season__year=season_year)

        team_slug = self.request.query_params.get("team")
        if team_slug:
            qs = qs.filter(
                Q(home_team__slug=team_slug) | Q(away_team__slug=team_slug)
            )

        season_type = self.request.query_params.get("season_type", "regular")
        if season_type:
            qs = qs.filter(season_type=season_type)

        return qs.order_by("-date")


class NBATeamDetailView(APIView):
    """
    GET /api/nba/team/<slug>/

    Returns team metadata + current-season ratings in one response.
    """

    def get(self, request, slug):
        try:
            team = NBATeam.objects.get(slug=slug)
        except NBATeam.DoesNotExist:
            return Response({"detail": "Team not found."}, status=status.HTTP_404_NOT_FOUND)

        season_year = request.query_params.get("season")
        if season_year:
            try:
                season = NBASeason.objects.get(year=season_year)
            except NBASeason.DoesNotExist:
                return Response(
                    {"detail": f"Season {season_year} not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            try:
                season = NBASeason.objects.get(is_current=True)
            except NBASeason.DoesNotExist:
                season = None

        ratings = None
        if season:
            try:
                r = NBATeamSeasonRatings.objects.get(team=team, season=season)
                ratings = NBATeamSeasonRatingsSerializer(r).data
            except NBATeamSeasonRatings.DoesNotExist:
                pass

        return Response(
            {
                "team": NBATeamSerializer(team).data,
                "season": NBASeasonSerializer(season).data if season else None,
                "ratings": ratings,
            }
        )


class NBAHealthView(APIView):
    """
    GET /api/nba/health/

    Quick status check — how much data is loaded?
    """

    def get(self, request):
        return Response(
            {
                "status": "ok",
                "phase": "Phase 2 — live data",
                "counts": {
                    "seasons": NBASeason.objects.count(),
                    "teams": NBATeam.objects.count(),
                    "games": NBAGame.objects.count(),
                    "games_with_box_scores": NBAGame.objects.filter(
                        box_score_synced=True
                    ).count(),
                    "team_season_ratings": NBATeamSeasonRatings.objects.count(),
                    "players": NBAPlayer.objects.count(),
                },
            }
        )


class NBAModelCalibrationView(APIView):
    """
    GET /api/nba/model-calibration/?season=2026

    Returns the NBAModelCalibration record for the requested season (or the
    current season if no season param is provided).  Returns 404 if
    nba_eval_model has not been run yet for that season.
    """

    def get(self, request):
        season_year = request.query_params.get("season")
        try:
            if season_year:
                calibration = NBAModelCalibration.objects.select_related("season").get(
                    season__year=season_year
                )
            else:
                calibration = (
                    NBAModelCalibration.objects.select_related("season")
                    .filter(season__is_current=True)
                    .first()
                )
                if calibration is None:
                    # Fall back to most recent
                    calibration = (
                        NBAModelCalibration.objects.select_related("season")
                        .order_by("-season__year")
                        .first()
                    )
        except NBAModelCalibration.DoesNotExist:
            calibration = None

        if calibration is None:
            return Response(
                {"detail": "No calibration data found. Run: python manage.py nba_eval_model --season YYYY"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(NBAModelCalibrationSerializer(calibration).data)


class NBATeamRosterView(APIView):
    """
    GET /api/nba/team/<slug>/players/?season=YYYY

    Returns season-averaged stats for all players on a team.
    Ordered by pts descending (scorers first).
    """

    def get(self, request, slug: str):
        try:
            team = NBATeam.objects.get(slug=slug)
        except NBATeam.DoesNotExist:
            return Response({"detail": "Team not found."}, status=status.HTTP_404_NOT_FOUND)

        season_param = request.query_params.get("season")
        if season_param:
            try:
                season = NBASeason.objects.get(year=int(season_param))
            except (NBASeason.DoesNotExist, ValueError):
                return Response({"detail": "Season not found."}, status=status.HTTP_404_NOT_FOUND)
        else:
            season = (
                NBASeason.objects.filter(is_current=True).first()
                or NBASeason.objects.order_by("-year").first()
            )
            if season is None:
                return Response({"detail": "No seasons available."}, status=status.HTTP_404_NOT_FOUND)

        players = (
            NBAPlayerSeasonStats.objects
            .filter(team=team, season=season)
            .select_related("player", "team", "season")
            .order_by("-pts")
        )

        if not players.exists():
            return Response(
                {
                    "detail": (
                        f"No player stats for {team.name} in {season.display_name}. "
                        f"Run: python manage.py nba_sync_team_logs --season {season.year}"
                        f" && python manage.py nba_compute_player_stats --season {season.year}"
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(NBAPlayerSeasonStatsSerializer(players, many=True).data)


_BLEND_FIELDS = (
    "adj_off", "adj_def", "adj_net", "pace",
    "efg_pct", "opp_efg_pct",
    "tov_rate", "opp_tov_rate",
    "oreb_pct", "opp_oreb_pct",
    "fta_rate", "opp_fta_rate",
)


def _get_blended_ratings(reg, po_ratings):
    """
    Blend regular-season ratings toward playoff ratings in memory (no .save()).
    Weight: w = min(po.games / (po.games + 5.0), 0.7).
    Returns reg unchanged if po_ratings is None or has 0 games.

    Derived margin fields (efg_margin, tov_edge, oreb_edge, fta_margin) are
    recomputed from blended raws. rank_adj_net and rank_ffi are nulled because
    they are stale after the adj_net shift.

    NOTE: recent_form and volatility league distributions in NBAMatchupView
    always use regular-season data regardless of this blend (by design).
    """
    if po_ratings is None or not po_ratings.games or po_ratings.games < 4:
        return reg

    w = min(po_ratings.games / (po_ratings.games + 8.0), 0.7)

    for field in _BLEND_FIELDS:
        r_val = getattr(reg, field)
        p_val = getattr(po_ratings, field)
        if r_val is not None and p_val is not None:
            setattr(reg, field, (1.0 - w) * r_val + w * p_val)

    # Recompute derived margin fields from blended raws
    if reg.efg_pct is not None and reg.opp_efg_pct is not None:
        reg.efg_margin = reg.efg_pct - reg.opp_efg_pct
    if reg.tov_rate is not None and reg.opp_tov_rate is not None:
        reg.tov_edge = reg.opp_tov_rate - reg.tov_rate
    if reg.oreb_pct is not None and reg.opp_oreb_pct is not None:
        reg.oreb_edge = reg.oreb_pct - reg.opp_oreb_pct
    if reg.fta_rate is not None and reg.opp_fta_rate is not None:
        reg.fta_margin = reg.fta_rate - reg.opp_fta_rate

    reg.rank_adj_net = None
    reg.rank_ffi = None

    return reg


class NBAMatchupView(APIView):
    """
    GET /api/nba/matchup/?teamA=<slug>&teamB=<slug>&site=neutral&season=2026&mode=game

    Returns comprehensive head-to-head NBA matchup analysis.

    Query Parameters:
        teamA:   Team A slug (required)
        teamB:   Team B slug (required)
        site:    'neutral' | 'home' (A home) | 'away' (B home) — default neutral
        season:  Season year integer — default current season
        mode:    'game' | 'series' — default 'game'; 'series' adds 7-game series DP
    """

    def get(self, request):
        from api.matchup_engine import (
            apply_hca_adjustment,
            compute_matchup_four_factors,
            compute_shot_profile_edges,
            compute_volatility_score,
            compute_win_probability,
            forecast_game,
        )
        from nba.matchup_engine import (
            NBA_NAT_EFG,
            NBA_NAT_FTR,
            NBA_NAT_ORB,
            NBA_NAT_TOV,
            NBA_PACE_DEFAULT,
            NBA_VOLATILITY_WEIGHTS,
            compute_nba_national_four_factors,
            compute_nba_recent_form,
            compute_nba_record,
            compute_nba_shot_profile,
            compute_series_probability,
            get_nba_four_factors_pct,
            get_nba_model_params,
        )
        from api.matchup_engine import (
            compute_points_from_four_factors,
            identify_top_drivers,
        )

        team_a_slug = request.query_params.get("teamA", "").lower()
        team_b_slug = request.query_params.get("teamB", "").lower()
        site = request.query_params.get("site", "neutral")
        mode = request.query_params.get("mode", "game")
        season_year = request.query_params.get("season")
        _upb_raw = request.query_params.get("use_playoff_blend", "true")
        use_playoff_blend = _upb_raw.lower() not in ("0", "false", "no", "off")

        if not team_a_slug or not team_b_slug:
            return Response({"error": "teamA and teamB required"}, status=status.HTTP_400_BAD_REQUEST)

        if site not in ("neutral", "home", "away"):
            return Response({"error": "site must be neutral, home, or away"}, status=status.HTTP_400_BAD_REQUEST)

        if mode not in ("game", "series"):
            return Response({"error": "mode must be game or series"}, status=status.HTTP_400_BAD_REQUEST)

        _blend_flag = "blend" if use_playoff_blend else "reg"
        cache_key = f"nba:matchup:{team_a_slug}:{team_b_slug}:{site}:{season_year or 'current'}:{mode}:{_blend_flag}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        # Resolve season
        if season_year:
            try:
                season = NBASeason.objects.get(year=int(season_year))
            except (NBASeason.DoesNotExist, ValueError):
                return Response({"error": f"Season {season_year} not found"}, status=status.HTTP_404_NOT_FOUND)
        else:
            season = NBASeason.objects.filter(is_current=True).first()
            if not season:
                return Response({"error": "No current season found"}, status=status.HTTP_404_NOT_FOUND)

        # Load teams
        try:
            team_a = NBATeam.objects.get(slug=team_a_slug)
        except NBATeam.DoesNotExist:
            return Response({"error": f"Team '{team_a_slug}' not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            team_b = NBATeam.objects.get(slug=team_b_slug)
        except NBATeam.DoesNotExist:
            return Response({"error": f"Team '{team_b_slug}' not found"}, status=status.HTTP_404_NOT_FOUND)

        # Load ratings
        try:
            ratings_a = NBATeamSeasonRatings.objects.get(team=team_a, season=season, season_type="regular")
            ratings_b = NBATeamSeasonRatings.objects.get(team=team_b, season=season, season_type="regular")
        except NBATeamSeasonRatings.DoesNotExist:
            return Response(
                {"error": "Team ratings not found for this season. Run nba_compute_ratings first."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if use_playoff_blend:
            po_qs = {
                r.team_id: r
                for r in NBATeamSeasonRatings.objects.filter(
                    team__in=[team_a, team_b], season=season, season_type="playoffs"
                )
            }
            ratings_a = _get_blended_ratings(ratings_a, po_qs.get(team_a.id))
            ratings_b = _get_blended_ratings(ratings_b, po_qs.get(team_b.id))

        # Model parameters (HCA, sigma, nat_avg_ortg)
        params = get_nba_model_params(season)
        hca_points = params["hca_points"]
        sigma = params["sigma"]
        nat_avg_ortg = params["nat_avg_ortg"]
        ols_r_squared = params["ols_r_squared"]

        # National four-factor averages (percentage-point scale)
        # Guard: never let zero/None reach the shared engine — use NBA defaults, not NCAA ones
        _raw_nat_ff = compute_nba_national_four_factors(season)
        nat_ff = {
            "nat_efg": _raw_nat_ff["nat_efg"] if _raw_nat_ff["nat_efg"] > 0 else NBA_NAT_EFG,
            "nat_tov": _raw_nat_ff["nat_tov"] if _raw_nat_ff["nat_tov"] > 0 else NBA_NAT_TOV,
            "nat_orb": _raw_nat_ff["nat_orb"] if _raw_nat_ff["nat_orb"] > 0 else NBA_NAT_ORB,
            "nat_ftr": _raw_nat_ff["nat_ftr"] if _raw_nat_ff["nat_ftr"] > 0 else NBA_NAT_FTR,
        }

        # Convert NBA decimal four factors to percentage points
        ff_a = get_nba_four_factors_pct(ratings_a)
        ff_b = get_nba_four_factors_pct(ratings_b)

        # ===== FORECAST =====
        _log.debug(
            "[NBA matchup] %s adj_off=%.1f adj_def=%.1f adj_net=%.1f pace=%.1f | "
            "%s adj_off=%.1f adj_def=%.1f adj_net=%.1f pace=%.1f | "
            "nat_avg_ortg=%.1f sigma=%.2f hca=%.2f",
            team_a.abbreviation,
            ratings_a.adj_off or -999, ratings_a.adj_def or -999,
            ratings_a.adj_net or -999, ratings_a.pace or -999,
            team_b.abbreviation,
            ratings_b.adj_off or -999, ratings_b.adj_def or -999,
            ratings_b.adj_net or -999, ratings_b.pace or -999,
            nat_avg_ortg, sigma, hca_points,
        )

        forecast = forecast_game(
            adj_o_a=ratings_a.adj_off or nat_avg_ortg,
            adj_d_a=ratings_a.adj_def or nat_avg_ortg,
            adj_em_a=ratings_a.adj_net or 0.0,
            tempo_a=ratings_a.pace or NBA_PACE_DEFAULT,
            adj_o_b=ratings_b.adj_off or nat_avg_ortg,
            adj_d_b=ratings_b.adj_def or nat_avg_ortg,
            adj_em_b=ratings_b.adj_net or 0.0,
            tempo_b=ratings_b.pace or NBA_PACE_DEFAULT,
            nat_avg_ortg=nat_avg_ortg,
            hca_points=hca_points,
            sigma=sigma,
            site=site,
        )

        # Score sanity: neutral-site pts should be within ±15% of nat_avg_ortg × (pace/100)
        _expected = nat_avg_ortg * ((ratings_a.pace or NBA_PACE_DEFAULT) / 100)
        if not (0.85 * _expected < forecast["pts_a_neutral"] < 1.15 * _expected):
            _log.warning(
                "[NBA matchup] Score sanity: %s pts_a_neutral=%.1f, expected ~%.1f. "
                "Check adj_off/adj_def units.",
                team_a.abbreviation, forecast["pts_a_neutral"], _expected,
            )

        _log.debug(
            "[NBA matchup] forecast margin=%.1f pts_a=%.1f pts_b=%.1f prob_a=%.3f",
            forecast["margin"], forecast["pts_a"], forecast["pts_b"], forecast["prob_a"],
        )

        # ===== FOUR FACTOR EDGES =====
        ff_edges = compute_matchup_four_factors(
            efg_a=ff_a["efg"],     tov_a=ff_a["tov"],     orb_a=ff_a["orb"],     ftr_a=ff_a["ftr"],
            efg_d_a=ff_a["opp_efg"], tov_d_a=ff_a["opp_tov"], orb_d_a=ff_a["opp_orb"], ftr_d_a=ff_a["opp_ftr"],
            efg_b=ff_b["efg"],     tov_b=ff_b["tov"],     orb_b=ff_b["orb"],     ftr_b=ff_b["ftr"],
            efg_d_b=ff_b["opp_efg"], tov_d_b=ff_b["opp_tov"], orb_d_b=ff_b["opp_orb"], ftr_d_b=ff_b["opp_ftr"],
            nat_efg=nat_ff["nat_efg"], nat_tov=nat_ff["nat_tov"],
            nat_orb=nat_ff["nat_orb"], nat_ftr=nat_ff["nat_ftr"],
        )

        # ===== FFI EDGE =====
        ffi_a = ratings_a.ffi if ratings_a.ffi is not None else 50.0
        ffi_b = ratings_b.ffi if ratings_b.ffi is not None else 50.0
        ffi_edge = round(ffi_a - ffi_b, 1)

        # ===== RECORDS =====
        record_a = compute_nba_record(team_a, season)
        record_b = compute_nba_record(team_b, season)

        # ===== SHOT PROFILE =====
        shot_a = compute_nba_shot_profile(team_a, season)
        shot_b = compute_nba_shot_profile(team_b, season)
        shot_profile = None
        if shot_a and shot_b:
            shot_profile = compute_shot_profile_edges(
                fg3_rate_a=shot_a["fg3_rate"], fg3_pct_a=shot_a["fg3_pct"], fg2_pct_a=shot_a["fg2_pct"],
                fg3_rate_b=shot_b["fg3_rate"], fg3_pct_b=shot_b["fg3_pct"], fg2_pct_b=shot_b["fg2_pct"],
            )

        # ===== RECENT FORM =====
        recent_form_a = compute_nba_recent_form(team_a, season, nat_avg_ortg, hca_points, sigma)
        recent_form_b = compute_nba_recent_form(team_b, season, nat_avg_ortg, hca_points, sigma)
        variance_a = recent_form_a["variance"] or None
        variance_b = recent_form_b["variance"] or None

        # ===== VOLATILITY =====
        all_paces = list(
            NBATeamSeasonRatings.objects.filter(
                season=season, season_type="regular", pace__isnull=False
            ).values_list("pace", flat=True)
        )
        all_fg3_rates = []
        for tr in NBATeamSeasonRatings.objects.filter(season=season, season_type="regular"):
            sp = compute_nba_shot_profile(tr.team, season)
            if sp:
                all_fg3_rates.append(sp["fg3_rate"])

        if len(all_paces) >= 10:
            import numpy as np
            tempo_range = (float(np.percentile(all_paces, 5)), float(np.percentile(all_paces, 95)))
        else:
            tempo_range = (90.0, 102.0)

        if len(all_fg3_rates) >= 10:
            import numpy as np
            fg3_range = (float(np.percentile(all_fg3_rates, 5)), float(np.percentile(all_fg3_rates, 95)))
        else:
            fg3_range = (36.0, 50.0)

        volatility = compute_volatility_score(
            tempo_a=ratings_a.pace or NBA_PACE_DEFAULT,
            tempo_b=ratings_b.pace or NBA_PACE_DEFAULT,
            fg3_rate_a=shot_a["fg3_rate"] if shot_a else 42.0,
            fg3_rate_b=shot_b["fg3_rate"] if shot_b else 42.0,
            recent_variance_a=variance_a,
            recent_variance_b=variance_b,
            tempo_range=tempo_range,
            fg3_rate_range=fg3_range,
            variance_range=(3.0, 15.0),
            weights=NBA_VOLATILITY_WEIGHTS,
        )

        # ===== SERIES PREDICTION =====
        series_prediction = None
        if mode == "series":
            pts_a_neutral = forecast["pts_a_neutral"]
            pts_b_neutral = forecast["pts_b_neutral"]
            pts_a_home, pts_b_home = apply_hca_adjustment(pts_a_neutral, pts_b_neutral, "home", hca_points)
            pts_a_away, pts_b_away = apply_hca_adjustment(pts_a_neutral, pts_b_neutral, "away", hca_points)
            prob_a_home, _ = compute_win_probability(pts_a_home - pts_b_home, sigma)
            prob_a_away, _ = compute_win_probability(pts_a_away - pts_b_away, sigma)
            series_home = "b" if site == "away" else "a"
            series_prediction = compute_series_probability(prob_a_home, prob_a_away, series_home)

        # ===== POINTS BREAKDOWN + TOP DRIVERS =====
        _pts_breakdown = None
        _top_drivers = None
        _has_coefs = False
        _cal = None
        try:
            _cal = NBAModelCalibration.objects.get(season=season)
            _has_coefs = all([
                _cal.ffi_raw_coef_efg  is not None,
                _cal.ffi_raw_coef_tov  is not None,
                _cal.ffi_raw_coef_oreb is not None,
                _cal.ffi_raw_coef_fta  is not None,
            ])
        except NBAModelCalibration.DoesNotExist:
            pass

        if _has_coefs:
            _pts_breakdown = compute_points_from_four_factors(
                efg_edge=ff_edges["efg_edge"],
                tov_edge=ff_edges["tov_edge"],
                orb_edge=ff_edges["orb_edge"],
                ftr_edge=ff_edges["ftr_edge"],
                coef_efg=_cal.ffi_raw_coef_efg,
                coef_tov=_cal.ffi_raw_coef_tov,
                coef_orb=_cal.ffi_raw_coef_oreb,
                coef_ftr=_cal.ffi_raw_coef_fta,
                coef_intercept=_cal.ffi_raw_intercept or 0.0,
                pace=forecast["pace"],
            )
            _top_drivers = identify_top_drivers(
                efg_edge=ff_edges["efg_edge"],
                tov_edge=ff_edges["tov_edge"],
                orb_edge=ff_edges["orb_edge"],
                ftr_edge=ff_edges["ftr_edge"],
                coef_efg=_cal.ffi_raw_coef_efg,
                coef_tov=_cal.ffi_raw_coef_tov,
                coef_orb=_cal.ffi_raw_coef_oreb,
                coef_ftr=_cal.ffi_raw_coef_fta,
                pace=forecast["pace"],
            )

        response_data = {
            "season": season.display_name,
            "site": site,
            "mode": mode,
            "teamA": {
                "id": team_a.id,
                "name": team_a.name,
                "slug": team_a.slug,
                "logo_url": team_a.logo_url,
                "conference": team_a.conference,
                "division": team_a.division,
                "rank": ratings_a.rank_adj_net,
                "record": record_a,
                "adj_em": round(ratings_a.adj_net or 0.0, 1),
                "adj_o": round(ratings_a.adj_off or nat_avg_ortg, 1),
                "adj_d": round(ratings_a.adj_def or nat_avg_ortg, 1),
                "adj_tempo": round(ratings_a.pace or NBA_PACE_DEFAULT, 1),
                "ffi": round(ffi_a, 1),
            },
            "teamB": {
                "id": team_b.id,
                "name": team_b.name,
                "slug": team_b.slug,
                "logo_url": team_b.logo_url,
                "conference": team_b.conference,
                "division": team_b.division,
                "rank": ratings_b.rank_adj_net,
                "record": record_b,
                "adj_em": round(ratings_b.adj_net or 0.0, 1),
                "adj_o": round(ratings_b.adj_off or nat_avg_ortg, 1),
                "adj_d": round(ratings_b.adj_def or nat_avg_ortg, 1),
                "adj_tempo": round(ratings_b.pace or NBA_PACE_DEFAULT, 1),
                "ffi": round(ffi_b, 1),
            },
            "forecast": forecast,
            "four_factor_edges": ff_edges,
            "ffi_edge": ffi_edge,
            "points_breakdown": _pts_breakdown,
            "top_drivers": _top_drivers,
            "shot_profile": shot_profile,
            "volatility": volatility,
            "recent_form_a": recent_form_a,
            "recent_form_b": recent_form_b,
            "series_prediction": series_prediction,
            "metadata": {
                "hca_points": round(hca_points, 2),
                "prediction_sigma": round(sigma, 2),
                "nat_avg_ortg": round(nat_avg_ortg, 1),
                "playoff_blend": use_playoff_blend,
                "coefficients": {
                    "efg":       round(_cal.ffi_raw_coef_efg,  3) if _has_coefs else None,
                    "tov":       round(_cal.ffi_raw_coef_tov,  3) if _has_coefs else None,
                    "orb":       round(_cal.ffi_raw_coef_oreb, 3) if _has_coefs else None,
                    "ftr":       round(_cal.ffi_raw_coef_fta,  3) if _has_coefs else None,
                    "r_squared": round(_cal.ffi_adj_net_r_squared, 3) if (_has_coefs and _cal.ffi_adj_net_r_squared) else None,
                },
            },
        }

        cache.set(cache_key, response_data, 60 * 30)
        return Response(response_data)


class NBALeaguePlayersView(APIView):
    """
    GET /api/nba/players/?season=YYYY&ordering=-pts&min_gp=5

    League-wide player season stats, ordered by pts (or any allowed field).
    """

    _ALLOWED_ORDERINGS = {
        # Traditional
        "pts", "-pts", "reb", "-reb", "ast", "-ast",
        "stl", "-stl", "blk", "-blk", "mpg", "-mpg", "gp", "-gp",
        "tov", "-tov", "plus_minus", "-plus_minus",
        "fg_pct", "-fg_pct", "fg3_pct", "-fg3_pct", "ft_pct", "-ft_pct",
        "fga_pg", "-fga_pg", "fg3a_pg", "-fg3a_pg",
        "oreb_pg", "-oreb_pg", "dreb_pg", "-dreb_pg",
        "fta_pg", "-fta_pg",
        # Advanced efficiency
        "efg_pct", "-efg_pct", "ts_pct", "-ts_pct",
        "usg_pct", "-usg_pct", "pie", "-pie",
        "oreb_pct", "-oreb_pct", "dreb_pct", "-dreb_pct",
        "ast_pct", "-ast_pct", "tov_pct", "-tov_pct", "ast_to", "-ast_to",
        # On-court ratings (raw)
        "on_court_ortg", "-on_court_ortg",
        "on_court_drtg", "-on_court_drtg",
        "on_court_net", "-on_court_net",
        # On-court ratings (E_* stabilised)
        "on_court_adj_o", "-on_court_adj_o",
        "on_court_adj_d", "-on_court_adj_d",
        "on_court_adj_em", "-on_court_adj_em",
        # MPIR
        "mpir", "-mpir", "o_mpir", "-o_mpir", "d_mpir", "-d_mpir",
        # Final BPR (prior-informed RAPM)
        "bpr", "-bpr", "obpr", "-obpr", "dbpr", "-dbpr",
        # Box BPR (intermediate)
        "box_bpr", "-box_bpr", "box_obpr", "-box_obpr", "box_dbpr", "-box_dbpr",
        # Baseline RAPM
        "baseline_obpr", "-baseline_obpr", "baseline_dbpr", "-baseline_dbpr",
        # Defense
        "stl_pct", "-stl_pct", "blk_pct", "-blk_pct",
    }

    def get(self, request):
        season_param = request.query_params.get("season")
        ordering = request.query_params.get("ordering", "-pts")
        if ordering not in self._ALLOWED_ORDERINGS:
            ordering = "-pts"

        min_gp = max(1, int(request.query_params.get("min_gp", "5")))

        if season_param:
            try:
                season = NBASeason.objects.get(year=int(season_param))
            except (NBASeason.DoesNotExist, ValueError):
                return Response({"detail": "Season not found."}, status=status.HTTP_404_NOT_FOUND)
        else:
            season = (
                NBASeason.objects.filter(is_current=True).first()
                or NBASeason.objects.order_by("-year").first()
            )
            if season is None:
                return Response([], status=status.HTTP_200_OK)

        season_type = request.query_params.get("season_type", "regular")

        players = (
            NBAPlayerSeasonStats.objects
            .filter(season=season, gp__gte=min_gp, season_type=season_type)
            .select_related("player", "team", "season")
            .order_by(ordering)
        )

        return Response(NBAPlayerSeasonStatsSerializer(players, many=True).data)

