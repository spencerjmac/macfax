"""
Core Django Models for CBB Analytics
Normalized schema for college basketball team statistics
"""

from django.db import models
from django.utils.text import slugify


class Season(models.Model):
    """Represents a basketball season (e.g., 2025-26)"""

    year = models.IntegerField(
        unique=True, help_text="Ending year (2026 for 2025-26 season)"
    )
    display_name = models.CharField(max_length=20, help_text="Human-readable name")
    is_current = models.BooleanField(
        default=False, help_text="Is this the active season?"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-year"]

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
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


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


class DataIngestionRun(models.Model):
    """Track data ingestion runs for auditing and debugging"""

    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=[
            ("running", "Running"),
            ("success", "Success"),
            ("error", "Error"),
        ],
        default="running",
    )

    teams_ingested = models.IntegerField(default=0)
    error_log = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return (
            f"Ingestion {self.season.display_name} - {self.status} ({self.started_at})"
        )


class GameLog(models.Model):
    """
    Game-level boxscore data for computing AOR/ADR/AEM metrics

    Required fields for AOR/ADR computation:
    - Pts, PtsAllowed, FGA, OR (offensive rebounds), TO (turnovers), FTA
    - location (home/away/neutral) for venue tax
    - opponent for opponent adjustment lookup
    - date for temporal matching
    """

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="game_logs")
    season = models.ForeignKey(
        Season, on_delete=models.CASCADE, related_name="game_logs"
    )

    # Game identifiers
    date = models.DateField(db_index=True)
    opponent = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="opponent_games",
        null=True,
        blank=True,
    )
    opponent_name = models.CharField(
        max_length=100, help_text="Opponent name (for matching)"
    )
    location = models.CharField(
        max_length=1,
        choices=[("H", "Home"), ("A", "Away"), ("N", "Neutral")],
        help_text="H=Home, A=Away, N=Neutral",
    )

    # Boxscore stats (required for AOR/ADR computation)
    pts = models.IntegerField(help_text="Points scored")
    pts_allowed = models.IntegerField(help_text="Points allowed")
    fga = models.IntegerField(help_text="Field goal attempts")
    fgm = models.IntegerField(null=True, blank=True, help_text="Field goals made")
    or_total = models.IntegerField(
        help_text="Offensive rebounds", db_column="offensive_rebounds"
    )
    to = models.IntegerField(help_text="Turnovers")
    fta = models.IntegerField(help_text="Free throw attempts")
    ftm = models.IntegerField(null=True, blank=True, help_text="Free throws made")

    # Opponent boxscore (for their efficiency)
    opp_fga = models.IntegerField(
        null=True, blank=True, help_text="Opponent field goal attempts"
    )
    opp_or = models.IntegerField(
        null=True, blank=True, help_text="Opponent offensive rebounds"
    )
    opp_to = models.IntegerField(null=True, blank=True, help_text="Opponent turnovers")
    opp_fta = models.IntegerField(
        null=True, blank=True, help_text="Opponent free throw attempts"
    )

    # Computed fields (auto-calculated)
    possessions = models.FloatField(
        null=True, blank=True, help_text="Estimated possessions via formula"
    )
    raw_oe = models.FloatField(
        null=True, blank=True, help_text="Raw offensive efficiency (pts/100 poss)"
    )
    raw_de = models.FloatField(
        null=True,
        blank=True,
        help_text="Raw defensive efficiency (pts allowed/100 poss)",
    )

    # Opponent adjusted ratings (joined from KenPom/Torvik at computation time)
    opp_adj_o = models.FloatField(
        null=True,
        blank=True,
        help_text="Opponent's adjusted offensive rating (for defense calc)",
    )
    opp_adj_d = models.FloatField(
        null=True,
        blank=True,
        help_text="Opponent's adjusted defensive rating (for offense calc)",
    )

    # Game-level adjusted ratings (with venue tax)
    aor_game = models.FloatField(
        null=True, blank=True, help_text="This game's AOR (with venue tax)"
    )
    adr_game = models.FloatField(
        null=True, blank=True, help_text="This game's ADR (with venue tax)"
    )

    # Weighting
    recency_mult = models.FloatField(
        default=1.0, help_text="Recency multiplier (future use)"
    )
    weight = models.FloatField(
        null=True, blank=True, help_text="Game weight = possessions * recency_mult"
    )

    # Result
    won = models.BooleanField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [["team", "date", "opponent_name"]]
        indexes = [
            models.Index(fields=["team", "season", "date"]),
            models.Index(fields=["date"]),
        ]
        ordering = ["date"]

    def __str__(self):
        result = "W" if self.won else "L" if self.won is not None else "?"
        return f"{self.team.name} vs {self.opponent_name} ({self.date}) - {result}"

    def save(self, *args, **kwargs):
        # Auto-calculate possessions and efficiencies
        if all(
            [
                self.fga is not None,
                self.or_total is not None,
                self.to is not None,
                self.fta is not None,
            ]
        ):
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


