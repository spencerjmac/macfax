"""
Phase 4: Pace & Scheme Contextual Fit — constants.

All tunable weights, thresholds, caps, and reference distributions for the
pace and scheme compatibility layer.

Design principles
─────────────────
1. PACE IS SEASONING, NOT THE STEAK.
   Every pace modifier is tightly capped so it can never overpower the
   Phase 3 fit score.  Pace is a weak, noisy signal — the caps reflect that.

2. UNITS CONSISTENCY.
   Team adj_tempo (poss/game) is normalized to the same 0-100 scale used
   everywhere else in the fit model using:
       team_pace_score = 50 + ((adj_tempo - TEMPO_MEAN) / TEMPO_STD) * Z_TO_SCORE_SCALE
   Player pace tendency is computed on the same 0-100 scale, allowing a
   direct apples-to-apples comparison.

3. MISSING DATA IS TRULY NEUTRAL.
   If a team has no TeamSeasonRatings, all alignment scores are set to 50
   (neutral) and all modifiers to 0.  We never silently pretend a team is
   "average" — we just produce no signal.  has_team_style_data=False flags
   this explicitly.

4. HARD CAPS ARE ENFORCED AT EVERY LEVEL.
   Per-component modifier → combined contextual modifier → per-side total.
   Caps are enforced in engine.py after all components are summed.

5. PACE BIASED TOWARD OFFENSE.
   Pace alignment impacts offensive fit 100% and defensive fit 50%.
   Rationale: pace primarily governs how many offensive possessions a team
   gets, and secondarily how much stamina/rotation pressure is on defense.

Score scale
───────────
   All alignment scores: 0-100 (50 = perfectly neutral / no mismatch).
   All modifiers: signed float; negative = mismatch penalty, positive = bonus.

Reference calibration (2026 season, D1 teams with TeamSeasonRatings, n=361)
────────────────────────────────────────────────────────────────────────────
   adj_tempo:       mean=69.24  std=2.17
   adj_tov_pct:     mean=17.03  std=1.98
   adj_orb_pct:     mean=30.13  std=4.18
   adj_ftr:         mean=35.06  std=4.76
   adj_efg_pct:     mean=51.41  std=3.41
   adj_opp_tov_pct: mean=16.89  std=2.10
   adj_opp_orb_pct: mean=30.43  std=3.14
   adj_drb_pct:     mean=72.03  std=5.14
"""

# ── Score scale — mirrors Phase 3 conventions exactly ─────────────────────────
SCORE_MIN       = 0.0
SCORE_MAX       = 100.0
SCORE_MID       = 50.0    # neutral reference point (no alignment, no mismatch)
Z_TO_SCORE_SCALE = 15.0   # pts per 1σ on 0-100 scale
WINSOR_SIGMA     = 3.0    # z-score clamp before mapping

# ── Modifier caps ─────────────────────────────────────────────────────────────
# Pace: tightest cap — weakest and noisiest signal
MAX_PACE_MODIFIER_OFF   = 2.0   # pace modifier contribution to off_contextual
MAX_PACE_MODIFIER_DEF   = 1.0   # pace modifier contribution to def_contextual (50% of off)

# Scheme: slightly looser — more structurally meaningful
MAX_SCHEME_MODIFIER_OFF = 3.0
MAX_SCHEME_MODIFIER_DEF = 3.0

# Combined contextual total per side (hard outer cap)
MAX_CONTEXTUAL_TOTAL = 5.0   # clamps |off_contextual_modifier| and |def_contextual_modifier|

# ── Neutral sentinel ─────────────────────────────────────────────────────────
# Returned for alignment scores when no team style data available.
NEUTRAL_ALIGNMENT_SCORE = 50.0
NEUTRAL_MODIFIER        = 0.0

# ── Team-level style reference distributions (2026 calibration) ───────────────
# Format: (mean, std_dev)
REF_ADJ_TEMPO        = (69.24, 2.17)   # possessions per game (pace)
REF_ADJ_TOV_PCT      = (17.03, 1.98)   # offensive turnover % (lower = better discipline)
REF_ADJ_ORB_PCT      = (30.13, 4.18)   # offensive rebound % (glass crashing)
REF_ADJ_FTR          = (35.06, 4.76)   # free throw rate (pressure / foul-drawing offense)
REF_ADJ_EFG_PCT      = (51.41, 3.41)   # adjusted eFG% (efficiency-driven offense)
REF_ADJ_OPP_TOV_PCT  = (16.89, 2.10)   # opponent turnover % (defensive pressure)
REF_ADJ_OPP_ORB_PCT  = (30.43, 3.14)   # opponent offensive rebound % (def glass control)
REF_ADJ_DRB_PCT      = (72.03, 5.14)   # defensive rebound % (overall glass dominance)

