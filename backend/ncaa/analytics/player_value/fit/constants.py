"""
Roster Fit Model constants — Phase 3.

All tunable weights, thresholds, and reference values for the fit engine.

Design principles
─────────────────
1. Every raw feature is z-scored against D1 seasonal reference values, then
   mapped to 0–100 with 50 = D1 average.  Winsorizing at ±2.5σ prevents
   single-player outliers from hijacking team scores.

2. On-court adjusted metrics (on_court_adj_o / d / em) are secondary modifiers
   only, dampened by a sample-reliability factor:
       reliability = poss / (poss + ON_COURT_SHRINKAGE_K)
   At 500 poss ≈ 60% reliability; at 200 poss ≈ 40%.

3. Structural penalties are tracked in a registry.  Each identifiable roster
   flaw is assigned to exactly one primary subcomponent.  An aggregate cap
   (MAX_STRUCTURAL_PENALTY_OFF / DEF) prevents double-stacking.

4. Reference values (means + SDs) are calibrated from the 2026 season (3,629
   qualifying player-seasons, gp ≥ 10, off_poss ≥ 200) and used as fallbacks.
   The service layer will recompute season-relative references when enough
   data is present (≥ SEASON_REF_MIN_PLAYERS rows).

Score scale
───────────
   0–100, higher = better, 50 = D1 average rotation player
   Subcomponent scores and overall scores are on the same scale.
   offensive_fit_score and defensive_fit_score are weighted averages of their
   respective subcomponents after structural penalty caps are applied.
   overall_fit_score = OFF_WEIGHT × off + DEF_WEIGHT × def
"""

# ── Score scale ───────────────────────────────────────────────────────────────
SCORE_MIN  = 0.0
SCORE_MAX  = 100.0
SCORE_MID  = 50.0   # D1 average reference point

# ── z-score → 0-100 mapping ───────────────────────────────────────────────────
# Maps a z-score to the 0-100 scale.
#   score = 50 + Z_TO_SCORE_SCALE × z_score
# A player at +2σ gets score 50 + 2×15 = 80.  At −2σ: 20.
# This matches the intuition of a percentile map without requiring per-season
# empirical percentiles.
Z_TO_SCORE_SCALE = 15.0   # pts per 1σ on the 0-100 scale

# Winsorization: clamp z-scores to ±WINSOR_SIGMA before mapping.
# Prevents one truly extreme player (e.g. Zach Edey's rebound rate) from
# pulling team averages outside [0, 100] range.
WINSOR_SIGMA = 3.0

# ── Minutes weighting ─────────────────────────────────────────────────────────
# Players with minutes_share_p2 below this floor get included in aggregate
# computation but with very low weight.  Structural penalty checks only use
# players with minutes_share_p2 >= TOP_ROTATION_THRESHOLD.
TOP_ROTATION_THRESHOLD = 0.075   # ≈ 3.0 mpg — meaningful rotation minutes
DEEP_BENCH_THRESHOLD   = 0.04    # < 1.6 mpg — effectively DNP territory

# ── Minimum sample ────────────────────────────────────────────────────────────
# season-relative reference recomputation requires at least this many
# qualifying player-seasons in the DB.  Below this we fall back to the
# hard-coded D1 reference constants below.
SEASON_REF_MIN_PLAYERS = 500

# ── On-court signal dampening ─────────────────────────────────────────────────
# on_court_adj_o/d/em are used as secondary nudges only, scaled by:
#   reliability = poss / (poss + K)
# At K = 300: 300 poss → 50% weight, 600 poss → 67%, 1200 poss → 80%.
ON_COURT_SHRINKAGE_K       = 300.0   # possessions for 50% reliability
ON_COURT_MAX_MODIFIER      = 6.0     # max 0-100-scale pts the on-court nudge can add/subtract

# ── D1 reference values (2026 calibration, gp≥10, off_poss≥200) ──────────────
# Format: (mean, std_dev) — what an "average" D1 rotation player looks like.
# These are fallbacks used when season-relative references are unavailable.

