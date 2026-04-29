"""
Phase 5: Team Projection Engine — tunable constants.

TRANSLATION (BPR → AdjO / AdjD)
─────────────────────────────────
  base_team_offense = Σ(minutes_share_p2 × projected_obpr)
  base_team_defense = Σ(minutes_share_p2 × projected_dbpr)

Centering ensures an average-talent team projects to the D1 average rating:

  projected_adj_o = D1_avg_adj_o + SLOPE_OFF × (base_off − league_mean_base_off)
  projected_adj_d = D1_avg_adj_d − SLOPE_DEF × (base_def − league_mean_base_def)

SLOPE_OFF ~0.73 and SLOPE_DEF ~0.66 from BT-4 OLS regression (Sprint 2).
Pre-2021 data excluded — BPR scale inconsistency (player RMSE 34–117 vs 3–5 for 2021+).
N=1779 team pairs (2021–2025), R²=0.436 (off) / 0.378 (def).

CONTINUITY
──────────
  returner_fraction = Σ(min_share for returners) / Σ(all min_share)
  continuity_score  = returner_fraction × 100  (0-100)

  raw_adj = 2 × MAX × (returner_fraction − NEUTRAL_FRACTION)
  → clamp to [−MAX, +MAX]

  At 50 % returners → 0 adjustment (neutral).
  At 100 % returners → +MAX_CONTINUITY_ADJ bonus.
  Defense benefits slightly more than offense.

FIT ADJUSTMENTS
───────────────
Uses Phase 3+4 adjusted_off_fit / adjusted_def_fit (0-100 scale):

  fit_adjustment_off = FIT_TO_RATING_OFF × (adjusted_off_fit − 50) / 50
  fit_adjustment_def = FIT_TO_RATING_DEF × (adjusted_def_fit − 50) / 50

Phase 9e (April 2026): FIT_TO_RATING_OFF = FIT_TO_RATING_DEF = 0.0.
No detectable predictive signal found in Phase 9e calibration sweep.
Mean projections are now Model-D-equivalent.  TeamRosterFit data is
still loaded for transfer_fit_risk uncertainty (Phase 6b).

COACHING CONTINUITY
───────────────────
No coach identity data in the current codebase.
coaching_continuity_adjustment = 0.0 (always neutral, placeholder hook).

UNCERTAINTY
───────────
team_projection_uncertainty ∈ [0, 1] (0 = high confidence, 1 = low).

  uncertainty_pts = SIGMA_SCALE × (1 + team_projection_uncertainty)

Used to build ±confidence bands on projected_adj_o / adj_d / adj_em and
to compute national / offense / defense rank ranges.
"""

# ── Translation slopes ────────────────────────────────────────────────────────
# BPR (pts/100 poss above D1 avg, weighted by min share) → adj rating delta.
# Formula: projected_adj_o = D1_avg + SLOPE_OFF × (base_off − league_mean_off)
# Updated 1.40 → 0.73 by BT-4 OLS (Sprint 2, 2021–2025 only). R²=0.436, N=1779 pairs.
SLOPE_OFF: float = 0.73
# Updated 1.55 → 0.66 by BT-4 OLS (Sprint 2, 2021–2025 only). R²=0.378, N=1779 pairs.
SLOPE_DEF: float = 0.66

# D1 average fallback — used if NationalAverages record is missing
FALLBACK_D1_ADJ_O: float = 108.06
FALLBACK_D1_ADJ_D: float = 108.24

