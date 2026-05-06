"""
box_bpr.py — NBA Box-score Bayesian Performance Rating.

Trains two Ridge regression models (offensive and defensive) that map
per-100-possession box-score features to on-court impact targets, then
generates box_obpr / box_dbpr for each qualified player.

Stage 1 training targets: o_mpir / d_mpir (NBA.com E_OFF/DEF_RATING
residuals relative to league average). These are the best available
proxy until RAPM stint data is added in Stage 2, at which point we
retrain with baseline_obpr / baseline_dbpr targets.

Compared with NCAA box_bpr.py:
  - No pf100 / pf_per_min — personal fouls not stored in NBAPlayerSeasonStats
  - No on_court_tov_edge / on_court_reb_edge — NBA stints not yet available
  - d_mpir and on_court_adj_d added as first-class defensive signals
  - Archetypes encoded as 6-dim one-hot (vs NCAA tag-based separate models)
  - on_court_poss used for both off and def possession denominators (proxy)
  - MIN_POSS = 500 (vs NCAA 100) — 82-game season yields larger samples
"""

from __future__ import annotations

import logging
from collections import defaultdict

import numpy as np
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from nba.analytics.archetypes import ALL_ARCHETYPES, archetype_onehot, classify_nba_archetype

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

MIN_POSS = 500           # minimum on_court_poss to qualify for box BPR
MIN_GP = 20              # minimum games played
MIN_MPG = 12.0           # minimum minutes per game

BOX_BPR_ALPHAS_OFF = [0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 50.0]
BOX_BPR_ALPHAS_DEF = [0.1, 0.5, 1.0, 5.0, 10.0, 50.0, 100.0, 200.0]
BOX_BPR_CV_FOLDS = 5

# Feature lists — order must match extract_nba_box_features()
OFF_FEATURES = [
    "pts100", "ast100", "tov100", "oreb100",
    "fga100", "fg3a100", "fta100",
    "efg_pct", "ts_pct", "usg_pct",
    "min_share", "fg3_rate", "ft_rate", "ast_tov_ratio",
    "opp_quality", "usage_rate", "ast_rate",
    "on_off_adj_em_delta",
] + [f"arch_{a}" for a in ALL_ARCHETYPES]

DEF_FEATURES = [
    "stl100", "blk100", "dreb100",
    "d_mpir", "on_court_adj_d",
    "stl_pct", "blk_pct",
    "fg3a_share", "oreb_share", "min_share",
    "opp_quality", "on_off_adj_em_delta",
] + [f"arch_{a}" for a in ALL_ARCHETYPES]


# ── Opponent quality ──────────────────────────────────────────────────────────

def compute_opp_quality_map(season_year: int) -> dict[int, float]:
    """
    Return {team_id: mean_opponent_adj_net} for all teams in the season.

    For each game, the opponent quality contribution equals the opposing
    team's season adj_net. We average across all games per team so that
    players on difficult-schedule teams get a positive opp_quality signal.
    """
    from nba.models import NBAGame, NBATeamSeasonRatings

    # Build season adj_net lookup
    team_adj: dict[int, float] = {
        r.team_id: r.adj_net
        for r in NBATeamSeasonRatings.objects.filter(
            season__year=season_year,
            adj_net__isnull=False,
        ).only("team_id", "adj_net")
    }

    if not team_adj:
        logger.warning("No NBATeamSeasonRatings found for season %s — opp_quality=0 for all", season_year)
        return {}

    opp_totals: dict[int, list[float]] = defaultdict(list)

    for game in NBAGame.objects.filter(
        season__year=season_year,
        counts_toward_regular_season=True,
        status="Final",
    ).only("home_team_id", "away_team_id"):
        home_adj = team_adj.get(game.home_team_id)
        away_adj = team_adj.get(game.away_team_id)
        if home_adj is not None and away_adj is not None:
            opp_totals[game.home_team_id].append(away_adj)
            opp_totals[game.away_team_id].append(home_adj)

    return {
        team_id: float(np.mean(vals))
        for team_id, vals in opp_totals.items()
        if vals
    }