# ==================== GAME LOG PIPELINE MODELS ====================


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


class Game(models.Model):
    """
    Represents a single Division I men's basketball game
    Central table for game metadata
    """

    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("in_progress", "In Progress"),
        ("final", "Final"),
        ("canceled", "Canceled"),
        ("postponed", "Postponed"),
    ]

    season_year = models.IntegerField(
        db_index=True, help_text="Ending year (2026 for 2025-26 season)"
    )
    game_date = models.DateField(db_index=True, help_text="Game date (local)")
    start_time_utc = models.DateTimeField(null=True, blank=True)

    home_team = models.ForeignKey(
        Team, on_delete=models.PROTECT, related_name="home_games"
    )
    away_team = models.ForeignKey(
        Team, on_delete=models.PROTECT, related_name="away_games"
    )

    neutral_site = models.BooleanField(default=False)
    venue_name = models.CharField(max_length=200, null=True, blank=True)
    venue_city = models.CharField(max_length=100, null=True, blank=True)
    venue_state = models.CharField(max_length=2, null=True, blank=True)

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="scheduled"
    )

    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)

    # Data source
    source = models.CharField(
        max_length=20, default="ncaa", help_text="Data source (ncaa, espn)"
    )
    source_game_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Unique game ID from source",
    )

    # Game format
    period_count = models.IntegerField(
        null=True,
        blank=True,
        help_text="Number of periods played (2 = regulation, 3+ = OT)",
    )
    went_to_ot = models.BooleanField(default=False)

    # Raw API response for audit
    raw_json = models.JSONField(null=True, blank=True, help_text="Raw API response")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["season_year", "game_date"]),
            models.Index(fields=["home_team", "game_date"]),
            models.Index(fields=["away_team", "game_date"]),
            models.Index(fields=["status"]),
        ]
        ordering = ["-game_date", "-start_time_utc"]

    def __str__(self):
        score = ""
        if self.status == "final" and self.home_score is not None:
            score = f" {self.away_score}-{self.home_score}"
        loc = " (N)" if self.neutral_site else ""
        return f"{self.away_team.name} @ {self.home_team.name}{loc} ({self.game_date}){score}"

    @property
    def winner(self):
        """Returns the winning team or None if not final"""
        if self.status != "final" or self.home_score is None or self.away_score is None:
            return None
        return self.home_team if self.home_score > self.away_score else self.away_team


