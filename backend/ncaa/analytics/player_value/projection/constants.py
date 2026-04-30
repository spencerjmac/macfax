"""
Player projection model constants (Phase 1).

All tunable parameters for the next-season player projection model.
Override these to experiment without changing the model logic.

Phase 1 design notes:
  - The talent signal is the final prior-informed BPR (obpr/dbpr) when
    available, falling back to Box BPR only when RAPM is absent.  We do
    NOT blend the two because obpr already incorporates box_obpr as a
    Bayesian prior; blending again would double-count the box signal.
  - recruitment_type includes a 'newcomer' umbrella bucket.  Distinguish-
    ing freshman vs grad-transfer requires external roster data not yet
    available in this system.  The code is structured for easy extension.
  - transfer competition adjustment reflects how the player arrived at
    their current season team (retrospective), not future destination.
  - All coefficients are Phase 1 provisional and should be backtested on
    prior seasons before being refined for Phase 2.
"""

PROJECTION_VERSION = "1.1"

# ── Talent signal selection ───────────────────────────────────────────────────
# Phase 1 uses a priority-select strategy rather than a weighted blend:
#   Primary:  obpr / dbpr  (final prior-informed RAPM; box prior already baked in)
#   Fallback: box_obpr / box_dbpr  (only when RAPM data is absent)
#
# A weighted blend of the two (e.g. 0.65 * RAPM + 0.35 * box) would
# double-count the box signal because the BPR fitting chain is:
#   baseline RAPM → Box BPR prior → final prior-informed RAPM
# Mixing the output (obpr) with its own prior input (box_obpr) inflates
# box's influence beyond its intended regularization weight.
#
# Provisional Phase 1 design.  Backtest on historical seasons before
# considering a baseline_rapm × box blend for Phase 2.

# ── Year-to-year regression to mean ──────────────────────────────────────────
# BPR is a Bayesian in-season estimate, but genuine year-to-year variance
# exists beyond measurement uncertainty (injuries, role changes, etc.).
#
# Shrinkage formula (applied to the selected talent signal):
#   λ = SHRINK_POSS / (SHRINK_POSS + observed_poss)
#   projected_bpr = (1 - λ) * talent_signal   [shrinks toward 0 = D1 avg]
#
# At SHRINK_POSS possessions observed: λ = 0.50 (50% shrinkage)
# At 2×SHRINK_POSS possessions:        λ ≈ 0.33 (33% shrinkage)
YTY_SHRINK_POSS_OFF = 500.0
YTY_SHRINK_POSS_DEF = 500.0

# ── Multi-year trend ──────────────────────────────────────────────────────────
# When prior-season RAPM is available, apply a fraction of the observed
# trend (current_bpr − prior_bpr) to capture momentum.
# College trends are noisy, so weights are small.
TREND_WEIGHT_OFF = 0.10
TREND_WEIGHT_DEF = 0.08

# ── Development / aging adjustments (pts/100 poss) ───────────────────────────
# Expected year-over-year growth or decline by player experience stage.
# n_prior_seasons = number of seasons before from_season in DB:
#   0 (newcomer)  → development boost (freshman → sophomore)
#   1             → moderate growth (sophomore → junior)
#   2             → stabilizing (no adjustment)
#   ≥ 3 (senior+) → slight expected decline
DEV_OFF_NEWCOMER    = +0.20
DEV_DEF_NEWCOMER    = +0.10
DEV_OFF_SECOND_YEAR = +0.10
DEV_DEF_SECOND_YEAR = +0.05
DEV_OFF_SENIOR      = -0.10
DEV_DEF_SENIOR      = -0.05
SENIOR_SEASON_THRESHOLD = 3   # n_prior_seasons >= this → apply senior adjustment

# ── Transfer competition-level adjustment ─────────────────────────────────────
# BPR partially adjusts for competition through the RAPM opponent structure,
# but cross-conference strength differences may not be fully captured.
#
# Adjustment:
#   adj_delta = prior_team_adj_em − current_team_adj_em
#   projected_bpr += TRANSFER_COMP_WEIGHT * adj_delta
#
# Positive adj_delta (came from stronger program) → slight upward correction
# Negative adj_delta (came from weaker program) → slight downward correction
# Weight is small because BPR already partially accounts for schedule strength.
# Updated 0.03 → 0.04 by BT-2 sweep (Sprint 2).
# Validated on 10 source→target pairs, 2141 transfers. RMSE Δ=-0.0010 (marginal).
# NOTE: sweep showed nearly flat RMSE across all weights (0.01–0.20) — adj has minimal
# predictive signal. 0.04 is the empirical winner by a small margin.
TRANSFER_COMP_WEIGHT_OFF = 0.04
TRANSFER_COMP_WEIGHT_DEF = 0.04

