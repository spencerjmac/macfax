"""
Core Django Models for CBB Analytics
Normalized schema for college basketball team statistics
"""

from django.db import models
from django.utils.text import slugify


class Season(models.Model):
    """Represents a basketball season (e.g., 2025-26)"""
    year = models.IntegerField(unique=True, help_text="Ending year (2026 for 2025-26 season)")
    display_name = models.CharField(max_length=20, help_text="Human-readable name")
    is_current = models.BooleanField(default=False, help_text="Is this the active season?")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-year']
    
    def __str__(self):
        return self.display_name
    
    def save(self, *args, **kwargs):
        # Auto-set is_current to False for all others if this is current
        if self.is_current:
            Season.objects.filter(is_current=True).update(is_current=False)
        super().save(*args, **kwargs)


class Conference(models.Model):
    """NCAA conferences"""
    code = models.CharField(max_length=10, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.code})"


class Team(models.Model):
    """NCAA D1 basketball teams (365 teams)"""
    slug = models.SlugField(unique=True, db_index=True, max_length=100)
    name = models.CharField(max_length=100)
    aliases = models.JSONField(default=list, blank=True, help_text="Alternative names")
    logo_url = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class TeamSeasonStats(models.Model):
    """
    Statistics for a team in a specific season
    This is the main table combining data from KenPom, Torvik, CBB Analytics
    """
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='season_stats')
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name='team_stats')
    conference = models.ForeignKey(Conference, on_delete=models.SET_NULL, null=True, blank=True)
    
    # ==================== Record ====================
    games = models.IntegerField(default=0)
    wins = models.IntegerField(default=0)
    losses = models.IntegerField(default=0)
    
    # ==================== National Rankings ====================
    rank = models.IntegerField(null=True, blank=True, help_text="Overall rank")
    rank_adj_em = models.IntegerField(null=True, blank=True)
    rank_adj_o = models.IntegerField(null=True, blank=True)
    rank_adj_d = models.IntegerField(null=True, blank=True)
    t_rank = models.IntegerField(null=True, blank=True, help_text="T-Rank (Torvik composite ranking)")
    ap_poll_week6 = models.IntegerField(null=True, blank=True, help_text="AP Poll ranking at week 6")
    
    # ==================== Core Efficiency Metrics ====================
    adj_em = models.FloatField(help_text="Adjusted Efficiency Margin")
    adj_o = models.FloatField(help_text="Adjusted Offensive Efficiency")
    adj_d = models.FloatField(help_text="Adjusted Defensive Efficiency")
    adj_tempo = models.FloatField(help_text="Adjusted Tempo")
    
    # ==================== Four Factors - Offense ====================
    efg_pct = models.FloatField(help_text="Effective FG%")
    tov_pct = models.FloatField(help_text="Turnover %")
    orb_pct = models.FloatField(help_text="Offensive Rebound %")
    ftr = models.FloatField(help_text="Free Throw Rate")
    
    # ==================== Four Factors - Defense ====================
    efg_pct_d = models.FloatField(help_text="Opponent Effective FG%")
    tov_pct_d = models.FloatField(help_text="Opponent Turnover %")
    drb_pct = models.FloatField(help_text="Defensive Rebound %")
    ftr_d = models.FloatField(help_text="Opponent Free Throw Rate")
    
    # ==================== Shooting Splits ====================
    fg2_pct = models.FloatField(null=True, blank=True, help_text="2-point FG%")
    fg2_pct_d = models.FloatField(null=True, blank=True, help_text="Opponent 2-point FG%")
    fg3_pct = models.FloatField(null=True, blank=True, help_text="3-point FG%")
    fg3_pct_d = models.FloatField(null=True, blank=True, help_text="Opponent 3-point FG%")
    fg3_rate = models.FloatField(null=True, blank=True, help_text="3-point attempt rate")
    fg3_rate_d = models.FloatField(null=True, blank=True, help_text="Opponent 3-point attempt rate")
    ft_pct = models.FloatField(null=True, blank=True, help_text="Free throw percentage")
    
    # ==================== Resume Metrics ====================
    wab = models.FloatField(null=True, blank=True, help_text="Wins Above Bubble")
    sor = models.FloatField(null=True, blank=True, help_text="Strength of Record")
    barthag = models.FloatField(null=True, blank=True, help_text="Barthag win probability")
    luck = models.FloatField(null=True, blank=True, help_text="Luck rating")
    sos_adj_em = models.FloatField(null=True, blank=True, help_text="Strength of Schedule (AdjEM)")
    ncsos_adj_em = models.FloatField(null=True, blank=True, help_text="Non-conference SOS (AdjEM)")
    
    # ==================== Precomputed Margins ====================
    efg_margin = models.FloatField(default=0, help_text="eFG% - Opp eFG%")
    tov_edge = models.FloatField(default=0, help_text="Opp TOV% - TOV%")
    reb_edge = models.FloatField(default=0, help_text="ORB% - Opponent ORB%")
    ftr_margin = models.FloatField(default=0, help_text="FTR - Opp FTR")
    
    # ==================== Four Factor Index ====================
    # Z-scores for four factors (computed per-season)
    efg_margin_z = models.FloatField(null=True, blank=True, help_text="eFG Margin Z-score")
    tov_edge_z = models.FloatField(null=True, blank=True, help_text="Turnover Edge Z-score")
    reb_edge_z = models.FloatField(null=True, blank=True, help_text="Rebounding Edge Z-score")
    ftr_margin_z = models.FloatField(null=True, blank=True, help_text="FTR Margin Z-score")
    
    # Four Factor Index (weighted composite)
    four_factor_index_wz = models.FloatField(null=True, blank=True, help_text="Four Factor Weighted Z-score")
    four_factor_index_100 = models.FloatField(null=True, blank=True, db_index=True, help_text="Four Factor Index (0-100 scale)")
    rank_four_factor_index_100 = models.IntegerField(null=True, blank=True, help_text="Rank by Four Factor Index (1 = best)")
    
    # ==================== Game-Level Adjusted Ratings (NEW) ====================
    # Computed from game-level boxscores with venue tax and Bayesian shrinkage
    aor = models.FloatField(null=True, blank=True, help_text="Adjusted Offensive Rating (pts/100 possessions)")
    adr = models.FloatField(null=True, blank=True, help_text="Adjusted Defensive Rating (pts/100 possessions)")
    aem = models.FloatField(null=True, blank=True, help_text="Adjusted Net Rating (AOR - ADR)")
    
    # 0-100 "2K-style" ratings (higher is better for all)
    aor_100 = models.FloatField(null=True, blank=True, help_text="AOR mapped to 0-100 scale via z-score")
    adr_100 = models.FloatField(null=True, blank=True, help_text="ADR mapped to 0-100 scale (inverted: lower ADR = higher rating)")
    net_100 = models.FloatField(null=True, blank=True, help_text="Net Rating mapped to 0-100 scale via z-score")
    
    # Rankings for adjusted ratings
    rank_aor = models.IntegerField(null=True, blank=True, help_text="Rank by AOR (1 = best offense)")
    rank_adr = models.IntegerField(null=True, blank=True, help_text="Rank by ADR (1 = best defense)")
    rank_aem = models.IntegerField(null=True, blank=True, help_text="Rank by AEM/Net (1 = best overall)")
    
    # ==================== Evan Miya Relative Ratings ====================
    # Relative ratings centered around 0 (above/below average)
    em_o_rate = models.FloatField(null=True, blank=True, help_text="Evan Miya O-Rate (relative to average)")
    em_d_rate = models.FloatField(null=True, blank=True, help_text="Evan Miya D-Rate (relative to average)")
    em_rating = models.FloatField(null=True, blank=True, help_text="Evan Miya Relative Rating (O+D)")
    rank_em = models.IntegerField(null=True, blank=True, help_text="Evan Miya Relative Ranking")
    
    # Kill Shots metrics (Evan Miya)
    em_kill_shots_pg = models.FloatField(null=True, blank=True, help_text="Kill Shots per game")
    em_kill_shots_conceded_pg = models.FloatField(null=True, blank=True, help_text="Kill Shots conceded per game")
    em_kill_shot_margin_pg = models.FloatField(null=True, blank=True, help_text="Kill Shot margin per game")
    
    # ==================== CBB Analytics Per-Game & Percentage Stats ====================
    cbb_ast_g = models.FloatField(null=True, blank=True, help_text="Assists per game")
    cbb_ast_pct = models.FloatField(null=True, blank=True, help_text="Assist percentage")
    cbb_blk_g = models.FloatField(null=True, blank=True, help_text="Blocks per game")
    cbb_blk_pct = models.FloatField(null=True, blank=True, help_text="Block percentage")
    cbb_dpf_g = models.FloatField(null=True, blank=True, help_text="Defensive personal fouls per game")
    cbb_drb_g = models.FloatField(null=True, blank=True, help_text="Defensive rebounds per game")
    cbb_fg_pct = models.FloatField(null=True, blank=True, help_text="Field goal percentage")
    cbb_hkm_pct = models.FloatField(null=True, blank=True, help_text="Help-Kill Metric percentage")
    cbb_opf_g = models.FloatField(null=True, blank=True, help_text="Offensive personal fouls per game")
    cbb_pace_raw = models.FloatField(null=True, blank=True, help_text="Raw pace (possessions per game)")
    cbb_pf_g = models.FloatField(null=True, blank=True, help_text="Personal fouls per game")
    cbb_pts_g = models.FloatField(null=True, blank=True, help_text="Points per game")
    cbb_reb_g = models.FloatField(null=True, blank=True, help_text="Rebounds per game")
    cbb_stl_g = models.FloatField(null=True, blank=True, help_text="Steals per game")
    cbb_tov_g = models.FloatField(null=True, blank=True, help_text="Turnovers per game")
    
    # ==================== Data Provenance ====================
    has_kenpom = models.BooleanField(default=False)
    has_torvik = models.BooleanField(default=False)
    has_cbb_analytics = models.BooleanField(default=False)
    has_evan_miya = models.BooleanField(default=False)
    
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = [['team', 'season']]
        indexes = [
            models.Index(fields=['season', 'rank']),
            models.Index(fields=['season', 'conference']),
            models.Index(fields=['season', 'adj_em']),
        ]
        ordering = ['season', 'rank']
        verbose_name_plural = "Team Season Stats"
    
    def __str__(self):
        return f"{self.team.name} {self.season.display_name} (Rank #{self.rank})"
    
    @property
    def record(self):
        """Returns record as string (e.g., '22-3')"""
        return f"{self.wins}-{self.losses}"
    
    def save(self, *args, **kwargs):
        # Auto-calculate margins
        self.efg_margin = self.efg_pct - self.efg_pct_d
        self.tov_edge = self.tov_pct_d - self.tov_pct
        # Rebounding Edge = ORB% - Opponent ORB% (Torvik's 'drb' is opponent ORB%)
        self.reb_edge = self.orb_pct - self.drb_pct
        self.ftr_margin = self.ftr - self.ftr_d
        super().save(*args, **kwargs)


