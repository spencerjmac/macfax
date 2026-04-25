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


class PipelineConfig(models.Model):
    """
    Singleton model storing all tunable analytics parameters for the compute pipeline.

    Only one row (pk=1) should ever exist. Use PipelineConfig.get_config() to
    retrieve it (creates with defaults on first access).

    Parameters are grouped into 6 logical sections matching the compute commands
    that consume them.
    """

    # ── Adjusted Ratings ──────────────────────────────────────────────────────
    adj_ratings_iterations = models.IntegerField(
        default=75,
        help_text="Max solver iterations before declaring convergence (compute_adjusted_ratings --iterations)",
    )
    adj_ratings_convergence = models.FloatField(
        default=0.001,
        help_text="Max AdjEM change between iterations to declare convergence",
    )
    adj_ratings_shrinkage_floor = models.IntegerField(
        default=170,
        help_text="Minimum shrinkage constant (possessions) regardless of games played",
    )
    adj_ratings_shrinkage_ceiling = models.IntegerField(
        default=300,
        help_text="Starting/maximum shrinkage constant (possessions)",
    )
    adj_ratings_shrinkage_decay = models.FloatField(
        default=6.25,
        help_text="Shrinkage k drops by this amount per average game played",
    )

    # ── Adjusted Four Factors ─────────────────────────────────────────────────
    adj_ff_iterations = models.IntegerField(
        default=3,
        help_text="Adjustment iterations for compute_adjusted_four_factors",
    )

    # ── Four Factor Index ─────────────────────────────────────────────────────
    ffi_weight_efg = models.FloatField(
        default=0.47,
        help_text="eFG% margin weight in the FFI composite score",
    )
    ffi_weight_tov = models.FloatField(
        default=0.24,
        help_text="Turnover edge weight in the FFI composite score",
    )
    ffi_weight_reb = models.FloatField(
        default=0.21,
        help_text="Rebounding edge weight in the FFI composite score",
    )
    ffi_weight_ftr = models.FloatField(
        default=0.08,
        help_text="FTR margin weight in the FFI composite score",
    )
    ffi_scale_midpoint = models.IntegerField(
        default=50,
        help_text="FFI output scale midpoint (score = midpoint + multiplier * z)",
    )
    ffi_scale_multiplier = models.IntegerField(
        default=20,
        help_text="FFI z-score scale multiplier",
    )

    # ── Strength of Record ────────────────────────────────────────────────────
    sor_trials = models.IntegerField(
        default=10000,
        help_text="Monte Carlo win-simulation trials (compute_sor --trials)",
    )
    sor_baseline_rank_min = models.IntegerField(
        default=20,
        help_text="Primary SOR baseline: use teams ranked this or better",
    )
    sor_baseline_rank_max = models.IntegerField(
        default=30,
        help_text="Primary SOR baseline: use teams ranked this or worse",
    )
    sor_fallback_rank_min = models.IntegerField(
        default=15,
        help_text="Fallback SOR baseline (when primary range is underpopulated): rank floor",
    )
    sor_fallback_rank_max = models.IntegerField(
        default=35,
        help_text="Fallback SOR baseline (when primary range is underpopulated): rank ceiling",
    )

    # ── WAB / Game Value ──────────────────────────────────────────────────────
    wab_bubble_rank = models.IntegerField(
        default=45,
        help_text="AdjEM rank of the 'bubble team' used as the WAB and game-value baseline",
    )

    # ── Strength of Schedule ──────────────────────────────────────────────────
    sos_baseline_adjem = models.FloatField(
        default=0.0,
        help_text="AdjEM of the 'average D1 team' anchor for the SOS logistic model",
    )
    sos_logistic_sigma = models.FloatField(
        default=10.0,
        help_text="Logistic spread/scale parameter for the SOS win-probability model",
    )
    sos_home_advantage = models.FloatField(
        default=1.5,
        help_text="Points added to the home team's margin in SOS win-probability calculations",
    )
    sos_away_penalty = models.FloatField(
        default=1.5,
        help_text="Points subtracted from the away team's margin in SOS win-probability calculations",
    )

    # ── Shared Fallbacks ──────────────────────────────────────────────────────
    fallback_hca = models.FloatField(
        default=1.85,
        help_text="HCA (points) used when NationalAverages.hca_points has not been computed yet",
    )
    fallback_sigma = models.FloatField(
        default=11.08,
        help_text="Prediction sigma used when NationalAverages.prediction_sigma has not been computed yet",
    )
    fallback_avg_ortg = models.FloatField(
        default=108.0,
        help_text="National average offensive rating used when NationalAverages has not been computed yet",
    )

    class Meta:
        verbose_name = "Pipeline Configuration"
        verbose_name_plural = "Pipeline Configuration"

    def __str__(self):
        return "Pipeline Configuration"

    @classmethod
    def get_config(cls):
        """Return the singleton config row, creating it with defaults if absent."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Player(models.Model):
    """NCAA college basketball player, identified by ESPN athlete ID."""

    espn_athlete_id = models.CharField(max_length=20, unique=True, db_index=True)
    display_name = models.CharField(max_length=150)
    short_name = models.CharField(max_length=100, blank=True, default="")
    jersey = models.CharField(max_length=5, blank=True, default="")
    position = models.CharField(
        max_length=10, blank=True, default="", help_text="Position abbreviation (G, F, C)"
    )
    headshot_url = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_name"]

    def __str__(self):
        return self.display_name


class PlayerRecruitingProfile(models.Model):
    """
    Recruiting / prospect profile for an incoming college player.

    Stores the recruiting tier (star rating + composite score) from external
    scouting services (247Sports, Rivals, ESPN) for the year a player enrolled
    in college.  Used by the BPR pipeline to set a non-neutral preseason prior
    for freshmen who have no prior college BPR data.

    The `class_year` field is the season year the player's first college season
    began (e.g., class_year=2026 for a player who enrolled in Fall 2025 and
    played their first season in 2025-26).  This matches PlayerSeasonStats.season.year.

    Only used when a player lacks box BPR data (typically their first college season).
    Once box BPR predictions are available, the recruiting prior is superseded.
    """
    STARS_CHOICES = [(1, "1-star"), (2, "2-star"), (3, "3-star"), (4, "4-star"), (5, "5-star")]
    SOURCE_CHOICES = [
        ("247sports", "247Sports"),
        ("rivals",    "Rivals"),
        ("espn",      "ESPN"),
        ("on3",       "On3"),
        ("manual",    "Manual entry"),
    ]

    player = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="recruiting_profiles",
    )
    class_year = models.IntegerField(
        help_text="Season year of the player's first college season (matches Season.year).",
        db_index=True,
    )
    stars = models.IntegerField(
        choices=STARS_CHOICES, null=True, blank=True,
        help_text="Star rating (1–5). Null for unrated / walk-on prospects.",
    )
    national_rank = models.IntegerField(
        null=True, blank=True,
        help_text="Overall national recruiting rank (1-based). Lower is better.",
    )
    composite_score = models.FloatField(
        null=True, blank=True,
        help_text=(
            "247Sports-style composite score in [0, 1].  "
            "~1.000 = top recruit; ~0.980+ = 5-star; ~0.950-0.979 = 4-star; "
            "~0.880-0.949 = 3-star; <0.880 = 2-star or below."
        ),
    )
    position_rank = models.IntegerField(
        null=True, blank=True,
        help_text="Rank within the player's position group.",
    )
    source = models.CharField(
        max_length=30, choices=SOURCE_CHOICES, default="manual",
        help_text="Where the recruiting data originated.",
    )
    notes = models.CharField(
        max_length=200, blank=True, default="",
        help_text="Free-text notes (e.g. 'consensus 5-star; top-5 national').",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["player", "class_year"], name="unique_player_class_year"
            )
        ]
        indexes = [
            models.Index(fields=["class_year"]),
            models.Index(fields=["stars", "class_year"]),
        ]
        ordering = ["class_year", "national_rank"]

    def __str__(self) -> str:
        stars_str = f"{self.stars}★" if self.stars else "unrated"
        return f"{self.player.display_name} ({stars_str}, class of {self.class_year})"


class PlayerGameStats(models.Model):
    """Per-game box score for a single NCAA player from ESPN."""

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="game_stats")
    game = models.ForeignKey("Game", on_delete=models.CASCADE, related_name="player_stats")
    team = models.ForeignKey(
        Team, on_delete=models.SET_NULL, null=True, blank=True, related_name="player_game_stats"
    )
    starter = models.BooleanField(default=False)
    did_not_play = models.BooleanField(default=False)
    minutes = models.FloatField(default=0.0)
    points = models.IntegerField(default=0)
    fg_made = models.IntegerField(default=0)
    fg_attempted = models.IntegerField(default=0)
    fg3_made = models.IntegerField(default=0)
    fg3_attempted = models.IntegerField(default=0)
    ft_made = models.IntegerField(default=0)
    ft_attempted = models.IntegerField(default=0)
    rebounds = models.IntegerField(default=0)
    offensive_rebounds = models.IntegerField(default=0)
    defensive_rebounds = models.IntegerField(default=0)
    assists = models.IntegerField(default=0)
    turnovers = models.IntegerField(default=0)
    steals = models.IntegerField(default=0)
    blocks = models.IntegerField(default=0)
    fouls = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["player", "game"], name="unique_player_game")
        ]
        indexes = [
            models.Index(fields=["game"]),
            models.Index(fields=["player", "team"]),
        ]

    def __str__(self):
        return f"{self.player.display_name} @ {self.game}"


class PlayerSeasonStats(models.Model):
    """Aggregated per-season stats for an NCAA player on a specific team."""

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="season_stats")
    team = models.ForeignKey(
        Team, on_delete=models.SET_NULL, null=True, blank=True, related_name="player_season_stats"
    )
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="player_season_stats")
    gp = models.IntegerField(default=0, help_text="Games played")
    mpg = models.FloatField(default=0.0, help_text="Minutes per game")
    pts = models.FloatField(default=0.0)
    reb = models.FloatField(default=0.0)
    ast = models.FloatField(default=0.0)
    stl = models.FloatField(default=0.0)
    blk = models.FloatField(default=0.0)
    tov = models.FloatField(default=0.0)
    pf = models.FloatField(default=0.0)
    fg_pct = models.FloatField(null=True, blank=True)
    fg3_pct = models.FloatField(null=True, blank=True)
    ft_pct = models.FloatField(null=True, blank=True)
    fga_pg = models.FloatField(default=0.0, help_text="FG attempts per game")
    fg3a_pg = models.FloatField(default=0.0, help_text="3PA per game")
    # Per-game counting rates computed from PlayerGameStats totals
    ftm_pg = models.FloatField(default=0.0, help_text="FTM per game")
    fta_pg = models.FloatField(default=0.0, help_text="FTA per game")
    oreb_pg = models.FloatField(default=0.0, help_text="Offensive rebounds per game")
    dreb_pg = models.FloatField(default=0.0, help_text="Defensive rebounds per game")
    # Shooting efficiency
    efg_pct = models.FloatField(null=True, blank=True, help_text="Effective FG% = (FGM + 0.5*FG3M) / FGA")
    ts_pct = models.FloatField(null=True, blank=True, help_text="True Shooting% = PTS / (2*(FGA + 0.44*FTA))")
    # Playmaking ratio
    ast_to = models.FloatField(null=True, blank=True, help_text="Assist-to-turnover ratio")
    # On-court raw ratings (from ESPN PBP lineup reconstruction)
    on_court_secs_pg = models.FloatField(
        null=True, blank=True,
        help_text="Avg seconds on court per game (from PBP)",
    )
    on_court_pts_pg = models.FloatField(
        null=True, blank=True,
        help_text="Avg team pts scored while on per game",
    )
    on_court_def_pg = models.FloatField(
        null=True, blank=True,
        help_text="Avg team pts allowed while on per game",
    )
    on_court_net_pg = models.FloatField(
        null=True, blank=True,
        help_text="Avg net pts while on per game",
    )
    on_court_ortg = models.FloatField(
        null=True, blank=True,
        help_text="On-court pts per 40 min on court (raw, from PBP)",
    )
    on_court_drtg = models.FloatField(
        null=True, blank=True,
        help_text="On-court opp pts per 40 min on court (raw, from PBP)",
    )
    on_court_net = models.FloatField(
        null=True, blank=True,
        help_text="On-court net rating per 40 min on court (raw, from PBP)",
    )

    # ── On-court Four Factors (team while player is on; Phase D) ─────────────
    on_court_efg_pct     = models.FloatField(null=True, blank=True, help_text="Team eFG% while on court")
    on_court_tov_pct     = models.FloatField(null=True, blank=True, help_text="Team TOV% while on court")
    on_court_orb_pct     = models.FloatField(null=True, blank=True, help_text="Team ORB% while on court")
    on_court_ftr         = models.FloatField(null=True, blank=True, help_text="Team FTR (FTA/FGA) while on court")
    on_court_opp_efg_pct = models.FloatField(null=True, blank=True, help_text="Opp eFG% while on court")
    on_court_opp_tov_pct = models.FloatField(null=True, blank=True, help_text="Opp TOV% while on court")
    on_court_drb_pct     = models.FloatField(null=True, blank=True, help_text="Team DRB% (opp ORB%) while on court")
    on_court_opp_ftr     = models.FloatField(null=True, blank=True, help_text="Opp FTR while on court")
    on_court_efg_margin  = models.FloatField(null=True, blank=True, help_text="eFG% margin while on")
    on_court_tov_edge    = models.FloatField(null=True, blank=True, help_text="TOV edge while on")
    on_court_reb_edge    = models.FloatField(null=True, blank=True, help_text="Rebound edge while on")
    on_court_ftr_margin  = models.FloatField(null=True, blank=True, help_text="FTR margin while on")
    on_court_ffi         = models.FloatField(null=True, blank=True, help_text="Four Factor Index (0-100) while on court")

    # ── MPIR (Macfax Player Impact Rating) ───────────────────────────────────
    o_mpir = models.FloatField(null=True, blank=True, help_text="Offensive MPIR: blend of on-court offensive impact and box-score offensive prior")
    d_mpir = models.FloatField(null=True, blank=True, help_text="Defensive MPIR: blend of on-court defensive impact and box-score defensive prior")
    mpir   = models.FloatField(null=True, blank=True, help_text="Macfax Player Impact Rating = O-MPIR + D-MPIR")

    # ── BPR (Bayesian Performance Rating) ────────────────────────────────────
    # Core outputs (prior-informed Bayesian RAPM)
    bpr  = models.FloatField(null=True, blank=True, help_text="Bayesian Performance Rating = OBPR + DBPR")
    obpr = models.FloatField(null=True, blank=True, help_text="Offensive BPR: pts/100 poss above D1 avg on offense")
    dbpr = models.FloatField(null=True, blank=True, help_text="Defensive BPR: pts/100 poss better than D1 avg on defense")
    # Box BPR (box-score model only; no lineup data required)
    box_bpr  = models.FloatField(null=True, blank=True, help_text="Box BPR = box_obpr + box_dbpr")
    box_obpr = models.FloatField(null=True, blank=True, help_text="Offensive Box BPR (box-score model)*")
    box_dbpr = models.FloatField(null=True, blank=True, help_text="Defensive Box BPR (box-score model)")
    # Preseason priors
    preseason_obpr = models.FloatField(null=True, blank=True, help_text="Preseason estimated OBPR")
    preseason_dbpr = models.FloatField(null=True, blank=True, help_text="Preseason estimated DBPR")
    # Bayesian prior parameters used in RAPM fit
    prior_mean_obpr = models.FloatField(null=True, blank=True, help_text="Prior mean for OBPR in Bayesian RAPM")
    prior_mean_dbpr = models.FloatField(null=True, blank=True, help_text="Prior mean for DBPR in Bayesian RAPM")
    prior_sd_obpr   = models.FloatField(null=True, blank=True, help_text="Prior SD for OBPR")
    prior_sd_dbpr   = models.FloatField(null=True, blank=True, help_text="Prior SD for DBPR")
    # Possession counts (estimated from box events while on court)
    off_poss = models.FloatField(null=True, blank=True, help_text="Estimated offensive possessions while on court")
    def_poss = models.FloatField(null=True, blank=True, help_text="Estimated defensive possessions while on court")
    # Adjusted on-court team efficiencies (pts/100 poss)
    adj_team_off_eff_on = models.FloatField(null=True, blank=True, help_text="Team adj off eff (pts/100 poss) while player on court")
    adj_team_def_eff_on = models.FloatField(null=True, blank=True, help_text="Team adj def eff (pts/100 poss) while player on court")
    # ── Phase E: possession-based adjusted on-court ratings ──────────────────
    # Distinct from legacy on_court_ortg/drtg (per-40 raw pts-based values).
    # Formula: AOR_g = rawOE_g × (NatAvg / OppAdjD) × offSiteFactor, then
    #          shrunk toward NatAvg with k=200 poss prior. Same methodology
    #          as compute_adjusted_ratings team engine.
    on_court_off_poss = models.FloatField(null=True, blank=True, help_text="Offensive possessions on court (FGA + 0.44·FTA + TOV − OREB)")
    on_court_def_poss = models.FloatField(null=True, blank=True, help_text="Defensive possessions on court (opp FGA + 0.44·FTA + TOV − OREB)")
    on_court_raw_oe   = models.FloatField(null=True, blank=True, help_text="Raw on-court offensive efficiency (pts/100 off poss)")
    on_court_raw_de   = models.FloatField(null=True, blank=True, help_text="Raw on-court defensive efficiency (opp pts/100 def poss)")
    on_court_adj_o    = models.FloatField(null=True, blank=True, help_text="Adjusted on-court offensive efficiency (opponent-/site-adjusted, shrunk toward nat avg)")
    on_court_adj_d    = models.FloatField(null=True, blank=True, help_text="Adjusted on-court defensive efficiency (opponent-/site-adjusted, shrunk toward nat avg)")
    on_court_adj_em   = models.FloatField(null=True, blank=True, help_text="Adjusted on-court net efficiency (on_court_adj_o − on_court_adj_d)")

    # ── Four Factor Impact (RAPM-based, player-specific) ─────────────────────
    # 8 impact components — all stored positive-good.
    off_efg_impact = models.FloatField(null=True, blank=True, help_text="Offensive eFG% impact vs average (pp, positive-good)")
    def_efg_impact = models.FloatField(null=True, blank=True, help_text="Defensive eFG% impact: reduction in opp eFG vs average (pp, positive-good)")
    off_tov_impact = models.FloatField(null=True, blank=True, help_text="Offensive TOV impact: reduction in team TOV% vs average (pp, positive-good)")
    def_tov_impact = models.FloatField(null=True, blank=True, help_text="Defensive TOV generation: increase in forced opp TOV% vs average (pp, positive-good)")
    off_orb_impact = models.FloatField(null=True, blank=True, help_text="Offensive ORB% impact vs average (pp, positive-good)")
    def_reb_impact = models.FloatField(null=True, blank=True, help_text="Defensive rebounding impact: reduction in opp ORB% vs average (pp, positive-good)")
    off_ftr_impact = models.FloatField(null=True, blank=True, help_text="Offensive FTR impact vs average (pp, positive-good)")
    def_ftr_impact = models.FloatField(null=True, blank=True, help_text="Defensive FTR prevention: reduction in opp FTR vs average (pp, positive-good)")
    # 4 combined two-way margins (off + def impact)
    efg_impact_margin = models.FloatField(null=True, blank=True, help_text="Combined eFG impact margin (off + def)")
    tov_impact_margin = models.FloatField(null=True, blank=True, help_text="Combined TOV impact margin (off + def)")
    reb_impact_margin = models.FloatField(null=True, blank=True, help_text="Combined rebounding impact margin (off ORB + def REB)")
    ftr_impact_margin = models.FloatField(null=True, blank=True, help_text="Combined FTR impact margin (off + def)")
    # Four Factor Impact Index (0-100, standardized & weighted like team FFI)
    four_factor_impact_index = models.FloatField(null=True, blank=True, help_text="Four Factor Impact Index (0-100): RAPM-based, player-specific, not team-context-driven")

    # Baseline RAPM targets (raw, before prior-informed fit)
    # These are stored as training targets for future Box BPR training,
    # eliminating recursive contamination (prior-informed BPR → Box BPR → next BPR).
    baseline_obpr = models.FloatField(null=True, blank=True, help_text="Baseline RAPM OBPR (before prior-informed fit; clean target for Box BPR training)")
    baseline_dbpr = models.FloatField(null=True, blank=True, help_text="Baseline RAPM DBPR (before prior-informed fit; clean target for Box BPR training)")
    # BPR source provenance — records where each component came from
    obpr_source = models.CharField(max_length=20, null=True, blank=True, help_text="Source of OBPR: 'rapm', 'box_bpr', or null")
    dbpr_source = models.CharField(max_length=20, null=True, blank=True, help_text="Source of DBPR: 'rapm', 'box_bpr', or null")
    bpr_source  = models.CharField(max_length=20, null=True, blank=True, help_text="Source of total BPR: 'rapm', 'box_bpr', 'mixed', 'partial', or null")
    # BPR model metadata
    bpr_model_version = models.CharField(max_length=32, null=True, blank=True, help_text="BPR model version tag")
    bpr_last_updated  = models.DateTimeField(null=True, blank=True, help_text="When BPR was last computed")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["player", "season", "team"], name="unique_player_season_team"
            )
        ]
        indexes = [
            models.Index(fields=["team", "season"]),
            models.Index(fields=["player", "season"]),
        ]

    def __str__(self):
        return f"{self.player.display_name} — {self.season}"


class PlayerSeasonProjection(models.Model):
    """
    Next-season player projection generated by compute_player_projections.

    Stores a Bayesian-prior-informed projection of each player's expected
    performance in the season immediately following from_season.

    Phase 1 (current):
      - projected_obpr / projected_dbpr / projected_bpr via priority-selected
        talent signal (RAPM primary; box fallback) + year-to-year shrinkage +
        trend + development + transfer competition translation
      - projected_minutes_share as a provisional baseline estimate
      - projection_uncertainty as a structured 0–1 confidence score
      - recruitment_type classification from consecutive-season roster data

    Phase 2 will add:
      - optimized minutes model with team roster context
      - team continuity / fit signals
      - team-level roster aggregation
    """

    RECRUITMENT_TYPE_CHOICES = [
        ("returner", "Returner"),    # same team as prior season
        ("transfer", "Transfer"),    # prior season at a different team
        ("newcomer", "Newcomer"),    # no prior college season found in DB
    ]

    player = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="season_projections",
    )
    team = models.ForeignKey(
        Team, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="player_projections",
        help_text=(
            "Canonical team for this projection — the team with the most possessions "
            "logged by this player in from_season.  For single-team players this is "
            "their only team.  For split-season players this is the team they logged "
            "the most court time with."
        ),
    )
    from_season = models.ForeignKey(
        Season, on_delete=models.CASCADE, related_name="player_projections",
        help_text="The season this projection is based on",
    )
    projected_season_year = models.IntegerField(
        help_text="The season year being projected to (e.g. 2027 if from_season.year=2026)",
    )

    # ── Recruitment type ──────────────────────────────────────────────────────
    recruitment_type = models.CharField(
        max_length=20,
        choices=RECRUITMENT_TYPE_CHOICES,
        help_text="How the player arrived at their current team (vs prior season)",
    )

    # ── Core projections ──────────────────────────────────────────────────────
    projected_obpr = models.FloatField(
        null=True, blank=True,
        help_text="Projected offensive BPR for next season (pts/100 poss above D1 avg)",
    )
    projected_dbpr = models.FloatField(
        null=True, blank=True,
        help_text="Projected defensive BPR for next season (pts/100 poss above D1 avg)",
    )
    projected_bpr = models.FloatField(
        null=True, blank=True,
        help_text="projected_obpr + projected_dbpr",
    )
    projected_minutes_share = models.FloatField(
        null=True, blank=True,
        help_text=(
            "Estimated fraction of 40 minutes played per game (mpg/40) for next season. "
            "Phase 1 baseline — will be refined in Phase 2."
        ),
    )
    projection_uncertainty = models.FloatField(
        null=True, blank=True,
        help_text=(
            "Projection confidence score: 0 = low uncertainty (high confidence), "
            "1 = high uncertainty. Influenced by recruitment type and sample size."
        ),
    )

    # ── Diagnostics / provenance ──────────────────────────────────────────────
    n_prior_seasons = models.IntegerField(
        default=0,
        help_text="Number of prior college seasons in DB before from_season",
    )
    prior_rapm_used = models.BooleanField(
        default=False,
        help_text="Whether prior-season RAPM (obpr/dbpr) was available and incorporated",
    )
    projection_version = models.CharField(
        max_length=20,
        default="1.0",
        help_text="Version tag of the projection model that generated this row",
    )
    computed_at = models.DateTimeField(auto_now=True)

    # ── Phase 2: roster‑context minutes allocation ────────────────────────────
    # Populated by compute_player_minutes (run_minutes_pipeline).
    # These fields are NULL until Phase 2 has been run for this season.
    role_bucket = models.CharField(
        max_length=10, null=True, blank=True,
        choices=[("G", "Guard"), ("Wing", "Wing"), ("Big", "Big")],
        help_text=(
            "Role bucket derived from Player.position, with box‑score rates as "
            "fallback for ambiguous positions (ATH, NA, empty).  "
            "G = Guard, Wing = Forward/Wing, Big = Center/Power Forward."
        ),
    )
    minutes_share_p2 = models.FloatField(
        null=True, blank=True,
        help_text=(
            "Phase 2 projected minutes share (mpg / 40) from the roster‑context "
            "allocator.  Sums to 5.00 across all players on the same team.  "
            "Replaces the Phase 1 baseline (projected_minutes_share) for roster work."
        ),
    )
    mpg_p2 = models.FloatField(
        null=True, blank=True,
        help_text="Phase 2 projected MPG = minutes_share_p2 × 40.",
    )
    rotation_rank = models.IntegerField(
        null=True, blank=True,
        help_text=(
            "Rotation rank within the player's team (1 = highest projected minutes).  "
            "Computed by the Phase 2 minutes allocator."
        ),
    )
    minutes_overridden = models.BooleanField(
        default=False,
        help_text=(
            "True when this player's minutes share was manually pinned via a "
            "sandbox override.  Always False for baseline (non‑scenario) runs."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["player", "from_season"],
                name="unique_player_season_projection",
            )
        ]
        indexes = [
            models.Index(fields=["from_season", "projected_season_year"]),
            models.Index(fields=["player", "from_season"]),
        ]

    def __str__(self):
        return (
            f"{self.player.display_name} projection "
            f"({self.from_season.year}→{self.projected_season_year}): "
            f"BPR={self.projected_bpr:.2f}"
            if self.projected_bpr is not None
            else f"{self.player.display_name} projection ({self.from_season.year}→{self.projected_season_year})"
        )


class PlayerGameStint(models.Model):
    """
    One contiguous on-court stint for a player within a single half/OT period.

    Created by sync_ncaa_pbp from ESPN play-by-play data.
    Aggregated into PlayerSeasonStats.on_court_* by compute_ncaa_player_impact.
    """

    player = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="game_stints"
    )
    game = models.ForeignKey(
        Game, on_delete=models.CASCADE, related_name="player_stints"
    )
    team = models.ForeignKey(
        Team, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="player_stints",
    )
    stint_index = models.IntegerField(help_text="0-based sequential per (player, game)")
    period = models.IntegerField(
        default=1, help_text="1=first half, 2=second half, 3+=OT"
    )
    clock_start_secs = models.IntegerField(
        help_text="Seconds remaining in period at stint start"
    )
    clock_end_secs = models.IntegerField(
        help_text="Seconds remaining in period at stint end"
    )
    secs_on = models.IntegerField(
        default=0, help_text="Duration in seconds (clock_start - clock_end)"
    )
    pts_scored = models.IntegerField(
        default=0, help_text="Team pts scored while this player was on court"
    )
    pts_allowed = models.IntegerField(
        default=0, help_text="Opp pts scored while this player was on court"
    )
    plus_minus = models.IntegerField(
        default=0, help_text="pts_scored - pts_allowed"
    )

    # ── Team box events while on court (populated by sync_ncaa_pbp Phase D) ──
    team_fgm  = models.SmallIntegerField(default=0, help_text="Team FG made while on")
    team_fga  = models.SmallIntegerField(default=0, help_text="Team FG attempted while on")
    team_fg3m = models.SmallIntegerField(default=0, help_text="Team 3P made while on")
    team_fta  = models.SmallIntegerField(default=0, help_text="Team FT attempted while on")
    team_tov  = models.SmallIntegerField(default=0, help_text="Team turnovers while on")
    team_oreb = models.SmallIntegerField(default=0, help_text="Team offensive rebounds while on")
    team_dreb = models.SmallIntegerField(default=0, help_text="Team defensive rebounds while on")

    # ── Opponent box events while on court ────────────────────────────────────
    opp_fgm  = models.SmallIntegerField(default=0, help_text="Opp FG made while on")
    opp_fga  = models.SmallIntegerField(default=0, help_text="Opp FG attempted while on")
    opp_fg3m = models.SmallIntegerField(default=0, help_text="Opp 3P made while on")
    opp_fta  = models.SmallIntegerField(default=0, help_text="Opp FT attempted while on")
    opp_tov  = models.SmallIntegerField(default=0, help_text="Opp turnovers while on")
    opp_oreb = models.SmallIntegerField(default=0, help_text="Opp offensive rebounds while on")
    opp_dreb = models.SmallIntegerField(default=0, help_text="Opp defensive rebounds while on")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["player", "game", "stint_index"],
                name="unique_player_game_stint",
            )
        ]
        indexes = [
            models.Index(fields=["game", "team"]),
            models.Index(fields=["player", "game"]),
        ]

    def __str__(self):
        return f"{self.player} stint {self.stint_index} in game {self.game_id}"


class BPRModelArtifact(models.Model):
    """
    Stores trained BPR model weights and cross-validation metrics.

    model_type choices:
      box_off         — Box BPR offensive model (predicts OBPR from box stats)
      box_def         — Box BPR defensive model (predicts DBPR from box stats)
      rapm_baseline   — Single-season RAPM with global zero priors
      rapm_informed   — Prior-informed RAPM using Box BPR as player-specific priors
    """

    season = models.ForeignKey(
        Season, on_delete=models.CASCADE, related_name="bpr_artifacts",
        help_text="Season this model was trained on",
    )
    model_type = models.CharField(
        max_length=32,
        help_text="box_off | box_def | rapm_baseline | rapm_informed",
    )
    version = models.CharField(max_length=32, help_text="Semantic version tag")
    feature_names = models.JSONField(default=list)
    coefficients  = models.JSONField(default=list, help_text="Trained coefficients aligned to feature_names")
    intercept     = models.FloatField(null=True, blank=True)
    regularization_alpha = models.FloatField(null=True, blank=True, help_text="Ridge lambda chosen by CV")
    cv_metrics    = models.JSONField(null=True, blank=True, help_text="{rmse, r2, best_alpha, fold_rmses}")
    assumptions   = models.JSONField(null=True, blank=True, help_text="Documented BPR article deviations")
    n_observations = models.IntegerField(null=True, blank=True)
    n_players      = models.IntegerField(null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"BPRModelArtifact({self.model_type}, season={self.season_id}, v={self.version})"


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


class PlaceholderArchetype(models.Model):
    """
    Pre-built archetype player buckets derived from real PlayerSeasonProjection data.

    Each row represents the median statistical profile of a real cohort of D1 players
    (e.g. "all Power Conference starters at the Guard position projected for 2027").
    Built by: python manage.py build_placeholder_archetypes

    Fields are intentionally named to match PlayerSeasonProjection fields so the
    scenario engine can accept archetype rows as drop-in player inputs.
    """

    CONF_GROUP_CHOICES = [
        ("national",  "National (All D1)"),
        ("power",     "Power Conference"),
        ("high_mid",  "High Mid-Major (WCC, MWC, A10, Amer)"),
        ("mid_major", "Mid-Major"),
    ]
    QUALITY_TIER_CHOICES = [
        ("elite",         "Elite (All-American)"),
        ("all_conference","All-Conference"),
        ("starter",       "Starter"),
        ("rotation",      "Rotation"),
        ("bench",         "Bench"),
    ]
    ROLE_CHOICES = [
        ("G",    "Guard"),
        ("Wing", "Wing"),
        ("Big",  "Big"),
    ]

    # Identity
    key = models.CharField(max_length=64, unique=True, db_index=True,
                           help_text="Stable slug, e.g. 'power_starter_g'")
    display_name = models.CharField(max_length=128,
                                    help_text="Human-readable label shown in UI")
    conf_group = models.CharField(max_length=16, choices=CONF_GROUP_CHOICES,
                                  db_index=True)
    role_bucket = models.CharField(max_length=8, choices=ROLE_CHOICES,
                                   db_index=True)
    quality_tier = models.CharField(max_length=16, choices=QUALITY_TIER_CHOICES,
                                    db_index=True)

    # Core projection stats (medians from bucket)
    projected_obpr = models.FloatField()
    projected_dbpr = models.FloatField()
    projected_bpr = models.FloatField()
    minutes_share = models.FloatField(help_text="Median minutes_share_p2 of bucket")
    mpg = models.FloatField(help_text="Median mpg_p2 of bucket")
    uncertainty = models.FloatField(help_text="Median projection_uncertainty of bucket")

    # Box-score profile (medians from matching PlayerSeasonStats — nullable)
    efg_pct = models.FloatField(null=True, blank=True)
    fg3_pct = models.FloatField(null=True, blank=True)
    ts_pct   = models.FloatField(null=True, blank=True)
    ast_to   = models.FloatField(null=True, blank=True)
    oreb_pg  = models.FloatField(null=True, blank=True)
    dreb_pg  = models.FloatField(null=True, blank=True)
    tov      = models.FloatField(null=True, blank=True,
                                 help_text="Median turnovers per game")

    # Provenance
    sample_n = models.IntegerField(help_text="Number of real players in source bucket")
    source_season_year = models.IntegerField(
        help_text="Season year (from_season.year) data was drawn from")
    built_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["conf_group", "role_bucket", "quality_tier"]
        indexes = [
            models.Index(fields=["conf_group", "role_bucket", "quality_tier"]),
        ]

    def __str__(self):
        return f"{self.display_name} (n={self.sample_n}, BPR≈{self.projected_bpr:.2f})"
