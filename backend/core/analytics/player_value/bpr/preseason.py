"""
preseason.py — Preseason prior computation for BPR.

Deviation from EvanMiya article (Deviation #4 in constants.py):
  The article uses player recruiting rankings and transfer portal ratings
  to set preseason priors for new/transferred players.  We do not have
  recruiting data, so we fall back to Box BPR from the most recent season
  with a slightly wider prior uncertainty.

  For players who:
    • Have Box BPR from the current or prior season  → use as prior mean
    • Have no BPR history (true freshmen, walk-ons)  → prior mean = 0 (league avg)
  
  Prior SDs:
    • box_bpr available   → PRIOR_SD_BOX_OFF / PRIOR_SD_BOX_DEF
    • no bpr history      → PRIOR_SD_DEFAULT_OFF / PRIOR_SD_DEFAULT_DEF

  Prior-history blending (v1.3):
    For returning players who have a prior-season baseline RAPM
    (baseline_obpr / baseline_dbpr stored from last year's pipeline run),
    the prior mean is blended between the box prediction and the historical
    actual:

        prior_mean = (1 - α) * box_bpr + α * prior_baseline_rapm

    where α = PRIOR_HISTORY_BLEND is a small weight giving gentle regression
    toward actual prior performance.  This dampens the defensive overrating
    that can occur when box priors lean too heavily on noisy defensive stats
    for players whose actual RAPM was lower.

  In-season update:
    As the season progresses and RAPM observations accumulate, the posterior
    for each player shifts from the prior toward the RAPM estimate.  With the
    augmented weighted least-squares formulation, the prior is implicit in the
    regularization terms and does not require explicit Bayesian updating.
"""

from __future__ import annotations

from core.analytics.player_value.bpr.constants import (
    PRIOR_SD_BOX_OFF,
    PRIOR_SD_BOX_DEF,
    PRIOR_SD_DEFAULT_OFF,
    PRIOR_SD_DEFAULT_DEF,
    PRIOR_HISTORY_BLEND,
)


def build_prior_maps(
    player_ids: list[int],
    box_bpr_preds: dict[int, dict],  # player_id → {box_obpr, box_dbpr}  (from box_bpr.predict_box_bpr)
    prior_history: "dict[int, dict] | None" = None,  # player_id → {baseline_obpr, baseline_dbpr}
) -> tuple[dict[int, float], dict[int, float], dict[int, float], dict[int, float]]:
    """
    Build prior mean and SD maps for all players in the RAPM dataset.

    Args:
        player_ids:    All player DB PKs in the current RAPM design matrix.
        box_bpr_preds: Current-season Box BPR predictions per player.
        prior_history: Optional dict of prior-season baseline RAPM values.
                       When provided, the prior mean for returning players is
                       blended: (1 - PRIOR_HISTORY_BLEND) * box + PRIOR_HISTORY_BLEND * history.

    Returns four dicts:
        prior_mean_obpr  player_id → float
        prior_mean_dbpr  player_id → float
        prior_sd_obpr    player_id → float
        prior_sd_dbpr    player_id → float
    """
    prior_mean_obpr: dict[int, float] = {}
    prior_mean_dbpr: dict[int, float] = {}
    prior_sd_obpr:   dict[int, float] = {}
    prior_sd_dbpr:   dict[int, float] = {}

    for pid in player_ids:
        box = box_bpr_preds.get(pid)
        hist = prior_history.get(pid) if prior_history else None

        if box is not None:
            box_obpr = box["box_obpr"]
            box_dbpr = box["box_dbpr"]

            if hist is not None:
                # Blend box prediction with prior-season actual baseline RAPM
                hist_obpr = hist.get("baseline_obpr")
                hist_dbpr = hist.get("baseline_dbpr")
                if hist_obpr is not None:
                    box_obpr = (1.0 - PRIOR_HISTORY_BLEND) * box_obpr + PRIOR_HISTORY_BLEND * hist_obpr
                if hist_dbpr is not None:
                    box_dbpr = (1.0 - PRIOR_HISTORY_BLEND) * box_dbpr + PRIOR_HISTORY_BLEND * hist_dbpr

            prior_mean_obpr[pid] = box_obpr
            prior_mean_dbpr[pid] = box_dbpr
            prior_sd_obpr[pid]   = PRIOR_SD_BOX_OFF
            prior_sd_dbpr[pid]   = PRIOR_SD_BOX_DEF
        else:
            # No box BPR available → flat prior centered at league average (0.0)
            prior_mean_obpr[pid] = 0.0
            prior_mean_dbpr[pid] = 0.0
            prior_sd_obpr[pid]   = PRIOR_SD_DEFAULT_OFF
            prior_sd_dbpr[pid]   = PRIOR_SD_DEFAULT_DEF

    return prior_mean_obpr, prior_mean_dbpr, prior_sd_obpr, prior_sd_dbpr
