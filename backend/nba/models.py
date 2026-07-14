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
    elevation = models.IntegerField(null=True, blank=True, help_text="Home arena elevation in feet")
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
    elevation = models.IntegerField(null=True, blank=True, help_text="Game arena elevation in feet")

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

    # ── Play-by-play sync state (nba_sync_play_by_play) ──────────────────────
    pbp_synced = models.BooleanField(default=False, db_index=True)
    pbp_synced_at = models.DateTimeField(null=True, blank=True)
    pbp_quality_flag = models.BooleanField(
        default=False, db_index=True,
        help_text="True when > 5% of stints fail 10-player validation — excluded from RAPM",
    )

    # AI-generated insights (cached after first generation)
    game_insights = models.TextField(null=True, blank=True)

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
    date_of_birth = models.DateField(null=True, blank=True)

    # Career-level aggregates — written by nba_compute_career_bpr command
    # Computed across all qualifying seasons (≥500 min) from stored bpr values
    peak_bpr   = models.FloatField(null=True, blank=True, help_text="Best single-season BPR (≥500 min qualifier)")
    career_bpr = models.FloatField(null=True, blank=True, help_text="Minutes-weighted career average BPR")

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
    oreb = models.IntegerField(null=True, blank=True)
    dreb = models.IntegerField(null=True, blank=True)
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


