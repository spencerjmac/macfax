"""
preseason.py — Preseason prior computation for BPR.

Deviation from EvanMiya article (Deviation #4 in constants.py):
  The article uses player recruiting rankings and transfer portal ratings
  to set preseason priors for new/transferred players.  We partially
  implement this via PlayerRecruitingProfile:

  For players who:
    • Have Box BPR from the current or prior season  → use as prior mean
    • Have a recruiting profile (no box BPR yet)     → recruiting-tier prior mean + SD
    • Neither (walk-ons, unregistered players)       → prior mean = 0 (league avg)
  
  Prior SDs:
    • box_bpr available          → PRIOR_SD_BOX_OFF / PRIOR_SD_BOX_DEF
    • recruiting profile only    → RECRUITING_PRIOR_SD_OFF[stars] / DEF[stars]
    • no bpr, no profile         → PRIOR_SD_DEFAULT_OFF / PRIOR_SD_DEFAULT_DEF

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

from ncaa.analytics.player_value.bpr.constants import (
    PRIOR_SD_BOX_OFF,
    PRIOR_SD_BOX_DEF,
    PRIOR_SD_DEFAULT_OFF,
    PRIOR_SD_DEFAULT_DEF,
    PRIOR_HISTORY_BLEND,
    RECRUITING_PRIOR_MEAN_OFF,
    RECRUITING_PRIOR_MEAN_DEF,
    RECRUITING_PRIOR_SD_OFF,
    RECRUITING_PRIOR_SD_DEF,
    RECRUITING_UNRATED_PRIOR_MEAN_OFF,
    RECRUITING_UNRATED_PRIOR_MEAN_DEF,
    RECRUITING_UNRATED_PRIOR_SD_OFF,
    RECRUITING_UNRATED_PRIOR_SD_DEF,
)


def build_prior_maps(
    player_ids: list[int],
    box_bpr_preds: dict[int, dict],  # player_id → {box_obpr, box_dbpr}  (from box_bpr.predict_box_bpr)
    prior_history: "dict[int, dict] | None" = None,  # player_id → {baseline_obpr, baseline_dbpr}
    recruiting_priors: "dict[int, dict] | None" = None,  # player_id → {stars, composite_score}
) -> tuple[dict[int, float], dict[int, float], dict[int, float], dict[int, float]]:
    """
    Build prior mean and SD maps for all players in the RAPM design matrix.

    Args:
        player_ids:         All player DB PKs in the current RAPM design matrix.
        box_bpr_preds:      Current-season Box BPR predictions per player.
        prior_history:      Optional dict of prior-season baseline RAPM values.
                            When provided, the prior mean for returning players is
                            blended: (1 - PRIOR_HISTORY_BLEND) * box + PRIOR_HISTORY_BLEND * history.
        recruiting_priors:  Optional dict of recruiting profiles for freshmen.
                            Keyed by player_id.  Each value has at least:
                                stars           int | None  (1-5, or None for unrated)
                                composite_score float | None
                            Used as prior when no box BPR is available.

    Returns four dicts keyed by player_id:
        prior_mean_obpr, prior_mean_dbpr, prior_sd_obpr, prior_sd_dbpr
    """
    prior_mean_obpr: dict[int, float] = {}
    prior_mean_dbpr: dict[int, float] = {}
    prior_sd_obpr:   dict[int, float] = {}
    prior_sd_dbpr:   dict[int, float] = {}

    _recruiting = recruiting_priors or {}

    for pid in player_ids:
        box  = box_bpr_preds.get(pid)
        hist = prior_history.get(pid) if prior_history else None
        rec  = _recruiting.get(pid)

        if box is not None:
            # ── Box BPR prior (primary path — most accurate) ─────────────────
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

        elif rec is not None:
            # ── Recruiting-tier prior (Phase C1 — freshmen with no box BPR) ──
            stars = rec.get("stars")
            if stars is not None and stars in RECRUITING_PRIOR_MEAN_OFF:
                prior_mean_obpr[pid] = RECRUITING_PRIOR_MEAN_OFF[stars]
                prior_mean_dbpr[pid] = RECRUITING_PRIOR_MEAN_DEF[stars]
                prior_sd_obpr[pid]   = RECRUITING_PRIOR_SD_OFF[stars]
                prior_sd_dbpr[pid]   = RECRUITING_PRIOR_SD_DEF[stars]
            else:
                # Unrated or stars outside 1-5
                prior_mean_obpr[pid] = RECRUITING_UNRATED_PRIOR_MEAN_OFF
                prior_mean_dbpr[pid] = RECRUITING_UNRATED_PRIOR_MEAN_DEF
                prior_sd_obpr[pid]   = RECRUITING_UNRATED_PRIOR_SD_OFF
                prior_sd_dbpr[pid]   = RECRUITING_UNRATED_PRIOR_SD_DEF

        else:
            # ── Flat prior — no box BPR, no recruiting profile ───────────────
            prior_mean_obpr[pid] = 0.0
            prior_mean_dbpr[pid] = 0.0
            prior_sd_obpr[pid]   = PRIOR_SD_DEFAULT_OFF
            prior_sd_dbpr[pid]   = PRIOR_SD_DEFAULT_DEF

    return prior_mean_obpr, prior_mean_dbpr, prior_sd_obpr, prior_sd_dbpr
