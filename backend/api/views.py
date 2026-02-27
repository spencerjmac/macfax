"""
DRF Views for CBB Analytics API
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q

from core.models import (
    Season, Conference, Team, TeamSeasonStats,
    Game, TeamGameStats, TeamSeasonMetrics, TeamSeasonRatings, NationalAverages
)
from .serializers import (
    SeasonSerializer, 
    ConferenceSerializer, 
    TeamSerializer,
    TeamSeasonStatsSerializer,
    RankingsSerializer,
    TeamDetailSerializer,
    # Game log serializers
    GameSerializer,
    TeamGameStatsSerializer,
    GameLogSerializer,
    TeamSeasonMetricsSerializer,
    TeamSeasonRatingsSerializer,
    GameDetailSerializer,
)
from .matchup_engine import (
    forecast_game,
    compute_matchup_four_factors,
    compute_points_from_four_factors,
    identify_top_drivers,
    compute_shot_profile_edges,
    compute_volatility_score,
    format_recent_form
)


class SeasonViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/seasons
    Returns list of all available seasons
    """
    queryset = Season.objects.all()
    serializer_class = SeasonSerializer
    pagination_class = None  # Disable pagination for seasons


class ConferenceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/conferences
    Returns list of all conferences
    """
    queryset = Conference.objects.all()
    serializer_class = ConferenceSerializer
    pagination_class = None  # Disable pagination for conferences


class RankingsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/rankings?season=2026&sort=adj_em&dir=desc&conference=B10&search=mich
    
    Returns sortable/filterable rankings table
    
    Query Params:
    - season: year (default: current season)
    - sort: field to sort by (default: rank)
    - dir: asc or desc (default: asc)
    - conference: conference code filter
    - search: team name search
    """
    serializer_class = RankingsSerializer
    # pagination_class uses default settings (PAGE_SIZE: 500, enough for all 365 D1 teams)
    
    def get_queryset(self):
        # Get season (default to current)
        season_year = self.request.query_params.get('season')
        if season_year:
            season = get_object_or_404(Season, year=season_year)
        else:
            season = Season.objects.filter(is_current=True).first()
        
        # Use TeamSeasonRatings (our computed data) instead of TeamSeasonStats
        # ONLY show Division I teams
        queryset = TeamSeasonRatings.objects.filter(
            season=season,
            team__is_d1=True
        ).select_related('team')
        
        # Search by team name
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(team__name__icontains=search) | Q(team__slug__icontains=search)
            )
        
        # Sorting
        sort_field = self.request.query_params.get('sort', 'rank')
        sort_dir = self.request.query_params.get('dir', 'asc')
        
        # Map frontend field names to model field names
        field_mapping = {
            'rank': 'rank_adj_em',
            'adj_em': 'adj_em',
            'adj_o': 'adj_o',
            'adj_d': 'adj_d',
            'adj_tempo': 'adj_tempo',
            'aor_100': 'adj_o',
            'adr_100': 'adj_d',
            'net_100': 'adj_em',
            # Adjusted Four Factors - Offense
            'efg_pct': 'adj_efg_pct',
            'tov_pct': 'adj_tov_pct',
            'orb_pct': 'adj_orb_pct',
            'ftr': 'adj_ftr',
            # Adjusted Four Factors - Defense
            'efg_pct_d': 'adj_opp_efg_pct',
            'tov_pct_d': 'adj_opp_tov_pct',
            'orb_pct_d': 'adj_opp_orb_pct',
            'ftr_d': 'adj_opp_ftr',
            # Adjusted Four Factor Margins
            'efg_margin': 'adj_efg_margin',
            'tov_edge': 'adj_tov_edge',
            'reb_edge': 'adj_reb_edge',
            'ftr_margin': 'adj_ftr_margin',
            # Four Factor Index
            'four_factor_index_100': 'ffi_adj',
            'raw_four_factor_index_100': 'ffi_raw',
            # Other
            'team__name': 'team__name',
        }
        
        # Get the actual field name to sort by
        actual_field = field_mapping.get(sort_field, 'rank_adj_em')
        
        # Apply sort direction
        order_prefix = '-' if sort_dir == 'desc' else ''
        queryset = queryset.order_by(f'{order_prefix}{actual_field}')
        
        return queryset
    
    def list(self, request, *args, **kwargs):
        """Override list to add conference filtering after serialization"""
        queryset = self.filter_queryset(self.get_queryset())
        
        # Get conference filter
        conference_filter = request.query_params.get('conference')
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            data = serializer.data
            
            # Apply conference filter on serialized data
            if conference_filter:
                data = [item for item in data if item.get('conference') == conference_filter]
            
            return self.get_paginated_response(data)

        serializer = self.get_serializer(queryset, many=True)
        data = serializer.data
        
        # Apply conference filter on serialized data
        if conference_filter:
            data = [item for item in data if item.get('conference') == conference_filter]
        
        return Response(data)


class TeamViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/teams?season=2026&search=michigan
    GET /api/teams/{slug}?season=2026
    
    Returns team information and stats
    """
    queryset = Team.objects.filter(is_d1=True)
    serializer_class = TeamSerializer
    lookup_field = 'slug'
    
    @action(detail=True, methods=['get'])
    def stats(self, request, slug=None):
        """
        GET /api/teams/{slug}/stats?season=2026
        
        Returns detailed stats for a team in a specific season
        """
        team = self.get_object()
        
        # Get season
        season_year = request.query_params.get('season')
        if season_year:
            season = get_object_or_404(Season, year=season_year)
        else:
            season = Season.objects.filter(is_current=True).first()
        
        # Get stats
        stats = get_object_or_404(
            TeamSeasonStats,
            team=team,
            season=season
        )
        
        serializer = TeamSeasonStatsSerializer(stats)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def profile(self, request, slug=None):
        """
        GET /api/teams/{slug}/profile?season=2026
        
        Returns complete team profile with historical data
        """
        team = self.get_object()
        
        # Get requested season or current
        season_year = request.query_params.get('season')
        if season_year:
            season = get_object_or_404(Season, year=season_year)
        else:
            season = Season.objects.filter(is_current=True).first()
        
        # Get current season stats
        current_stats = TeamSeasonStats.objects.filter(
            team=team,
            season=season
        ).select_related('conference').first()
        
        # Get all historical stats
        all_stats = TeamSeasonStats.objects.filter(
            team=team
        ).select_related('season', 'conference').order_by('-season__year')
        
        response_data = {
            'team': TeamSerializer(team).data,
            'current_season_stats': TeamSeasonStatsSerializer(current_stats).data if current_stats else None,
            'seasons': TeamSeasonStatsSerializer(all_stats, many=True).data,
        }
        
        return Response(response_data)
    
    @action(detail=True, methods=['get'])
    def games(self, request, slug=None):
        """
        GET /api/teams/{slug}/games?season=2026
        
        Returns list of all games for a team in a season
        """
        team = self.get_object()
        
        # Get season
        season_year = request.query_params.get('season')
        if season_year:
            season = get_object_or_404(Season, year=season_year)
        else:
            season = Season.objects.filter(is_current=True).first()
        
        # Get all games (home and away)
        games = Game.objects.filter(
            Q(home_team=team) | Q(away_team=team),
            season_year=season.year
        ).select_related('home_team', 'away_team').order_by('game_date')
        
        serializer = GameSerializer(games, many=True)
        return Response({
            'team': TeamSerializer(team).data,
            'season_year': season.year,
            'games': serializer.data,
            'last_updated': games.latest('updated_at').updated_at if games.exists() else None,
        })
    
    @action(detail=True, methods=['get'])
    def gamelog(self, request, slug=None):
        """
        GET /api/teams/{slug}/gamelog?season=2026
        
        Returns game log with derived metrics (ORtg, Four Factors, etc.)
        """
        team = self.get_object()
        
        # Get season
        season_year = request.query_params.get('season')
        if season_year:
            season = get_object_or_404(Season, year=season_year)
        else:
            season = Season.objects.filter(is_current=True).first()
        
        # Get game stats
        game_stats = TeamGameStats.objects.filter(
            team=team,
            game__season_year=season.year
        ).select_related('game', 'opponent').order_by('game__game_date')
        
        serializer = GameLogSerializer(game_stats, many=True)
        
        return Response({
            'team': TeamSerializer(team).data,
            'season_year': season.year,
            'game_log': serializer.data,
            'total_games': game_stats.count(),
            'last_updated': game_stats.latest('updated_at').updated_at if game_stats.exists() else None,
        })
    
    @action(detail=True, methods=['get'], url_path='season-stats')
    def season_stats_combined(self, request, slug=None):
        """
        GET /api/teams/{slug}/season-stats?season=2026
        
        Returns combined season stats (metrics + ratings + kill shots)
        """
        team = self.get_object()
        
        # Get season
        season_year = request.query_params.get('season')
        if season_year:
            season = get_object_or_404(Season, year=season_year)
        else:
            season = Season.objects.filter(is_current=True).first()
        
        # Get computed metrics
        metrics = TeamSeasonMetrics.objects.filter(
            team=team,
            season=season
        ).first()
        
        # Get adjusted ratings
        ratings = TeamSeasonRatings.objects.filter(
            team=team,
            season=season
        ).first()
        
        return Response({
            'team': TeamSerializer(team).data,
            'season_year': season.year,
            'metrics': TeamSeasonMetricsSerializer(metrics).data if metrics else None,
            'ratings': TeamSeasonRatingsSerializer(ratings).data if ratings else None,
        })


class MatchupViewSet(viewsets.ViewSet):
    """
    GET /api/matchup?season=2026&teamA=michigan&teamB=duke&site=neutral
    
    Returns comprehensive head-to-head matchup analysis using our forecast engine.
    
    Query Parameters:
        - teamA: Team A slug (required)
        - teamB: Team B slug (required)
        - site: 'neutral', 'home' (A home), or 'away' (B home) - default: neutral
        - season: Season year (default: current season)
    
    Returns:
        - teamA, teamB: Full team data
        - forecast: Projected score, spread, total, win%, pace
        - four_factor_edges: Matchup-specific four factor analysis
        - Overall FFI edge
    """
    
    def list(self, request):
        team_a_slug = request.query_params.get('teamA')
        team_b_slug = request.query_params.get('teamB')
        site = request.query_params.get('site', 'neutral')  # neutral, home, away
        
        if not team_a_slug or not team_b_slug:
            return Response(
                {'error': 'teamA and teamB required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate site parameter
        if site not in ['neutral', 'home', 'away']:
            return Response(
                {'error': 'site must be neutral, home, or away'},
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
        
        # Get teams
        team_a = get_object_or_404(Team, slug=team_a_slug)
        team_b = get_object_or_404(Team, slug=team_b_slug)
        
        # Get team ratings (using TeamSeasonRatings which has our computed data)
        try:
            ratings_a = TeamSeasonRatings.objects.get(team=team_a, season=season)
            ratings_b = TeamSeasonRatings.objects.get(team=team_b, season=season)
        except TeamSeasonRatings.DoesNotExist:
            return Response(
                {'error': 'Team ratings not found for this season'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get conferences from TeamSeasonStats (conference is stored there)
        stats_a = None
        conference_a_name = None
        try:
            stats_a = TeamSeasonStats.objects.get(team=team_a, season=season)
            conference_a_name = stats_a.conference.name if stats_a.conference else None
        except TeamSeasonStats.DoesNotExist:
            pass
        
        stats_b = None
        conference_b_name = None
        try:
            stats_b = TeamSeasonStats.objects.get(team=team_b, season=season)
            conference_b_name = stats_b.conference.name if stats_b.conference else None
        except TeamSeasonStats.DoesNotExist:
            pass
        
        # Get national averages
        try:
            nat_avg = NationalAverages.objects.get(season=season)
        except NationalAverages.DoesNotExist:
            return Response(
                {'error': 'National averages not computed for this season'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Use HCA and sigma from national averages, with fallbacks
        hca_points = nat_avg.hca_points if nat_avg.hca_points else 1.85
        sigma = nat_avg.prediction_sigma if nat_avg.prediction_sigma else 11.08
        
        # ===== FORECAST =====
        forecast = forecast_game(
            adj_o_a=ratings_a.adj_o,
            adj_d_a=ratings_a.adj_d,
            adj_em_a=ratings_a.adj_em,
            tempo_a=ratings_a.adj_tempo,
            adj_o_b=ratings_b.adj_o,
            adj_d_b=ratings_b.adj_d,
            adj_em_b=ratings_b.adj_em,
            tempo_b=ratings_b.adj_tempo,
            nat_avg_ortg=nat_avg.avg_ortg,
            hca_points=hca_points,
            sigma=sigma,
            site=site
        )
        
        # ===== FOUR FACTOR EDGES =====
        ff_edges = compute_matchup_four_factors(
            # Team A offense
            efg_a=ratings_a.adj_efg_pct,
            tov_a=ratings_a.adj_tov_pct,
            orb_a=ratings_a.adj_orb_pct,
            ftr_a=ratings_a.adj_ftr,
            # Team A defense
            efg_d_a=ratings_a.adj_opp_efg_pct,
            tov_d_a=ratings_a.adj_opp_tov_pct,
            orb_d_a=ratings_a.adj_opp_orb_pct,
            ftr_d_a=ratings_a.adj_opp_ftr,
            # Team B offense
            efg_b=ratings_b.adj_efg_pct,
            tov_b=ratings_b.adj_tov_pct,
            orb_b=ratings_b.adj_orb_pct,
            ftr_b=ratings_b.adj_ftr,
            # Team B defense
            efg_d_b=ratings_b.adj_opp_efg_pct,
            tov_d_b=ratings_b.adj_opp_tov_pct,
            orb_d_b=ratings_b.adj_opp_orb_pct,
            ftr_d_b=ratings_b.adj_opp_ftr,
            # National averages
            nat_efg=nat_avg.avg_efg,
            nat_tov=nat_avg.avg_tov,
            nat_orb=nat_avg.avg_orb,
            nat_ftr=nat_avg.avg_ftr
        )
        
        # ===== OVERALL FFI EDGE =====
        # Use adjusted FFI if available, otherwise raw
        ffi_a = ratings_a.ffi_adj if ratings_a.ffi_adj else (ratings_a.ffi_raw if ratings_a.ffi_raw else 50.0)
        ffi_b = ratings_b.ffi_adj if ratings_b.ffi_adj else (ratings_b.ffi_raw if ratings_b.ffi_raw else 50.0)
        ffi_edge = ffi_a - ffi_b
        
        # ===== POINTS FROM FOUR FACTORS =====
        # Use regression coefficients if available
        pts_breakdown = None
        top_drivers = None
        
        if all([
            nat_avg.coef_efg is not None,
            nat_avg.coef_tov is not None,
            nat_avg.coef_orb is not None,
            nat_avg.coef_ftr is not None,
            nat_avg.coef_intercept is not None
        ]):
            pts_breakdown = compute_points_from_four_factors(
                efg_edge=ff_edges['efg_edge'],
                tov_edge=ff_edges['tov_edge'],
                orb_edge=ff_edges['orb_edge'],
                ftr_edge=ff_edges['ftr_edge'],
                coef_efg=nat_avg.coef_efg,
                coef_tov=nat_avg.coef_tov,
                coef_orb=nat_avg.coef_orb,
                coef_ftr=nat_avg.coef_ftr,
                coef_intercept=nat_avg.coef_intercept
            )
            
            top_drivers = identify_top_drivers(
                efg_edge=ff_edges['efg_edge'],
                tov_edge=ff_edges['tov_edge'],
                orb_edge=ff_edges['orb_edge'],
                ftr_edge=ff_edges['ftr_edge'],
                coef_efg=nat_avg.coef_efg,
                coef_tov=nat_avg.coef_tov,
                coef_orb=nat_avg.coef_orb,
                coef_ftr=nat_avg.coef_ftr
            )
        
        # ===== SHOT PROFILE EDGES =====
        shot_profile = None
        if stats_a and stats_b:
            # Use TeamSeasonStats for shot profile data
            shot_profile = compute_shot_profile_edges(
                fg3_rate_a=stats_a.fg3_rate if stats_a.fg3_rate else 35.0,
                fg3_pct_a=stats_a.fg3_pct if stats_a.fg3_pct else 33.0,
                fg2_pct_a=stats_a.fg2_pct if stats_a.fg2_pct else 50.0,
                fg3_rate_b=stats_b.fg3_rate if stats_b.fg3_rate else 35.0,
                fg3_pct_b=stats_b.fg3_pct if stats_b.fg3_pct else 33.0,
                fg2_pct_b=stats_b.fg2_pct if stats_b.fg2_pct else 50.0
            )
        
        # ===== RECENT FORM =====
        # Get last 10 games for each team
        recent_games_a = TeamGameStats.objects.filter(
            team=team_a,
            game__season_year=season.year,
            game__status='final'
        ).select_related('game', 'opponent').order_by('-game__game_date')[:10]
        
        recent_games_b = TeamGameStats.objects.filter(
            team=team_b,
            game__season_year=season.year,
            game__status='final'
        ).select_related('game', 'opponent').order_by('-game__game_date')[:10]
        
        # Format recent form with opponent scores
        recent_form_a_data = []
        margins_a = []
        for game_stat in recent_games_a:
            # Get opponent's score from same game
            try:
                opp_stat = TeamGameStats.objects.get(
                    game=game_stat.game,
                    team=game_stat.opponent
                )
                opp_pts = opp_stat.pts
            except TeamGameStats.DoesNotExist:
                opp_pts = 0
            
            margin = game_stat.pts - opp_pts
            margins_a.append(margin)
            
            recent_form_a_data.append({
                'date': game_stat.game.game_date.isoformat(),
                'opponent': game_stat.opponent.name,
                'result': 'W' if margin > 0 else 'L',
                'score': f"{game_stat.pts}-{opp_pts}",
                'margin': margin,
            })
        
        recent_form_b_data = []
        margins_b = []
        for game_stat in recent_games_b:
            try:
                opp_stat = TeamGameStats.objects.get(
                    game=game_stat.game,
                    team=game_stat.opponent
                )
                opp_pts = opp_stat.pts
            except TeamGameStats.DoesNotExist:
                opp_pts = 0
            
            margin = game_stat.pts - opp_pts
            margins_b.append(margin)
            
            recent_form_b_data.append({
                'date': game_stat.game.game_date.isoformat(),
                'opponent': game_stat.opponent.name,
                'result': 'W' if margin > 0 else 'L',
                'score': f"{game_stat.pts}-{opp_pts}",
                'margin': margin,
            })
        
        # Calculate variance for volatility
        import statistics
        variance_a = statistics.stdev(margins_a) if len(margins_a) >= 2 else None
        variance_b = statistics.stdev(margins_b) if len(margins_b) >= 2 else None
        
        recent_form_a = {
            'games_analyzed': len(recent_games_a),
            'record': f"{sum(1 for m in margins_a if m > 0)}-{sum(1 for m in margins_a if m <= 0)}",
            'avg_margin': round(statistics.mean(margins_a), 1) if margins_a else 0.0,
            'variance': round(variance_a, 1) if variance_a else 0.0,
            'games': recent_form_a_data[:5]  # Return only last 5 for display
        }
        
        recent_form_b = {
            'games_analyzed': len(recent_games_b),
            'record': f"{sum(1 for m in margins_b if m > 0)}-{sum(1 for m in margins_b if m <= 0)}",
            'avg_margin': round(statistics.mean(margins_b), 1) if margins_b else 0.0,
            'variance': round(variance_b, 1) if variance_b else 0.0,
            'games': recent_form_b_data[:5]
        }
        
        # ===== VOLATILITY SCORE =====
        # Compute volatility using tempo and variance (fg3_rate from stats or defaults)
        fg3_rate_a = stats_a.fg3_rate if (stats_a and stats_a.fg3_rate) else 35.0
        fg3_rate_b = stats_b.fg3_rate if (stats_b and stats_b.fg3_rate) else 35.0
        
        volatility = compute_volatility_score(
            tempo_a=ratings_a.adj_tempo,
            tempo_b=ratings_b.adj_tempo,
            fg3_rate_a=fg3_rate_a,
            fg3_rate_b=fg3_rate_b,
            recent_variance_a=variance_a,
            recent_variance_b=variance_b
        )
        
        # Build response
        return Response({
            'season': season.display_name,
            'site': site,
            'teamA': {
                'id': team_a.id,
                'name': team_a.name,
                'slug': team_a.slug,
                'logo_url': team_a.logo_url,
                'conference': conference_a_name,
                'rank': ratings_a.rank_adj_em,
                'record': f"{ratings_a.wins}-{ratings_a.losses}",
                'adj_em': round(ratings_a.adj_em, 1),
                'adj_o': round(ratings_a.adj_o, 1),
                'adj_d': round(ratings_a.adj_d, 1),
                'adj_tempo': round(ratings_a.adj_tempo, 1),
                'ffi': round(ffi_a, 1),
            },
            'teamB': {
                'id': team_b.id,
                'name': team_b.name,
                'slug': team_b.slug,
                'logo_url': team_b.logo_url,
                'conference': conference_b_name,
                'rank': ratings_b.rank_adj_em,
                'record': f"{ratings_b.wins}-{ratings_b.losses}",
                'adj_em': round(ratings_b.adj_em, 1),
                'adj_o': round(ratings_b.adj_o, 1),
                'adj_d': round(ratings_b.adj_d, 1),
                'adj_tempo': round(ratings_b.adj_tempo, 1),
                'ffi': round(ffi_b, 1),
            },
            'forecast': forecast,
            'four_factor_edges': ff_edges,
            'ffi_edge': round(ffi_edge, 1),
            'points_breakdown': pts_breakdown,
            'top_drivers': top_drivers,
            'shot_profile': shot_profile,
            'volatility': volatility,
            'recent_form_a': recent_form_a,
            'recent_form_b': recent_form_b,
            'metadata': {
                'hca_points': round(hca_points, 2),
                'prediction_sigma': round(sigma, 2),
                'nat_avg_ortg': round(nat_avg.avg_ortg, 1),
                'coefficients': {
                    'efg': round(nat_avg.coef_efg, 3) if nat_avg.coef_efg else None,
                    'tov': round(nat_avg.coef_tov, 3) if nat_avg.coef_tov else None,
                    'orb': round(nat_avg.coef_orb, 3) if nat_avg.coef_orb else None,
                    'ftr': round(nat_avg.coef_ftr, 3) if nat_avg.coef_ftr else None,
                    'r_squared': round(nat_avg.coef_r_squared, 3) if nat_avg.coef_r_squared else None,
                }
            }
        })



class GameViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/games?season=2026&team=michigan&date=2025-12-01
    GET /api/games/{id}
    
    Returns game details with box scores
    """
    queryset = Game.objects.all().select_related('home_team', 'away_team')
    serializer_class = GameSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by season
        season_year = self.request.query_params.get('season')
        if season_year:
            queryset = queryset.filter(season_year=season_year)
        
        # Filter by team (either home or away)
        team_slug = self.request.query_params.get('team')
        if team_slug:
            team = get_object_or_404(Team, slug=team_slug)
            queryset = queryset.filter(Q(home_team=team) | Q(away_team=team))
        
        # Filter by date
        game_date = self.request.query_params.get('date')
        if game_date:
            queryset = queryset.filter(game_date=game_date)
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.order_by('-game_date', '-start_time_utc')
    
    def retrieve(self, request, pk=None):
        """
        GET /api/games/{id}
        
        Returns full game details including team stats
        """
        game = self.get_object()
        serializer = GameDetailSerializer(game)
        return Response(serializer.data)