# Box-score rates
REF_FG3A_PG   = (2.44, 2.00)   # 3-point attempts per game
REF_AST_PG    = (1.46, 1.21)   # assists per game
REF_TOV_PG    = (1.16, 0.66)   # turnovers per game
REF_BLK_PG    = (0.35, 0.40)   # blocks per game
REF_STL_PG    = (0.70, 0.44)   # steals per game
REF_PF_PG     = (1.84, 0.65)   # personal fouls per game
REF_OREB_PG   = (0.96, 0.71)   # offensive rebounds per game
REF_DREB_PG   = (2.39, 1.27)   # defensive rebounds per game
REF_FTA_PG    = (2.16, 1.55)   # free throw attempts per game
REF_FG_PCT    = (0.46, 0.07)   # field goal percentage (estimated)
REF_EFG_PCT   = (0.50, 0.06)   # effective FG%
REF_TS_PCT    = (0.53, 0.07)   # true shooting %
REF_AST_TO    = (1.26, 0.80)   # assist-to-turnover ratio

# RAPM / BPR projections
REF_PROJ_OBPR = (0.20, 1.80)   # projected_obpr; positive because
REF_PROJ_DBPR = (0.10, 1.10)   # projected_dbpr  Macfax projects next year

# Four-factor impact fields (RAPM-derived, mean near 0, positive-good)
#   avg values near 0 because these are marginal impacts vs D1 average
REF_OFF_EFG_IMPACT = (0.24, 1.24)
REF_DEF_EFG_IMPACT = (0.19, 1.11)
REF_OFF_TOV_IMPACT = (0.16, 0.82)
REF_DEF_TOV_IMPACT = (0.06, 0.77)
REF_OFF_ORB_IMPACT = (0.12, 1.02)
REF_DEF_REB_IMPACT = (0.14, 0.85)
REF_OFF_FTR_IMPACT = (0.10, 1.87)
REF_DEF_FTR_IMPACT = (0.13, 1.68)

# On-court adjusted efficiencies (pts/100 poss, team level)
REF_ON_COURT_ADJ_O = (111.8, 9.0)   # rough spread across players
REF_ON_COURT_ADJ_D = (110.8, 8.5)

# ── Archetype thresholds (box-score-based, unscaled) ─────────────────────────
# Used to tag each player with internal role labels.
# These drive structural (composition) penalty checks, not subcomponent scores.

# Offense archetypes
SPACER_FG3A_THRESHOLD        = 3.5    # ≥ 3.5 three-point attempts/game → spacer
SHOOTER_EFG_THRESHOLD        = 0.53   # efg_pct ≥ 0.53 → shooter above avg
PRIMARY_CREATOR_AST_THRESHOLD = 4.0   # ast/game ≥ 4.0 → primary creator
SECONDARY_CREATOR_AST_THRESHOLD = 2.5 # ast/game ≥ 2.5 → secondary creator
BALL_STOPPER_TOV_THRESHOLD   = 2.8    # tov/game threshold part of ball-stopper
BALL_STOPPER_AST_MAX         = 1.0    # ast/game ≤ 1.0 (high-tov, low creation)
OFF_REBOUNDER_THRESHOLD      = 1.5    # oreb/game ≥ 1.5 → offensive rebounder
NON_SHOOTING_BIG_FG3A_MAX    = 1.5    # big with < 1.5 fg3a → non-shooting big
PRESSURE_DRIVER_FTA_THRESHOLD = 3.5   # fta/game ≥ 3.5 → pressure driver

# Defense archetypes
RIM_PROTECTOR_BLK_THRESHOLD  = 0.70   # blk/game ≥ 0.70 → rim protector
DISRUPTOR_STL_THRESHOLD      = 1.00   # stl/game ≥ 1.00 → disruptor
FOUL_PRONE_THRESHOLD         = 3.20   # pf/game ≥ 3.20 → foul-prone
WEAK_DEFENDER_DBPR_MAX       = -1.0   # projected_dbpr ≤ -1.0 → weak defender
SWITCHABLE_WING_ROLE         = "Wing" # wings with stl ≥ DISRUPTOR_STL_THRESHOLD → switchable