def compute_team_adj_em_map(season_year: int) -> dict[int, float]:
    """Return {team_id: adj_net} for use in on-off delta computation."""
    from nba.models import NBATeamSeasonRatings

    return {
        r.team_id: r.adj_net
        for r in NBATeamSeasonRatings.objects.filter(
            season__year=season_year,
            adj_net__isnull=False,
        ).only("team_id", "adj_net")
    }


# ── Feature extraction ────────────────────────────────────────────────────────

def extract_nba_box_features(
    stats: list[dict],
    opp_quality_map: dict[int, float],
    team_adj_em_map: dict[int, float],
) -> dict[int, dict]:
    """
    Compute per-100-possession features for each qualified player.

    stats: list of dicts from NBAPlayerSeasonStats.values(...)
    Returns: {player_id: {"off": [...], "def": [...], "archetype": str}}
    Only includes players meeting minimum qualifications.
    """
    features: dict[int, dict] = {}

    for p in stats:
        pid = p.get("player_id") or p.get("id")
        if pid is None:
            continue

        gp = p.get("gp") or 0
        mpg = p.get("mpg") or 0.0
        poss = p.get("on_court_poss") or 0.0

        if gp < MIN_GP or mpg < MIN_MPG or poss < MIN_POSS:
            continue

        def per100(stat_pg: float, poss: float) -> float:
            if poss <= 0:
                return 0.0
            return (stat_pg * gp) / poss * 100.0

        pts_pg   = p.get("pts") or 0.0
        ast_pg   = p.get("ast") or 0.0
        tov_pg   = p.get("tov") or 0.0
        oreb_pg  = p.get("oreb_pg") or 0.0
        dreb_pg  = p.get("dreb_pg") or 0.0
        fga_pg   = p.get("fga_pg") or 0.0
        fg3a_pg  = p.get("fg3a_pg") or 0.0
        fta_pg   = p.get("fta_pg") or 0.0
        stl_pg   = p.get("stl") or 0.0
        blk_pg   = p.get("blk") or 0.0
        efg_pct  = p.get("efg_pct") or 0.0
        ts_pct   = p.get("ts_pct") or 0.0
        usg_pct  = p.get("usg_pct") or 0.0
        ast_to   = p.get("ast_to") or 0.0
        stl_pct  = p.get("stl_pct") or 0.0
        blk_pct  = p.get("blk_pct") or 0.0
        oreb_pct = p.get("oreb_pct") or 0.0
        d_mpir   = p.get("d_mpir") or 0.0
        on_ct_adj_d = p.get("on_court_adj_d") or 0.0

        min_share = min(mpg / 48.0, 1.0)

        team_id = p.get("team_id")
        opp_quality = opp_quality_map.get(team_id, 0.0) if team_id else 0.0

        # On-off delta: player's on-court net rating minus team baseline.
        # Possession-dampened to reduce noise from small samples.
        _on_ct_adj_em = p.get("on_court_adj_em")
        if _on_ct_adj_em is not None:
            team_em = team_adj_em_map.get(team_id, 0.0) if team_id else 0.0
            _raw_delta = float(_on_ct_adj_em) - team_em
            _poss_scale = min((poss / 3000.0) ** 1.5, 1.0)
            on_off_delta = max(min(_raw_delta * _poss_scale, 6.0), -6.0)
        else:
            on_off_delta = 0.0

        archetype = classify_nba_archetype(
            usg_pct=usg_pct,
            ast_pct=p.get("ast_pct"),
            fg3a_pg=fg3a_pg,
            oreb_pct=oreb_pct,
            blk_pct=blk_pct,
            d_mpir=d_mpir,
        )
        arch_vec = archetype_onehot(archetype)

        fga100  = per100(fga_pg, poss)
        fta100  = per100(fta_pg, poss)
        tov100  = per100(tov_pg, poss)
        ast100  = per100(ast_pg, poss)
        usage_rate = fga100 + 0.44 * fta100 + tov100
        ast_rate = ast100 / max(usage_rate, 1.0)

        total_reb_pg = oreb_pg + dreb_pg

        off_feat = [
            per100(pts_pg, poss),           # pts100
            ast100,                          # ast100
            tov100,                          # tov100
            per100(oreb_pg, poss),           # oreb100
            fga100,                          # fga100
            per100(fg3a_pg, poss),           # fg3a100
            fta100,                          # fta100
            efg_pct,                         # efg_pct
            ts_pct,                          # ts_pct
            usg_pct,                         # usg_pct
            min_share,                       # min_share
            fg3a_pg / max(fga_pg, 0.01),     # fg3_rate
            fta_pg  / max(fga_pg, 0.01),     # ft_rate
            ast_to,                          # ast_tov_ratio (pre-computed by NBA.com)
            opp_quality,                     # opp_quality
            usage_rate,                      # usage_rate
            ast_rate,                        # ast_rate
            on_off_delta,                    # on_off_adj_em_delta
        ] + arch_vec

        def_feat = [
            per100(stl_pg, poss),            # stl100
            per100(blk_pg, poss),            # blk100
            per100(dreb_pg, poss),           # dreb100
            d_mpir,                          # d_mpir (NBA-exclusive signal)
            on_ct_adj_d,                     # on_court_adj_d
            stl_pct,                         # stl_pct
            blk_pct,                         # blk_pct
            fg3a_pg / max(fga_pg, 0.01),     # fg3a_share (position proxy)
            oreb_pg / max(total_reb_pg, 0.01), # oreb_share
            min_share,                       # min_share
            opp_quality,                     # opp_quality
            on_off_delta,                    # on_off_adj_em_delta
        ] + arch_vec

        features[pid] = {"off": off_feat, "def": def_feat, "archetype": archetype}

    return features