class NBAPlayerGameStint(models.Model):
    """
    One contiguous on-court stint for a player within a single quarter/OT period.

    Created by: python manage.py nba_sync_play_by_play --season YYYY
    Used by:    python manage.py nba_compute_baseline_rapm --season YYYY

    Design matrix for RAPM groups stints by (game, stint_index) to reconstruct
    the full 5v5 lineup from each side's player rows.
    """

    player = models.ForeignKey(NBAPlayer, on_delete=models.CASCADE, related_name="game_stints")
    game   = models.ForeignKey(NBAGame,   on_delete=models.CASCADE, related_name="player_stints")
    team   = models.ForeignKey(NBATeam,   on_delete=models.SET_NULL, null=True, blank=True, related_name="player_stints")

    stint_index      = models.IntegerField(help_text="0-based sequential per (player, game)")
    period           = models.IntegerField(help_text="1-4 regulation, 5+ OT")
    clock_start_secs = models.IntegerField(help_text="Seconds remaining in period at stint start")
    clock_end_secs   = models.IntegerField(help_text="Seconds remaining in period at stint end")
    secs_on          = models.IntegerField(default=0, help_text="Duration in seconds")
    pts_scored       = models.IntegerField(default=0, help_text="Team pts scored while on court")
    pts_allowed      = models.IntegerField(default=0, help_text="Opp pts scored while on court")
    plus_minus       = models.IntegerField(default=0)

    # ── Team box events while on court ────────────────────────────────────────
    team_fgm  = models.SmallIntegerField(default=0)
    team_fga  = models.SmallIntegerField(default=0)
    team_fg3m = models.SmallIntegerField(default=0)
    team_fta  = models.SmallIntegerField(default=0)
    team_tov  = models.SmallIntegerField(default=0)
    team_oreb = models.SmallIntegerField(default=0)
    team_dreb = models.SmallIntegerField(default=0)

    # ── Opponent box events while on court ────────────────────────────────────
    opp_fgm  = models.SmallIntegerField(default=0)
    opp_fga  = models.SmallIntegerField(default=0)
    opp_fg3m = models.SmallIntegerField(default=0)
    opp_fta  = models.SmallIntegerField(default=0)
    opp_tov  = models.SmallIntegerField(default=0)
    opp_oreb = models.SmallIntegerField(default=0)
    opp_dreb = models.SmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["player", "game", "stint_index"],
                name="unique_nba_player_game_stint",
            )
        ]
        indexes = [
            models.Index(fields=["game", "stint_index"]),  # RAPM design matrix construction
            models.Index(fields=["player", "game"]),        # per-player season lookup
            models.Index(fields=["game", "team"]),          # home/away split per stint
        ]

    def __str__(self):
        return f"{self.player.name} stint {self.stint_index} in {self.game.game_id}"


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

    # ── Standings / playoff results (filled by nba_sync_playoff_results) ─────
    conference_seed = models.IntegerField(
        null=True, blank=True,
        help_text="Regular-season conference rank (1-15) from compute_standings()",
    )

    PLAYOFF_FINISH_CHOICES = [
        ('Champion', 'Champion'),
        ('Runner-Up', 'Runner-Up'),
        ('Conf Finals', 'Conference Finals'),
        ('Conf Semis', 'Conference Semifinals'),
        ('Round 1', 'First Round'),
    ]
    playoff_finish = models.CharField(
        max_length=20, null=True, blank=True,
        choices=PLAYOFF_FINISH_CHOICES,
        help_text="Playoff finish (null if missed playoffs)",
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

    # ── Baseline RAPM (nba_compute_baseline_rapm) ────────────────────────────
    baseline_obpr = models.FloatField(null=True, blank=True, help_text="Baseline RAPM offensive BPR")
    baseline_dbpr = models.FloatField(null=True, blank=True, help_text="Baseline RAPM defensive BPR")
    off_poss = models.FloatField(null=True, blank=True, help_text="Total offensive possessions (from PBP stints)")
    def_poss = models.FloatField(null=True, blank=True, help_text="Total defensive possessions (from PBP stints)")

    # ── Box BPR (nba_compute_box_bpr) ────────────────────────────────────────
    box_obpr = models.FloatField(null=True, blank=True, help_text="Box-score offensive BPR")
    box_dbpr = models.FloatField(null=True, blank=True, help_text="Box-score defensive BPR")
    box_bpr = models.FloatField(null=True, blank=True, help_text="Box-score total BPR")
    nba_archetype = models.CharField(
        max_length=32, null=True, blank=True, help_text="Role archetype (creator/scorer/stretch/three_and_d/interior/connector)"
    )
    bpr_last_updated = models.DateTimeField(null=True, blank=True)

    # ── Final BPR (nba_compute_final_bpr) — prior-informed RAPM ─────────────
    # Box-score prior regularized toward 3-year lineup RAPM. This is the
    # displayed player rating — use instead of box_bpr or baseline_obpr.
    obpr = models.FloatField(null=True, blank=True, help_text="Final offensive BPR (prior-informed RAPM)")
    dbpr = models.FloatField(null=True, blank=True, help_text="Final defensive BPR (prior-informed RAPM)")
    bpr  = models.FloatField(null=True, blank=True, help_text="Final total BPR (obpr + dbpr)")

    # Wins above replacement — derived from BPR at write time, never fed back into model
    # Formula: (bpr + 2.0) × (mpg / 48) × (gp / 56)  — replacement level = BPR -2.0
    wins_added = models.FloatField(null=True, blank=True, help_text="Wins above replacement player")

    # ── Projection Value (docs/bpr_audit/09) ──────────────────────────────────
    # Forward-looking TEAM-FORECAST input: alpha*z(BPR) + (1-alpha)*z(BPM).
    # This is NOT BPR and must never be displayed as BPR — player evaluation
    # surfaces show bpr/obpr/dbpr; team outlooks consume projection_value.
    projection_value = models.FloatField(
        null=True, blank=True,
        help_text="Team-forecast player input (z-scored blend; see docs/bpr_audit/09)")
    projection_value_version = models.CharField(max_length=10, null=True, blank=True)
    projection_value_source = models.CharField(
        max_length=20, null=True, blank=True,
        help_text="bpr+bpm | bpr_only (no BPM match)")
    projection_alpha = models.FloatField(
        null=True, blank=True, help_text="Blend weight on z(BPR)")

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
    prediction_sigma = models.FloatField(
        null=True, blank=True,
        help_text="Std dev of OLS residuals (actual margin − predicted) in raw game points. "
                  "Used as sigma for win-probability CDF in the matchup model.",
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

    # Raw OLS coefficients from the four-factor → adj_net regression.
    # Units: adj_net pts/100 poss per 1 percentage-point of factor margin.
    # Used by the matchup engine for points_breakdown and top_drivers.
    ffi_raw_intercept = models.FloatField(
        null=True, blank=True,
        help_text="OLS intercept from four-factors → adj_net regression",
    )
    ffi_raw_coef_efg = models.FloatField(
        null=True, blank=True,
        help_text="adj_net pts/100 poss per 1pp of eFG margin",
    )
    ffi_raw_coef_tov = models.FloatField(
        null=True, blank=True,
        help_text="adj_net pts/100 poss per 1pp of TOV edge",
    )
    ffi_raw_coef_oreb = models.FloatField(
        null=True, blank=True,
        help_text="adj_net pts/100 poss per 1pp of OREB edge",
    )
    ffi_raw_coef_fta = models.FloatField(
        null=True, blank=True,
        help_text="adj_net pts/100 poss per 1pp of FTA margin",
    )

    class Meta:
        ordering = ["-season__year"]

    def __str__(self):
        return f"NBAModelCalibration {self.season.display_name} (computed {self.computed_at:%Y-%m-%d})"


class NBABPRModelArtifact(models.Model):
    """
    Fitted Box BPR Ridge pipelines and diagnostics per season.

    Persisted so nba_compute_box_bpr can load a prior-season model for
    prediction on incremental runs, rather than retraining from scratch.
    Use --retrain flag or change target_type (mpir → rapm) to force retrain.

    Written by: python manage.py nba_compute_box_bpr --season YYYY
    """

    season       = models.OneToOneField(NBASeason, on_delete=models.CASCADE, related_name="bpr_artifact")
    model_version = models.CharField(max_length=32, default="1.0")
    target_type  = models.CharField(
        max_length=32, default="mpir",
        help_text="Training target: 'mpir' (Stage 1 proxy) or 'rapm' (Stage 2+)",
    )

    off_pipeline = models.BinaryField(help_text="Pickled sklearn Pipeline (StandardScaler + RidgeCV) for offense")
    def_pipeline = models.BinaryField(help_text="Pickled sklearn Pipeline for defense")

    off_cv_alpha = models.FloatField(null=True, blank=True)
    def_cv_alpha = models.FloatField(null=True, blank=True)
    off_r2       = models.FloatField(null=True, blank=True)
    def_r2       = models.FloatField(null=True, blank=True)
    n_train_off  = models.IntegerField(default=0)
    n_train_def  = models.IntegerField(default=0)

    off_features = models.JSONField(default=list)
    def_features = models.JSONField(default=list)

    prior_sd_off = models.FloatField(null=True, blank=True, help_text="sqrt(1 - R²) × σ_target for offense")
    prior_sd_def = models.FloatField(null=True, blank=True)

    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-season__year"]

    def __str__(self):
        return f"NBABPRModelArtifact {self.season.display_name} [{self.target_type}]"


class NBAPlayerAvailability(models.Model):
    """
    Game-day availability report for an NBA player.

    Written by: python manage.py nba_sync_injury_report --date YYYY-MM-DD
    Used by:    NBAMatchupView to compute real-time injury adjustments.
    Never stored to NBATeamSeasonRatings — matchup-projection only.
    """

    STATUS_AVAILABLE       = "available"
    STATUS_PROBABLE        = "probable"
    STATUS_DAY_TO_DAY      = "day_to_day"
    STATUS_QUESTIONABLE    = "questionable"
    STATUS_GAME_TIME       = "game_time_decision"
    STATUS_DOUBTFUL        = "doubtful"
    STATUS_OUT             = "out"
    STATUS_OUT_FOR_SEASON  = "out_for_season"

    STATUS_CHOICES = [
        (STATUS_AVAILABLE,      "Available"),
        (STATUS_PROBABLE,       "Probable"),
        (STATUS_DAY_TO_DAY,     "Day-to-Day"),
        (STATUS_QUESTIONABLE,   "Questionable"),
        (STATUS_GAME_TIME,      "Game-Time Decision"),
        (STATUS_DOUBTFUL,       "Doubtful"),
        (STATUS_OUT,            "Out"),
        (STATUS_OUT_FOR_SEASON, "Out for Season"),
    ]

    # Fraction of player value to subtract; 0.0 = full availability, 1.0 = full absence
    STATUS_WEIGHTS = {
        STATUS_AVAILABLE:      0.00,
        STATUS_PROBABLE:       0.15,
        STATUS_DAY_TO_DAY:     0.35,
        STATUS_QUESTIONABLE:   0.50,
        STATUS_GAME_TIME:      0.60,
        STATUS_DOUBTFUL:       0.80,
        STATUS_OUT:            1.00,
        STATUS_OUT_FOR_SEASON: 1.00,
    }

    player         = models.ForeignKey(NBAPlayer,  on_delete=models.CASCADE, related_name="availability_reports")
    team           = models.ForeignKey(NBATeam,    on_delete=models.CASCADE, related_name="injury_reports")
    season         = models.ForeignKey(NBASeason,  on_delete=models.CASCADE, related_name="injury_reports")
    game_date      = models.DateField(db_index=True, help_text="Date of the game this report applies to")
    status         = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_AVAILABLE, db_index=True)
    injury_reason  = models.CharField(max_length=200, blank=True, default="")
    notes          = models.TextField(blank=True, default="")
    source         = models.CharField(max_length=32, default="espn", help_text="Data source slug (espn, nba_official, manual)")
    report_timestamp = models.DateTimeField(null=True, blank=True, help_text="When the source reported this status")
    # Optional override: expected minutes as fraction of normal (1.0 = full, 0.5 = limited)
    expected_minutes_pct = models.FloatField(null=True, blank=True, help_text="Override minute share (null = use full mpg)")
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["game_date", "team", "player"]
        unique_together = [("player", "game_date", "source")]
        indexes = [
            models.Index(fields=["team", "game_date"]),
            models.Index(fields=["game_date", "status"]),
        ]

    def __str__(self):
        return f"{self.player.name} – {self.get_status_display()} ({self.game_date})"

    @property
    def weight(self) -> float:
        return self.STATUS_WEIGHTS.get(self.status, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Season Outlook — editorial + projection layer
# ─────────────────────────────────────────────────────────────────────────────


class TeamSeasonOutlook(models.Model):
    """
    One row per team. Holds 2025-26 final results (denormalized from
    NBATeamSeasonRatings for read simplicity) plus editorial / projection
    fields populated via Django admin.

    Four-factor fields stored as raw percentages (e.g. 56.1 for 56.1%),
    consistent with the seed data format.
    """

    OUTLOOK_TIER_CHOICES = [
        ("title_contender", "Title Contender"),
        ("playoff_contender", "Playoff Contender"),
        ("bubble", "Bubble Team"),
        ("lottery", "Lottery Team"),
        ("rebuilding", "Rebuilding"),
    ]

    # ── Identity ──────────────────────────────────────────────────────────────
    team_name = models.CharField(max_length=100)
    team_abbr = models.CharField(max_length=5)
    team_slug = models.SlugField(unique=True, db_index=True)
    conference = models.CharField(max_length=10, choices=CONFERENCE_CHOICES)
    primary_color = models.CharField(max_length=7, default="#000000")
    secondary_color = models.CharField(max_length=7, default="#FFFFFF")

    # ── 2025-26 season results ────────────────────────────────────────────────
    wins = models.IntegerField(null=True, blank=True)
    losses = models.IntegerField(null=True, blank=True)
    adj_offensive_rating = models.FloatField(null=True, blank=True)
    adj_defensive_rating = models.FloatField(null=True, blank=True)
    adj_net_rating = models.FloatField(null=True, blank=True)
    ffi = models.FloatField(null=True, blank=True)

    # ── Four factors (raw percentages, e.g. 56.1 for 56.1%) ─────────────────
    efg_pct = models.FloatField(null=True, blank=True)
    opp_efg_pct = models.FloatField(null=True, blank=True)
    tov_pct = models.FloatField(null=True, blank=True)
    opp_tov_pct = models.FloatField(null=True, blank=True)
    oreb_pct = models.FloatField(null=True, blank=True)
    opp_oreb_pct = models.FloatField(null=True, blank=True)
    fta_rate = models.FloatField(null=True, blank=True)
    opp_fta_rate = models.FloatField(null=True, blank=True)
    pace = models.FloatField(null=True, blank=True)

    # ── 2026-27 projections (populated after offseason settles) ───────────────
    projected_wins = models.IntegerField(null=True, blank=True)
    projected_losses = models.IntegerField(null=True, blank=True)
    projected_adj_net = models.FloatField(null=True, blank=True)
    projected_adj_o = models.FloatField(null=True, blank=True)
    projected_adj_d = models.FloatField(null=True, blank=True)
    projected_floor_wins = models.IntegerField(null=True, blank=True)
    projected_ceil_wins = models.IntegerField(null=True, blank=True)
    outlook_tier = models.CharField(
        max_length=20, choices=OUTLOOK_TIER_CHOICES, null=True, blank=True
    )

    # ── Computed roster construction metrics ──────────────────────────────────
    continuity_score = models.FloatField(
        null=True, blank=True, help_text="0-100: returner minutes fraction × 100"
    )
    weighted_effective_age = models.FloatField(
        null=True, blank=True, help_text="BPR-weighted average age of projected rotation"
    )
    top2_bpr_concentration = models.FloatField(
        null=True, blank=True, help_text="0-1: fraction of projected wins added from top-2 players"
    )

    # ── Cap data (computed from NBAPlayerContract or manually overridden) ─────
    CAP_STATUS_CHOICES = [
        ("under_cap", "Under Cap"),
        ("over_cap", "Over Cap"),
        ("taxpayer", "Luxury Taxpayer"),
        ("first_apron", "First Apron"),
        ("second_apron", "Second Apron"),
    ]
    cap_total_salary = models.BigIntegerField(
        null=True, blank=True, help_text="Total guaranteed salary commitment in dollars"
    )
    cap_status_tier = models.CharField(
        max_length=20, choices=CAP_STATUS_CHOICES, null=True, blank=True
    )

    # ── Hand-authored editorial ───────────────────────────────────────────────
    season_headline = models.CharField(max_length=200, blank=True)
    macfax_take = models.TextField(blank=True)
    development_spotlight_player = models.CharField(max_length=100, blank=True)
    development_spotlight_text = models.TextField(blank=True)
    season_defining_variable = models.TextField(blank=True)

    updated_at = models.DateTimeField(auto_now=True)
    pipeline_version = models.CharField(
        max_length=20, default="", blank=True,
        help_text="PIPELINE_VERSION of compute_nba_team_outlooks that last wrote projections",
    )

    class Meta:
        ordering = ["-adj_net_rating"]

    def __str__(self):
        return self.team_name

    @property
    def league_rank(self) -> int:
        return (
            TeamSeasonOutlook.objects.filter(
                adj_net_rating__gt=self.adj_net_rating
            ).count()
            + 1
        )


class TeamOutseasonMove(models.Model):
    """One offseason roster transaction for a team."""

    MOVE_TYPE_CHOICES = [
        ("signed", "Free Agent Signed"),
        ("lost", "Free Agent Lost"),
        ("drafted", "Drafted"),
        ("traded_in", "Acquired via Trade"),
        ("traded_out", "Traded Away"),
        ("extended", "Extension Signed"),
        ("waived", "Waived"),
    ]
    IMPACT_CHOICES = [
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    ]

    team = models.ForeignKey(
        TeamSeasonOutlook, on_delete=models.CASCADE, related_name="offseason_moves"
    )
    move_type = models.CharField(max_length=20, choices=MOVE_TYPE_CHOICES)
    player_name = models.CharField(max_length=100)
    detail = models.CharField(max_length=200, blank=True)
    impact_rating = models.CharField(max_length=10, choices=IMPACT_CHOICES, default="medium")
    round_number = models.IntegerField(null=True, blank=True)
    overall_pick = models.IntegerField(null=True, blank=True)
    mps_score = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-impact_rating", "move_type"]

    def __str__(self):
        return f"{self.get_move_type_display()}: {self.player_name} ({self.team.team_abbr})"


class ProjectedStarter(models.Model):
    """One projected starter slot for a team's 2026-27 lineup."""

    team = models.ForeignKey(
        TeamSeasonOutlook, on_delete=models.CASCADE, related_name="projected_starters"
    )
    position = models.CharField(max_length=5)
    player_name = models.CharField(max_length=100)
    position_order = models.IntegerField(default=0, help_text="1-5 display order")
    role_note = models.CharField(max_length=200, blank=True)
    bpr_rating = models.FloatField(null=True, blank=True)
    key_question = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["position_order"]

    def __str__(self):
        return f"{self.team.team_abbr} {self.position}: {self.player_name}"


# ─────────────────────────────────────────────────────────────────────────────
# Computed projected roster — one slot per player per team for next season
# ─────────────────────────────────────────────────────────────────────────────


class NBAProjectedRosterSlot(models.Model):
    """
    Per-player next-season projection computed by compute_nba_team_outlooks.
    One row per (team, season, player_name). season is the TARGET season (e.g. 2026-27).
    prior_stats links to the source season stats used to derive projections.
    """

    ACQUISITION_CHOICES = [
        ("returner", "Returner"),
        ("signed", "Free Agent Signed"),
        ("traded_in", "Acquired via Trade"),
        ("drafted", "Drafted"),
        ("extended", "Extension"),
    ]
    CONFIDENCE_CHOICES = [
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    ]

    team = models.ForeignKey(
        TeamSeasonOutlook, on_delete=models.CASCADE, related_name="projected_roster_slots"
    )
    season = models.ForeignKey(NBASeason, on_delete=models.CASCADE)
    player = models.ForeignKey(
        NBAPlayer, on_delete=models.SET_NULL, null=True, blank=True
    )
    prior_stats = models.ForeignKey(
        NBAPlayerSeasonStats, on_delete=models.SET_NULL, null=True, blank=True
    )
    player_name = models.CharField(max_length=150)
    position = models.CharField(max_length=10, blank=True)
    archetype = models.CharField(max_length=32, null=True, blank=True)
    age = models.IntegerField(null=True, blank=True)
    acquisition_type = models.CharField(max_length=20, choices=ACQUISITION_CHOICES, default="returner")
    projected_obpr = models.FloatField(null=True, blank=True)
    projected_dbpr = models.FloatField(null=True, blank=True)
    projected_bpr = models.FloatField(null=True, blank=True)
    projected_minutes_share = models.FloatField(
        null=True, blank=True,
        help_text=(
            "Share of the 5.0-slot minutes pool (0–1.8); 1.0 = 20% of team "
            "minutes = ~9.6 MPG-equivalent at 48min"
        ),
    )
    projected_wins_added = models.FloatField(null=True, blank=True)
    confidence = models.CharField(max_length=10, choices=CONFIDENCE_CHOICES, default="medium")
    pipeline_version = models.CharField(
        max_length=20, default="", blank=True,
        help_text="PIPELINE_VERSION of compute_nba_team_outlooks that wrote this row",
    )
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-projected_minutes_share"]
        unique_together = [("team", "season", "player_name")]

    def __str__(self):
        return f"{self.team.team_abbr} {self.player_name} ({self.season})"


# ─────────────────────────────────────────────────────────────────────────────
# Player contracts — annual salary data for cap computation
# ─────────────────────────────────────────────────────────────────────────────


class NBAPlayerContract(models.Model):
    """
    One player's salary for a given season. Imported via import_nba_contracts command.
    Used by compute_nba_team_cap to populate TeamSeasonOutlook.cap_total_salary.
    """

    CONTRACT_TYPE_CHOICES = [
        ("max", "Max Contract"),
        ("mid", "Mid-Level Exception"),
        ("mini", "Mini Mid-Level"),
        ("veteran", "Veteran Exception"),
        ("two_way", "Two-Way Contract"),
        ("rookie", "Rookie Scale"),
        ("vet_min", "Veteran Minimum"),
        ("other", "Other"),
    ]

    player = models.ForeignKey(NBAPlayer, on_delete=models.CASCADE, related_name="contracts")
    team = models.ForeignKey(NBATeam, on_delete=models.CASCADE, related_name="contracts")
    season = models.ForeignKey(NBASeason, on_delete=models.CASCADE, related_name="contracts")
    salary = models.BigIntegerField(help_text="Annual salary in dollars")
    years_remaining = models.IntegerField(
        default=0, help_text="Contract years remaining after this season"
    )
    contract_type = models.CharField(max_length=20, choices=CONTRACT_TYPE_CHOICES, default="other")
    player_option = models.BooleanField(default=False)
    team_option = models.BooleanField(default=False)
    is_guaranteed = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("player", "team", "season")]
        ordering = ["-salary"]

    def __str__(self):
        return f"{self.player.name} ({self.team.abbreviation}) ${self.salary:,}"
