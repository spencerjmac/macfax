"""
BPR (Bayesian Performance Rating) constants and documented assumptions.

Public reference: https://blog.evanmiya.com/p/bayesian-performance-rating

---
DEVIATIONS FROM THE PUBLIC BPR ARTICLE
---------------------------------------

1. Multi-year RAPM window
   Article: 4-year rolling window as a single training sample.
   Macfax:  Multi-year pooled RAPM is supported via the --rapm-years flag.  When
            multiple season years are provided, observations are pooled into a
            single design matrix and coefficients are estimated at the
            (player_id, season_year) level — the same player across different
            seasons receives independent coefficients, not one pooled coefficient
            across all seasons (v1.3.1, datasets.py / rapm.py / pipeline.py).
            Only the target season's (highest-year) coefficients and possession
            totals are written back to PlayerSeasonStats; earlier seasons
            contribute estimation power only.
            Single-season mode (rapm_window="single_season") remains the default
            production path.
   Impact:  Single-season runs have higher variance than pooled multi-year RAPM,
            partially offset by stronger box-score priors.  Multi-year pooling
            reduces noise for returning players.  Macfax's implementation still
            differs from the EvanMiya rolling-window framework in prior sources,
            prior blending strategy, and Box BPR training targets (baseline RAPM
            rather than a true multi-season coefficient history).

2. Possession-level observations
   Article: True possession-by-possession design matrix (who's on floor each play).
   Macfax:  Lineup segments from stint intersection (~77.5% of time resolves to
            clean 5v5).  Home-side pts/poss attributed from home_ref stint;
            away-side pts/poss attributed from away_ref stint (native perspective).
   Impact:  Small proportional-scaling attribution noise, unbiased in expectation.

3. Box BPR training — leakage prevention and clean teacher-student chain
   Article: Box model trained on multi-year RAPM coefficients; used as prior for
            current-season RAPM.
   Macfax:  Prior-season training uses baseline_obpr / baseline_dbpr as targets —
            the raw baseline RAPM output BEFORE prior-informed fitting.  This
            ensures the chain is strictly:
              baseline RAPM → Box BPR prior → final prior-informed RAPM
            and NOT:
              final BPR → Box BPR prior → next-season final BPR  (recursive contamination).
            When ≥ MIN_PRIOR_TRAINING_SAMPLES prior-season baseline targets exist,
            Box BPR trains on those.  Otherwise falls back to out-of-fold (k-fold
            on players) so no player's prior uses their own RAPM target.
   Impact:  Eliminates both same-season leakage and cross-season target contamination.

4. Preseason priors
   Article: Separate preseason model using historical player data + recruiting
            rankings + transfer context + minutes projections.
   Macfax:  Returns Box BPR as prior mean with fixed σ (no transfer data).
            For players with a PlayerRecruitingProfile, the recruiting tier
            (star bucket) sets a non-neutral prior mean + tighter σ for
            freshmen who have no prior college BPR.  Players with no profile
            and no box BPR fall back to 0.0 with wide σ.

5. Prior standard deviation tuning — joint and separate off/def
   Article: Weight between box priors and RAPM optimized by cross-validation.
   Macfax:  Pipeline tunes BOTH a joint global sd_scale AND separate sd_scale_off /
            sd_scale_def via 1D coordinate descent.  Both are evaluated by 5-fold
            game-split CV on held-out offensive efficiency (WMSE); whichever gives
            lower held-out WMSE is used for the final fit.  A value of s < 1 trusts
            box priors more; s > 1 trusts RAPM data more.
            BOX_ONLY_SD_SCALE_REF = 0.01 is evaluated as a reference point to
            report near-box-only held-out WMSE without being eligible for selection.

6. Home court advantage
   Article: Not publicly specified.
   Macfax:  HCA is estimated freely as a latent coefficient in the RAPM regression
            (column 1 of the design matrix, signed ±1 for home/away offense).
            The constant HCA_PTS_PER_100 = 3.0 is retained as a reference /
            sanity-check bound; it is NOT used in the fitting code.

7. RAPM centering
   Article: Average D1 player ≈ 0. Achieved through prior + multi-year regularization.
   Macfax:  The intercept term (column 0 of the design matrix) absorbs the league
            average offensive efficiency.  Player coefficients are implicitly
            relative to the average because the intercept is free.  We do NOT
            subtract the league average from y before fitting.

8. Model version
   Article: Private versioning.
   Macfax:  BPR_MODEL_VERSION = "1.3" adds:
            v1.2: baseline RAPM target storage (eliminates cross-season recursive
              contamination), separate off/def prior SD tuning, BPR source provenance
              fields (obpr_source, dbpr_source, bpr_source), box-only held-out WMSE
              reference, and improved validation truthfulness.
            v1.3: collinear defensive feature pruning (reb100 and stl_blk100 removed),
              separate Box BPR alpha grids (stronger regularization for defense),
              multi-year RAPM implementation (player-season-keyed design matrix,
              rolling window via rapm_years, target-season-only writes — v1.3.1),
              prior-history signals (prior-season baseline RAPM blended into prior mean
              with PRIOR_HISTORY_BLEND weight), component influence diagnostics,
              ranking sanity validation (strict_bpr / full_two_sided / box_bpr views),
              bpr_mode API filter, baseline_obpr/dbpr and source fields in serializer.
            v1.4: on-court efficiency features added to Box BPR (on_court_adj_em to
              both OFF and DEF feature sets; on_court_tov_edge and on_court_reb_edge
              added to DEF). Preseason model training window extended from 2 to 4 years.
              These changes improve Box BPR R² (especially defensive), giving tighter
              and more accurate priors — particularly for intangible players whose
              on-court impact exceeds their raw box stats.
            v1.5: two fixes to close gap vs EvanMiya's published ratings.
              (1) on-off delta replaces raw on_court_adj_em in Box BPR: feature is now
              on_court_adj_em − team_adj_em, removing team-quality bias so role players
              on elite teams (Duke, Iowa State) are no longer inflated.
              (2) Separate BOX_TRAINING_RAPM_LAMBDA for Box BPR training targets:
              a second, less-regularised RAPM fit generates the baseline_obpr/dbpr stored
              in DB and used as Box BPR training labels. Less shrinkage → targets span
              10-15 range → Box BPR learns correct scale → top player priors reach 12-14.
            v1.6: backtesting vs Evan Miya 2025-26 season (backtest_bpr_vs_evan_miya).
              (1) BOX_TRAINING_RAPM_LAMBDA remains 500 (tested 100 — noisier baseline
              RAPM targets inflated all players by ~1.65 pts/100, worse RMSE 3.10 vs
              1.89). 500 is the correct working value; v1.5 docstring "(100)" was wrong.
              (2) blk_to_fga_ratio added to DEF_FEATURES: BLK / own FGA captures
              rim-protection intensity for shot-blockers whose value exceeds blk100.
              (3) EM reference data + backtest command added (see evan_miya_reference.py
              and backtest_bpr_vs_evan_miya management command).

9. Opponent quality (schedule strength) adjustment in Box BPR
   Article: uses "average opponent rating faced by each player" as a Box BPR
            predictor to account for competition level.
   Macfax:  opp_quality = mean(TeamSeasonRatings.adj_em of all opponents faced
            by the player's team in the target season). Added to both OFF_FEATURES
            and DEF_FEATURES in box_bpr.py. Sourced from _build_opponent_quality_map()
            in pipeline.py via the Game model (status="final" games only).
            adj_em is zero-sum across D1, so no centering needed.
   Impact:  Corrects mid-major inflation: equal stats against harder opponents
            → higher Box BPR. Ridge learns a positive coefficient on opp_quality.
"""