# ── Model training ────────────────────────────────────────────────────────────

def _build_pipeline(alphas: list[float]) -> Pipeline:
    return Pipeline([
        ("scaler", StandardScaler()),
        ("ridge",  RidgeCV(alphas=alphas, cv=BOX_BPR_CV_FOLDS, scoring="neg_mean_squared_error")),
    ])


def train_nba_box_bpr(
    stats: list[dict],
    opp_quality_map: dict[int, float],
    team_adj_em_map: dict[int, float],
    target_obpr: dict[int, float],   # player_id → offensive target (o_mpir or baseline_obpr)
    target_dbpr: dict[int, float],   # player_id → defensive target (d_mpir or baseline_dbpr)
) -> dict:
    """
    Train offensive and defensive Box BPR models.

    Returns artifact dict with fitted pipelines and diagnostics.
    """
    box_features = extract_nba_box_features(stats, opp_quality_map, team_adj_em_map)

    off_X, off_y, off_pids = [], [], []
    def_X, def_y, def_pids = [], [], []

    for pid, feats in box_features.items():
        if pid in target_obpr:
            off_X.append(feats["off"])
            off_y.append(target_obpr[pid])
            off_pids.append(pid)
        if pid in target_dbpr:
            def_X.append(feats["def"])
            def_y.append(target_dbpr[pid])
            def_pids.append(pid)

    if len(off_X) < 20 or len(def_X) < 20:
        raise ValueError(
            f"Too few training samples: {len(off_X)} offense, {len(def_X)} defense. "
            "Need at least 20 each."
        )

    off_pipe = _build_pipeline(BOX_BPR_ALPHAS_OFF)
    def_pipe = _build_pipeline(BOX_BPR_ALPHAS_DEF)

    off_pipe.fit(np.array(off_X), np.array(off_y))
    def_pipe.fit(np.array(def_X), np.array(def_y))

    off_cv_alpha = float(off_pipe.named_steps["ridge"].alpha_)
    def_cv_alpha = float(def_pipe.named_steps["ridge"].alpha_)

    logger.info(
        "Box BPR trained — off alpha=%.2f (n=%d), def alpha=%.2f (n=%d)",
        off_cv_alpha, len(off_X), def_cv_alpha, len(def_X),
    )

    return {
        "off_pipeline": off_pipe,
        "def_pipeline": def_pipe,
        "off_cv_alpha": off_cv_alpha,
        "def_cv_alpha": def_cv_alpha,
        "n_train_off": len(off_X),
        "n_train_def": len(def_X),
        "off_features": OFF_FEATURES,
        "def_features": DEF_FEATURES,
    }


