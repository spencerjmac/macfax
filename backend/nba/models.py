"""
NBA Django Models — macfax NBA app (Phase 1)

All models are NBA-specific. No shared schema with NCAA core/ models.
These tables are populated by nba/ management commands using the nba_api provider layer.
"""

from django.db import models
from django.utils.text import slugify


# ─────────────────────────────────────────────────────────────────────────────
# Choice constants
# ─────────────────────────────────────────────────────────────────────────────

SEASON_TYPE_CHOICES = [
    ("preseason", "Preseason"),
    ("regular", "Regular Season"),
    ("play_in", "Play-In"),
    ("playoffs", "Playoffs"),
]

COMPETITION_CHOICES = [
    ("regular", "Regular"),
    ("nba_cup_group", "NBA Cup Group Stage"),
    ("nba_cup_qf", "NBA Cup Quarterfinal"),
    ("nba_cup_sf", "NBA Cup Semifinal"),
    # Championship game does NOT count toward regular-season standings
    ("nba_cup_final", "NBA Cup Championship"),
]

CONFERENCE_CHOICES = [
    ("East", "Eastern Conference"),
    ("West", "Western Conference"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Core domain models
# ─────────────────────────────────────────────────────────────────────────────


class NBASeason(models.Model):
    """Represents one NBA season (e.g., 2025-26 → year=2026)."""

    year = models.IntegerField(
        unique=True, db_index=True, help_text="Ending year (2026 for 2025-26)"
    )
    display_name = models.CharField(max_length=20, help_text="Human-readable, e.g. 2025-26")
    is_current = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-year"]

    def __str__(self):
        return self.display_name

    def save(self, *args, **kwargs):
        if self.is_current:
            NBASeason.objects.filter(is_current=True).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)


class NBATeam(models.Model):
    """One NBA franchise. nba_team_id is the canonical NBA.com integer ID."""

    nba_team_id = models.IntegerField(
        unique=True, db_index=True, help_text="NBA.com canonical team ID"
    )
    slug = models.SlugField(unique=True, db_index=True, max_length=100)
    name = models.CharField(max_length=100, help_text="Full franchise name, e.g. Boston Celtics")
    abbreviation = models.CharField(max_length=5, help_text="e.g. BOS")
    city = models.CharField(max_length=100)
    conference = models.CharField(max_length=10, choices=CONFERENCE_CHOICES)
    division = models.CharField(max_length=50)
    logo_url = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class NBAGame(models.Model):
    """
    One NBA game. Seeded by LeagueGameLog (partial stats), then enriched
    by BoxScoreTraditionalV3 (box_score_synced=True).

    counts_toward_regular_season reflects NBA Cup rules:
      - Group stage, QF, SF games count toward standings.
      - Championship game does NOT.
    """

    game_id = models.CharField(
        max_length=20, unique=True, db_index=True, help_text="NBA.com game ID"
    )
    season = models.ForeignKey(NBASeason, on_delete=models.CASCADE, related_name="games")
    date = models.DateField(db_index=True)
    home_team = models.ForeignKey(
        NBATeam, on_delete=models.CASCADE, related_name="home_games"
    )
    away_team = models.ForeignKey(
        NBATeam, on_delete=models.CASCADE, related_name="away_games"
    )
    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)
    arena = models.CharField(max_length=150, blank=True)

    season_type = models.CharField(
        max_length=20, choices=SEASON_TYPE_CHOICES, default="regular"
    )
    competition = models.CharField(
        max_length=20, choices=COMPETITION_CHOICES, default="regular"
    )
    # Derived at ingest time from competition type — see _set_counts_flag()
    counts_toward_regular_season = models.BooleanField(
        default=True,
        db_index=True,
        help_text="False only for NBA Cup Championship and non-regular season games.",
    )

    status = models.CharField(
        max_length=20, default="Scheduled", help_text="Final | Scheduled | Live"
    )

    # Rest context — set during ingestion from schedule data
    rest_days_home = models.IntegerField(
        null=True, blank=True, help_text="Days since last game for home team"
    )
    rest_days_away = models.IntegerField(
        null=True, blank=True, help_text="Days since last game for away team"
    )
    home_b2b = models.BooleanField(default=False)
    away_b2b = models.BooleanField(default=False)

    # Set to True after BoxScoreTraditionalV3 enrichment runs
    box_score_synced = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.away_team.abbreviation} @ {self.home_team.abbreviation} ({self.date})"

    def save(self, *args, **kwargs):
        self._set_counts_flag()
        super().save(*args, **kwargs)

    def _set_counts_flag(self):
        if self.season_type != "regular":
            self.counts_toward_regular_season = False