# ── Model version ─────────────────────────────────────────────────────────────
# v1.7 (BPR v2, 2026-07): truthful RAPM-target gating is the production default
# (pre-2025 placeholder-stint seasons excluded from the RAPM pool, internal Box
# BPR targets, prior-history blend, and preseason-model training); stint layer
# repaired (phantom OT blocks, duplicate/zero-length rows, parser sequence-sort
# and period-reopen fixes); OT and 2026 neutral-site flags backfilled.
# Validated leak-free: 2025→26 cross-season bpr 13.09 RMSE beats adj_em 13.62;
# rolling 2026 bpr beats/ties adj_em at every cutoff; player YoY r 0.69.
# ESPN serves no substitution events before ~Feb 2025 (probed 2026-07) —
# pre-2025 seasons are permanently placeholder unless a new PBP source appears.
BPR_MODEL_VERSION = "1.7"

# ── RAPM target validity by season (2026-07 data audit) ──────────────────────
# Stored ESPN play-by-play before 2025 contains NO substitution events: every
# game's stints are the 5 boxscore starters riding full halves (97.7% of 2024
# team-games have exactly 5 stint-players). "RAPM" fit on those seasons is
# fixed-unit game plus-minus, not lineup-isolated player impact.
# See docs/bpr_audit/02_data_integrity_report.md (headline finding).
#
# FIRST_VALID_RAPM_SEASON gates which seasons may serve as RAPM *targets*
# (Box BPR training labels, prior-history blending, preseason-model targets)
# and which seasons may be pooled into the RAPM design matrix when the
# pipeline runs in truthful_targets mode. 2025 is transitional (~27% of games
# have real substitution data) and is accepted as the first valid year;
# 2026+ is fully valid. Pre-2025 seasons remain usable for box features,
# team context, and external (Evan Miya) training targets.
FIRST_VALID_RAPM_SEASON = 2025