class TeamGameStats(models.Model):
    """
    Box score statistics for one team in one game
    Each game should have exactly 2 rows (one per team)
    """

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="team_stats")
    team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="game_stats")
    opponent = models.ForeignKey(
        Team, on_delete=models.PROTECT, related_name="opponent_stats"
    )

    home_away = models.CharField(
        max_length=1,
        choices=[("H", "Home"), ("A", "Away"), ("N", "Neutral")],
        help_text="H=Home, A=Away, N=Neutral",
    )

    # Core box score stats
    minutes = models.IntegerField(
        null=True, blank=True, help_text="Total minutes played"
    )
    pts = models.IntegerField(default=0, help_text="Points")

    # Shooting
    fgm = models.IntegerField(default=0, help_text="Field goals made")
    fga = models.IntegerField(default=0, help_text="Field goal attempts")
    fg3m = models.IntegerField(default=0, help_text="3-pointers made")
    fg3a = models.IntegerField(default=0, help_text="3-point attempts")
    ftm = models.IntegerField(default=0, help_text="Free throws made")
    fta = models.IntegerField(default=0, help_text="Free throw attempts")

    # Rebounding
    oreb = models.IntegerField(default=0, help_text="Offensive rebounds")
    dreb = models.IntegerField(default=0, help_text="Defensive rebounds")
    reb = models.IntegerField(default=0, help_text="Total rebounds")

    # Other stats
    ast = models.IntegerField(default=0, help_text="Assists")
    stl = models.IntegerField(default=0, help_text="Steals")
    blk = models.IntegerField(default=0, help_text="Blocks")
    tov = models.IntegerField(default=0, help_text="Turnovers")
    pf = models.IntegerField(default=0, help_text="Personal fouls")

    # Resume metrics
    game_value = models.FloatField(
        null=True,
        blank=True,
        help_text="Game Value: Result (1=W, 0=L) - P(bubble team wins). Higher = better resume win",
    )

    # Raw API data for debugging
    raw_json = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [["game", "team"]]
        indexes = [
            models.Index(fields=["team", "game"]),
            models.Index(fields=["game"]),
        ]
        verbose_name = "Team Game Stats"
        verbose_name_plural = "Team Game Stats"

    def __str__(self):
        return f"{self.team.name} vs {self.opponent.name} ({self.game.game_date}): {self.pts} pts"

    # ==================== HELPER METHODS ====================

    def _get_opp_stats(self):
        """Get opponent's stats from same game (cached)"""
        if not hasattr(self, "_cached_opp_stats"):
            self._cached_opp_stats = self.game.team_stats.exclude(
                team=self.team
            ).first()
        return self._cached_opp_stats

    @property
    def site_factor(self):
        """Offensive site adjustment factor based on home/away/neutral"""
        if self.home_away == "H":
            return 0.9862
        elif self.home_away == "A":
            return 1.0140
        else:  # 'N' neutral
            return 1.0000

    @property
    def defensive_site_factor(self):
        """Defensive site adjustment factor (inverse of offensive)

        Home court makes defense look better (fewer points allowed),
        so we inflate to neutralize. Road makes defense look worse,
        so we deflate.
        """
        if self.home_away == "H":
            return 1.0140  # Inverse of offensive home factor
        elif self.home_away == "A":
            return 0.9862  # Inverse of offensive away factor
        else:  # 'N' neutral
            return 1.0000

    @property
    def game_minutes(self):
        """Total game minutes (40 for regulation, 45 for OT approximation)"""
        if self.minutes:
            return self.minutes
        return 45 if self.game.went_to_ot else 40

    # ==================== 2-POINT STATS ====================

    @property
    def fg2m(self):
        """2-point field goals made"""
        return self.fgm - self.fg3m

    @property
    def fg2a(self):
        """2-point field goal attempts"""
        return self.fga - self.fg3a

    # ==================== POSSESSIONS ====================

    @property
    def poss_team(self):
        """Team possessions: fga - oreb + tov + 0.475*fta"""
        return self.fga - self.oreb + self.tov + 0.475 * self.fta

    @property
    def poss_opp(self):
        """Opponent possessions"""
        opp = self._get_opp_stats()
        if not opp:
            return None
        return opp.fga - opp.oreb + opp.tov + 0.475 * opp.fta

    @property
    def poss_game(self):
        """Game possessions: average of team + opponent"""
        poss_o = self.poss_opp
        if poss_o is None:
            return None
        return 0.5 * (self.poss_team + poss_o)

    # Alias for backward compatibility
    @property
    def possessions_est(self):
        """Alias for poss_game"""
        return self.poss_game or self.poss_team

    # ==================== SHOOTING PERCENTAGES ====================

    @property
    def fg_pct(self):
        """Field Goal Percentage"""
        return round(self.fgm / self.fga * 100, 1) if self.fga > 0 else None

    @property
    def fg2_pct(self):
        """2-Point Percentage"""
        fg2a = self.fga - self.fg3a
        fg2m = self.fgm - self.fg3m if self.fgm else 0
        return round(fg2m / fg2a * 100, 1) if fg2a > 0 else None

    @property
    def fg3_pct(self):
        """3-Point Percentage"""
        return round(self.fg3m / self.fg3a * 100, 1) if self.fg3a > 0 else None

    @property
    def ft_pct(self):
        """Free Throw Percentage"""
        return round(self.ftm / self.fta * 100, 1) if self.fta > 0 else None

    @property
    def fg3_rate(self):
        """3-Point Attempt Rate: 3PA / FGA"""
        return round(self.fg3a / self.fga * 100, 1) if self.fga > 0 else None

    @property
    def ts_pct(self):
        """True Shooting Percentage"""
        tsa = 2 * (self.fga + 0.44 * self.fta)
        return round(self.pts / tsa * 100, 1) if tsa > 0 else None

    # ==================== FOUR FACTORS (OFFENSE) ====================

    @property
    def efg_pct(self):
        """Effective Field Goal Percentage"""
        if self.fga == 0:
            return None
        return round((self.fgm + 0.5 * self.fg3m) / self.fga * 100, 1)

    @property
    def orb_pct(self):
        """Offensive Rebound Percentage: oreb / (oreb + opp.dreb)"""
        opp = self._get_opp_stats()
        if not opp:
            return None
        denom = self.oreb + opp.dreb
        return round(self.oreb / denom * 100, 1) if denom > 0 else None

    @property
    def tov_pct(self):
        """Turnover Percentage: tov / poss_team"""
        poss = self.poss_team
        return round(self.tov / poss * 100, 1) if poss > 0 else None

    @property
    def ftr(self):
        """Free Throw Rate: fta / fga"""
        return round(self.fta / self.fga * 100, 1) if self.fga > 0 else None

    # ==================== FOUR FACTORS (DEFENSE) ====================

    @property
    def opp_efg_pct(self):
        """Opponent Effective FG%"""
        opp = self._get_opp_stats()
        if not opp or opp.fga == 0:
            return None
        return round((opp.fgm + 0.5 * opp.fg3m) / opp.fga * 100, 1)

    @property
    def opp_orb_pct(self):
        """Opponent ORB%: opp.oreb / (opp.oreb + dreb)"""
        opp = self._get_opp_stats()
        if not opp:
            return None
        denom = opp.oreb + self.dreb
        return round(opp.oreb / denom * 100, 1) if denom > 0 else None

    @property
    def opp_tov_pct(self):
        """Opponent TO%: opp.tov / poss_opp"""
        opp = self._get_opp_stats()
        poss_o = self.poss_opp
        if not opp or not poss_o or poss_o == 0:
            return None
        return round(opp.tov / poss_o * 100, 1)

    @property
    def opp_ftr(self):
        """Opponent FTR: opp.fta / opp.fga"""
        opp = self._get_opp_stats()
        if not opp or opp.fga == 0:
            return None
        return round(opp.fta / opp.fga * 100, 1)

    # ==================== MARGINS / EDGES ====================

    @property
    def efg_margin(self):
        """eFG Margin: eFG - Opp_eFG (positive = good)"""
        efg = self.efg_pct
        opp_efg = self.opp_efg_pct
        if efg is None or opp_efg is None:
            return None
        return round(efg - opp_efg, 1)

    @property
    def tov_edge(self):
        """Turnover Edge: Opp_TO% - TO% (positive = good)"""
        to = self.tov_pct
        opp_to = self.opp_tov_pct
        if to is None or opp_to is None:
            return None
        return round(opp_to - to, 1)

    @property
    def reb_edge(self):
        """Rebounding Edge: ORB% - Opp_ORB% (positive = good)"""
        orb = self.orb_pct
        opp_orb = self.opp_orb_pct
        if orb is None or opp_orb is None:
            return None
        return round(orb - opp_orb, 1)

    @property
    def ftr_margin(self):
        """FTR Margin: FTR - Opp_FTR (positive = good)"""
        ftr = self.ftr
        opp_ftr = self.opp_ftr
        if ftr is None or opp_ftr is None:
            return None
        return round(ftr - opp_ftr, 1)

    # ==================== RATINGS ====================

    @property
    def ortg(self):
        """Offensive Rating: 100 * pts / poss_game"""
        poss = self.poss_game
        if not poss or poss == 0:
            return None
        return round(100 * self.pts / poss, 1)

    @property
    def drtg(self):
        """Defensive Rating: 100 * opp.pts / poss_game"""
        opp = self._get_opp_stats()
        poss = self.poss_game
        if not opp or not poss or poss == 0:
            return None
        return round(100 * opp.pts / poss, 1)

    @property
    def net_rating(self):
        """Net Rating: ORtg - DRtg"""
        ortg = self.ortg
        drtg = self.drtg
        if ortg is None or drtg is None:
            return None
        return round(ortg - drtg, 1)

    # ==================== ASSIST METRICS ====================

    @property
    def ast_pct(self):
        """Assist %: ast / fgm"""
        return round(self.ast / self.fgm * 100, 1) if self.fgm > 0 else None

    @property
    def ast_to_ratio(self):
        """Assist/Turnover Ratio"""
        return round(self.ast / self.tov, 2) if self.tov > 0 else None

    @property
    def ast_ratio(self):
        """Assist Ratio: 100 * ast / poss_team"""
        poss = self.poss_team
        return round(100 * self.ast / poss, 1) if poss > 0 else None

    # ==================== PACE ====================

    @property
    def pace(self):
        """Pace: 40 * poss_game / minutes"""
        poss = self.poss_game
        minutes = self.game_minutes
        if not poss or not minutes or minutes == 0:
            return None
        return round(40 * poss / minutes, 1)

    # ==================== DEFENSE METRICS ====================

    @property
    def stl_pct(self):
        """Steal %: 100 * stl / poss_opp"""
        poss_o = self.poss_opp
        if not poss_o or poss_o == 0:
            return None
        return round(100 * self.stl / poss_o, 1)

    @property
    def blk_pct(self):
        """Block %: 100 * blk / opp.fg2a"""
        opp = self._get_opp_stats()
        if not opp:
            return None
        opp_fg2a = opp.fga - opp.fg3a
        return round(100 * self.blk / opp_fg2a, 1) if opp_fg2a > 0 else None

    @property
    def stl_to_ratio(self):
        """Steal/Turnover Ratio"""
        return round(self.stl / self.tov, 2) if self.tov > 0 else None

    @property
    def stocks_per_100(self):
        """Stocks (STL+BLK) per 100 defensive possessions"""
        poss_o = self.poss_opp
        if not poss_o or poss_o == 0:
            return None
        return round(100 * (self.stl + self.blk) / poss_o, 1)

    # ==================== FOUL METRICS ====================

    @property
    def pf_per_100(self):
        """Personal Fouls per 100 possessions"""
        poss = self.poss_game
        if not poss or poss == 0:
            return None
        return round(100 * self.pf / poss, 1)

    @property
    def stl_per_pf(self):
        """Steals per Personal Foul"""
        return round(self.stl / self.pf, 2) if self.pf > 0 else None

    @property
    def blk_per_pf(self):
        """Blocks per Personal Foul"""
        return round(self.blk / self.pf, 2) if self.pf > 0 else None