# ─────────────────────────────────────────────────────────────────────────────
# Per-game stats models
# ─────────────────────────────────────────────────────────────────────────────


class NBATeamGameStats(models.Model):
    """
    Box-score stats for one team in one game.
    Partial records (pts, opp_pts only) exist after LeagueGameLog sync.
    Full records (four factors, possessions, ratings) exist after BoxScore sync.
    """

    game = models.ForeignKey(NBAGame, on_delete=models.CASCADE, related_name="team_stats")
    team = models.ForeignKey(NBATeam, on_delete=models.CASCADE, related_name="game_stats")
    is_home = models.BooleanField()

    # ── Scoring ──────────────────────────────────────────────────────────────
    pts = models.IntegerField(null=True, blank=True)
    opp_pts = models.IntegerField(null=True, blank=True)

    # ── Box score (filled after BoxScore sync) ────────────────────────────────
    fgm = models.IntegerField(null=True, blank=True)
    fga = models.IntegerField(null=True, blank=True)
    fg3m = models.IntegerField(null=True, blank=True)
    fg3a = models.IntegerField(null=True, blank=True)
    ftm = models.IntegerField(null=True, blank=True)
    fta = models.IntegerField(null=True, blank=True)
    oreb = models.IntegerField(null=True, blank=True)
    dreb = models.IntegerField(null=True, blank=True)
    tov = models.IntegerField(null=True, blank=True)

    # ── Derived (filled after BoxScore sync) ─────────────────────────────────
    # poss = FGA - OREB + TO + 0.44*FTA
    poss = models.FloatField(null=True, blank=True, help_text="Estimated possessions")
    raw_ortg = models.FloatField(
        null=True, blank=True, help_text="Raw offensive rating (pts/100 poss)"
    )
    raw_drtg = models.FloatField(
        null=True, blank=True, help_text="Raw defensive rating (opp pts/100 opp poss)"
    )

    # ── Opponent-adjusted (filled after nba_compute_ratings) ─────────────────
    adj_ortg = models.FloatField(null=True, blank=True)
    adj_drtg = models.FloatField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["game", "team"], name="unique_nba_team_game_stats")
        ]

    def __str__(self):
        return f"{self.team.abbreviation} in {self.game.game_id}"


class NBAPlayer(models.Model):
    """NBA player. player_id is the NBA.com canonical integer ID."""

    player_id = models.IntegerField(
        unique=True, db_index=True, help_text="NBA.com canonical player ID"
    )
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True, db_index=True)
    current_team = models.ForeignKey(
        NBATeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_players",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class NBAPlayerGameStats(models.Model):
    """
    Player-level box score for one game.

    seconds_played: store as int (parse "MM:SS" at adapter layer).
    Display layer converts back: f"{s//60}:{s%60:02d}"
    """

    game = models.ForeignKey(NBAGame, on_delete=models.CASCADE, related_name="player_stats")
    player = models.ForeignKey(
        NBAPlayer, on_delete=models.CASCADE, related_name="game_stats"
    )
    team = models.ForeignKey(NBATeam, on_delete=models.CASCADE, related_name="player_game_stats")

    # ── Time ─────────────────────────────────────────────────────────────────
    # Stored as integer seconds — avoids float precision issues with "34:21" strings.
    seconds_played = models.IntegerField(null=True, blank=True)

    # ── Counting stats ────────────────────────────────────────────────────────
    pts = models.IntegerField(null=True, blank=True)
    reb = models.IntegerField(null=True, blank=True)
    ast = models.IntegerField(null=True, blank=True)
    stl = models.IntegerField(null=True, blank=True)
    blk = models.IntegerField(null=True, blank=True)
    tov = models.IntegerField(null=True, blank=True)

    # ── Shooting ─────────────────────────────────────────────────────────────
    fgm = models.IntegerField(null=True, blank=True)
    fga = models.IntegerField(null=True, blank=True)
    fg3m = models.IntegerField(null=True, blank=True)
    fg3a = models.IntegerField(null=True, blank=True)
    ftm = models.IntegerField(null=True, blank=True)
    fta = models.IntegerField(null=True, blank=True)

    plus_minus = models.IntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["game", "player"], name="unique_nba_player_game_stats"
            )
        ]

    def __str__(self):
        return f"{self.player.name} in {self.game.game_id}"


# ─────────────────────────────────────────────────────────────────────────────
# Season-level aggregated ratings
# ─────────────────────────────────────────────────────────────────────────────