def is_valid_rapm_target_season(year: int) -> bool:
    """True when a season's stint data supports lineup-isolated RAPM."""
    return year >= FIRST_VALID_RAPM_SEASON

# ── Possession estimation (Kubatko formula) ───────────────────────────────────
# Possessions ≈ FGA + 0.44×FTA + TOV − ORB
FTA_POSS_FACTOR = 0.44

# ── Minimum data thresholds ───────────────────────────────────────────────────
# Lineup segment must have at least this many possessions to be a valid observation
MIN_SEGMENT_POSS = 0.5  # ~1 possession minimum
# Each OBSERVATION side (home-offense or away-offense) must have this many
# estimated possessions to be included in the design matrix.
# Prevents near-zero denominators from blowing up y = pts/poss * 100.
MIN_OBS_POSS = 1.0
# Player must have at least this many offensive possessions to receive BPR
MIN_OFF_POSS_BPR = 200
# Player must have at least this many defensive possessions
MIN_DEF_POSS_BPR = 200
# Box BPR: minimum minutes per game to include in box model training
MIN_MPG_BOX_BPR = 8.0
# Box BPR: minimum games played
MIN_GP_BOX_BPR = 5

# ── Home court advantage ──────────────────────────────────────────────────────
# Reference value (consensus NCAA estimate).  NOT used in the fitting code;
# HCA is estimated freely as a regression coefficient in rapm.py.
# Retained here as a sanity-check bound in validation.
HCA_PTS_PER_100 = 3.0

# ── RAPM regularization ───────────────────────────────────────────────────────
# Default lambda candidates for cross-validation (pts/100 poss^2 units)
# Lower λ = less shrinkage (trusts data more); higher λ = more shrinkage (trusts prior more)
RAPM_LAMBDA_CANDIDATES = [1.0, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 2500.0, 5000.0]
RAPM_CV_FOLDS = 5

# Lambda for the secondary RAPM fit whose coefficients become Box BPR training targets.
# LOWER than the production CV lambda (~1000) so elite player coefficients are less
# shrunk and span the 10-15 range — Box BPR then learns to predict in that range,
# breaking the recursive attenuation chain that compresses final BPR values.
# The production RAPM (CV-selected lambda) is unaffected; only baseline_obpr/dbpr
# written to DB for future Box BPR training use this lambda.
BOX_TRAINING_RAPM_LAMBDA = 500.0

# ── Prior standard deviations ────────────────────────────────────────────────
# Used when Box BPR is unavailable (e.g., new players) or as initial fallback.
# Deviation: not CV-tuned per-player; using conservative defaults.
# Interpretation: ~95% of players should land within ±2σ of their prior mean.
PRIOR_SD_DEFAULT_OFF = 4.0   # pts/100 poss for offensive coefficient
PRIOR_SD_DEFAULT_DEF = 3.0   # pts/100 poss for defensive coefficient (defense is noisier)

# When box BPR IS available as the prior, use tighter SDs (box model has real signal).
# These are BASE values; the actual SD used = base × cv-tuned PRIOR_SD_SCALE.
PRIOR_SD_BOX_OFF = 3.0
PRIOR_SD_BOX_DEF = 2.5

# Prior-history blending weight (v1.3).
# For returning players with a stored prior-season baseline RAPM, the prior mean
# is blended: prior = (1 - α) * box_bpr + α * prior_season_baseline_rapm.
# α = 0 → use box BPR only; α = 1 → use prior RAPM only.
# A small α (0.20) gently anchors the prior to actual observed performance
# without over-correcting when box features disagree.
PRIOR_HISTORY_BLEND = 0.20

# ── Prior SD global scale factor (tuned by CV) ────────────────────────────────
# A multiplier s applied uniformly to all per-player SDs before building the
# prior-informed RAPM penalty.  s < 1 → trust box priors more; s > 1 → trust data more.
# Pipeline tunes BOTH a single joint sd_scale AND separate sd_scale_off/sd_scale_def,
# using whichever gives lower held-out WMSE.
PRIOR_SD_SCALE_CANDIDATES = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.4, 0.5, 0.6, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0]

