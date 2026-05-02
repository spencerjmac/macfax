"""
Team-centric models: Team, TeamExternalId, TeamSeasonStats, TeamSeasonRatings,
TeamSeasonMetrics, TeamRosterFit, TeamSeasonProjection
"""

from django.db import models
from django.utils.text import slugify

from .base import Season, Conference


class Team(models.Model):
    """NCAA D1 basketball teams (365 teams)"""

    slug = models.SlugField(unique=True, db_index=True, max_length=100)
    name = models.CharField(max_length=100)
    aliases = models.JSONField(default=list, blank=True, help_text="Alternative names")
    logo_url = models.CharField(max_length=255, null=True, blank=True)
    is_d1 = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Is this a Division I team? False for non-D1 opponents.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class TeamExternalId(models.Model):
    """
    Maps external data source IDs/names to our canonical Team records
    Supports NCAA API, ESPN, and other sources
    """

    SOURCE_CHOICES = [
        ("ncaa", "NCAA Stats API"),
        ("espn", "ESPN API"),
        ("kenpom", "KenPom"),
        ("torvik", "Barttorvik"),
        ("evanmiya", "Evan Miya"),
    ]

    team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="external_ids"
    )
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    external_id = models.CharField(
        max_length=100, help_text="External source's team ID"
    )
    external_name = models.CharField(
        max_length=200, help_text="External source's team name"
    )
    confidence = models.FloatField(
        default=1.0, help_text="Match confidence score (0.0-1.0, 1.0 = exact match)"
    )
    is_manual_override = models.BooleanField(
        default=False, help_text="True if this mapping was manually specified"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [["team", "source"]]
        indexes = [
            models.Index(fields=["source", "external_id"]),
            models.Index(fields=["source", "external_name"]),
        ]
        verbose_name = "Team External ID"
        verbose_name_plural = "Team External IDs"

    def __str__(self):
        return f"{self.team.name} → {self.source}:{self.external_id} ({self.external_name})"


class TeamSeasonStats(models.Model):
    """
    Statistics for a team in a specific season
    This is the main table combining data from KenPom, Torvik, CBB Analytics
    """

    team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="season_stats"
    )
    season = models.ForeignKey(
        Season, on_delete=models.CASCADE, related_name="team_stats"
    )
    conference = models.ForeignKey(
        Conference, on_delete=models.SET_NULL, null=True, blank=True
    )

    # ==================== Record ====================
    games = models.IntegerField(default=0)
    wins = models.IntegerField(default=0)
    losses = models.IntegerField(default=0)

    # ==================== National Rankings ====================
    rank = models.IntegerField(null=True, blank=True, help_text="Overall rank")
    rank_adj_em = models.IntegerField(null=True, blank=True)
    rank_adj_o = models.IntegerField(null=True, blank=True)
    rank_adj_d = models.IntegerField(null=True, blank=True)
    t_rank = models.IntegerField(
        null=True, blank=True, help_text="T-Rank (Torvik composite ranking)"
    )
    ap_poll_week6 = models.IntegerField(
        null=True, blank=True, help_text="AP Poll ranking at week 6"
    )

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
    fg2_pct_d = models.FloatField(
        null=True, blank=True, help_text="Opponent 2-point FG%"
    )
    fg3_pct = models.FloatField(null=True, blank=True, help_text="3-point FG%")
    fg3_pct_d = models.FloatField(
        null=True, blank=True, help_text="Opponent 3-point FG%"
    )
    fg3_rate = models.FloatField(
        null=True, blank=True, help_text="3-point attempt rate"
    )
    fg3_rate_d = models.FloatField(
        null=True, blank=True, help_text="Opponent 3-point attempt rate"
    )
    ft_pct = models.FloatField(null=True, blank=True, help_text="Free throw percentage")

    # ==================== Resume Metrics ====================
    wab = models.FloatField(null=True, blank=True, help_text="Wins Above Bubble")
    sor = models.FloatField(null=True, blank=True, help_text="Strength of Record")
    barthag = models.FloatField(
        null=True, blank=True, help_text="Barthag win probability"
    )
    luck = models.FloatField(null=True, blank=True, help_text="Luck rating")
    sos_adj_em = models.FloatField(
        null=True, blank=True, help_text="Strength of Schedule (AdjEM)"
    )
    ncsos_adj_em = models.FloatField(
        null=True, blank=True, help_text="Non-conference SOS (AdjEM)"
    )

    # ==================== Precomputed Margins ====================
    efg_margin = models.FloatField(default=0, help_text="eFG% - Opp eFG%")
    tov_edge = models.FloatField(default=0, help_text="Opp TOV% - TOV%")
    reb_edge = models.FloatField(default=0, help_text="ORB% - Opponent ORB%")
    ftr_margin = models.FloatField(default=0, help_text="FTR - Opp FTR")

    # ==================== Four Factor Index ====================
    # Z-scores for four factors (computed per-season)
    efg_margin_z = models.FloatField(
        null=True, blank=True, help_text="eFG Margin Z-score"
    )
    tov_edge_z = models.FloatField(
        null=True, blank=True, help_text="Turnover Edge Z-score"
    )
    reb_edge_z = models.FloatField(
        null=True, blank=True, help_text="Rebounding Edge Z-score"
    )
    ftr_margin_z = models.FloatField(
        null=True, blank=True, help_text="FTR Margin Z-score"
    )

    # Four Factor Index (weighted composite)
    four_factor_index_wz = models.FloatField(
        null=True, blank=True, help_text="Four Factor Weighted Z-score"
    )
    four_factor_index_100 = models.FloatField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Four Factor Index (0-100 scale)",
    )
    rank_four_factor_index_100 = models.IntegerField(
        null=True, blank=True, help_text="Rank by Four Factor Index (1 = best)"
    )

    # ==================== Game-Level Adjusted Ratings (NEW) ====================
    # Computed from game-level boxscores with venue tax and Bayesian shrinkage
    aor = models.FloatField(
        null=True,
        blank=True,
        help_text="Adjusted Offensive Rating (pts/100 possessions)",
    )
    adr = models.FloatField(
        null=True,
        blank=True,
        help_text="Adjusted Defensive Rating (pts/100 possessions)",
    )
    aem = models.FloatField(
        null=True, blank=True, help_text="Adjusted Net Rating (AOR - ADR)"
    )

    # 0-100 "2K-style" ratings (higher is better for all)
    aor_100 = models.FloatField(
        null=True, blank=True, help_text="AOR mapped to 0-100 scale via z-score"
    )
    adr_100 = models.FloatField(
        null=True,
        blank=True,
        help_text="ADR mapped to 0-100 scale (inverted: lower ADR = higher rating)",
    )
    net_100 = models.FloatField(
        null=True, blank=True, help_text="Net Rating mapped to 0-100 scale via z-score"
    )

    # Rankings for adjusted ratings
    rank_aor = models.IntegerField(
        null=True, blank=True, help_text="Rank by AOR (1 = best offense)"
    )
    rank_adr = models.IntegerField(
        null=True, blank=True, help_text="Rank by ADR (1 = best defense)"
    )
    rank_aem = models.IntegerField(
        null=True, blank=True, help_text="Rank by AEM/Net (1 = best overall)"
    )

    # ==================== Evan Miya Relative Ratings ====================
    # Relative ratings centered around 0 (above/below average)
    em_o_rate = models.FloatField(
        null=True, blank=True, help_text="Evan Miya O-Rate (relative to average)"
    )
    em_d_rate = models.FloatField(
        null=True, blank=True, help_text="Evan Miya D-Rate (relative to average)"
    )
    em_rating = models.FloatField(
        null=True, blank=True, help_text="Evan Miya Relative Rating (O+D)"
    )
    rank_em = models.IntegerField(
        null=True, blank=True, help_text="Evan Miya Relative Ranking"
    )

    # Kill Shots metrics (Evan Miya)
    em_kill_shots_pg = models.FloatField(
        null=True, blank=True, help_text="Kill Shots per game"
    )
    em_kill_shots_conceded_pg = models.FloatField(
        null=True, blank=True, help_text="Kill Shots conceded per game"
    )
    em_kill_shot_margin_pg = models.FloatField(
        null=True, blank=True, help_text="Kill Shot margin per game"
    )

    # ==================== CBB Analytics Per-Game & Percentage Stats ====================
    cbb_ast_g = models.FloatField(null=True, blank=True, help_text="Assists per game")
    cbb_ast_pct = models.FloatField(
        null=True, blank=True, help_text="Assist percentage"
    )
    cbb_blk_g = models.FloatField(null=True, blank=True, help_text="Blocks per game")
    cbb_blk_pct = models.FloatField(null=True, blank=True, help_text="Block percentage")
    cbb_dpf_g = models.FloatField(
        null=True, blank=True, help_text="Defensive personal fouls per game"
    )
    cbb_drb_g = models.FloatField(
        null=True, blank=True, help_text="Defensive rebounds per game"
    )
    cbb_fg_pct = models.FloatField(
        null=True, blank=True, help_text="Field goal percentage"
    )
    cbb_hkm_pct = models.FloatField(
        null=True, blank=True, help_text="Help-Kill Metric percentage"
    )
    cbb_opf_g = models.FloatField(
        null=True, blank=True, help_text="Offensive personal fouls per game"
    )
    cbb_pace_raw = models.FloatField(
        null=True, blank=True, help_text="Raw pace (possessions per game)"
    )
    cbb_pf_g = models.FloatField(
        null=True, blank=True, help_text="Personal fouls per game"
    )
    cbb_pts_g = models.FloatField(null=True, blank=True, help_text="Points per game")
    cbb_reb_g = models.FloatField(null=True, blank=True, help_text="Rebounds per game")
    cbb_stl_g = models.FloatField(null=True, blank=True, help_text="Steals per game")
    cbb_tov_g = models.FloatField(null=True, blank=True, help_text="Turnovers per game")

    # ==================== Data Provenance ====================
    has_kenpom = models.BooleanField(default=False)
    has_torvik = models.BooleanField(default=False)
    has_cbb_analytics = models.BooleanField(default=False)
    has_evan_miya = models.BooleanField(default=False)

    # ==================== Coaching ====================
    is_first_year_coach = models.BooleanField(
        default=False,
        help_text=(
            "True when the head coach is in their first season with this program. "
            "Set manually each season via python manage.py set_coach_flags --season YEAR. "
            "Used to add uncertainty to team projections for high-variance coaching transitions."
        ),
    )

    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["team", "season"]]
        indexes = [
            models.Index(fields=["season", "rank"]),
            models.Index(fields=["season", "conference"]),
            models.Index(fields=["season", "adj_em"]),
        ]
        ordering = ["season", "rank"]
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


