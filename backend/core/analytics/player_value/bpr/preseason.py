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
)


def build_prior_maps(
    player_ids: list[int],
    box_bpr_preds: dict[int, dict],  # player_id → {box_obpr, box_dbpr}  (from box_bpr.predict_box_bpr)
) -> tuple[dict[int, float], dict[int, float], dict[int, float], dict[int, float]]:
    """
    Build prior mean and SD maps for all players in the RAPM dataset.

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
        if box is not None:
            prior_mean_obpr[pid] = box["box_obpr"]
            prior_mean_dbpr[pid] = box["box_dbpr"]
            prior_sd_obpr[pid]   = PRIOR_SD_BOX_OFF
            prior_sd_dbpr[pid]   = PRIOR_SD_BOX_DEF
        else:
            # No box BPR available → flat prior centered at league average (0.0)
            prior_mean_obpr[pid] = 0.0
            prior_mean_dbpr[pid] = 0.0
            prior_sd_obpr[pid]   = PRIOR_SD_DEFAULT_OFF
            prior_sd_dbpr[pid]   = PRIOR_SD_DEFAULT_DEF

    return prior_mean_obpr, prior_mean_dbpr, prior_sd_obpr, prior_sd_dbpr