# Reference scale evaluated during CV to approximate "box-only" held-out WMSE.
# At this scale, per-player penalty ≈ λ / (base_SD × 0.01)² → ∞,
# forcing coefficients to the box prior mean.  NOT eligible for selection.
BOX_ONLY_SD_SCALE_REF = 0.01

# ── BPR source provenance constants ──────────────────────────────────────────
# Values for PlayerSeasonStats.obpr_source / dbpr_source / bpr_source.
BPR_SOURCE_RAPM    = "rapm"     # component came from prior-informed RAPM fit
BPR_SOURCE_BOX     = "box_bpr"  # component came from Box BPR fallback
BPR_SOURCE_MIXED   = "mixed"    # bpr_source: one side RAPM, one side box
BPR_SOURCE_PARTIAL = "partial"  # bpr_source: only one component non-null

# ── Box BPR leakage guard ─────────────────────────────────────────────────────
# Minimum number of prior-season RAPM records needed to use prior-season
# training instead of out-of-fold.  Below this, fall back to OOF.
MIN_PRIOR_TRAINING_SAMPLES = 200
# Number of player-folds for out-of-fold box BPR prediction
BOX_BPR_OOF_FOLDS = 5

# ── Box BPR feature weights (initial guess; overwritten when model is trained) ─
# These are used as fallback if no trained box model artifact exists.
# Deviation: not EvanMiya's published weights (those are not public). These are
# directionally calibrated approximations using known BPM-style research.
# Offensive term contributions (per 100 possessions, relative to league avg):
#   pts: ~0.5 (each pt above avg = +0.5 raw; adjusted for usage context)
#   ast: ~0.7 (assists reduce teammate scoring burden significantly)
#   tov: ~-1.0 (turnovers end possessions entirely)
#   fta: ~0.1 (drawing fouls = small positive when above avg)
#   efg_bonus: ~15.0 * (efg - avg_efg) (shooting efficiency above avg)
#   oreb: ~0.3 per 100 poss above avg (offensive rebounding)
# Defensive term contributions:
#   dreb: ~0.3 per 100 poss above avg
#   stl:  ~2.5 per 100 poss above avg (steals end possessions)
#   blk:  ~0.8 per 100 poss above avg (blocks often lead to long rebounds)
#   pf:   ~-0.1 (fouls give opponent FTs)
#
# These fallback weights are ONLY used if the box model has never been trained.
# Once fit_ncaa_box_bpr runs successfully, the DB artifact supersedes these.

# ── Preseason model ───────────────────────────────────────────────────────────
# Ridge regression sub-models (returner + transfer) replace the flat box+history blend.
# Minimum training pairs required to use the model (else fall back to box+history blend).
PRESEASON_MIN_PAIRS = 100
# Ridge alpha grid for cross-validated model selection.
PRESEASON_ALPHAS = [0.01, 0.1, 1.0, 5.0, 10.0, 50.0, 100.0, 500.0]
# Fallback prior SDs when preseason model is unavailable (slightly tighter than PRIOR_SD_BOX_*).
PRESEASON_FALLBACK_SD_RETURNER_OFF = 2.5
PRESEASON_FALLBACK_SD_RETURNER_DEF = 2.0
PRESEASON_FALLBACK_SD_TRANSFER_OFF = 3.0
PRESEASON_FALLBACK_SD_TRANSFER_DEF = 2.5
# Low-possession uncertainty add-on: players with < this many off-poss get +σ added.
PRESEASON_LOW_POSS_THRESHOLD = 300
PRESEASON_LOW_POSS_SD_BONUS  = 0.4

# ── Box BPR regularization ────────────────────────────────────────────────────
# Separate alpha grids for off and def (v1.3): defense benefits from stronger
# regularization because defensive box stats are noisier predictors of on-court DBPR.
BOX_BPR_ALPHAS_OFF = [0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 50.0]
BOX_BPR_ALPHAS_DEF = [0.1, 0.5, 1.0, 5.0, 10.0, 50.0, 100.0, 200.0]
# Backward-compat alias (used outside the box_bpr module)
BOX_BPR_ALPHAS = BOX_BPR_ALPHAS_OFF
BOX_BPR_CV_FOLDS = 5