class TeamSeasonRatings(models.Model):
    """
    Computed adjusted ratings (proprietary system) for a team-season
    Generated by compute_adjusted_ratings command
    """

    team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="season_ratings"
    )
    season = models.ForeignKey(
        Season, on_delete=models.CASCADE, related_name="team_ratings"
    )

    # Adjusted efficiency metrics (pts per 100 possessions)
    adj_o = models.FloatField(default=0.0, help_text="Adjusted Offensive Rating")
    adj_d = models.FloatField(default=0.0, help_text="Adjusted Defensive Rating")
    adj_em = models.FloatField(default=0.0, help_text="Adjusted Net Rating (O - D)")
    adj_tempo = models.FloatField(default=0.0, help_text="Adjusted Tempo (possessions per game)")

    # ==================== Adjusted Four Factors - Offense ====================
    adj_efg_pct = models.FloatField(default=0.0, help_text="Adjusted Effective FG%")
    adj_tov_pct = models.FloatField(default=0.0, help_text="Adjusted Turnover %")
    adj_orb_pct = models.FloatField(
        default=0.0, help_text="Adjusted Offensive Rebound %"
    )
    adj_ftr = models.FloatField(default=0.0, help_text="Adjusted Free Throw Rate")

    # ==================== Adjusted Four Factors - Defense ====================
    adj_opp_efg_pct = models.FloatField(default=0.0, help_text="Adjusted Opponent eFG%")
    adj_opp_tov_pct = models.FloatField(default=0.0, help_text="Adjusted Opponent TOV%")
    adj_opp_orb_pct = models.FloatField(default=0.0, help_text="Adjusted Opponent ORB%")
    adj_drb_pct = models.FloatField(
        default=0.0, help_text="Adjusted Defensive Rebound %"
    )
    adj_opp_ftr = models.FloatField(default=0.0, help_text="Adjusted Opponent FTR")

    # ==================== Adjusted Four Factor Margins ====================
    adj_efg_margin = models.FloatField(default=0.0, help_text="Adjusted eFG margin")
    adj_tov_edge = models.FloatField(default=0.0, help_text="Adjusted TOV edge")
    adj_reb_edge = models.FloatField(default=0.0, help_text="Adjusted REB edge")
    adj_ftr_margin = models.FloatField(default=0.0, help_text="Adjusted FTR margin")

    # ==================== Four Factor Index ====================
    ffi_raw = models.FloatField(
        default=50.0, help_text="Four Factor Index (from raw margins, 0-100 scale)"
    )
    ffi_adj = models.FloatField(
        default=50.0, help_text="Four Factor Index (from adjusted margins, 0-100 scale)"
    )

    # ==================== Resume Metrics ====================
    wab = models.FloatField(null=True, blank=True, help_text="Wins Above Bubble")
    sor_rank = models.IntegerField(
        null=True, blank=True, help_text="Strength of Record rank"
    )
    net_rank = models.IntegerField(null=True, blank=True, help_text="NCAA NET ranking")
    sos_rank = models.IntegerField(
        null=True, blank=True, help_text="Strength of Schedule rank (1 = hardest)"
    )
    sos_win_pct = models.FloatField(
        null=True,
        blank=True,
        help_text="Expected win% for an average D1 team vs this schedule",
    )

    # Rankings
    rank_adj_o = models.IntegerField(null=True, blank=True)
    rank_adj_d = models.IntegerField(null=True, blank=True)
    rank_adj_em = models.IntegerField(null=True, blank=True)
    ap_poll_week6 = models.IntegerField(
        null=True, blank=True, help_text="AP Poll Week 6 ranking (1-25, null if unranked)"
    )

    # NCAA Tournament
    TOURNAMENT_REGION_CHOICES = [
        ('South', 'South'),
        ('East', 'East'),
        ('West', 'West'),
        ('Midwest', 'Midwest'),
    ]
    tournament_seed = models.IntegerField(
        null=True, blank=True,
        help_text="NCAA Tournament seed (1-16, null if not in tournament)"
    )
    tournament_region = models.CharField(
        max_length=20,
        null=True, blank=True,
        choices=TOURNAMENT_REGION_CHOICES,
        help_text="NCAA Tournament region (South/East/West/Midwest)"
    )

    # Model parameters
    games_played = models.IntegerField(
        default=0, help_text="Total games played (all opponents)"
    )
    wins = models.IntegerField(default=0, help_text="Total wins (all opponents)")
    losses = models.IntegerField(default=0, help_text="Total losses (all opponents)")
    d1_games_played = models.IntegerField(
        default=0, help_text="Games vs D1 opponents only"
    )
    total_possessions = models.FloatField(default=0.0)
    hca_estimate = models.FloatField(
        null=True, blank=True, help_text="Home court advantage (in points per 100 poss)"
    )

    # Metadata
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [["team", "season"]]
        indexes = [
            models.Index(fields=["season", "adj_em"]),
        ]
        verbose_name = "Team Season Ratings"
        verbose_name_plural = "Team Season Ratings"

    def __str__(self):
        return f"{self.team.name} {self.season.display_name}: O={self.adj_o:.1f} D={self.adj_d:.1f}"