# ── Structural penalty thresholds ────────────────────────────────────────────
# One penalty per identifiable structural flaw; each assigned to one primary
# subcomponent to prevent double-counting.
# Cap separately for offense and defense.

MAX_STRUCTURAL_PENALTY_OFF  = 25.0   # max total pts deducted from off subcomponents
MAX_STRUCTURAL_PENALTY_DEF  = 25.0   # max total pts deducted from def subcomponents

# Offensive structural checks (primary subcomponent owner in brackets)
OFF_NO_PRIMARY_CREATOR_PENALTY    = 15.0  # [creation_fit] no player with ast≥4.0 in top-8
OFF_NO_SECONDARY_CREATOR_PENALTY  =  8.0  # [creation_fit] no player with ast≥2.5 in top-8
OFF_FEW_SPACERS_PENALTY           = 10.0  # [shooting_fit] fewer than 2 spacers in top-8
OFF_SPACER_CONCENTRATION_BONUS    =  5.0  # [shooting_fit] 3+ spacers in top-9 (positive)
OFF_MANY_NONSHOOTING_BIGS_PENALTY = 10.0  # [role_balance_off_fit] ≥ 2 non-shoot bigs in top-8
OFF_BALL_STOPPER_POLLUTION_PENALTY =  8.0  # [ball_security_fit] ball-stopper in top-5 slots
OFF_ROLE_OVERLAP_PENALTY          =  6.0  # [role_balance_off_fit] 0 spacers AND 0 creators

# Defensive structural checks (primary subcomponent owner in brackets)
DEF_NO_RIM_PROTECTOR_PENALTY      = 12.0  # [rim_protection_fit] no player blk≥0.70 in top-8
DEF_WEAK_TOP5_PENALTY             = 10.0  # [role_balance_def_fit] ≥ 3 weak defenders in top-5
DEF_POOR_REBOUND_BALANCE_PENALTY  =  8.0  # [def_rebounding_fit] team dreb < threshold
DEF_FOUL_STACK_PENALTY            =  8.0  # [foul_discipline_fit] ≥ 2 foul-prone in top-5
DEF_FEW_BIGS_PENALTY              = 10.0  # [size_coverage_fit] weighted big-fraction < 0.07

# Threshold for POOR_REBOUND_BALANCE check
DEF_WEAK_DREB_THRESHOLD           = 1.8   # minutes-weighted avg dreb < this → poor

# ── Subcomponent weights (offense) ───────────────────────────────────────────
# Must sum to 1.0.
# creation_fit has highest weight: this is the single biggest driver of
# offensive floor/ceiling.
OFF_WEIGHTS = {
    "creation_fit":          0.25,
    "shooting_fit":          0.20,
    "ball_security_fit":     0.15,
    "finishing_fit":         0.15,
    "pressure_fit":          0.10,
    "off_rebounding_fit":    0.08,
    "role_balance_off_fit":  0.07,
}

# ── Subcomponent weights (defense) ───────────────────────────────────────────
# Must sum to 1.0.
# rim_protection and def_rebounding together form the backbone of any
# serious defense; perimeter_defense covers guard/wing stopper quality.
DEF_WEIGHTS = {
    "rim_protection_fit":      0.18,
    "def_rebounding_fit":      0.18,
    "perimeter_defense_fit":   0.15,
    "disruption_fit":          0.12,
    "size_coverage_fit":       0.12,
    "foul_discipline_fit":     0.10,
    "mobility_fit":            0.08,
    "role_balance_def_fit":    0.07,
}

# ── Overall fit weights ───────────────────────────────────────────────────────
OFF_WEIGHT = 0.50   # can be adjusted if offense/ defense have unequal signal quality
DEF_WEIGHT = 0.50

