"""
Minutes model constants — Phase 2: Roster-context minutes allocation.

All tunable parameters for the Phase 2 minutes allocation model.
Override these to experiment with rotation shapes without touching model logic.

Phase 2 minutes model overview
───────────────────────────────
Each player's "demand score" is computed from:
  - Projected BPR (dominant signal)
  - Prior minutes / usage history (from the from_season PlayerSeasonStats)
  - Experience / returner trust
  - Projection uncertainty dampening

Demand scores are then:
  1. Roster-context adjusted (scarcity bonus, crowding penalty)
  2. Power-transformed for rotation concentration
  3. Water-fill normalized to sum to TEAM_TOTAL_SHARES (5.00)

Manual overrides pin individual players first; remaining shares are
distributed across unlocked players.

Conventions
───────────
  minutes_share = projected_mpg / 40
  TEAM_TOTAL_SHARES = 5.00   (5 players × 40 min = 200 team player-minutes)
"""

# ── Team minutes accounting ───────────────────────────────────────────────────
# 5 players × 40 min = 200 team player-minutes; 200 / 40 = 5.00 shares.
TEAM_TOTAL_SHARES = 5.0

# Per-player floor and ceiling applied during normalization.
#   Floor: 0.025 = 1.0 mpg — any rostered player can be scorecarded even
#          at the very bottom of the bench.  Set to 0.0 to allow true zero.
#   Ceiling: 0.875 = 35 mpg — elite starters rarely exceed this; allows
#            the rare star (Cooper Flagg, Zach Edey type) to reach ~35.
MINIMUM_PLAYER_SHARE = 0.025   # 1.0 mpg
MAXIMUM_PLAYER_SHARE = 0.875   # 35.0 mpg

# ── Demand score — BPR component ─────────────────────────────────────────────
# The BPR component shifts all BPR values above a replacement level floor,
# ensuring every player contributes a non-negative raw demand before other
# signals are added.
#
# A player sitting exactly at REPLACEMENT_BPR_FLOOR receives 0 from the BPR
# component.  National D1 average is 0; replacement-level players are typically
# in the −5 to −7 range for players who barely contribute.
REPLACEMENT_BPR_FLOOR = -7.0   # pts/100 poss; sets the zero point for demand
BPR_WEIGHT            = 1.0    # multiplier on the shifted BPR

# ── Demand score — prior playing-time component ───────────────────────────────
# Uses prior MPG (from the current season's PlayerSeasonStats) as a signal that
# the coaching staff trusts this player.  Normalized to [0, 1] by mpg / 40.
# Only applied when the player has logged enough meaningful games.
MPG_WEIGHT            = 0.5    # multiplier on (prior_mpg / 40)
MIN_GP_FOR_MPG_SIGNAL =  5     # minimum GP to trust the MPG signal

# ── Demand score — experience / trust component ───────────────────────────────
# Returner stability bump: a returning player has proven they fit the system.
# Experience accumulates per prior season in the DB, reflecting coaches'
# known-quantity preference.
RETURNER_STABILITY_BONUS      = 0.10   # added to demand score for returners
EXPERIENCE_BONUS_PER_SEASON   = 0.04   # per prior season in DB
MAX_EXPERIENCE_SEASONS        = 3      # cap — avoids over-rewarding grad-transfers

# ── Demand score — uncertainty dampening ─────────────────────────────────────
# Projection uncertainty (0 = confident, 1 = very uncertain) multiplicatively
# reduces demand.  The reduction is intentionally modest: we do not want to
# bury potentially great newcomers simply because they are unknown.
# UNCERTAINTY_DAMPEN = 0.15 means:
#   uncertainty = 1.0 → demand × (1 − 0.15) = 0.85  (15% reduction, max)
#   uncertainty = 0.4 → demand × 0.94                 (6% reduction, returner)
UNCERTAINTY_DAMPEN = 0.15

# ── Rotation concentration ────────────────────────────────────────────────────
# Power transform applied to demand scores before normalization.
#
# Higher power → sharper concentration in the top players.
# CONCENTRATION_POWER = 2.0 naturally delivers ~85–90% of a 5.00-share
# team budget to the top 8–9 players on a 13-man roster for realistic
# BPR distributions (top player ~8 pts/100, bottom ~−3 pts/100).
#
# Example with two players and scores 0.8 vs 0.2:
#   power=1.0 → weight ratio 4:1
#   power=2.0 → weight ratio 16:1     ← chosen default
#   power=3.0 → weight ratio 64:1     (too greedy for top player)
CONCENTRATION_POWER  = 2.0

# Absolute floor on individual demand scores before the power transform.
# Prevents exact-zero inputs from creating numerical degenerate cases.
MINIMUM_DEMAND_SCORE = 0.005

# ── Roster context — scarcity ─────────────────────────────────────────────────
# A team with only 1–2 credible players in a role bucket has no real option:
# those players must log major minutes regardless of their raw BPR rank.
SCARCITY_THRESHOLD = 2    # ≤ N players in a bucket → positional scarcity
SCARCITY_BONUS     = 0.15 # added to demand score (pre-power-transform)

# ── Roster context — crowding ─────────────────────────────────────────────────
# When many similar players compete for roles in the same bucket, the
# lower-ranked ones compress each other's minutes.
CROWDING_THRESHOLD        = 4    # > N players in a bucket → crowded bucket
CROWDING_PENALTY_START    = 3    # penalty applied from the Nth player down (1-indexed)
CROWDING_PENALTY_PER_SLOT = 0.08 # demand reduction per slot past CROWDING_PENALTY_START

# ── Role bucket thresholds (box-score fallbacks) ──────────────────────────────
# Used when Player.position is empty, "ATH", or "NA".
# A high-rebound / high-block player is almost certainly a big; a high-assist
# player with no block/reb dominance is almost certainly a guard.
BIG_BLK_THRESHOLD   = 1.0   # blocks/game
BIG_REB_THRESHOLD   = 6.5   # rebounds/game
GUARD_AST_THRESHOLD = 3.0   # assists/game (when no interior signals present)

# ── Normalization convergence ─────────────────────────────────────────────────
MAX_NORMALIZATION_ITERS = 25  # max water-filling passes before forced exit
