"""
Role bucket classification — Phase 2 minutes model.

Derives a three‑bucket position grouping (Guard / Wing / Big) from the
data that is reliably available in the codebase:
  primary   — Player.position (ESPN abbreviation: G, F, C, PG, SG, etc.)
  fallback  — box‑score rates (blk, reb, ast) for ambiguous/missing positions

Three‑bucket system rationale
──────────────────────────────
  • Player.position uses a small set of ESPN abbreviations (G, F, C dominate;
    minor: PG, SG, SF, PF, ATH, NA) that map cleanly to three groups.
  • Height / weight are absent from the codebase; box signals are the next
    best interior/perimeter discriminator.
  • Three buckets is granular enough to detect meaningful roster imbalances
    (e.g. "only one credible big", "five similar guards") without overfitting
    thin rosters.

Bucket definitions for roster insight
──────────────────────────────────────
  G    (Guard) — perimeter ball-handlers; high assist rates; primary creators
  Wing         — versatile forwards; can guard multiple positions; stretch risk
  Big          — interior players; post scorers / rim protectors / rebounders
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ncaa.analytics.player_value.minutes.constants import (
    BIG_BLK_THRESHOLD,
    BIG_REB_THRESHOLD,
    GUARD_AST_THRESHOLD,
    SCARCITY_THRESHOLD,
    SCARCITY_BONUS,
    CROWDING_THRESHOLD,
    CROWDING_PENALTY_START,
    CROWDING_PENALTY_PER_SLOT,
)

# ── Bucket name constants ─────────────────────────────────────────────────────
GUARD = "G"
WING  = "Wing"
BIG   = "Big"

ALL_BUCKETS: tuple[str, ...] = (GUARD, WING, BIG)

# ── ESPN position → bucket mapping ────────────────────────────────────────────
# Positions classified without needing box‑score signals.
_PURE_GUARD: frozenset[str] = frozenset({"G", "PG", "SG"})
_PURE_BIG:   frozenset[str] = frozenset({"C", "PF"})
_PURE_WING:  frozenset[str] = frozenset({"F", "SF"})
# Ambiguous hybrids — need box‑score tiebreaker.
_AMBIGUOUS:  frozenset[str] = frozenset({"ATH", "NA", ""})


def classify_role_bucket(
    position: str,
    blk_pg:   float = 0.0,
    reb_pg:   float = 0.0,
    ast_pg:   float = 0.0,
    fg3a_pg:  float = 0.0,
) -> str:
    """
    Classify a player into GUARD ("G"), WING ("Wing"), or BIG ("Big").

    Primary signal:   Player.position string from ESPN.
    Secondary signal: Box‑score per‑game rates for ambiguous or missing
                      positions ("F", "ATH", "NA", empty).

    Args:
        position:  Player.position ("G", "F", "C", "PG", "ATH", etc.)
        blk_pg:    Blocks per game  (from PlayerSeasonStats.blk)
        reb_pg:    Rebounds per game (from PlayerSeasonStats.reb)
        ast_pg:    Assists per game  (from PlayerSeasonStats.ast)
        fg3a_pg:   Three‑point attempts per game (supplementary context)

    Returns:
        "G", "Wing", or "Big"
    """
    pos = (position or "").strip().upper()

    # ── Unambiguous positions ─────────────────────────────────────────────────
    if pos in _PURE_GUARD:
        return GUARD
    if pos in _PURE_BIG:
        return BIG
    if pos in _PURE_WING:
        # Forwards that play like interior bigs — reclassify with box signals.
        if blk_pg >= BIG_BLK_THRESHOLD or reb_pg >= BIG_REB_THRESHOLD:
            return BIG
        return WING

    # ── Ambiguous / missing position — box‑score fallback ───────────────────
    # Order: Big signals are sharpest (blocks / rebounds are position-defining);
    # Guard signals next (assists); default to Wing as the safe middle bucket.
    if blk_pg >= BIG_BLK_THRESHOLD or reb_pg >= BIG_REB_THRESHOLD:
        return BIG
    if ast_pg >= GUARD_AST_THRESHOLD:
        return GUARD
    return WING  # safe default for truly unknown positions


@dataclass(frozen=True)
class BucketContext:
    """
    Roster‑level summary for a single role bucket.

    Attributes:
        bucket:     Bucket name ("G", "Wing", or "Big").
        count:      Number of players assigned to this bucket on this roster.
        is_scarce:  True when count ≤ SCARCITY_THRESHOLD.  Coach is forced to
                    play these players regardless of raw talent rank.
        is_crowded: True when count > CROWDING_THRESHOLD.  Competition for
                    minutes is high; lower‑ranked players are compressed.
    """
    bucket:     str
    count:      int
    is_scarce:  bool
    is_crowded: bool


def compute_bucket_contexts(
    player_buckets: dict[int, str],
) -> dict[str, BucketContext]:
    """
    Compute scarcity / crowding context for every role bucket on a roster.

    Args:
        player_buckets: {player_id: bucket} mapping for all rostered players.

    Returns:
        Dict mapping each bucket name to its BucketContext.
        All three buckets (G, Wing, Big) are always present in the output
        even when a roster has zero players in a bucket.
    """
    counts: dict[str, int] = defaultdict(int)
    for bucket in player_buckets.values():
        counts[bucket] += 1

    return {
        b: BucketContext(
            bucket=b,
            count=counts[b],
            is_scarce=(counts[b] <= SCARCITY_THRESHOLD),
            is_crowded=(counts[b] > CROWDING_THRESHOLD),
        )
        for b in ALL_BUCKETS
    }


def bucket_rank_by_bpr(
    player_id: int,
    player_buckets: dict[int, str],
    player_bpr:     dict[int, float],
) -> int:
    """
    Return the 1‑indexed rank of a player within their role bucket,
    sorted descending by projected BPR.

    Rank 1 = the best player in the bucket (highest projected BPR).
    Used to identify which players in a crowded bucket absorb the
    crowding penalty.

    Args:
        player_id:      The player to rank.
        player_buckets: {player_id: bucket} for all roster members.
        player_bpr:     {player_id: projected_bpr} for all roster members.

    Returns:
        1‑indexed rank (1 = best in bucket).
    """
    my_bucket = player_buckets[player_id]
    peers = sorted(
        ((pid, bpr) for pid, bpr in player_bpr.items() if player_buckets.get(pid) == my_bucket),
        key=lambda x: x[1],
        reverse=True,
    )
    for rank, (pid, _) in enumerate(peers, start=1):
        if pid == player_id:
            return rank
    return 1  # fallback — should never occur when player_id is in player_bpr
