"""
nba/outlook_constants.py — calibration constants of the NBA team-outlook pipeline (task 5.10).

One source: compute_nba_team_outlooks, derive_nba_slope and diagnose_nba_projection_variance import
these names from here.

Two sets, keyed by the source season's rating scale (nba.rating_scale.native_scale):
  - earlier scale (no native-1 rows; all of prod before the native deploy): the constants below,
    unchanged from before task 5.10;
  - native-1 seasons: the NATIVE_* overrides at the bottom. By the task-5.10 rule, constants that
    carry the rating level move with the centred scale; shape constants change only with evidence,
    so the native set keeps every constant without a NATIVE_* override.
"""

from nba.rating_scale import WA_DIVISOR


# ── Calibration constants ──────────────────────────────────────────────────────
REPLACEMENT_LEVEL = 2.0        # BPR units added above zero to form demand signal
SHRINKAGE_RETURNER = 0.10      # 10% regression to league mean for returning players
SHRINKAGE_ACQUISITION = 0.20   # 20% for trades/signings (higher projection uncertainty)

# AGE_CURVE — HUMAN-REVIEWED CONSTANT, do not auto-update.
# Empirical BPR aging curve: mean bpr(Y+1)−bpr(Y) by age at Y, derived 2026-08-03
# on pairs 2022:2023/2023:2024/2024:2025 (2025→2026 lineage-excluded), FULL
# population N=1321. Buckets: ≤20 +0.61, 21-30 ≈0 (flat prime), 31-33 −0.50, 34+
# −0.17 (survivorship-masked → regularized toward the 31-33 decline). Piecewise-
# linear knots (age, delta); clamp beyond the ends.
#   CAVEAT: per-player LOYO barely beats zero (age Δ is small vs BPR noise SD ~2.4).
#   This term is here for correct veteran-decline / young-development DIRECTION and
#   to drive the development-watch — NOT a large r lift. The dominant young
#   high-pick development (+2.69 for young bad-team players) is NOT captured here;
#   that is the separate team-agnostic PICK-CONDITIONAL curve (next task).
AGE_CURVE_KNOTS = [(20.0, 0.60), (21.0, 0.00), (28.0, 0.00), (32.0, -0.50)]

# PICK_DEV_CURVE — HUMAN-REVIEWED CONSTANT, do not auto-update.
# Early-career development bonus by DRAFT PICK, ON TOP OF the age curve. Derived
# 2026-09-10 on pairs 2022:2023/2023:2024/2024:2025 (2025→2026 lineage-excluded),
# all teams (team-agnostic), RESIDUAL after the age curve so it does not
# double-count general aging. Fires only in years_of_experience ≤ 3 (the signal is
# concentrated there; later-career pick effect ≈ 0). Early-career residuals by
# pick: 1-3 +0.52, 4-9 +0.34, 10-20 +0.16, 21-30 −0.06, 31-60 −0.25 (strongly
# monotone). This is the decomposed +2.08 young-bad-team development — high picks
# develop, late picks fade — keyed on PICK, not team (so it does not re-absorb the
# P3 tanking-context effect).
PICK_DEV_KNOTS = [(2.0, 0.52), (6.5, 0.34), (15.0, 0.16), (25.0, -0.06), (45.0, -0.25)]

# SLOPE — HUMAN-REVIEWED CONSTANT, do not auto-update.
# Derivation: `manage.py derive_nba_slope --pairs 2022:2023,2023:2024,2024:2025`
# (Phase 2 Stage 2, 2026-07-07, operator-approved decision tree).
#   Pooled through-origin OLS, actual adj_net(Y+1) ~ (excess_off + excess_def),
#   N=90 (3 pairs × 30), r=0.456, RMSE=4.63. Allocator: MINUTES_CEIL=1.80.
#   Pairs included: 2022→23, 2023→24, 2024→25 — each passed the fresh-BPR
#   lineage check (mean |stored − fresh| = 0.109/0.084/0.115, threshold 0.5).
#   2025→2026 excluded: stored 2025 BPR predates the current BPR pipeline
#   (e.g. Amen Thompson stored ≈5.7 vs freshly-computed 9.43).
#   History: 0.48 (2024→25 single pair, old allocator CEIL=1.20; its target
#   ratings were also corrupted by a missing season_type='regular' filter —
#   playoff rows overwrote 16 teams' actual adj_net).
SLOPE = 0.453
WINS_PER_EM = 2.46             # wins per 1 pt of adj_em (OLS-calibrated from 2025-26 season)
# WINS_INTERCEPT (legacy, removed Phase 2): 44.3 was OLS-fit on an uncentered
# legacy scale whose league-mean EM was ~-1.34. A fixed intercept cannot
# guarantee league closure (Σ wins = 1230). Wins now use a self-centering
# effective intercept computed per run: 41.0 - WINS_PER_EM × league_mean_em.
SIGMA_EM = 4.7                 # pooled forward RMSE 4.63 (legacy BPR path, N=90, same
                               # derive_nba_slope run as SLOPE above), rounded up to
                               # one decimal. History: 5.5 (single pair, old allocator).
WINS_ADDED_SCALAR = 0.38       # converts (minutes_share × bpr) → wins added