# ── Projection uncertainty (0 = low uncertainty, 1 = high) ───────────────────
# Base uncertainty before sample-size adjustment.
UNCERTAINTY_BASE = {
    "returner": 0.40,
    "transfer": 0.60,
    "newcomer": 0.80,
}
# Additional uncertainty for small RAPM samples.
# Starts at UNCERTAINTY_POSS_MAX_ADD (at 0 poss) and decays to 0
# as observed possessions approach UNCERTAINTY_STABLE_POSS.
UNCERTAINTY_POSS_MAX_ADD  = 0.20
UNCERTAINTY_STABLE_POSS   = 1500.0  # poss at which sample-size add → 0

# ── Baseline minutes share ────────────────────────────────────────────────────
# Phase 1 baseline only. Phase 2 replaces this with a model that
# incorporates team roster context and positional depth.
#
# For players with observed MPG from from_season: mpg / 40.
# For newcomers or players with <5 GP: type-based default.
MINUTES_SHARE_BASE_BY_TYPE = {
    "returner": 0.55,
    "transfer": 0.45,
    "newcomer": 0.25,
}
# Small BPR-based upward adjustment: better players tend to log more time.
#   projected_minutes_share += MINUTES_BPR_WEIGHT * projected_bpr
MINUTES_BPR_WEIGHT = 0.008
MINUTES_SHARE_MIN  = 0.05
MINUTES_SHARE_MAX  = 0.90

# Approximate possessions per minute (NCAA D1 average tempo).
# Used to estimate possession counts from MPG when explicit poss data is absent.
POSS_PER_MINUTE = 1.5

# ── Transfer-specific projection tuning ──────────────────────────────────────
# Transfers face a system/context change: their RAPM on-off splits were measured
# in a different team environment than the one they will play in next season.
# Box BPR captures portable individual skill more independently of team context.
#
# Returner path:  RAPM primary, box as fallback only (unchanged).
# Transfer path:  blend RAPM with box, apply higher shrinkage, dampen trend.

# Talent signal blending for transfers (when both RAPM and box BPR are available).
# RAPM gets (1 − weight); box_bpr gets weight.
# 0.35 → 65 % RAPM + 35 % box: leans on RAPM but gives meaningful portable weight.
# The double-counting concern (obpr already has box prior baked in) is mitigated
# for transfers because the box prior was fitted at their OLD school — blending it
# in explicitly gives the portable skill signal a voice in the projection for the
# NEW context without re-counting the environmental on-off component.
BOX_BLEND_WEIGHT_TRANSFER = 0.35

# YtY shrinkage: transfers face more environmental uncertainty → regress harder.
YTY_SHRINK_POSS_OFF_TRANSFER = 750.0   # vs 500 for returners
YTY_SHRINK_POSS_DEF_TRANSFER = 750.0

# Multi-year trend: prior-season trend was measured in a different system →
# dampen the contribution for transfers.
TREND_WEIGHT_OFF_TRANSFER = 0.05   # vs 0.10 for returners
TREND_WEIGHT_DEF_TRANSFER = 0.04   # vs 0.08 for returners

# ── Newcomer BPR priors from recruiting rank (Phase 1.1) ─────────────────────
# All values are Phase 1.1 PROVISIONAL — must be validated against
# BT-1 (player RMSE backtest) and BT-5 (holdout calibration) before Phase 2.
#
# USE_RECRUITING_PRIOR: master toggle. False disables entirely for A/B testing.
USE_RECRUITING_PRIOR: bool = True