# ── Continuity ────────────────────────────────────────────────────────────────
# Returner fraction at which the continuity adjustment is zero (neither boost nor penalty).
#
# Phase 9b calibration (April 2026):
#   Old value : 0.50  (pre-calibration)
#   Phase 9b  : 0.45  (selected after sweeping 0.30–0.50 on 2024 and 2025 source years —
#                      the only two valid pairs with prior-year PSS data at that time)
#
# Phase 9c recalibration (April 2026):
#   New value : 0.50  (selected after expanding backtest window to 4 valid pairs:
#                      2022→2023, 2023→2024, 2024→2025, 2025→2026)
#
# Phase 9c rationale:
#   - Historical ingest added 2021 + 2022 PlayerGameStats and PSS box stats.
#   - 2022 and 2021 PSS have null obpr/dbpr (BPR requires PlayerGameStint, which only
#     goes back to 2023). The data_loader uses 0.0 for null BPR fields.
#   - With 4 valid pairs: neutral=0.50 → combined D_bias = +0.036 (near zero).
#   - With 4 valid pairs: neutral=0.45 → combined D_bias = +0.384 (positive bias).
#   - The AvgRetFrac across all valid pairs is 0.518, extremely close to 0.50, making
#     0.50 the natural neutral point — average team gets ~0 continuity adjustment.
#   - Per-pair at neutral=0.50: 2022→2023 +0.48, 2023→2024 +0.17, 2024→2025 −0.01,
#     2025→2026 −0.49. Overall nearly balanced. The 2022/2023 pairs are slightly
#     over/under because BPR=0 affects the talent weights but not returner_fraction.
#
# Backtest limitation note:
#   Phase 9b reveals that the continuity signal cannot be fully validated via historical
#   backtesting because the backtest uses backward-looking classification (who returned
#   from Y-1 into Y) while the production engine uses forward-looking data (who is
#   committed to return from Y into Y+1).  See backtest_report.md for details.
CONTINUITY_NEUTRAL_FRACTION: float = 0.50

# Maximum continuity adjustment (pts/100 poss) achievable at full or zero continuity.
# Applied as ± relative to neutral via: 2 × MAX × (returner_frac − NEUTRAL)
# Caps unchanged from Phase 5 calibration — no backtest evidence for amplitude change.
MAX_CONTINUITY_ADJ_OFF: float = 1.5   # ±1.5 pts adj_o
MAX_CONTINUITY_ADJ_DEF: float = 2.0   # ±2.0 pts adj_d (defense gains more)

# ── Fit adjustments ───────────────────────────────────────────────────────────
# Maximum adjustment from Phase 3+4 roster-fit score (0-100) → pts/100 poss
# At score=100 → +FIT_TO_RATING bonus; at score=0 → −FIT_TO_RATING penalty
#
# Phase 9e calibration (April 2026):
#   Fit recalibration sweep (N=1081, source years 2023-2025) found that the fit
#   layer provides no detectable predictive signal.  No configuration — shrinkage,
#   recentering, offense-only, defense-only, Phase 3 scores, or Phase 4 scores —
#   improved over Model D (zero fit).  Root cause: adjusted_off_fit is
#   systematically ~4.3 pts below the nominal neutral of 50 (empirical mean ≈ 45.7),
#   causing a mean negative bias of −0.21 pts/100 on adj_o.  Zeroing the scaling
#   constants makes the production engine compute Model-D-equivalent mean predictions
#   while preserving the TeamRosterFit data for uncertainty (transfer_fit_risk).
#
#   Previous values (kept for reference — do not restore without fresh sweep):
#     FIT_TO_RATING_OFF = 2.5
#     FIT_TO_RATING_DEF = 2.0
#     FIT_MAX_ADJ_OFF   = 2.5
#     FIT_MAX_ADJ_DEF   = 2.0
FIT_TO_RATING_OFF: float = 0.0   # zeroed: Phase 9e sweep — no detectable signal
FIT_TO_RATING_DEF: float = 0.0   # zeroed: Phase 9e sweep — no detectable signal

# Hard caps (irrelevant when FIT_TO_RATING = 0; retained for forward compatibility)
FIT_MAX_ADJ_OFF: float = 2.5
FIT_MAX_ADJ_DEF: float = 2.0

# ── Phase 6: BPR-weighted continuity ─────────────────────────────────────────
# continuity_value_score blends returner_minutes_fraction (lower signal priority)
# with returner_bpr_fraction (how much of the team's productive output comes from
# returners), weighted by CONTINUITY_BPR_BLEND_WEIGHT.
#
#   continuity_value_score = (
#       (1 − BLEND) × returner_minutes_frac + BLEND × returner_bpr_frac
#   ) × 100
#
# Returning your stars matters more than returning your bench.  A team that
# returns 60 % of minutes but 80 % of BPR-weighted output is more stable than
# one that returns 60 % of minutes from its lowest-BPR rotation fillers.
#
# BPR values are shifted above CONTINUITY_BPR_REPLACEMENT_FLOOR before
# computing fractions so that negative-BPR players do not invert the
# denominator.  The floor is intentionally shallower than the minutes model's
# replacement floor — we do not want to zero-out the contribution of average
# players, only prevent deeply negative outliers from corrupting the fractions.
CONTINUITY_BPR_BLEND_WEIGHT: float = 0.40        # 40 % BPR share, 60 % minutes
CONTINUITY_BPR_REPLACEMENT_FLOOR: float = -5.0   # pts/100 poss; shift floor

