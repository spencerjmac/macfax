"""
box_bpr.py — NBA Box-score Bayesian Performance Rating (Box Prior).

Trains two Ridge regression models (offensive and defensive) that map
per-100-possession box-score features to on-court impact targets, then
generates box_obpr / box_dbpr for each qualified player.

CURRENT PRODUCTION STATE (2025-26 season):

Training targets:
  Stage 1: o_mpir / d_mpir (NBA.com E_OFF/DEF_RATING residuals)
  Stage 2: baseline_obpr / baseline_dbpr (single-season RAPM targets)
  RAPM-only training: players without RAPM coverage excluded from
  training set (predicted only). See rapm_pids parameter.

Career stabilization (Phase 1 + Phase 2):
  Rate stats stabilized (Tier 1): ts_pct, fg3_pct, ft_pct, ast_pct,
    stl_pct, blk_pct, oreb_pct — possession-weighted career average
    blended with current season using full career weight.
  Counting stats stabilized (Tier 2, role-discounted): pts100, ast100,
    stl100, blk100, dreb100, oreb100, tov100, fga100, fg3a100, fta100
    — career average blended at 50% weight vs current season.
  Not stabilized (Tier 3 — current context only): on_court_adj_o/d/em,
    d_mpir, o_mpir, mpir, per-game counting stats, on_off_delta,
    opp_quality, team residual features.
  Career data window: 2016 to target season (up to 10 seasons).

Regularization:
  Alpha pinned: off=5.0, def=10.0 (not CV-selected).
  Rationale: CV selected wildly different alphas year-to-year
  (range 5-200) causing prior scale instability. Fixed alpha
  ensures consistent prior scale across all seasons.

Known properties:
  - Context-adjusted: players on winning lineups rated higher
  - Intentionally differs from BPM (pure box score)
  - Stars on underperforming teams rated lower than pure skill
    would suggest — this is expected behavior, not a bug

Compared with NCAA box_bpr.py:
  - No pf100 / pf_per_min — personal fouls not stored in NBAPlayerSeasonStats
  - d_mpir and on_court_adj_d added as first-class defensive signals
  - Archetypes encoded as 6-dim one-hot (vs NCAA tag-based separate models)
  - on_court_poss used for both off and def possession denominators
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

BOX_BPR_ALPHAS_OFF = [5.0]
BOX_BPR_ALPHAS_DEF = [10.0]
BOX_BPR_CV_FOLDS = 5

# Feature lists — order must match extract_nba_box_features()
OFF_FEATURES = [
    "pts100", "ast100", "tov100", "oreb100",
    "fga100", "fg3a100", "fta100",
    "efg_pct", "ts_pct", "usg_pct",
    "min_share", "fg3_rate", "ft_rate", "ast_tov_ratio",
    "opp_quality", "usage_rate", "ast_rate",
    "on_off_adj_em_delta",
    # USG × efficiency interactions — captures high-efficiency at high usage
    "usg_x_ts", "usg_x_efg", "usg_sq",
    "ts_above_avg", "usg_x_ts_above",
    # Team-quality residuals — player contribution above teammates
    "ts_vs_team", "ortg_vs_team",
] + [f"arch_{a}" for a in ALL_ARCHETYPES]

DEF_FEATURES = [
    "stl100", "blk100", "dreb100",
    "d_mpir", "on_court_adj_d",
    "stl_pct", "blk_pct",
    "fg3a_share", "oreb_share", "min_share",
    "opp_quality", "on_off_adj_em_delta",
    # Team-quality residual — player's on-court def vs team average
    "d_vs_team",
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
    career_stats_map: dict[int, dict[str, float]] | None = None,
) -> dict[int, dict]:
    """
    Compute per-100-possession features for each qualified player.

    career_stats_map: when provided, Tier 1/2 rate stats are replaced with
    career-stabilized estimates from career_stats.build_career_stats_map().
    Tier 3 stats (role/context) always come from the current season row.
    When None, behaviour is identical to the original implementation.

    stats: list of dicts from NBAPlayerSeasonStats.values(...)
    Returns: {player_id: {"off": [...], "def": [...], "archetype": str}}
    Only includes players meeting minimum qualifications.
    """
    # ── Pre-pass: league and team-level averages for residual features ─────────
    # Weighted by on_court_poss so bench players don't distort team baselines.
    _ts_num = 0.0
    _ts_den = 0.0
    _team_ts_num:   dict[int, float] = defaultdict(float)
    _team_ts_den:   dict[int, float] = defaultdict(float)
    _team_ortg_num: dict[int, float] = defaultdict(float)
    _team_ortg_den: dict[int, float] = defaultdict(float)
    _team_drtg_num: dict[int, float] = defaultdict(float)
    _team_drtg_den: dict[int, float] = defaultdict(float)

    for _p in stats:
        _tid  = _p.get("team_id")
        _poss = float(_p.get("on_court_poss") or 0)
        if _poss <= 0:
            continue
        _ts   = _p.get("ts_pct")
        _ortg = _p.get("on_court_adj_o")
        _drtg = _p.get("on_court_adj_d")
        if _ts is not None:
            _ts_num += float(_ts) * _poss
            _ts_den += _poss
            if _tid:
                _team_ts_num[_tid] += float(_ts) * _poss
                _team_ts_den[_tid] += _poss
        if _tid:
            if _ortg is not None:
                _team_ortg_num[_tid] += float(_ortg) * _poss
                _team_ortg_den[_tid] += _poss
            if _drtg is not None:
                _team_drtg_num[_tid] += float(_drtg) * _poss
                _team_drtg_den[_tid] += _poss

    league_avg_ts  = _ts_num / _ts_den if _ts_den > 0 else 0.56
    team_avg_ts    = {t: _team_ts_num[t]   / _team_ts_den[t]   for t in _team_ts_den   if _team_ts_den[t]   > 0}
    team_avg_ortg  = {t: _team_ortg_num[t] / _team_ortg_den[t] for t in _team_ortg_den if _team_ortg_den[t] > 0}
    team_avg_drtg  = {t: _team_drtg_num[t] / _team_drtg_den[t] for t in _team_drtg_den if _team_drtg_den[t] > 0}

    # ── Main loop ──────────────────────────────────────────────────────────────
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
        # Tier 1/2: use career-stabilized rates when available, else current season
        _c       = career_stats_map.get(pid, {}) if career_stats_map else {}
        efg_pct  = _c.get("efg_pct",  p.get("efg_pct")  or 0.0)
        ts_pct   = _c.get("ts_pct",   p.get("ts_pct")   or 0.0)
        usg_pct  = _c.get("usg_pct",  p.get("usg_pct")  or 0.0)
        stl_pct  = _c.get("stl_pct",  p.get("stl_pct")  or 0.0)
        blk_pct  = _c.get("blk_pct",  p.get("blk_pct")  or 0.0)
        oreb_pct = _c.get("oreb_pct", p.get("oreb_pct") or 0.0)
        _ast_pct = _c.get("ast_pct",  p.get("ast_pct"))  # used in archetype only

        # Tier 3: always raw current season (role/context stats)
        ast_to   = p.get("ast_to") or 0.0
        d_mpir   = p.get("d_mpir") or 0.0
        on_ct_adj_d = p.get("on_court_adj_d") or 0.0
        on_ct_adj_o = float(p.get("on_court_adj_o") or 0.0)

        min_share = min(mpg / 48.0, 1.0)

        team_id = p.get("team_id")
        opp_quality = opp_quality_map.get(team_id, 0.0) if team_id else 0.0

        # On-off delta: player's on-court net rating minus team baseline.
        _on_ct_adj_em = p.get("on_court_adj_em")
        if _on_ct_adj_em is not None:
            team_em = team_adj_em_map.get(team_id, 0.0) if team_id else 0.0
            _raw_delta = float(_on_ct_adj_em) - team_em
            _poss_scale = min(poss / 3000.0, 1.0)
            on_off_delta = max(min(_raw_delta * _poss_scale, 6.0), -6.0)
        else:
            on_off_delta = 0.0

        # USG × efficiency interactions — key signal for high-usage stars
        ts_above_avg   = ts_pct - league_avg_ts
        usg_x_ts       = usg_pct * ts_pct
        usg_x_efg      = usg_pct * efg_pct
        usg_sq         = usg_pct ** 2
        usg_x_ts_above = usg_pct * ts_above_avg

        # Team-quality residuals — player contribution above team context
        ts_vs_team   = ts_pct    - team_avg_ts.get(team_id, league_avg_ts)
        ortg_vs_team = on_ct_adj_o - team_avg_ortg.get(team_id, 0.0)
        # d_vs_team: negative means player improves team defense vs team average
        d_vs_team    = on_ct_adj_d - team_avg_drtg.get(team_id, 0.0)

        archetype = classify_nba_archetype(
            usg_pct=usg_pct,
            ast_pct=_ast_pct,
            fg3a_pg=fg3a_pg,
            oreb_pct=oreb_pct,
            blk_pct=blk_pct,
            d_mpir=d_mpir,
        )
        arch_vec = archetype_onehot(archetype)

        # Per-100 counting stats: use career-stabilized when available (Phase 2)
        # Falls back to raw current-season computation for rookies or no career map
        fga100  = _c.get("fga100")  if _c.get("fga100")  is not None else per100(fga_pg, poss)
        fta100  = _c.get("fta100")  if _c.get("fta100")  is not None else per100(fta_pg, poss)
        tov100  = _c.get("tov100")  if _c.get("tov100")  is not None else per100(tov_pg, poss)
        ast100  = _c.get("ast100")  if _c.get("ast100")  is not None else per100(ast_pg, poss)
        pts100  = _c.get("pts100")  if _c.get("pts100")  is not None else per100(pts_pg, poss)
        oreb100 = _c.get("oreb100") if _c.get("oreb100") is not None else per100(oreb_pg, poss)
        fg3a100 = _c.get("fg3a100") if _c.get("fg3a100") is not None else per100(fg3a_pg, poss)
        stl100  = _c.get("stl100")  if _c.get("stl100")  is not None else per100(stl_pg, poss)
        blk100  = _c.get("blk100")  if _c.get("blk100")  is not None else per100(blk_pg, poss)
        dreb100 = _c.get("dreb100") if _c.get("dreb100") is not None else per100(dreb_pg, poss)

        # Derived quantities recomputed from stabilized per-100 values
        usage_rate = fga100 + 0.44 * fta100 + tov100
        ast_rate   = ast100 / max(usage_rate, 1.0)

        total_reb_pg = oreb_pg + dreb_pg   # raw counts for ratio features (oreb_share)

        off_feat = [
            pts100,                          # pts100
            ast100,                          # ast100
            tov100,                          # tov100
            oreb100,                         # oreb100
            fga100,                          # fga100
            fg3a100,                         # fg3a100
            fta100,                          # fta100
            efg_pct,                         # efg_pct
            ts_pct,                          # ts_pct
            usg_pct,                         # usg_pct
            min_share,                       # min_share
            fg3a_pg / max(fga_pg, 0.01),     # fg3_rate  (raw ratio — not volume)
            fta_pg  / max(fga_pg, 0.01),     # ft_rate   (raw ratio — not volume)
            ast_to,                          # ast_tov_ratio
            opp_quality,                     # opp_quality
            usage_rate,                      # usage_rate
            ast_rate,                        # ast_rate
            on_off_delta,                    # on_off_adj_em_delta
            usg_x_ts,                        # usg_x_ts
            usg_x_efg,                       # usg_x_efg
            usg_sq,                          # usg_sq
            ts_above_avg,                    # ts_above_avg
            usg_x_ts_above,                  # usg_x_ts_above
            ts_vs_team,                      # ts_vs_team
            ortg_vs_team,                    # ortg_vs_team
        ] + arch_vec

        def_feat = [
            stl100,                          # stl100
            blk100,                          # blk100
            dreb100,                         # dreb100
            d_mpir,                          # d_mpir
            on_ct_adj_d,                     # on_court_adj_d
            stl_pct,                         # stl_pct
            blk_pct,                         # blk_pct
            fg3a_pg / max(fga_pg, 0.01),     # fg3a_share  (raw ratio)
            oreb_pg / max(total_reb_pg, 0.01), # oreb_share (raw ratio)
            min_share,                       # min_share
            opp_quality,                     # opp_quality
            on_off_delta,                    # on_off_adj_em_delta
            d_vs_team,                       # d_vs_team
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
    rapm_pids: set[int] | None = None,  # when set, only these players enter the training matrices
    career_stats_map: dict[int, dict[str, float]] | None = None,
) -> dict:
    """
    Train offensive and defensive Box BPR models.

    rapm_pids: restrict training to players with RAPM-based targets only.
    Excludes MPIR-only players from the training set (they are predicted
    via predict_nba_box_bpr using the model learned from RAPM players).
    This prevents the mixed-scale target problem where ~30% of training
    targets are on a different scale (MPIR ~±8) vs RAPM (~±5).

    Returns artifact dict with fitted pipelines and diagnostics.
    """
    box_features = extract_nba_box_features(stats, opp_quality_map, team_adj_em_map, career_stats_map)

    off_X, off_y, off_pids = [], [], []
    def_X, def_y, def_pids = [], [], []

    for pid, feats in box_features.items():
        if rapm_pids is not None and pid not in rapm_pids:
            continue   # exclude MPIR-only players from training set
        if pid in target_obpr:
            off_X.append(feats["off"])
            off_y.append(target_obpr[pid])
            off_pids.append(pid)
        if pid in target_dbpr:
            def_X.append(feats["def"])
            def_y.append(target_dbpr[pid])
            def_pids.append(pid)

    n_mpir_excluded = len(box_features) - len(set(off_pids) | set(def_pids))
    if rapm_pids is not None:
        logger.info(
            "Target split — training: %d RAPM-only | eligible excluded: %d MPIR-only",
            len(off_X), n_mpir_excluded,
        )
        if off_y:
            logger.info(
                "RAPM target range: off [%.2f, %.2f]  def [%.2f, %.2f]",
                min(off_y), max(off_y),
                min(def_y) if def_y else 0, max(def_y) if def_y else 0,
            )
            logger.info(
                "Target SD: off=%.3f  def=%.3f",
                float(np.std(off_y)), float(np.std(def_y)) if def_y else 0,
            )

    if len(off_X) < 20 or len(def_X) < 20:
        raise ValueError(
            f"Too few training samples: {len(off_X)} offense, {len(def_X)} defense. "
            "Need at least 20 each."
        )

    off_pipe = _build_pipeline(BOX_BPR_ALPHAS_OFF)
    def_pipe = _build_pipeline(BOX_BPR_ALPHAS_DEF)

    off_X_arr = np.array(off_X)
    def_X_arr = np.array(def_X)
    off_y_arr = np.array(off_y)
    def_y_arr = np.array(def_y)

    off_pipe.fit(off_X_arr, off_y_arr)
    def_pipe.fit(def_X_arr, def_y_arr)

    off_cv_alpha = float(off_pipe.named_steps["ridge"].alpha_)
    def_cv_alpha = float(def_pipe.named_steps["ridge"].alpha_)

    logger.info(
        "Box BPR trained — off alpha=%.2f (n=%d), def alpha=%.2f (n=%d)",
        off_cv_alpha, len(off_X), def_cv_alpha, len(def_X),
    )

    # ── Feature importance (standardized coefficients) ────────────────────────
    off_coefs = off_pipe.named_steps["ridge"].coef_
    def_coefs = def_pipe.named_steps["ridge"].coef_

    off_importance = sorted(zip(OFF_FEATURES, off_coefs), key=lambda x: -abs(x[1]))
    def_importance = sorted(zip(DEF_FEATURES, def_coefs), key=lambda x: -abs(x[1]))

    logger.info("Top 10 OBPR features (standardized |coeff|):")
    for feat, coef in off_importance[:10]:
        logger.info("  %-32s %+.4f", feat, coef)

    logger.info("Top 10 DBPR features (standardized |coeff|):")
    for feat, coef in def_importance[:10]:
        logger.info("  %-32s %+.4f", feat, coef)

    top5_off_names = {f for f, _ in off_importance[:5]}
    if "usg_x_ts" not in top5_off_names and "usg_x_ts_above" not in top5_off_names:
        logger.warning("usg_x_ts / usg_x_ts_above not in top-5 OBPR — interaction terms not driving signal")

    # ── LassoCV comparison (informational only — not used for prediction) ──────
    try:
        from sklearn.linear_model import LassoCV as _LassoCV
        from sklearn.preprocessing import StandardScaler as _SS
        _sc_off = _SS()
        _X_off_std = _sc_off.fit_transform(off_X_arr)
        _lasso_off = _LassoCV(alphas=BOX_BPR_ALPHAS_OFF, cv=BOX_BPR_CV_FOLDS, max_iter=5000).fit(
            _X_off_std, off_y_arr
        )
        ridge_r2_off = float(off_pipe.score(off_X_arr, off_y_arr))
        lasso_r2_off = float(_lasso_off.score(_X_off_std, off_y_arr))
        logger.info(
            "OBPR — Ridge α=%.2f R²=%.3f | Lasso α=%.4f R²=%.3f",
            off_cv_alpha, ridge_r2_off, _lasso_off.alpha_, lasso_r2_off,
        )
    except Exception as _e:
        logger.debug("LassoCV comparison skipped: %s", _e)

    return {
        "off_pipeline":    off_pipe,
        "def_pipeline":    def_pipe,
        "off_cv_alpha":    off_cv_alpha,
        "def_cv_alpha":    def_cv_alpha,
        "n_train_off":     len(off_X),
        "n_train_def":     len(def_X),
        "n_mpir_excluded": n_mpir_excluded,
        "off_features":    OFF_FEATURES,
        "def_features":    DEF_FEATURES,
        "off_importance":  off_importance[:10],
        "def_importance":  def_importance[:10],
    }


def predict_nba_box_bpr(
    stats: list[dict],
    opp_quality_map: dict[int, float],
    team_adj_em_map: dict[int, float],
    model_artifacts: dict,
    career_stats_map: dict[int, dict[str, float]] | None = None,
) -> dict[int, dict]:
    """
    Apply trained pipelines to generate box_obpr / box_dbpr for all qualified players.

    Returns: {player_id: {"box_obpr": float, "box_dbpr": float, "archetype": str}}
    """
    off_pipe = model_artifacts["off_pipeline"]
    def_pipe = model_artifacts["def_pipeline"]

    box_features = extract_nba_box_features(stats, opp_quality_map, team_adj_em_map, career_stats_map)

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
    rapm_pids: set[int] | None = None,
    career_stats_map: dict[int, dict[str, float]] | None = None,
) -> tuple[dict[int, dict], dict]:
    """
    Generate out-of-fold predictions to avoid leakage when training and
    predicting on the same season.

    Returns (predictions_dict, model_artifacts_from_last_fold).
    predictions_dict: {player_id: {"box_obpr": float, "box_dbpr": float, "archetype": str}}
    """
    import random

    box_features = extract_nba_box_features(stats, opp_quality_map, team_adj_em_map, career_stats_map)

    # Players with targets for both offense and defense
    # Eligible for OOF folds: must have RAPM targets if rapm_pids is set
    eligible_pids = [
        pid for pid in box_features
        if pid in target_obpr and pid in target_dbpr
        and (rapm_pids is None or pid in rapm_pids)
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
            rapm_pids=rapm_pids,
            career_stats_map=career_stats_map,
        )

        val_stats = [s for s in stats if (s.get("player_id") or s.get("id")) in val_pids]
        fold_preds = predict_nba_box_bpr(val_stats, opp_quality_map, team_adj_em_map, artifacts, career_stats_map)
        oof_preds.update(fold_preds)

        if fold_i == n_folds - 1:
            last_artifacts = artifacts

    logger.info("OOF box BPR complete — %d players with predictions", len(oof_preds))
    return oof_preds, last_artifacts