# NEWCOMER_RANK_PRIORS: list in descending priority order (first match wins).
# 'max_rank' is the inclusive upper bound for national_rank (lower = better).
# Tiers:
#   top-10:   consensus blue-chip; historically ~+2 BPR production
#   top-30:   likely starter-level talent; high upside
#   top-60:   solid contributor; rotation-to-starter range
#   top-100:  fringe high-major; D1-average projection appropriate
#   top-200:  mid-major caliber; D1-average or slightly below
#   >200:     walk-on/low-priority; slight negative adjustment
NEWCOMER_RANK_PRIORS: list = [
    {"max_rank":  10, "obpr_prior": +2.2, "dbpr_prior": +0.7, "uncertainty_override": 0.65},
    {"max_rank":  30, "obpr_prior": +1.4, "dbpr_prior": +0.5, "uncertainty_override": 0.68},
    {"max_rank":  60, "obpr_prior": +0.8, "dbpr_prior": +0.3, "uncertainty_override": 0.73},
    {"max_rank": 100, "obpr_prior": +0.4, "dbpr_prior": +0.1, "uncertainty_override": 0.76},
    {"max_rank": 200, "obpr_prior": +0.0, "dbpr_prior": +0.0, "uncertainty_override": 0.80},
    # no max_rank → catch-all for rank > 200
    {"obpr_prior": -0.2, "dbpr_prior": -0.1, "uncertainty_override": 0.82},
]

# NEWCOMER_STARS_PRIORS: fallback when national_rank is None but stars exist.
# Keyed by integer star rating (1–5). Phase 1.1 provisional.
NEWCOMER_STARS_PRIORS: dict = {
    5: {"obpr_prior": +1.0, "dbpr_prior": +0.4, "uncertainty_override": 0.70},
    4: {"obpr_prior": +0.3, "dbpr_prior": +0.1, "uncertainty_override": 0.77},
    3: {"obpr_prior": -0.1, "dbpr_prior":  0.0, "uncertainty_override": 0.81},
    2: {"obpr_prior": -0.2, "dbpr_prior": -0.1, "uncertainty_override": 0.82},
    1: {"obpr_prior": -0.2, "dbpr_prior": -0.1, "uncertainty_override": 0.82},
}

# ── Position-stratified development adjustments (Phase 1.2 — BT-3 validated) ──
# Source years: [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025], N observations: 20136
# Low-confidence cells (n < 20) retain the current flat constant value.
# Set USE_STRATIFIED_DEV_ADJUSTMENTS = False to revert to flat constants.

USE_STRATIFIED_DEV_ADJUSTMENTS: bool = True

# Newcomer development adjustments (offense)
DEV_OFF_NEWCOMER_G: float = 0.6  # n=4045, high
DEV_OFF_NEWCOMER_WING: float = 0.6  # n=2085, high
DEV_OFF_NEWCOMER_BIG: float = 0.6  # n=716, high
# Newcomer development adjustments (defense)
DEV_DEF_NEWCOMER_G: float = 0.6  # n=4045
DEV_DEF_NEWCOMER_WING: float = 0.6  # n=2085
DEV_DEF_NEWCOMER_BIG: float = 0.6  # n=716

# Second year development adjustments (offense)
DEV_OFF_SECOND_YEAR_G: float = 0.4  # n=3823, high
DEV_OFF_SECOND_YEAR_WING: float = 0.4  # n=1866, high
DEV_OFF_SECOND_YEAR_BIG: float = 0.4  # n=957, high
# Second year development adjustments (defense)
DEV_DEF_SECOND_YEAR_G: float = 0.4  # n=3823
DEV_DEF_SECOND_YEAR_WING: float = 0.4  # n=1866
DEV_DEF_SECOND_YEAR_BIG: float = 0.4  # n=957

# Senior+ development adjustments (offense)
DEV_OFF_SENIOR_G: float = 0.1  # n=1131, high
DEV_OFF_SENIOR_WING: float = 0.1  # n=491, high
DEV_OFF_SENIOR_BIG: float = 0.1  # n=302, high
# Senior+ development adjustments (defense)
DEV_DEF_SENIOR_G: float = 0.1  # n=1131
DEV_DEF_SENIOR_WING: float = 0.1  # n=491
DEV_DEF_SENIOR_BIG: float = 0.1  # n=302

# ── JUCO transfer adjustments (Phase 1.3) ────────────────────────────────────
# Added in Sprint 3 — ManualPlayerSpec resolver.
# JUCOs have actual college production data (unlike HS freshmen), so their
# BPR prior is slightly higher and their uncertainty is lower at the same rank.
# Phase 1.3 provisional; pending BT-5 validation.
JUCO_BPR_BOOST: float = 0.15         # added to rank-lookup obpr_prior for JUCOs
JUCO_UNCERTAINTY_FACTOR: float = 0.90  # multiplied against base uncertainty

