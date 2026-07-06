"""
projection_transform.py — NCAA projection-time transform (experiment N-A).

    ncaa_projection_player_value(bpr, box_bpr, off_poss)
        = rel * bpr + (1 - rel) * box_bpr,   rel = off_poss / (off_poss + K)

THIS IS NOT BPR v1.8. Live NCAA rankings and player evaluation use v1.7 BPR
unchanged. This transform applies ONLY when season-Y ratings are used to
project season-Y+1 (cross-season team outlooks, year-ahead margin models).

Evidence (docs/bpr_audit/08, experiment N-A):
  - Cross-season 2025→26 margin RMSE: hard-gate 13.02 → 12.95 at K=1500,
    monotone in K, beats both pure endpoints.
  - Within-season: the same blend is WORSE at every cutoff — box-heavy
    weighting is a projection property (box transfers between seasons),
    not a rating property (RAPM carries live in-season signal).

Interpretation of K=1500: even an 800-possession starter projects forward
as ~65% box / 35% RAPM — most of a player's year-over-year portable value
is captured by the box model; the RAPM residual is real but less portable.
"""

from __future__ import annotations

PROJECTION_K = 1500.0
PROJECTION_TRANSFORM_VERSION = "nA-k1500"


def ncaa_projection_player_value(
    bpr: float | None,
    box_bpr: float | None,
    off_poss: float | None,
    k: float = PROJECTION_K,
) -> float | None:
    """Smooth reliability blend of live BPR and box BPR for forward projection.

    Returns None only when both inputs are missing.
    """
    if bpr is None and box_bpr is None:
        return None
    if bpr is None:
        return box_bpr
    if box_bpr is None:
        return bpr
    poss = max(0.0, off_poss or 0.0)
    rel = poss / (poss + k)
    return rel * bpr + (1.0 - rel) * box_bpr


def project_ratings_map(rows: "list[dict]", k: float = PROJECTION_K) -> dict[int, float]:
    """
    Bulk helper: rows of {player_id, bpr, box_bpr, off_poss} →
    {player_id: projection_value}. Convenience for team-outlook builders
    and the backtest suite's projection arms.
    """
    out: dict[int, float] = {}
    for r in rows:
        v = ncaa_projection_player_value(
            r.get("bpr"), r.get("box_bpr"), r.get("off_poss"), k=k)
        if v is not None:
            out[r["player_id"]] = v
    return out
