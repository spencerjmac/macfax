"""
DRF Serializers for CBB Analytics API
"""

from rest_framework import serializers
from core.models import Season, Conference, Team, TeamSeasonStats
from .checklist import compute_national_champion_checklist, compute_season_context


class SeasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Season
        fields = ['id', 'year', 'display_name', 'is_current']


class ConferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conference
        fields = ['id', 'code', 'name']


class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ['id', 'slug', 'name', 'aliases', 'logo_url']


class TeamSeasonStatsSerializer(serializers.ModelSerializer):
    """Full stats for a team in a season"""
    team_name = serializers.CharField(source='team.name', read_only=True)
    team_slug = serializers.CharField(source='team.slug', read_only=True)
    team_logo = serializers.CharField(source='team.logo_url', read_only=True)
    conference_code = serializers.CharField(source='conference.code', read_only=True)
    conference_name = serializers.CharField(source='conference.name', read_only=True)
    season_year = serializers.IntegerField(source='season.year', read_only=True)
    record = serializers.CharField(read_only=True)
    national_champion_checklist = serializers.SerializerMethodField()
    
    class Meta:
        model = TeamSeasonStats
        fields = [
            # Identifiers
            'id', 'team_name', 'team_slug', 'team_logo', 
            'conference_code', 'conference_name', 'season_year',
            
            # Record
            'games', 'wins', 'losses', 'record',
            
            # Rankings
            'rank', 'rank_adj_em', 'rank_adj_o', 'rank_adj_d',
            'rank_aor', 'rank_adr', 'rank_aem',
            'rank_four_factor_index_100',
            't_rank', 'ap_poll_week6',
            
            # Core Metrics
            'adj_em', 'adj_o', 'adj_d', 'adj_tempo',
            
            # Game-Level Adjusted Ratings (NEW)
            'aor', 'adr', 'aem',
            'aor_100', 'adr_100', 'net_100',
            
            # Four Factors - Offense
            'efg_pct', 'tov_pct', 'orb_pct', 'ftr',
            
            # Four Factors - Defense
            'efg_pct_d', 'tov_pct_d', 'drb_pct', 'ftr_d',
            
            # Margins
            'efg_margin', 'tov_edge', 'reb_edge', 'ftr_margin',
            
            # Four Factor Index (Z-scores and composite metric)
            'efg_margin_z', 'tov_edge_z', 'reb_edge_z', 'ftr_margin_z',
            'four_factor_index_wz', 'four_factor_index_100',
            
            # Shooting Splits
            'fg2_pct', 'fg2_pct_d', 'fg3_pct', 'fg3_pct_d', 
            'fg3_rate', 'fg3_rate_d', 'ft_pct',
            
            # Resume
            'wab', 'sor', 'barthag', 'luck', 'sos_adj_em', 'ncsos_adj_em',
            
            # National Champion Checklist
            'national_champion_checklist',
            
            # Provenance
            'has_kenpom', 'has_torvik', 'has_cbb_analytics',
            'last_updated',
        ]
    
    def get_national_champion_checklist(self, obj):
        """Compute the national champion checklist for this team"""
        # Check if we have cached season context in the serializer context
        context = self.context.get('season_context')
        
        # If not cached, compute it (less efficient, but works)
        if context is None:
            context = compute_season_context(obj.season)
        
        return compute_national_champion_checklist(obj, context)


class RankingsSerializer(serializers.ModelSerializer):
    """
    Simplified serializer for rankings table
    Only includes fields needed for the sortable/filterable table
    """
    team_name = serializers.CharField(source='team.name', read_only=True)
    team_slug = serializers.CharField(source='team.slug', read_only=True)
    team_logo = serializers.CharField(source='team.logo_url', read_only=True)
    conference = serializers.CharField(source='conference.code', read_only=True)
    record = serializers.CharField(read_only=True)
    
    class Meta:
        model = TeamSeasonStats
        fields = [
            'rank', 'team_name', 'team_slug', 'team_logo', 'conference', 
            'record', 'adj_em', 'adj_o', 'adj_d', 'adj_tempo',
            # New adjusted rating fields
            'aor', 'adr', 'aem', 'aor_100', 'adr_100', 'net_100',
            'rank_aor', 'rank_adr', 'rank_aem',
            # Four Factor Index
            'four_factor_index_100', 'rank_four_factor_index_100',
            'efg_pct', 'tov_pct', 'orb_pct', 'ftr',
            'efg_pct_d', 'tov_pct_d', 'drb_pct', 'ftr_d',
        ]


class TeamDetailSerializer(serializers.Serializer):
    """
    Combined serializer for team detail page
    Includes team info + stats across all available seasons
    """
    team = TeamSerializer()
    seasons = TeamSeasonStatsSerializer(many=True)
    current_season_stats = TeamSeasonStatsSerializer()