class TeamSeasonMetrics(models.Model):
    """
    Aggregated season metrics computed from game logs
    Includes Four Factors, Kill Shots, and CBB Analytics stats
    Generated by compute_team_metrics command
    """

    team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="season_metrics"
    )
    season = models.ForeignKey(
        Season, on_delete=models.CASCADE, related_name="team_metrics"
    )
    conference = models.ForeignKey(
        Conference,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="team_metrics",
        help_text="Conference for this team-season (for filtering/display)",
    )

    # Games played
    games = models.IntegerField(default=0)

    # ==================== Totals ====================
    total_pts = models.IntegerField(default=0)
    total_pts_allowed = models.IntegerField(default=0)
    total_possessions = models.FloatField(default=0.0)
    total_opp_possessions = models.FloatField(default=0.0)

    # Shooting totals
    total_fgm = models.IntegerField(default=0)
    total_fga = models.IntegerField(default=0)
    total_fg3m = models.IntegerField(default=0)
    total_fg3a = models.IntegerField(default=0)
    total_ftm = models.IntegerField(default=0)
    total_fta = models.IntegerField(default=0)

    # Rebounding totals
    total_oreb = models.IntegerField(default=0)
    total_dreb = models.IntegerField(default=0)
    total_reb = models.IntegerField(default=0)
    total_opp_dreb = models.IntegerField(default=0)

    # Other totals
    total_ast = models.IntegerField(default=0)
    total_stl = models.IntegerField(default=0)
    total_blk = models.IntegerField(default=0)
    total_tov = models.IntegerField(default=0)
    total_pf = models.IntegerField(default=0)

    # ==================== Per-Game Averages ====================
    ppg = models.FloatField(default=0.0, help_text="Points per game")
    papg = models.FloatField(default=0.0, help_text="Points allowed per game")
    pace = models.FloatField(default=0.0, help_text="Possessions per game")

    # ==================== Per-Possession Metrics ====================
    ortg = models.FloatField(default=0.0, help_text="Offensive rating (pts/100 poss)")
    drtg = models.FloatField(
        default=0.0, help_text="Defensive rating (pts allowed/100 poss)"
    )
    net_rtg = models.FloatField(default=0.0, help_text="Net rating (ORtg - DRtg)")

    # ==================== Four Factors - Offense ====================
    efg_pct = models.FloatField(default=0.0, help_text="Effective FG%")
    tov_pct = models.FloatField(default=0.0, help_text="Turnover %")
    orb_pct = models.FloatField(default=0.0, help_text="Offensive Rebound %")
    ftr = models.FloatField(default=0.0, help_text="Free Throw Rate")

    # ==================== Four Factors - Defense ====================
    opp_efg_pct = models.FloatField(default=0.0, help_text="Opponent eFG%")
    opp_tov_pct = models.FloatField(default=0.0, help_text="Opponent TOV%")
    opp_orb_pct = models.FloatField(default=0.0, help_text="Opponent ORB%")
    drb_pct = models.FloatField(default=0.0, help_text="Defensive Rebound %")
    opp_ftr = models.FloatField(default=0.0, help_text="Opponent FTR")

    # ==================== Four Factor Margins ====================
    efg_margin = models.FloatField(default=0.0)
    tov_edge = models.FloatField(default=0.0)
    reb_edge = models.FloatField(default=0.0)
    ftr_margin = models.FloatField(default=0.0)

    # ==================== Kill Shots ====================
    kill_shots_for = models.IntegerField(default=0, help_text="Total kill shots scored")
    kill_shots_against = models.IntegerField(
        default=0, help_text="Total kill shots allowed"
    )
    kill_shots_pg = models.FloatField(default=0.0, help_text="Kill shots per game")
    kill_shots_conceded_pg = models.FloatField(default=0.0)
    kill_shot_margin_pg = models.FloatField(default=0.0)

    # ==================== CBB Analytics Stats ====================
    ast_g = models.FloatField(default=0.0, help_text="Assists per game")
    ast_pct = models.FloatField(null=True, blank=True, help_text="Assist %")
    blk_g = models.FloatField(default=0.0, help_text="Blocks per game")
    blk_pct = models.FloatField(null=True, blank=True, help_text="Block %")
    dpf_g = models.FloatField(default=0.0, help_text="Defensive fouls per game")

    # Metadata
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [["team", "season"]]
        indexes = [
            models.Index(fields=["season", "net_rtg"]),
        ]
        verbose_name = "Team Season Metrics"
        verbose_name_plural = "Team Season Metrics"

    def __str__(self):
        return f"{self.team.name} {self.season.display_name}: {self.ppg:.1f} ppg, ORtg={self.ortg:.1f}"