class NBATeamSeasonRatings(models.Model):
    """
    Season-level aggregated adjusted ratings for one NBA team.
    Populated by: python manage.py nba_compute_ratings --season YYYY

    rank_adj_net and rank_ffi are DERIVED PRESENTATION VALUES written by the
    compute command. They are not foundational data — the truth is adj_off/adj_def/ffi.
    """

    team = models.ForeignKey(
        NBATeam, on_delete=models.CASCADE, related_name="season_ratings"
    )
    season = models.ForeignKey(
        NBASeason, on_delete=models.CASCADE, related_name="team_ratings"
    )
    season_type = models.CharField(
        max_length=20, choices=SEASON_TYPE_CHOICES, default="regular", db_index=True
    )
    games = models.IntegerField(default=0)

    # ── Adjusted efficiency ──────────────────────────────────────────────────
    adj_off = models.FloatField(null=True, blank=True, help_text="Opponent-adjusted offensive rating")
    adj_def = models.FloatField(null=True, blank=True, help_text="Opponent-adjusted defensive rating")
    adj_net = models.FloatField(null=True, blank=True, help_text="adj_off - adj_def")
    pace = models.FloatField(null=True, blank=True, help_text="Possessions per 48 min")

    # ── Four Factors — raw season averages ───────────────────────────────────
    efg_pct = models.FloatField(null=True, blank=True)
    opp_efg_pct = models.FloatField(null=True, blank=True)
    tov_rate = models.FloatField(null=True, blank=True)
    opp_tov_rate = models.FloatField(null=True, blank=True)
    oreb_pct = models.FloatField(null=True, blank=True)
    opp_oreb_pct = models.FloatField(null=True, blank=True)
    fta_rate = models.FloatField(null=True, blank=True)
    opp_fta_rate = models.FloatField(null=True, blank=True)

    # ── Four Factor margins (offense advantage) ───────────────────────────────
    efg_margin = models.FloatField(null=True, blank=True, help_text="eFG% - Opp eFG%")
    tov_edge = models.FloatField(null=True, blank=True, help_text="Opp TOV% - TOV%")
    oreb_edge = models.FloatField(null=True, blank=True, help_text="OREB% - Opp OREB%")
    fta_margin = models.FloatField(null=True, blank=True, help_text="FTA/FGA - Opp FTA/FGA")

    # ── Four Factor Index (PROVISIONAL — backtest before trusting) ───────────
    ffi = models.FloatField(
        null=True,
        blank=True,
        help_text="PROVISIONAL Four Factor Index. See nba/ratings_config.py for weights.",
    )

    # ── Derived presentation ranks (written by compute command, not source of truth) ──
    rank_adj_net = models.IntegerField(
        null=True, blank=True, help_text="Derived rank by adj_net. Not source of truth."
    )
    rank_ffi = models.IntegerField(
        null=True, blank=True, help_text="Derived rank by FFI. Not source of truth."
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["team", "season", "season_type"], name="unique_nba_team_season_ratings"
            )
        ]
        ordering = ["rank_adj_net"]

    def __str__(self):
        return f"{self.team.name} {self.season.display_name} ratings"