class ScoringEvent(models.Model):
    """
    Individual scoring events in sequential order
    Used to compute Kill Shots and other in-game momentum metrics
    """

    game = models.ForeignKey(
        Game, on_delete=models.CASCADE, related_name="scoring_events"
    )
    seq = models.IntegerField(help_text="Sequence number (order of scoring)")

    period = models.IntegerField(
        help_text="Period number (1=1st half, 2=2nd half, 3+=OT)"
    )
    clock = models.CharField(
        max_length=10, help_text="Game clock (e.g., '15:32', '0:45')"
    )

    scoring_team = models.ForeignKey(
        Team, on_delete=models.PROTECT, related_name="scoring_events"
    )
    points = models.IntegerField(help_text="Points scored on this event (1, 2, or 3)")

    # Running score after this event
    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)

    # Raw event data
    raw_json = models.JSONField(null=True, blank=True)

    class Meta:
        unique_together = [["game", "seq"]]
        indexes = [
            models.Index(fields=["game", "seq"]),
        ]
        ordering = ["game", "seq"]
        verbose_name = "Scoring Event"
        verbose_name_plural = "Scoring Events"

    def __str__(self):
        return (
            f"Game {self.game.id} #{self.seq}: {self.scoring_team.name} +{self.points}"
        )


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