class TeamRosterFit(models.Model):
    """
    Phase 3: Roster Fit Score for a team's projected next-season roster.

    Generated by compute_roster_fit (run_fit_pipeline).  Overwrites the
    previous row for the same (team, projected_season_year) on each run.

    All subcomponent scores are on 0-100 (50 = D1 average, higher = better).
    Structural penalties are stored as JSON lists for diagnostic inspection.

    This table stores baseline projections only.  Hypothetical / sandbox
    rosters are scored statelessly via score_roster_fit() without DB writes.
    """

    team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="roster_fits",
    )
    from_season = models.ForeignKey(
        Season, on_delete=models.CASCADE, related_name="team_roster_fits",
        help_text="The season the projection is based on (Phase 1 source season)",
    )
    projected_season_year = models.IntegerField(
        help_text="Season year being projected to (e.g. 2027 if from_season.year=2026)",
    )
    n_players = models.IntegerField(
        default=0, help_text="Number of players included in this fit computation",
    )

    # ── Overall scores ────────────────────────────────────────────────────────
    overall_fit_score   = models.FloatField(null=True, blank=True)
    offensive_fit_score = models.FloatField(null=True, blank=True)
    defensive_fit_score = models.FloatField(null=True, blank=True)

    # ── Offensive subcomponents ───────────────────────────────────────────────
    creation_fit         = models.FloatField(null=True, blank=True)
    shooting_fit         = models.FloatField(null=True, blank=True)
    ball_security_fit    = models.FloatField(null=True, blank=True)
    finishing_fit        = models.FloatField(null=True, blank=True)
    pressure_fit         = models.FloatField(null=True, blank=True)
    off_rebounding_fit   = models.FloatField(null=True, blank=True)
    role_balance_off_fit = models.FloatField(null=True, blank=True)
    off_total_penalty    = models.FloatField(null=True, blank=True)

    # ── Defensive subcomponents ───────────────────────────────────────────────
    rim_protection_fit    = models.FloatField(null=True, blank=True)
    def_rebounding_fit    = models.FloatField(null=True, blank=True)
    disruption_fit        = models.FloatField(null=True, blank=True)
    foul_discipline_fit   = models.FloatField(null=True, blank=True)
    perimeter_defense_fit = models.FloatField(null=True, blank=True)
    size_coverage_fit     = models.FloatField(null=True, blank=True)
    mobility_fit          = models.FloatField(null=True, blank=True)
    role_balance_def_fit  = models.FloatField(null=True, blank=True)
    def_total_penalty     = models.FloatField(null=True, blank=True)

    # ── Diagnostics (JSON) ────────────────────────────────────────────────────
    off_penalties         = models.JSONField(null=True, blank=True,
                               help_text="List of [label, pts] offensive structural penalties")
    def_penalties         = models.JSONField(null=True, blank=True,
                               help_text="List of [label, pts] defensive structural penalties")
    offensive_strengths   = models.JSONField(null=True, blank=True,
                               help_text="Top offensive subcomponent names")
    offensive_weaknesses  = models.JSONField(null=True, blank=True)
    defensive_strengths   = models.JSONField(null=True, blank=True)
    defensive_weaknesses  = models.JSONField(null=True, blank=True)

    # Compact summary for UI consumption
    fit_summary = models.JSONField(null=True, blank=True)

    # ── Phase 4: Pace & Scheme Contextual Fit ─────────────────────────────────
    # Alignment scores (0-100; 50 = neutral, no mismatch or bonus).
    # Modifiers are signed; positive = good alignment bonus, negative = mismatch.
    # has_team_style_data=False means no TeamSeasonRatings data was available
    # for this team; all Phase 4 fields will be neutral (50 / 0.0).

    # Pace
    pace_alignment_score = models.FloatField(
        null=True, blank=True,
        help_text="0-100: how well roster pace tendency matches team tempo identity",
    )
    pace_modifier = models.FloatField(
        null=True, blank=True,
        help_text="Pace modifier (-2 to +2); applied 100% to off, 50% to def",
    )

    # Offensive scheme
    off_scheme_alignment_score = models.FloatField(
        null=True, blank=True,
        help_text="0-100: how well roster archetypes match team offensive scheme",
    )
    off_scheme_modifier = models.FloatField(
        null=True, blank=True,
        help_text="Offensive scheme modifier (-3 to +3)",
    )

    # Defensive scheme
    def_scheme_alignment_score = models.FloatField(
        null=True, blank=True,
        help_text="0-100: how well roster archetypes match team defensive scheme",
    )
    def_scheme_modifier = models.FloatField(
        null=True, blank=True,
        help_text="Defensive scheme modifier (-3 to +3)",
    )

    # Combined contextual totals (clamped to ±5)
    off_contextual_modifier = models.FloatField(
        null=True, blank=True,
        help_text="pace(100%) + off_scheme modifier, clamped ±5",
    )
    def_contextual_modifier = models.FloatField(
        null=True, blank=True,
        help_text="pace(50%) + def_scheme modifier, clamped ±5",
    )

    # Adjusted fit scores (Phase 3 + contextual, clipped 0-100)
    adjusted_off_fit = models.FloatField(
        null=True, blank=True,
        help_text="Phase 3 offensive_fit_score + off_contextual_modifier",
    )
    adjusted_def_fit = models.FloatField(
        null=True, blank=True,
        help_text="Phase 3 defensive_fit_score + def_contextual_modifier",
    )
    adjusted_overall_fit = models.FloatField(
        null=True, blank=True,
        help_text="Recomputed overall from adjusted off/def fits",
    )

    # Transparency flag
    has_team_style_data = models.BooleanField(
        default=False,
        help_text="True if TeamSeasonRatings data existed for this team; "
                  "False means all Phase 4 fields are neutral placeholders",
    )

    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["team", "from_season"],
                name="unique_team_season_fit",
            )
        ]
        indexes = [
            models.Index(fields=["from_season", "projected_season_year"]),
            models.Index(fields=["team", "from_season"]),
        ]

    def __str__(self):
        return (
            f"{self.team} fit {self.from_season.year}→{self.projected_season_year}: "
            f"off={self.offensive_fit_score:.1f} def={self.defensive_fit_score:.1f}"
            if self.offensive_fit_score is not None else
            f"{self.team} fit (unscored)"
        )