# ── Projection Value wiring (docs/bpr_audit/09) ───────────────────────────────
# Team forecasts consume projection_value (0.25·z(BPR)+0.75·z(BPM)), NOT raw
# BPR — forward-validated: pooled r=0.601 vs 0.583 pure BPR (3 pairs).
# Centered (two-pass league-baseline) form — no intercept. The legacy BPR
# projection is still computed and logged for comparison; projected_* DB
# fields carry the PV-based numbers.
#
# PV_SLOPE — HUMAN-REVIEWED CONSTANT, do not auto-update.
# Derivation: LOYO out-of-sample re-fit under the CURRENT pipeline (2026-07-30,
# operator-approved). The old 5.591 was fit for the PRE-K1, PRE-trim allocator;
# roster trim sharpened the team_pv distribution, leaving 5.591 ~2x too small
# (compression diagnostic: projected AdjEM SD 2.55 vs actual 5.39, ratio 0.47).
#   Through-origin OLS, actual adj_net(Y+1) ~ (team_pv − league_pv_mean),
#   team_pv = minutes-share-weighted mean pv_effective under MINUTES_CEIL=1.80.
#   Pairs 2022:2023,2023:2024,2024:2025 (2025→2026 lineage-excluded, as before).
#   LOYO folds: demand 11.72/9.84/9.00 → pooled 10.10 (r 0.683); persistence
#   12.10/10.23/9.37 → pooled 10.52 (r 0.712). Nearly identical across allocators
#   → one value serves both (not overfit). OOS wins MAE 7.76→6.96; r INVARIANT
#   (pure scale re-fit — the ordering ceiling 0.68-0.71 is the values problem,
#   injury/tanking-deflation, untouched here by design).
#   History: 3.58 (old allocator CEIL=1.20) → 5.591 (Phase 2, 2026-07-07,
#   pre-trim) → 10.1 (LOYO under K1+trim+pool-12, 2026-07-30).
PV_SLOPE = 10.1
PV_SIGMA_EM = 4.0             # LOYO pooled forward RMSE 3.94 (demand) / 3.82
                              # (persistence), rounded up. Band coverage: 73-77%
                              # of actuals inside ±1σ (≥68% target, mildly
                              # conservative). History: 4.5 → 4.6 → 4.0.
# PV_WINS_INTERCEPT (removed Phase 2): the fixed 41.0 assumed projected EM is
# exactly mean-zero. handle() now computes effective_intercept =
# 41.0 − WINS_PER_EM × league_mean_em each full-league run, guaranteeing closure.

# ── Rookie priors (HUMAN-REVIEWED CONSTANTS, Phase 4 Stage 2, 2026-07-13) ─────
# Drafted players have no NBA stat to project from; before Phase 4 they were
# hardcoded obpr/dbpr 0.0 and mpg 12.0. Derivation:
#   `manage.py derive_rookie_priors --draft-years 2021,2022,2023,2024`
#   187 rookie outcomes / 4 draft classes, joined NBA.com DraftHistory PERSON_ID
#   → rookie-season stats (draft year D → season D+1), multi-team splits
#   collapsed minutes-weighted, one row per player asserted.
#
# BPR prior is FLAT (pick-independent) — operator decision D1. LOYO
# (leave-one-class-out) pooled BPR MAE: pick-binned map 1.69 beats the old
# hardcoded 0.0 (1.90) but LOSES to a flat global-rookie-mean (1.66). Pick
# carries no rookie-BPR signal, so we use the pooled minutes-weighted mean and
# reject pick-binned BPR. (The old 0.0 was, ironically, only ~1.1 pts off.)
ROOKIE_PRIOR_OBPR = -0.8662    # pooled minutes-weighted rookie obpr, N=187
ROOKIE_PRIOR_DBPR = -0.2714    # pooled minutes-weighted rookie dbpr, N=187
# (total rookie BPR prior = -1.1376; rookies are net-negative players — honest.)


# ── native-1 overrides (task 5.10, operator-approved 2026-11-19) ───────────────────────────────
# Level constants re-derived on the centred native ratings; everything else is kept (the gate
# backtest showed the refit PV_SLOPE 8.538 worse by +0.21 ± 0.12 wins MAE, and the refit aging and
# pick knots no better than the old ones).
#
# Rookie prior: derive_rookie_priors' population (draft classes 2021-2024, 187 rookies, rookie
# season D+1, min 5 MPG), pooled minutes-weighted native obpr / dbpr (total -2.03: rookies sit just
# below replacement, R = -1.918, on the centred scale).
NATIVE_ROOKIE_PRIOR_OBPR = -1.5671
NATIVE_ROOKIE_PRIOR_DBPR = -0.4583
# SLOPE: derive_nba_slope --pairs 2022:2023,2023:2024,2024:2025 on native ratings (native lineage
# check PASS, mean |stored - fresh| = 0 each season): pooled through-origin N=90, r=0.444,
# RMSE=4.66 (old: 0.453, r=0.456, RMSE=4.63). Drives only the offense / defense split of adj_em.
NATIVE_SLOPE = 0.240
# Wins Added per slot on native seasons: share x (bpr - R) x NATIVE_WINS_ADDED_PER_SHARE, so a
# projected slot and the player's stored Wins Added agree at equal minutes. One share = 20 MPG
# over 82 games = 1640 minutes; player Wins Added = (bpr - R) x minutes / 48 / D (D = WA_DIVISOR,
# 27.97 since 2026-11-26), so the factor is 1640 / 48 / D. Slot Wins Added is shown per player and
# feeds only the top-two share (a ratio), not projected team wins. (The Z4 through-origin regression
# on 2022-2025 rosters gives 0.5626 instead: demand shares are not real minutes and the fit attenuates.)
NATIVE_WINS_ADDED_PER_SHARE = 20.0 * 82.0 / 48.0 / WA_DIVISOR
# The aging knots were fitted on age at the start of the source season (Oct 1 of Y-1); the
# pipeline's slot age is on Oct 1 of the source year, one year older. Native seasons apply the
# curve at slot age minus this offset.
NATIVE_DEV_AGE_OFFSET = 1
