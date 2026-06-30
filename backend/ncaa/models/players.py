"""
Player-centric models: Player, PlayerRecruitingProfile, PlayerGameStats,
PlayerSeasonStats, PlayerSeasonProjection, PlayerGameStint,
BPRModelArtifact, PlaceholderArchetype
"""

from django.db import models

from .base import Season
from .teams import Team
from .games import Game


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
    game = models.ForeignKey("core.Game", on_delete=models.CASCADE, related_name="player_stats")
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
    # Box-score rate stats (minutes-adjusted where applicable)
    usg_pct  = models.FloatField(null=True, blank=True, help_text="Usage% = (FGA + 0.44*FTA + TOV) / team_poss * (tm_mp/5/mp) * 100")
    tov_pct  = models.FloatField(null=True, blank=True, help_text="Turnover% = TOV / (FGA + 0.44*FTA + TOV) * 100")
    orb_pct  = models.FloatField(null=True, blank=True, help_text="Offensive Rebound% (minutes-adjusted)")
    drb_pct  = models.FloatField(null=True, blank=True, help_text="Defensive Rebound% (minutes-adjusted)")
    fta_rate = models.FloatField(null=True, blank=True, help_text="FTA Rate = FTA / FGA")
    fg3_rate = models.FloatField(null=True, blank=True, help_text="3PA Rate = FG3A / FGA")
    blk_pct  = models.FloatField(null=True, blank=True, help_text="Block% vs opp 2PA (minutes-adjusted)")
    stl_pct  = models.FloatField(null=True, blank=True, help_text="Steal% vs opp possessions (minutes-adjusted)")
    ast_usg  = models.FloatField(null=True, blank=True, help_text="AST/USG = assists per game / usg_pct")
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
    recruiting_prior_used = models.BooleanField(
        default=False,
        help_text="True when a PlayerRecruitingProfile was used to set the newcomer BPR prior.",
    )
    classification_reason = models.CharField(
        max_length=60,
        blank=True,
        default="",
        help_text=(
            "How recruitment_type was determined: "
            "no_prior_season | same_team_prior | grad_transfer_return | different_team_prior"
        ),
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
    fg3a_pg  = models.FloatField(null=True, blank=True,
                                 help_text="Median 3-point attempts per game")

    # Conference — actual conference code for per-conference archetypes (e.g. 'ACC', 'WCC').
    # Blank for broad conf_group-level archetypes (national/power/mid_major/high_mid).
    conference = models.CharField(
        max_length=16, blank=True, default='',
        help_text="Actual conference code (e.g. 'ACC', 'WCC') — blank for conf_group-level archetypes",
        db_index=True,
    )

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


class PlayerAvailability(models.Model):
    """
    Game-day availability report for an NCAA player.

    Written by: python manage.py ncaa_sync_injury_report --date YYYY-MM-DD
    Used by:    NCAA matchup view to compute real-time injury adjustments.
    Never stored to TeamSeasonRatings — matchup-projection only.
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

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="availability_reports")
    team   = models.ForeignKey(Team,   on_delete=models.CASCADE, related_name="injury_reports")
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="injury_reports")
    game_date = models.DateField(db_index=True, help_text="Date of the game this report applies to")
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_AVAILABLE, db_index=True)
    injury_reason = models.CharField(max_length=200, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    source = models.CharField(max_length=32, default="espn", help_text="Data source slug (espn, ncaa_official, manual)")
    report_timestamp = models.DateTimeField(null=True, blank=True, help_text="When the source reported this status")
    expected_minutes_pct = models.FloatField(null=True, blank=True, help_text="Override minute share (null = use full mpg)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["game_date", "team", "player"]
        unique_together = [("player", "game_date", "source")]
        indexes = [
            models.Index(fields=["team", "game_date"]),
            models.Index(fields=["game_date", "status"]),
        ]

    def __str__(self):
        return f"{self.player.display_name} – {self.get_status_display()} ({self.game_date})"

    @property
    def weight(self) -> float:
        return self.STATUS_WEIGHTS.get(self.status, 0.0)