class TeamSeasonProjection(models.Model):
    """
    Phase 5: Team-level season projection.

    Synthesises Phase 1/2 player projections (BPR × minutes weights) and
    Phase 3/4 roster-fit scores into projected season ratings (AdjO, AdjD, AdjEM)
    with national / offense / defense rank estimates and uncertainty bands.

    Unique per (team, from_season). Re-running the pipeline is idempotent.

    Translation formula (backbone):
        base_team_offense = Σ(minutes_share_p2 × projected_obpr)
        base_team_defense = Σ(minutes_share_p2 × projected_dbpr)
        projected_adj_o   = D1_avg + SLOPE × (base_off − league_mean_base_off)
                           + continuity_adj + fit_adj
        projected_adj_d   = D1_avg − SLOPE × (base_def − league_mean_base_def)
                           − continuity_adj − fit_adj
    """

    team = models.ForeignKey("core.Team", on_delete=models.CASCADE, related_name="season_projections")
    from_season = models.ForeignKey(
        "core.Season",
        on_delete=models.CASCADE,
        related_name="team_projections",
        help_text="Season whose data (Phase 1-4) was used to build this projection",
    )
    projected_season_year = models.IntegerField(
        help_text="Calendar year of the season being projected (from_season.year + 1)",
    )

    # ── Base aggregates ───────────────────────────────────────────────────────
    base_team_offense = models.FloatField(
        null=True, blank=True,
        help_text="Σ(minutes_share_p2 × projected_obpr); weighted offensive BPR",
    )
    base_team_defense = models.FloatField(
        null=True, blank=True,
        help_text="Σ(minutes_share_p2 × projected_dbpr); weighted defensive BPR",
    )
    base_team_roster_strength = models.FloatField(
        null=True, blank=True,
        help_text="Σ(minutes_share_p2 × projected_bpr); weighted total BPR",
    )

    # ── Continuity ────────────────────────────────────────────────────────────
    returner_minutes_fraction = models.FloatField(
        null=True, blank=True,
        help_text="Fraction (0-1) of projected minutes allocated to returners",
    )
    continuity_score = models.FloatField(
        null=True, blank=True,
        help_text="returner_minutes_fraction × 100; 0-100 continuity index",
    )
    continuity_adjustment_off = models.FloatField(
        null=True, blank=True,
        help_text="Continuity bonus applied to projected_adj_o (pts/100 poss)",
    )
    continuity_adjustment_def = models.FloatField(
        null=True, blank=True,
        help_text="Continuity bonus applied to projected_adj_d (subtracted; positive = improvement)",
    )

    # ── Phase 6: BPR-weighted stability diagnostics ───────────────────────────
    # Diagnostic fields that expose WHY a team's stability score is what it is.
    # They do NOT directly shift the projected mean — the continuity_adjustment
    # above (driven by continuity_value_score) is the only channel to ratings.
    returner_bpr_fraction = models.FloatField(
        null=True, blank=True,
        help_text=(
            "Phase 6: fraction (0-1) of BPR-weighted output from returners. "
            "Higher than returner_minutes_fraction means returners are above-average contributors."
        ),
    )
    transfer_minutes_fraction = models.FloatField(
        null=True, blank=True,
        help_text="Phase 6: fraction (0-1) of projected minutes allocated to transfers",
    )
    transfer_bpr_fraction = models.FloatField(
        null=True, blank=True,
        help_text="Phase 6: fraction (0-1) of BPR-weighted output from transfers",
    )
    transfer_dependence_score = models.FloatField(
        null=True, blank=True,
        help_text=(
            "Phase 6: transfer_bpr_fraction × 100; 0-100. "
            "High score = team performance heavily reliant on transfers."
        ),
    )
    continuity_value_score = models.FloatField(
        null=True, blank=True,
        help_text=(
            "Phase 6: BPR-weighted continuity index, 0-100. "
            "Blend of returner_minutes_fraction (60%) and returner_bpr_fraction (40%). "
            "Drives continuity_adjustment_off/def — stable teams that keep their key "
            "contributors execute systems more reliably."
        ),
    )
    transfer_fit_risk_score = models.FloatField(
        null=True, blank=True,
        help_text=(
            "Phase 6b: transfer fit-risk ∈ [0, 1]. "
            "Interaction of transfer_dependence_score × fit_shortfall (below-neutral fit). "
            "Feeds into team_projection_uncertainty; does not affect mean ratings."
        ),
    )

    # ── Fit adjustments ───────────────────────────────────────────────────────
    fit_adjustment_off = models.FloatField(
        null=True, blank=True,
        help_text="Phase 3+4 fit bonus applied to projected_adj_o (pts/100 poss)",
    )
    fit_adjustment_def = models.FloatField(
        null=True, blank=True,
        help_text="Phase 3+4 fit bonus applied to projected_adj_d (pts/100 poss; positive = improvement)",
    )

    # ── Coaching continuity (placeholder) ────────────────────────────────────
    coaching_continuity_adjustment = models.FloatField(
        default=0.0,
        help_text="Coaching-continuity adjustment (always 0.0 — no coach data available)",
    )

    # ── Projected ratings ─────────────────────────────────────────────────────
    projected_adj_o = models.FloatField(
        null=True, blank=True,
        help_text="Projected adjusted tempo-free offensive efficiency (pts/100 poss)",
    )
    projected_adj_d = models.FloatField(
        null=True, blank=True,
        help_text="Projected adjusted tempo-free defensive efficiency (pts/100 poss; lower = better)",
    )
    projected_adj_em = models.FloatField(
        null=True, blank=True,
        help_text="projected_adj_o − projected_adj_d",
    )

    # ── Uncertainty + confidence bands ────────────────────────────────────────
    team_projection_uncertainty = models.FloatField(
        null=True, blank=True,
        help_text="0-1 uncertainty score; 0 = high confidence, 1 = low confidence",
    )
    projected_adj_o_low = models.FloatField(
        null=True, blank=True,
        help_text="Lower bound of projected_adj_o confidence band (−1σ)",
    )
    projected_adj_o_high = models.FloatField(
        null=True, blank=True,
        help_text="Upper bound of projected_adj_o confidence band (+1σ)",
    )
    projected_adj_d_low = models.FloatField(
        null=True, blank=True,
        help_text="Lower bound of projected_adj_d confidence band (numerically lower = better defense)",
    )
    projected_adj_d_high = models.FloatField(
        null=True, blank=True,
        help_text="Upper bound of projected_adj_d confidence band",
    )
    projected_adj_em_low = models.FloatField(
        null=True, blank=True,
        help_text="Lower bound of projected_adj_em confidence band (−2σ)",
    )
    projected_adj_em_high = models.FloatField(
        null=True, blank=True,
        help_text="Upper bound of projected_adj_em confidence band (+2σ)",
    )

    # ── Rank projections ──────────────────────────────────────────────────────
    projected_national_rank = models.IntegerField(
        null=True, blank=True,
        help_text="Projected national rank by adj_em (1 = best)",
    )
    projected_offense_rank = models.IntegerField(
        null=True, blank=True,
        help_text="Projected rank by adj_o (1 = highest offensive efficiency)",
    )
    projected_defense_rank = models.IntegerField(
        null=True, blank=True,
        help_text="Projected rank by adj_d (1 = lowest / best defensive efficiency)",
    )
    national_rank_range_low = models.IntegerField(
        null=True, blank=True,
        help_text="Most optimistic (lowest number = best) national rank from uncertainty band",
    )
    national_rank_range_high = models.IntegerField(
        null=True, blank=True,
        help_text="Most pessimistic (highest number = worst) national rank from uncertainty band",
    )
    offense_rank_range_low = models.IntegerField(
        null=True, blank=True,
        help_text="Most optimistic offense rank",
    )
    offense_rank_range_high = models.IntegerField(
        null=True, blank=True,
        help_text="Most pessimistic offense rank",
    )
    defense_rank_range_low = models.IntegerField(
        null=True, blank=True,
        help_text="Most optimistic defense rank",
    )
    defense_rank_range_high = models.IntegerField(
        null=True, blank=True,
        help_text="Most pessimistic defense rank",
    )

    # ── Diagnostics ───────────────────────────────────────────────────────────
    projection_summary = models.JSONField(
        default=dict,
        help_text="Compact projection summary dict for UI/API",
    )
    driver_breakdown = models.JSONField(
        default=list,
        help_text="Ordered list of adjustment driver dicts with magnitudes",
    )

    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["team", "from_season"],
                name="unique_team_season_projection",
            )
        ]
        indexes = [
            models.Index(fields=["from_season", "projected_season_year"]),
            models.Index(fields=["projected_adj_em"]),
            models.Index(fields=["team", "from_season"]),
        ]

    def __str__(self):
        em = f"{self.projected_adj_em:+.1f}" if self.projected_adj_em is not None else "?"
        rank = f"#{self.projected_national_rank}" if self.projected_national_rank else "?"
        return (
            f"{self.team} projection {self.from_season.year}→{self.projected_season_year}: "
            f"AdjEM={em} ({rank})"
        )