class NBAPlayerSeasonStats(models.Model):
    """
    Season-level per-game averages for one player.

    Populated by: python manage.py nba_compute_player_stats --season YYYY
    Requires NBAPlayerGameStats rows to exist first (nba_sync_team_logs).
    """

    player = models.ForeignKey(
        NBAPlayer, on_delete=models.CASCADE, related_name="season_stats"
    )
    team = models.ForeignKey(
        NBATeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="player_season_stats",
        help_text="Team the player spent the most minutes with this season",
    )
    season = models.ForeignKey(
        NBASeason, on_delete=models.CASCADE, related_name="player_season_stats"
    )
    season_type = models.CharField(
        max_length=20, choices=SEASON_TYPE_CHOICES, default="regular", db_index=True
    )
    updated_at = models.DateTimeField(auto_now=True)

    # ── Volume ────────────────────────────────────────────────────────────────
    gp = models.IntegerField(help_text="Games played")
    mpg = models.FloatField(null=True, blank=True, help_text="Minutes per game")

    # ── Per-game averages ─────────────────────────────────────────────────────
    pts = models.FloatField(null=True, blank=True)
    reb = models.FloatField(null=True, blank=True)
    ast = models.FloatField(null=True, blank=True)
    stl = models.FloatField(null=True, blank=True)
    blk = models.FloatField(null=True, blank=True)
    tov = models.FloatField(null=True, blank=True)
    plus_minus = models.FloatField(null=True, blank=True, help_text="+/- per game")

    # ── Shooting efficiencies ─────────────────────────────────────────────────
    fg_pct = models.FloatField(null=True, blank=True, help_text="FGM/FGA")
    fg3_pct = models.FloatField(null=True, blank=True, help_text="3PM/3PA")
    ft_pct = models.FloatField(null=True, blank=True, help_text="FTM/FTA")
    fga_pg = models.FloatField(null=True, blank=True, help_text="FGA per game")
    fg3a_pg = models.FloatField(null=True, blank=True, help_text="3PA per game")
    fta_pg = models.FloatField(null=True, blank=True, help_text="FTA per game")
    ftm_pg = models.FloatField(null=True, blank=True, help_text="FTM per game")
    oreb_pg = models.FloatField(null=True, blank=True, help_text="Offensive rebounds per game")
    dreb_pg = models.FloatField(null=True, blank=True, help_text="Defensive rebounds per game")

    # ── Advanced efficiency (from NBA.com LeagueDashPlayerStats Advanced) ─────
    # Populated by: python manage.py nba_sync_player_advanced --season YYYY
    efg_pct = models.FloatField(null=True, blank=True, help_text="Effective FG% (from NBA.com)")
    ts_pct = models.FloatField(null=True, blank=True, help_text="True Shooting %")
    usg_pct = models.FloatField(null=True, blank=True, help_text="Usage rate")
    oreb_pct = models.FloatField(null=True, blank=True, help_text="Offensive rebound %")
    dreb_pct = models.FloatField(null=True, blank=True, help_text="Defensive rebound %")
    ast_pct = models.FloatField(null=True, blank=True, help_text="Assist %")
    tov_pct = models.FloatField(null=True, blank=True, help_text="Turnover % (team TOV rate while on)")
    ast_to = models.FloatField(null=True, blank=True, help_text="Assist-to-turnover ratio")
    pie = models.FloatField(null=True, blank=True, help_text="Player Impact Estimate (NBA.com)")

    # ── Impact: on-court ratings (from NBA.com Advanced, per 100 possessions) ──
    # These are RAW on-court ratings — opponent-adjusted versions are in adj_* below.
    on_court_ortg = models.FloatField(null=True, blank=True, help_text="On-court offensive rating (raw, per 100 poss)")
    on_court_drtg = models.FloatField(null=True, blank=True, help_text="On-court defensive rating (raw, per 100 poss)")
    on_court_net = models.FloatField(null=True, blank=True, help_text="On-court net rating (raw)")
    on_court_poss = models.FloatField(null=True, blank=True, help_text="Possessions played (on-court)")

    # ── Impact: estimated (Bayesian-stabilized) on-court ratings from NBA.com ─
    # E_* fields are NBA.com's own stabilized estimates — this is our MPIR source.
    on_court_adj_o = models.FloatField(null=True, blank=True, help_text="Estimated adj offensive impact (NBA.com E_OFF_RATING)")
    on_court_adj_d = models.FloatField(null=True, blank=True, help_text="Estimated adj defensive impact (NBA.com E_DEF_RATING)")
    on_court_adj_em = models.FloatField(null=True, blank=True, help_text="Estimated adj net impact (NBA.com E_NET_RATING) = MPIR")

    # ── Macfax Player Impact Rating ──────────────────────────────────────────
    # MPIR = E_NET_RATING re-branded; broken into O and D components.
    mpir = models.FloatField(null=True, blank=True, help_text="Macfax Player Impact Rating (= E_NET_RATING)")
    o_mpir = models.FloatField(null=True, blank=True, help_text="Offensive MPIR (= E_OFF_RATING - league_avg_ortg)")
    d_mpir = models.FloatField(null=True, blank=True, help_text="Defensive MPIR (= league_avg_drtg - E_DEF_RATING)")

    # ── Defense-specific counts (NBA.com LeagueDashPlayerStats = Defense) ─────
    stl_pct = models.FloatField(null=True, blank=True, help_text="Steal %")
    blk_pct = models.FloatField(null=True, blank=True, help_text="Block %")

    # ── Box BPR (nba_compute_box_bpr) ────────────────────────────────────────
    box_obpr = models.FloatField(null=True, blank=True, help_text="Box-score offensive BPR")
    box_dbpr = models.FloatField(null=True, blank=True, help_text="Box-score defensive BPR")
    box_bpr = models.FloatField(null=True, blank=True, help_text="Box-score total BPR")
    nba_archetype = models.CharField(
        max_length=32, null=True, blank=True, help_text="Role archetype (creator/scorer/stretch/three_and_d/interior/connector)"
    )
    bpr_last_updated = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["player", "season", "team", "season_type"],
                name="unique_nba_player_season_stats",
            )
        ]
        ordering = ["-pts"]

    def __str__(self):
        return f"{self.player.name} {self.season.display_name} averages"