class DataIngestionRun(models.Model):
    """Track data ingestion runs for auditing and debugging"""
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    status = models.CharField(
        max_length=20,
        choices=[
            ('running', 'Running'),
            ('success', 'Success'),
            ('error', 'Error'),
        ],
        default='running'
    )
    
    teams_ingested = models.IntegerField(default=0)
    error_log = models.TextField(null=True, blank=True)
    
    class Meta:
        ordering = ['-started_at']
    
    def __str__(self):
        return f"Ingestion {self.season.display_name} - {self.status} ({self.started_at})"


class GameLog(models.Model):
    """
    Game-level boxscore data for computing AOR/ADR/AEM metrics
    
    Required fields for AOR/ADR computation:
    - Pts, PtsAllowed, FGA, OR (offensive rebounds), TO (turnovers), FTA
    - location (home/away/neutral) for venue tax
    - opponent for opponent adjustment lookup
    - date for temporal matching
    """
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='game_logs')
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name='game_logs')
    
    # Game identifiers
    date = models.DateField(db_index=True)
    opponent = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='opponent_games', null=True, blank=True)
    opponent_name = models.CharField(max_length=100, help_text="Opponent name (for matching)")
    location = models.CharField(
        max_length=1,
        choices=[('H', 'Home'), ('A', 'Away'), ('N', 'Neutral')],
        help_text="H=Home, A=Away, N=Neutral"
    )
    
    # Boxscore stats (required for AOR/ADR computation)
    pts = models.IntegerField(help_text="Points scored")
    pts_allowed = models.IntegerField(help_text="Points allowed")
    fga = models.IntegerField(help_text="Field goal attempts")
    fgm = models.IntegerField(null=True, blank=True, help_text="Field goals made")
    or_total = models.IntegerField(help_text="Offensive rebounds", db_column='offensive_rebounds')
    to = models.IntegerField(help_text="Turnovers")
    fta = models.IntegerField(help_text="Free throw attempts")
    ftm = models.IntegerField(null=True, blank=True, help_text="Free throws made")
    
    # Opponent boxscore (for their efficiency)
    opp_fga = models.IntegerField(null=True, blank=True, help_text="Opponent field goal attempts")
    opp_or = models.IntegerField(null=True, blank=True, help_text="Opponent offensive rebounds")
    opp_to = models.IntegerField(null=True, blank=True, help_text="Opponent turnovers")
    opp_fta = models.IntegerField(null=True, blank=True, help_text="Opponent free throw attempts")
    
    # Computed fields (auto-calculated)
    possessions = models.FloatField(null=True, blank=True, help_text="Estimated possessions via formula")
    raw_oe = models.FloatField(null=True, blank=True, help_text="Raw offensive efficiency (pts/100 poss)")
    raw_de = models.FloatField(null=True, blank=True, help_text="Raw defensive efficiency (pts allowed/100 poss)")
    
    # Opponent adjusted ratings (joined from KenPom/Torvik at computation time)
    opp_adj_o = models.FloatField(null=True, blank=True, help_text="Opponent's adjusted offensive rating (for defense calc)")
    opp_adj_d = models.FloatField(null=True, blank=True, help_text="Opponent's adjusted defensive rating (for offense calc)")
    
    # Game-level adjusted ratings (with venue tax)
    aor_game = models.FloatField(null=True, blank=True, help_text="This game's AOR (with venue tax)")
    adr_game = models.FloatField(null=True, blank=True, help_text="This game's ADR (with venue tax)")
    
    # Weighting
    recency_mult = models.FloatField(default=1.0, help_text="Recency multiplier (future use)")
    weight = models.FloatField(null=True, blank=True, help_text="Game weight = possessions * recency_mult")
    
    # Result
    won = models.BooleanField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = [['team', 'date', 'opponent_name']]
        indexes = [
            models.Index(fields=['team', 'season', 'date']),
            models.Index(fields=['date']),
        ]
        ordering = ['date']
    
    def __str__(self):
        result = "W" if self.won else "L" if self.won is not None else "?"
        return f"{self.team.name} vs {self.opponent_name} ({self.date}) - {result}"
    
    def save(self, *args, **kwargs):
        # Auto-calculate possessions and efficiencies
        if all([self.fga is not None, self.or_total is not None, self.to is not None, self.fta is not None]):
            self.possessions = self.fga - self.or_total + self.to + 0.475 * self.fta
            if self.possessions > 0:
                self.raw_oe = 100 * (self.pts / self.possessions)
                self.raw_de = 100 * (self.pts_allowed / self.possessions)
        
        # Auto-calculate weight
        if self.possessions and self.recency_mult:
            self.weight = self.possessions * self.recency_mult
        
        # Auto-determine won
        if self.won is None and self.pts is not None and self.pts_allowed is not None:
            self.won = self.pts > self.pts_allowed
        
        super().save(*args, **kwargs)