# ── Diagnostic labels ─────────────────────────────────────────────────────────
# How many strengths/weaknesses to surface per side in diagnostics output.
N_DIAGNOSTIC_ITEMS = 3

# ── Recruit-class archetype tags (Sprint 4) ──────────────────────────────────
# Tag name string constants emitted by tag_archetypes() when PlayerFitInput
# has national_rank, recruit_stars, or is_juco_transfer set.
# All rank thresholds are Phase 4 provisional.

RECRUIT_ELITE_RANK_THRESHOLD  = 30    # national_rank <= 30  → TAG_RECRUIT_ELITE
RECRUIT_HIGH_RANK_THRESHOLD   = 100   # national_rank 31–100 → TAG_RECRUIT_HIGH
RECRUIT_MID_RANK_THRESHOLD    = 200   # national_rank 101–200 → TAG_RECRUIT_MID
# national_rank > 200 → TAG_RECRUIT_LOW (when rank is explicitly set)

RECRUIT_STARS_HIGH_THRESHOLD  = 4    # stars >= 4 → TAG_STARS_HIGH (rank takes priority)
RECRUIT_STARS_MID_THRESHOLD   = 3    # stars == 3 → TAG_STARS_MID

TAG_RECRUIT_ELITE   = "recruit_elite"   # Top-30 national recruit
TAG_RECRUIT_HIGH    = "recruit_high"    # Top-100
TAG_RECRUIT_MID     = "recruit_mid"     # Top-200
TAG_RECRUIT_LOW     = "recruit_low"     # Ranked but outside top-200
TAG_RECRUIT_UNRATED = "recruit_unrated" # Newcomer with no rank/stars (set externally)
TAG_STARS_HIGH      = "stars_high"      # 4–5 stars, no rank
TAG_STARS_MID       = "stars_mid"       # 3 stars, no rank
TAG_JUCO            = "juco_transfer"   # JUCO transfer (from ManualPlayerSpec.is_juco)



# ── Role-bucket-relative thresholds (Sprint 4 — BT-10 validated, 2026-05-04) ──────
# These REPLACE the single-value thresholds above when USE_BUCKET_THRESHOLDS=True.
# Legacy single-value thresholds are retained for backward compatibility.
# Run `python manage.py run_bt10` to regenerate these values from fresh data.

USE_BUCKET_THRESHOLDS: bool = True

# Rim protector — Big p50 blk/game; Guards/Wings keep legacy 0.70
RIM_PROTECTOR_BLK_G: float = 0.7  # Guards: keep legacy (rim protection rarely applies)  [n=22266, high]
RIM_PROTECTOR_BLK_WING: float = 0.7  # Wings: keep legacy  [n=11815, high]
RIM_PROTECTOR_BLK_BIG: float = 0.9  # Bigs: p50 blk/game  [n=4414, high]

# Disruptor — per-bucket p70 stl/game
DISRUPTOR_STL_G: float = 0.86  # Guard p70  [n=22266, high]
DISRUPTOR_STL_WING: float = 0.48  # Wing p70  [n=11815, high]
DISRUPTOR_STL_BIG: float = 1.0  # Keep league-wide for Bigs  [n=4414, high]

# Spacer — per-bucket p60 fg3a/game
SPACER_FG3A_G: float = 2.29  # G p60 fg3a/game  [n=22266, high]
SPACER_FG3A_WING: float = 1.0  # WING p60 fg3a/game  [n=11815, high]
SPACER_FG3A_BIG: float = 0.52  # BIG p60 fg3a/game  [n=4414, high]

# Weak defender — per-conf-group p5 projected_dbpr (unfiltered pool, bottom 5%)
WEAK_DEFENDER_DBPR_POWER: float = -1.11  # [n=6628, high]
WEAK_DEFENDER_DBPR_HIGH_MID: float = -1.19  # [n=4189, high]
WEAK_DEFENDER_DBPR_MID_MAJOR: float = -1.1  # [n=28640, high]
WEAK_DEFENDER_DBPR_DEFAULT: float = -1.0  # fallback when conf_group unknown