class NationalAverages(models.Model):
    """
    National averages for a season (possession-weighted)
    Used for adjusted ratings and adjusted four factors
    """

    season = models.OneToOneField(
        Season, on_delete=models.CASCADE, related_name="national_averages"
    )

    # Basic efficiency
    avg_ortg = models.FloatField(help_text="National average offensive rating")
    avg_pace = models.FloatField(help_text="National average pace")

    # Four Factors averages
    avg_efg = models.FloatField(help_text="National average eFG%")
    avg_tov = models.FloatField(help_text="National average TOV%")
    avg_orb = models.FloatField(help_text="National average ORB%")
    avg_ftr = models.FloatField(help_text="National average FTR")

    # Total possessions (for weighting)
    total_possessions = models.FloatField(
        help_text="Total possessions across all games"
    )
    total_games = models.IntegerField(help_text="Total games in dataset")

    # Matchup prediction parameters
    hca_points = models.FloatField(
        null=True,
        blank=True,
        help_text="Home court advantage in points (estimated from game logs)",
    )
    prediction_sigma = models.FloatField(
        null=True,
        blank=True,
        help_text="Standard deviation of prediction errors (for win probability)",
    )

    # Four factor regression coefficients
    coef_efg = models.FloatField(
        null=True,
        blank=True,
        help_text="Regression coefficient for eFG% edge (points per % edge)",
    )
    coef_tov = models.FloatField(
        null=True,
        blank=True,
        help_text="Regression coefficient for TOV% edge (points per % edge)",
    )
    coef_orb = models.FloatField(
        null=True,
        blank=True,
        help_text="Regression coefficient for ORB% edge (points per % edge)",
    )
    coef_ftr = models.FloatField(
        null=True,
        blank=True,
        help_text="Regression coefficient for FTR edge (points per % edge)",
    )
    coef_intercept = models.FloatField(
        null=True, blank=True, help_text="Regression intercept (baseline margin)"
    )
    coef_r_squared = models.FloatField(
        null=True, blank=True, help_text="R-squared of four factor regression model"
    )

    # Metadata
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "National Averages"
        verbose_name_plural = "National Averages"

    def __str__(self):
        return f"{self.season.display_name} National Averages: ORtg={self.avg_ortg:.1f}"