# ── Box BPR inference possession floor ───────────────────────────────────────
# Minimum off_poss to allow box BPR as a fallback (players below this get null).
# Prevents per-100 inflation for players with near-zero lineup possessions
# (e.g. off_poss=1 → pts100 = pts_pg × gp × 100 → absurd predictions).
# Players with off_poss in [MIN_BOX_BPR_INFERENCE_POSS, MIN_OFF_POSS_BPR) get
# box BPR; players with off_poss >= MIN_OFF_POSS_BPR get RAPM BPR.
MIN_BOX_BPR_INFERENCE_POSS = 50

# ── BPR output bounds — HARD CAPS at write time ───────────────────────────────
# Hard clamp applied in _write_bpr_results(); prevents DB corruption from
# extreme RAPM coefficients on low-possession / badly-calibrated training seasons.
# Based on historical BPM/RAPM distributions in published research.
# Elite college players: ~8-14 BPR
# Strong starters: ~4-8
# Average starters: ~0-4
# Average bench: ~-3 to 0
# Poor rotation players: below -3
BPR_PLAUSIBLE_RANGE = (-20.0, 20.0)   # Flag, not clamp
OBPR_PLAUSIBLE_RANGE = (-15.0, 15.0)
DBPR_PLAUSIBLE_RANGE = (-12.0, 12.0)


# ── Recruiting-tier preseason priors (Phase C1) ───────────────────────────────
# Used when a player has no prior college BPR data (true freshmen, first-year
# internationals) but has a PlayerRecruitingProfile for their class_year.
# Values are OBPR/DBPR in pts/100 poss above D1 average expected in year 1.
#
# Calibration rationale (approximate empirical targets):
#   5-star  (top ~50 nationally):  elite NBA prospects; many earn +1.5-3.0 yr-1 OBPR
#   4-star  (~50-200):             high-end contributors; avg ~+0.5 yr-1 OBPR
#   3-star  (~200-500):            average college player; ~0.0
#   2-star  (~500-1000):           below-average starter; slight negative
#   1-star / unrated:              walk-on/marginal; near current default (0.0, wide SD)
#
# Note: Defense is harder to project from recruiting rank alone (lower signal).
# These are conservative — we widen the SD rather than trust the mean heavily.
RECRUITING_PRIOR_MEAN_OFF: dict[int, float] = {
    5: 2.5,   # raised from 1.5; empirical 5-star mean outcome ~2.1
    4: 0.8,   # raised from 0.5
    3: 0.0,
    2: -0.3,
    1: -0.5,
}
RECRUITING_PRIOR_MEAN_DEF: dict[int, float] = {
    5: 1.0,   # raised from 0.8
    4: 0.4,   # raised from 0.3
    3: 0.0,
    2: -0.2,
    1: -0.3,
}

# National rank continuous bonus applied on top of the star-tier base mean.
# Decays linearly: bonus = BONUS_MAX × max(0, 1 − national_rank / RANK_CUTOFF)
# Only applied when national_rank is available; only for 5-star and 4-star tiers.
RECRUITING_RANK_BONUS_OFF: dict[int, float] = {5: 1.5, 4: 0.5}
RECRUITING_RANK_BONUS_DEF: dict[int, float] = {5: 0.6, 4: 0.2}
RECRUITING_RANK_CUTOFF:    dict[int, int]   = {5: 60, 4: 250}

# Destination team adj_em context: strong programs → freshman more likely to contribute.
# Small positive multiplier; floored at 0 (no penalty for weak programs).
RECRUITING_TEAM_ADJM_FACTOR_OFF = 0.008   # adj_em=40 → +0.32
RECRUITING_TEAM_ADJM_FACTOR_DEF = 0.004   # smaller — defense harder to predict from team context

# Prior SDs by star tier — higher-star = more informative prior (narrower SD).
# Still wider than box BPR SDs (recruiting rank << in-season box stats in precision).
RECRUITING_PRIOR_SD_OFF: dict[int, float] = {
    5: 2.0,
    4: 2.5,
    3: 3.0,
    2: 3.5,
    1: 4.0,
}
RECRUITING_PRIOR_SD_DEF: dict[int, float] = {
    5: 1.5,
    4: 2.0,
    3: 2.5,
    2: 3.0,
    1: 3.0,
}

# Fallback tier for unrated recruits (no star data, but profile exists)
RECRUITING_UNRATED_PRIOR_MEAN_OFF = -0.2
RECRUITING_UNRATED_PRIOR_MEAN_DEF = -0.1
RECRUITING_UNRATED_PRIOR_SD_OFF   = PRIOR_SD_DEFAULT_OFF   # 4.0
RECRUITING_UNRATED_PRIOR_SD_DEF   = PRIOR_SD_DEFAULT_DEF   # 3.0