class NBAModelCalibration(models.Model):
    """
    Per-season validation / calibration results written by:
        python manage.py nba_eval_model --season YYYY

    Four analyses are stored here:
      1. Straight-up prediction accuracy using season-end adj_net.
      2. Empirical HCA (derived from OLS on completed-game margins).
      3. Empirical B2B penalty (same OLS regression).
      4. Data-driven FFI weight derivation (OLS on adj_net vs four factor margins).

    None of these fields are source-of-truth for the live model — they are
    diagnostic / calibration outputs only.
    """

    season = models.OneToOneField(
        NBASeason,
        on_delete=models.CASCADE,
        related_name="model_calibration",
    )
    computed_at = models.DateTimeField(auto_now=True)

    # ── 1. Prediction accuracy ────────────────────────────────────────────────
    # Straight-up picks using (home_adj_net - away_adj_net + configured_hca > 0).
    # Season-end ratings are used retroactively — not true hold-out validation.
    games_predicted = models.IntegerField(
        null=True, blank=True, help_text="Completed games where both teams have ratings"
    )
    correct_predictions = models.IntegerField(null=True, blank=True)
    straight_up_accuracy = models.FloatField(
        null=True, blank=True, help_text="% correct (0-100)"
    )
    brier_score = models.FloatField(
        null=True, blank=True,
        help_text="Brier score (lower=better). Baseline ~0.25.",
    )
    log_loss = models.FloatField(
        null=True, blank=True,
        help_text="Log-loss (lower=better). Baseline ~0.693.",
    )

    # ── 2 & 3. Empirical HCA + B2B via OLS ─────────────────────────────────
    # Model: home_margin ~ HCA + β₁*(home_adj_net - away_adj_net) + β₂*home_b2b + β₃*away_b2b
    # Uses numpy.linalg.lstsq on completed regular-season games.
    ols_games = models.IntegerField(
        null=True, blank=True, help_text="Games used in the HCA/B2B OLS regression"
    )
    ols_r_squared = models.FloatField(
        null=True, blank=True, help_text="R² of OLS fit"
    )
    empirical_hca = models.FloatField(
        null=True, blank=True, help_text="OLS intercept ≈ empirical HCA in raw points"
    )
    configured_hca = models.FloatField(
        null=True, blank=True, help_text="Current ratings_config home_court_adj value"
    )
    ols_model_scale = models.FloatField(
        null=True, blank=True,
        help_text="OLS β₁ coefficient: how many raw score points per 1 pt/100 poss "
                  "of adj_net advantage (should approach 1.0 as games accumulate)",
    )
    empirical_home_b2b_penalty = models.FloatField(
        null=True, blank=True,
        help_text="OLS β₂: raw-points penalty when home team is on B2B (negative value = home hurt)",
    )
    empirical_away_b2b_penalty = models.FloatField(
        null=True, blank=True,
        help_text="OLS β₃: raw-points penalty when away team is on B2B "
                  "(positive = home benefits when away team is tired)",
    )
    configured_b2b_penalty = models.FloatField(
        null=True, blank=True, help_text="Current ratings_config b2b_penalty value"
    )

    # ── 4. FFI weight regression ─────────────────────────────────────────────
    # OLS: adj_net ~ β₀ + β₁*efg_margin + β₂*tov_edge + β₃*oreb_edge + β₄*fta_margin
    # Normalized weights (β₁..β₄ scaled to sum to 1) form the data-driven FFI proposal.
    ffi_teams_used = models.IntegerField(
        null=True, blank=True, help_text="Teams with complete four-factor data"
    )
    ffi_adj_net_r_squared = models.FloatField(
        null=True, blank=True, help_text="R² of four-factors → adj_net regression"
    )
    ffi_proposed_weight_efg = models.FloatField(
        null=True, blank=True, help_text="Data-driven eFG margin weight (sums to 1 with others)"
    )
    ffi_proposed_weight_tov = models.FloatField(null=True, blank=True)
    ffi_proposed_weight_oreb = models.FloatField(null=True, blank=True)
    ffi_proposed_weight_fta = models.FloatField(null=True, blank=True)
    ffi_current_weight_efg = models.FloatField(
        null=True, blank=True, help_text="Currently configured eFG margin weight"
    )
    ffi_current_weight_tov = models.FloatField(null=True, blank=True)
    ffi_current_weight_oreb = models.FloatField(null=True, blank=True)
    ffi_current_weight_fta = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["-season__year"]

    def __str__(self):
        return f"NBAModelCalibration {self.season.display_name} (computed {self.computed_at:%Y-%m-%d})"