# ── Coaching continuity ───────────────────────────────────────────────────────
# No coach data available. Toggle to True once coach identity is trackable.
COACHING_CONTINUITY_HOOK_ENABLED: bool = False
COACHING_CONTINUITY_MAX_ADJ: float = 1.0  # reserved (pts/100 poss)

# ── Phase 6b: Transfer fit-dependent outcome spread ───────────────────────────
# A transfer-heavy roster is not inherently worse — but one where transfers land
# in a poor-fit system carries meaningful fragility that a pure talent model
# cannot see.  This layer adds that fragility to uncertainty / range only.
# It does NOT shift the mean projection (base_team_offense/defense unchanged).
#
# Signal:
#   fit_shortfall = max(0, (50 − avg_fit) / 50)       → 0 at neutral/good fit
#   dep_frac      = transfer_dependence_score / 100    → 0–1
#   transfer_fit_risk = dep_frac × fit_shortfall       → interaction ∈ [0, 1]
#
# The interaction means:
#   • no transfer dependence → risk = 0 (no effect regardless of fit)
#   • high dependence + good fit (≥ 50) → shortfall = 0 → risk = 0
#   • high dependence + poor fit → risk peaks toward 1.0
#
# Uncertainty contribution:
#   uncertainty += TRANSFER_FIT_RISK_WEIGHT × transfer_fit_risk
#
# Maximum uncertainty addition = TRANSFER_FIT_RISK_WEIGHT (when risk = 1.0).
# The cap equals the weight because risk is already bounded in [0, 1].
TRANSFER_FIT_RISK_WEIGHT: float = 0.12  # max uncertainty add (risk × weight)

# If no fit data is available, assume neutral fit (shortfall = 0). This prevents
# missing Phase 3/4 data from being interpreted as "poor fit."
# Only trigger the explicit no-style-data penalty (UNCERTAINTY_NO_STYLE_DATA)
# via the existing channel, not through this path.
TRANSFER_FIT_RISK_NO_STYLE_DEFAULT: float = 0.0  # treat missing as neutral risk

# ── Uncertainty ───────────────────────────────────────────────────────────────
# Base uncertainty applied to every team regardless of roster composition
UNCERTAINTY_BASE: float = 0.20

# Additive drivers for team_projection_uncertainty
UNCERTAINTY_PLAYER_SIGNAL_WEIGHT: float = 0.30   # minutes-weighted avg player uncertainty × this
# Reduced from 0.20 → 0.05 (Sprint 1, Phase 1.1 fix).
# Newcomer high projection_uncertainty (≈0.80) already flows through
# UNCERTAINTY_PLAYER_SIGNAL_WEIGHT = 0.30, contributing ~+0.24 per
# full-minutes newcomer. The original 0.20 weight double-counted the
# same signal. 0.05 retains a small categorical residual for systemic
# uncertainty (team chemistry, system installation) not captured by
# individual player uncertainty alone.
UNCERTAINTY_NEWCOMER_WEIGHT: float = 0.05
UNCERTAINTY_CONTINUITY_WEIGHT: float = 0.10  # (1 − returner_fraction) × this
UNCERTAINTY_NO_STYLE_DATA: float = 0.05      # if has_team_style_data == False

# Clamp bounds for team_projection_uncertainty
UNCERTAINTY_MIN: float = 0.10
UNCERTAINTY_MAX: float = 0.90

# Baseline sigma (pts/100 poss) at uncertainty=0; expands linearly to SIGMA_MAX
# projected_adj_o_low/high = projected_adj_o ± uncertainty_pts
# projected_adj_em_low/high = projected_adj_em ± 2 × uncertainty_pts
UNCERTAINTY_SIGMA_SCALE: float = 3.5   # pts/100 poss at uncertainty=0
UNCERTAINTY_SIGMA_MAX: float = 6.0     # pts/100 poss at uncertainty=1 (capped)