class DataProcessingJob(models.Model):
    """Track background data processing jobs (update_all, ingest_gamelogs, etc.)"""

    JOB_TYPE_CHOICES = [
        ("update_all", "Full Data Update"),
        ("ingest_gamelogs", "Ingest Game Logs"),
        ("compute_team_metrics", "Compute Team Metrics"),
        ("compute_adjusted_ratings", "Compute Adjusted Ratings"),
        ("compute_four_factor_index", "Compute Four Factor Index"),
        ("fetch_net_rankings", "Fetch NCAA NET Rankings"),
        ("compute_sor", "Compute Strength of Record"),
        ("compute_game_value", "Compute Game Value"),
        ("compute_sos", "Compute Strength of Schedule"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("success", "Success"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    # Job identification
    job_id = models.CharField(
        max_length=50, unique=True, help_text="Unique job identifier"
    )
    job_type = models.CharField(
        max_length=30, choices=JOB_TYPE_CHOICES, help_text="Type of data processing job"
    )

    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        help_text="Current job status",
    )
    progress_percent = models.IntegerField(
        default=0, help_text="Completion percentage (0-100)"
    )

    # Job parameters
    season = models.ForeignKey(
        Season,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Season for this job (if applicable)",
    )
    parameters = models.JSONField(
        default=dict, blank=True, help_text="Additional job parameters as JSON"
    )

    # Execution info
    started_at = models.DateTimeField(auto_now_add=True, help_text="When job started")
    completed_at = models.DateTimeField(
        null=True, blank=True, help_text="When job completed"
    )
    duration_seconds = models.IntegerField(
        null=True, blank=True, help_text="Total execution time in seconds"
    )

    # Logs and output
    logs = models.TextField(
        blank=True, default="", help_text="Job execution logs (stdout + stderr)"
    )
    error_message = models.TextField(
        blank=True, default="", help_text="Error message if job failed"
    )

    # Metadata
    created_by = models.CharField(
        max_length=100, default="system", help_text="User or system that triggered job"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Data Processing Job"
        verbose_name_plural = "Data Processing Jobs"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["job_id"]),
            models.Index(fields=["status"]),
            models.Index(fields=["season", "-started_at"]),
        ]

    def __str__(self):
        return f"{self.get_job_type_display()} - {self.job_id} ({self.get_status_display()})"

    @property
    def is_running(self):
        """Check if job is currently running"""
        return self.status == "running"

    @property
    def is_complete(self):
        """Check if job is complete (success or failed)"""
        return self.status in ("success", "failed")

    def append_log(self, text):
        """Append text to job logs"""
        if self.logs:
            self.logs += "\n" + text
        else:
            self.logs = text
        self.save(update_fields=["logs"])

    def set_progress(self, percent):
        """Update progress percentage"""
        self.progress_percent = min(100, max(0, percent))
        self.save(update_fields=["progress_percent"])
