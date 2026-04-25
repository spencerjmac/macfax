"""
Game-centric models: Game, GameLog, TeamGameStats, ScoringEvent
"""

from django.db import models

from .base import Season
from .teams import Team


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