# ── Player pace tendency weights ─────────────────────────────────────────────
# Positive signals → player prefers / enables faster pace
# Negative signals → player tends to slow pace
# tov_pg intentionally excluded: chaos ≠ deliberation, belongs in scheme
PACE_WEIGHT_FG3A  =  0.35   # spacers keep floor open → enable pace
PACE_WEIGHT_AST   =  0.35   # playmakers → transition capability
PACE_WEIGHT_STL   =  0.10   # steals → defensive transition opportunity (small)
PACE_WEIGHT_FTA   = -0.30   # foul-drawing slows game (FT stops the clock)
PACE_WEIGHT_OREB  = -0.30   # glass crashing → second-chance offense slows pace

# player pace reference distributions (from Phase 3 fit/constants.py 2026 cal.)
REF_PACE_FG3A_PG  = (2.44, 2.00)
REF_PACE_AST_PG   = (1.46, 1.21)
REF_PACE_STL_PG   = (0.70, 0.44)
REF_PACE_FTA_PG   = (2.16, 1.55)
REF_PACE_OREB_PG  = (0.96, 0.71)

# ── Scheme: offensive thresholds ─────────────────────────────────────────────
# Team style thresholds for tagging team offensive scheme
# "fast" tempo  ≥ TEMPO_MEAN + 1σ = 71.4
# "slow" tempo  ≤ TEMPO_MEAN - 1σ = 67.1

# spacing_driven: team relies on efficient eFG (high adj_efg_pct)
SPACING_DRIVEN_EFG_THRESHOLD      = 54.0   # ≈ mean + 0.75σ

# creator_driven: disciplined offense with low tov (ball-movement identity)
CREATOR_DRIVEN_TOV_MAX            = 15.5   # ≈ mean - 0.75σ (lower tov = creator driven)

# pressure_offense: high FTR — teams that get to the line a lot
PRESSURE_OFFENSE_FTR_THRESHOLD    = 39.0   # ≈ mean + 0.8σ

# glass_emphasis: high adj_orb_pct offensive glass control
GLASS_EMPHASIS_ORB_THRESHOLD      = 34.0   # ≈ mean + 0.9σ

# halfcourt_control: disciplined halfcourt — low tov, AND slow/mid tempo
HALFCOURT_CONTROL_TOV_MAX         = 16.0   # ≈ mean - 0.5σ (tight ball control)
HALFCOURT_CONTROL_TEMPO_MAX       = 68.5   # ≈ mean - 0.35σ (deliberate pace)

# ── Scheme: defensive thresholds ─────────────────────────────────────────────
# turnover_forcing: active pressure defense generating opponent turnovers
TURNOVER_FORCING_OPP_TOV_THRESHOLD  = 18.5  # ≈ mean + 0.77σ

# rim_anchored: dominant defensive glass + opponent ORB suppression
RIM_ANCHORED_DRB_THRESHOLD          = 76.0  # ≈ mean + 0.77σ
RIM_ANCHORED_OPP_ORB_MAX            = 28.0  # ≈ mean - 0.75σ (suppressing opp ORB)

# disciplined_rebounding: above-average defensive rebounding
DISC_REBOUNDING_DRB_THRESHOLD       = 72.0  # ≈ mean (at or above average)

# ── Rotation threshold ────────────────────────────────────────────────────────
# Mirrors Phase 3 fit/constants.py — players below this threshold are not
# counted in scheme composition checks (they don't affect team identity).
TOP_ROTATION_THRESHOLD = 0.075   # ≈ 3.0 mpg (minutes_share_p2 = mpg / 40)

# ── Roster composition thresholds for scheme tagging ─────────────────────────

# Spacing-driven team: at least this share of top-rotation minutes from spacers
ROSTER_SPACING_MIN_SHARE          = 0.30   # ≥ 30% of minutes from spacers
ROSTER_CREATOR_MIN_SHARE          = 0.20   # ≥ 20% of minutes from primary/secondary creators

# Pressure offense: foul-drawing players cover at least this share of minutes
ROSTER_PRESSURE_MIN_SHARE         = 0.25

# Glass emphasis: off rebounders cover this share
ROSTER_GLASS_MIN_SHARE            = 0.20

# Halfcourt control: low-tov disciplined players
ROSTER_HALFCOURT_LOW_TOV_MAX      = 1.0    # tov_pg ≤ this = disciplined player

# Rim-anchored D: rim_protectors in top rotation
ROSTER_RIM_PROTECTOR_MIN_SHARE    = 0.15   # ≥ 15% of minutes from rim protectors

# Turnover-forcing D: disruptors / high-stl players
ROSTER_DISRUPTOR_MIN_SHARE        = 0.20

# ── Alignment curve: mismatch distance → modifier ─────────────────────────────
# The alignment score (0-100) is mapped to a modifier via a piecewise linear
# function.  50 = neutral (modifier=0), 100 = perfect alignment, 0 = max mismatch.
#
# For pace: modifier = (alignment_score - 50) / 50 * MAX_PACE_MODIFIER_OFF
# For scheme: modifier = (alignment_score - 50) / 50 * MAX_SCHEME_MODIFIER
#
# This gives:
#   alignment=100 → max positive modifier
#   alignment=50  → 0 modifier
#   alignment=0   → max negative modifier
# Linear is intentional: simple, auditable, no hidden curve behavior.
