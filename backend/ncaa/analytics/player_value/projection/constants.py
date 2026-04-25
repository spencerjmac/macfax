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
TRANSFER_COMP_WEIGHT_OFF = 0.03
TRANSFER_COMP_WEIGHT_DEF = 0.03

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