def predict_nba_box_bpr(
    stats: list[dict],
    opp_quality_map: dict[int, float],
    team_adj_em_map: dict[int, float],
    model_artifacts: dict,
) -> dict[int, dict]:
    """
    Apply trained pipelines to generate box_obpr / box_dbpr for all qualified players.

    Returns: {player_id: {"box_obpr": float, "box_dbpr": float, "archetype": str}}
    """
    off_pipe = model_artifacts["off_pipeline"]
    def_pipe = model_artifacts["def_pipeline"]

    box_features = extract_nba_box_features(stats, opp_quality_map, team_adj_em_map)

    results: dict[int, dict] = {}
    for pid, feats in box_features.items():
        box_obpr = float(off_pipe.predict(np.array([feats["off"]]))[0])
        box_dbpr = float(def_pipe.predict(np.array([feats["def"]]))[0])
        results[pid] = {
            "box_obpr": round(box_obpr, 3),
            "box_dbpr": round(box_dbpr, 3),
            "archetype": feats["archetype"],
        }

    return results


def out_of_fold_box_bpr(
    stats: list[dict],
    opp_quality_map: dict[int, float],
    team_adj_em_map: dict[int, float],
    target_obpr: dict[int, float],
    target_dbpr: dict[int, float],
    n_folds: int = 5,
) -> tuple[dict[int, dict], dict]:
    """
    Generate out-of-fold predictions to avoid leakage when training and
    predicting on the same season.

    Returns (predictions_dict, model_artifacts_from_last_fold).
    predictions_dict: {player_id: {"box_obpr": float, "box_dbpr": float, "archetype": str}}
    """
    import random

    box_features = extract_nba_box_features(stats, opp_quality_map, team_adj_em_map)

    # Players with targets for both offense and defense
    eligible_pids = [
        pid for pid in box_features
        if pid in target_obpr and pid in target_dbpr
    ]
    random.shuffle(eligible_pids)

    fold_size = max(1, len(eligible_pids) // n_folds)
    oof_preds: dict[int, dict] = {}
    last_artifacts: dict = {}

    for fold_i in range(n_folds):
        val_pids = set(eligible_pids[fold_i * fold_size: (fold_i + 1) * fold_size])
        train_pids = [p for p in eligible_pids if p not in val_pids]

        train_stats = [s for s in stats if (s.get("player_id") or s.get("id")) in train_pids]

        artifacts = train_nba_box_bpr(
            stats=train_stats,
            opp_quality_map=opp_quality_map,
            team_adj_em_map=team_adj_em_map,
            target_obpr={p: target_obpr[p] for p in train_pids if p in target_obpr},
            target_dbpr={p: target_dbpr[p] for p in train_pids if p in target_dbpr},
        )

        val_stats = [s for s in stats if (s.get("player_id") or s.get("id")) in val_pids]
        fold_preds = predict_nba_box_bpr(val_stats, opp_quality_map, team_adj_em_map, artifacts)
        oof_preds.update(fold_preds)

        if fold_i == n_folds - 1:
            last_artifacts = artifacts

    logger.info("OOF box BPR complete — %d players with predictions", len(oof_preds))
    return oof_preds, last_artifacts
