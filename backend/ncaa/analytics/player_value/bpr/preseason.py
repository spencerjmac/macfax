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
    RECRUITING_RANK_BONUS_OFF,
    RECRUITING_RANK_BONUS_DEF,
    RECRUITING_RANK_CUTOFF,
    RECRUITING_TEAM_ADJM_FACTOR_OFF,
    RECRUITING_TEAM_ADJM_FACTOR_DEF,
)


def build_prior_maps(
    player_ids: list[int],
    box_bpr_preds: dict[int, dict],  # player_id → {box_obpr, box_dbpr}  (from box_bpr.predict_box_bpr)
    prior_history: "dict[int, dict] | None" = None,  # player_id → {baseline_obpr, baseline_dbpr}
    recruiting_priors: "dict[int, dict] | None" = None,  # player_id → {stars, composite_score}
    preseason_preds: "dict[int, dict] | None" = None,  # player_id → {obpr_mean, dbpr_mean, obpr_sd, dbpr_sd}
    prior_sd_box_off: "float | None" = None,  # R²-derived; falls back to PRIOR_SD_BOX_OFF constant
    prior_sd_box_def: "float | None" = None,  # R²-derived; falls back to PRIOR_SD_BOX_DEF constant
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

    # Use R²-derived SDs when provided; fall back to constants otherwise.
    _sd_box_off = prior_sd_box_off if prior_sd_box_off is not None else PRIOR_SD_BOX_OFF
    _sd_box_def = prior_sd_box_def if prior_sd_box_def is not None else PRIOR_SD_BOX_DEF

    _recruiting = recruiting_priors or {}
    _preseason  = preseason_preds or {}

    for pid in player_ids:
        box  = box_bpr_preds.get(pid)
        hist = prior_history.get(pid) if prior_history else None
        rec  = _recruiting.get(pid)
        pre  = _preseason.get(pid)

        if pre is not None:
            # ── Preseason regression prior (best path) ────────────────────────
            # Learned Ridge regression combining prior RAPM history, current box
            # BPR, position, class year, and competition adjustment (transfers).
            # Prior SD comes from per-group residual variance of the trained model.
            prior_mean_obpr[pid] = pre["obpr_mean"]
            prior_mean_dbpr[pid] = pre["dbpr_mean"]
            prior_sd_obpr[pid]   = pre["obpr_sd"]
            prior_sd_dbpr[pid]   = pre["dbpr_sd"]

        elif box is not None:
            # ── Box BPR prior (fallback — no preseason model coverage) ────────
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
            prior_sd_obpr[pid]   = _sd_box_off
            prior_sd_dbpr[pid]   = _sd_box_def

        elif rec is not None:
            # ── Recruiting-tier prior (Phase C1 — freshmen with no box BPR) ──
            stars         = rec.get("stars")
            national_rank = rec.get("national_rank")
            team_adj_em   = float(rec.get("team_adj_em") or 0.0)

            if stars is not None and stars in RECRUITING_PRIOR_MEAN_OFF:
                base_off = RECRUITING_PRIOR_MEAN_OFF[stars]
                base_def = RECRUITING_PRIOR_MEAN_DEF[stars]

                # National rank bonus: decays linearly from BONUS_MAX at rank 1
                # to 0 at RANK_CUTOFF. Only applied for tiers with defined bonus.
                rank_bonus_off = 0.0
                rank_bonus_def = 0.0
                if national_rank is not None and stars in RECRUITING_RANK_BONUS_OFF:
                    cutoff = RECRUITING_RANK_CUTOFF[stars]
                    frac = max(0.0, 1.0 - national_rank / cutoff)
                    rank_bonus_off = RECRUITING_RANK_BONUS_OFF[stars] * frac
                    rank_bonus_def = RECRUITING_RANK_BONUS_DEF[stars] * frac

                # Team context: strong programs → freshman more likely to contribute
                team_bonus_off = max(0.0, team_adj_em * RECRUITING_TEAM_ADJM_FACTOR_OFF)
                team_bonus_def = max(0.0, team_adj_em * RECRUITING_TEAM_ADJM_FACTOR_DEF)

                prior_mean_obpr[pid] = base_off + rank_bonus_off + team_bonus_off
                prior_mean_dbpr[pid] = base_def + rank_bonus_def + team_bonus_def
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
