"""
Macfax Player Market Value — committed constants (Phase 6 Stage 2, 2026-07-17).

HUMAN-REVIEWED CONSTANTS — operator gate cleared on the Stage 1 derivation
(`manage.py derive_market_value`); do not auto-update. House doctrine applies:
"constants that feed a chain get sanity bounds at birth" — the derivation
command carries a plausibility guard (its logistic k must land in [0.01, 0.5];
the first fit attempt diverged to k=1.12 and was refused, which is why the
guard exists).

Chain: BPR → marginal EM → marginal wins → dollars. Valuation basis is
current-season ACTUALS.
"""

from __future__ import annotations

import hashlib

# ── Wins per EM (operator decision D1) ────────────────────────────────────────
# Convention B, logistic at league center, FLAT for all players:
#   P(win) = σ(0.1343·ΔEM + 0.544·home), fit on 28,259 D1-vs-D1 game results
#   2022-2026 → marginal wins per EM point on a 30-game league-average
#   schedule = 30·k/4 = 1.007.
# Convention A (schedule-blind OLS, slope 0.400 wins/30) REJECTED: schedule
# residuals are material (power-conference −2.45 wins/30, mid-major +0.68) —
# a comparative product must not price a player by who their conference makes
# them play. Same principle as the Phase 3 D1 demeaning ruling.
WINS_PER_EM_NCAA: float = 1.007

# ── Replacement level, ACTUALS side (operator decision D3) ────────────────────
# Minutes-weighted mean obpr/dbpr of players outside their team's top-8
# actual-minutes rotation (rank>8 by mpg), season 2026, N=897.
# NOT the projection-side REPLACEMENT_FILL constants (+0.255/+0.316): those
# are shrunk toward the mean by the projection pipeline; actuals are not.
# Offense diverges by ~0.94 BPR — real bench players genuinely hurt on offense.
REPLACEMENT_ACTUALS_OBPR: float = -0.681
REPLACEMENT_ACTUALS_DBPR: float = +0.312

# ── Dollar anchor (operator decision D2 — tightened range) ────────────────────
# 2026-27 school rev-share cap, public reporting.
CAP_2026_27: float = 21_300_000.0
# MBB pool share 17-23% of cap. Public anchors bracketing the range:
#   - Texas Tech publicly projected ~17-18% of its full rev-share pool to
#     men's basketball.
#   - Missouri MBB credited with 23.2% of department revenue / 23.3% of
#     payments to its NIL entity.
# Corroborating: power schools with FBS football expected to direct ~75% to
# football, leaving ≈$4M for MBB — inside this pool range.
# (Supersedes Stage 1's provisional 15-25%.)
MBB_SHARE_LOW: float = 0.17
MBB_SHARE_HIGH: float = 0.23
MBB_POOL_LOW: float = CAP_2026_27 * MBB_SHARE_LOW    # $3.621M
MBB_POOL_HIGH: float = CAP_2026_27 * MBB_SHARE_HIGH  # $4.899M

# ── $/marginal-win ────────────────────────────────────────────────────────────
# pool ÷ median power-conference roster's total positive marginal wins.
# Median = 18.77 (n=78 power rosters, 2026 actuals, derive_market_value).
MEDIAN_POWER_ROSTER_MWINS: float = 18.77
DOLLARS_PER_WIN_LOW: float = MBB_POOL_LOW / MEDIAN_POWER_ROSTER_MWINS    # ≈ $192.9k
DOLLARS_PER_WIN_HIGH: float = MBB_POOL_HIGH / MEDIAN_POWER_ROSTER_MWINS  # ≈ $261.0k

# ── Anchor B — DECLINED (operator decision D4, preserved verbatim) ────────────
# Third-party NIL multiplier: no defensible public multiplier exists (On3
# figures are model estimates, not payments; CSC-cleared deals are a
# non-representative fraction of the market). Documented decline per the
# Phase 3 D3 pattern; revisit only if a sourced multiplier appears.

METHODOLOGY_VERSION: str = "1.0-pending-signoff"


def constants_hash() -> str:
    """Provenance hash of the committed constant set (stored per value row)."""
    blob = repr(sorted({
        "WINS_PER_EM_NCAA": WINS_PER_EM_NCAA,
        "REPLACEMENT_ACTUALS_OBPR": REPLACEMENT_ACTUALS_OBPR,
        "REPLACEMENT_ACTUALS_DBPR": REPLACEMENT_ACTUALS_DBPR,
        "CAP_2026_27": CAP_2026_27,
        "MBB_SHARE_LOW": MBB_SHARE_LOW,
        "MBB_SHARE_HIGH": MBB_SHARE_HIGH,
        "MEDIAN_POWER_ROSTER_MWINS": MEDIAN_POWER_ROSTER_MWINS,
    }.items()))
    return hashlib.md5(blob.encode()).hexdigest()[:12]
