"""
Management command: nba_fit_box_pooled

Box BPR fitted on pooled past seasons, read-only (writes JSON files only).

For each season Y in --seasons: one offense and one defense ridge model are
trained on the seasons BEFORE Y only (from --history-start, default 2016), on
the same features and targets as nba_compute_box_bpr at --lebron-blend-w 0
(baseline RAPM targets, players with both baseline O and D; no LEBRON). Then
season Y is predicted and written to OUT_DIR/box_<Y>.json as
{nba_id: [box_obpr, box_dbpr]}, the format nba_experiment_final_bpr
--box-json-dir reads.

Alpha is chosen from ALPHAS separately for offense and defense with the
one-standard-error rule (the largest alpha whose mean CV error is within one
standard error of the best mean):
  - 3 or more training seasons: leave-one-season-out CV inside them
  - fewer: 5-fold CV over players (a player's rows stay in one fold)
The history-start season has no history: it is fitted on itself (as
nba_compute_box_bpr does), with alpha from 5-fold CV over players.

--weight-by-poss weights each training row by on_court_poss divided by its
mean over the training rows (weights average 1), in the fits and in the CV
error. OUT_DIR/alphas.json records each season's plan, alphas and CV errors.

--features box_only drops every feature built from on-court results (NBA.com's
E_OFF/E_DEF/E_NET ratings: on_court_adj_*, d_mpir and what is derived from
them) instead of the player's own box score. That includes the three archetype
one-hots whose split depends on d_mpir (three_and_d / stretch / connector);
creator, scorer and interior depend on box inputs only and stay.

Usage:
  python manage.py nba_fit_box_pooled --seasons 2016 2017 2018 --out-dir box_pooled
  python manage.py nba_fit_box_pooled --seasons 2025 --weight-by-poss --out-dir box_pooled_w
  python manage.py nba_fit_box_pooled --seasons 2025 --features box_only --out-dir box_pooled_bo
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from django.core.management.base import BaseCommand, CommandError
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from nba.analytics.box_bpr import (
    DEF_FEATURES,
    OFF_FEATURES,
    compute_opp_quality_map,
    compute_team_adj_em_map,
    extract_nba_box_features,
    predict_nba_box_bpr,
)
from nba.analytics.career_stats import build_career_stats_map
from nba.management.commands.nba_compute_box_bpr import _merge_player_rows

ALPHAS = [1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0, 3000.0, 10000.0, 30000.0]
HISTORY_START = 2016
MIN_LOSO_SEASONS = 3
PLAYER_FOLDS = 5

# Features built from on-court results rather than the player's own box score.
_D_MPIR_ARCHETYPES = {"arch_three_and_d", "arch_stretch", "arch_connector"}
ON_COURT_FEATURES = {
    "off": {"on_off_adj_em_delta", "ortg_vs_team"} | _D_MPIR_ARCHETYPES,
    "def": {"d_mpir", "on_court_adj_d", "on_off_adj_em_delta", "d_vs_team"} | _D_MPIR_ARCHETYPES,
}
FEATURE_NAMES = {"off": OFF_FEATURES, "def": DEF_FEATURES}
FEATURE_SETS = ("all", "box_only")

# The same per-season fields nba_compute_box_bpr loads.
STATS_FIELDS = (
    "player_id", "team_id",
    "gp", "mpg",
    "pts", "ast", "stl", "blk", "tov",
    "oreb_pg", "dreb_pg", "fga_pg", "fg3a_pg", "fta_pg",
    "efg_pct", "ts_pct", "usg_pct", "ast_pct",
    "oreb_pct", "dreb_pct", "ast_to",
    "stl_pct", "blk_pct", "tov_pct",
    "on_court_poss", "on_court_adj_em",
    "on_court_adj_o", "on_court_adj_d",
    "o_mpir", "d_mpir",
    "baseline_obpr", "baseline_dbpr",
)


# ── pure pieces (tested without a database) ───────────────────────────────────

def plan_training(season: int, history_start: int = HISTORY_START) -> tuple[list[int], str]:
    """(training seasons, CV method) for season Y: seasons before Y, or Y itself with no history."""
    train = list(range(history_start, season))
    if not train:
        train = [season]
    method = "loso" if len(train) >= MIN_LOSO_SEASONS else "player_5fold"
    return train, method


def feature_index(side: str, features: str) -> list[int] | None:
    """Columns kept for a feature set: None (all) or the indices of the box-only columns."""
    if features == "all":
        return None
    if features != "box_only":
        raise ValueError(f"unknown feature set {features!r}")
    drop = ON_COURT_FEATURES[side]
    missing = drop - set(FEATURE_NAMES[side])
    if missing:
        raise ValueError(f"{side} features not found: {sorted(missing)}")
    return [i for i, name in enumerate(FEATURE_NAMES[side]) if name not in drop]


class SelectColumns:
    """Applies a fitted pipeline to the kept columns of a full-width feature row."""

    def __init__(self, idx: list[int], model: Pipeline):
        self.idx = idx
        self.model = model

    def predict(self, X):
        return self.model.predict(np.asarray(X)[:, self.idx])


def poss_weights(poss: np.ndarray) -> np.ndarray:
    """on_court_poss divided by its mean, so the weights average 1."""
    poss = np.asarray(poss, dtype=float)
    return poss / poss.mean()


def one_se_choice(alphas: list[float], fold_errors: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    """
    fold_errors: (n_alphas, n_folds). Returns (alpha, mean per alpha, SE per alpha):
    the largest alpha whose mean error is within one SE of the best mean.
    """
    fold_errors = np.asarray(fold_errors, dtype=float)
    mean = fold_errors.mean(axis=1)
    se = fold_errors.std(axis=1, ddof=1) / np.sqrt(fold_errors.shape[1])
    best = int(np.argmin(mean))
    ok = [i for i in range(len(alphas)) if mean[i] <= mean[best] + se[best]]
    return float(max(alphas[i] for i in ok)), mean, se


def fit_ridge(X: np.ndarray, y: np.ndarray, w: np.ndarray | None, alpha: float) -> Pipeline:
    pipe = Pipeline([("scaler", StandardScaler()), ("ridge", Ridge(alpha=alpha))])
    if w is None:
        pipe.fit(X, y)
    else:
        pipe.fit(X, y, ridge__sample_weight=w)
    return pipe


def cv_fold_errors(X, y, w, folds: np.ndarray, alphas: list[float]) -> np.ndarray:
    """(n_alphas, n_folds) held-out MSE (weighted by w when given) for each fold label."""
    labels = list(dict.fromkeys(folds.tolist()))
    errs = np.zeros((len(alphas), len(labels)))
    for j, lab in enumerate(labels):
        test = folds == lab
        train = ~test
        for i, a in enumerate(alphas):
            pipe = fit_ridge(X[train], y[train], None if w is None else w[train], a)
            resid = y[test] - pipe.predict(X[test])
            wt = np.ones(test.sum()) if w is None else w[test]
            errs[i, j] = float((wt * resid ** 2).sum() / wt.sum())
    return errs


def fold_labels(method: str, seasons: np.ndarray, players: np.ndarray) -> np.ndarray:
    """Season labels for LOSO; GroupKFold(5) by player otherwise."""
    if method == "loso":
        return np.asarray(seasons)
    labels = np.zeros(len(players), dtype=int)
    gkf = GroupKFold(n_splits=PLAYER_FOLDS)
    for k, (_tr, te) in enumerate(gkf.split(np.zeros(len(players)), groups=players)):
        labels[te] = k
    return labels


def fit_season(season: int, data: dict[int, dict], weight_by_poss: bool,
               history_start: int = HISTORY_START, alphas: list[float] = ALPHAS,
               features: str = "all") -> tuple[dict, dict]:
    """
    data[s]: {"X_off", "X_def", "y_off", "y_def", "poss", "pids"} training rows of season s
    (full-width feature rows). Returns (artifacts {"off_pipeline", "def_pipeline"}, info for
    alphas.json); the artifacts take full-width rows. Only the seasons plan_training gives are used.
    """
    train, method = plan_training(season, history_start)
    rows = [data[s] for s in train]
    seasons = np.concatenate([np.full(len(r["pids"]), s) for s, r in zip(train, rows)])
    players = np.concatenate([np.asarray(r["pids"]) for r in rows])
    w = poss_weights(np.concatenate([r["poss"] for r in rows])) if weight_by_poss else None
    folds = fold_labels(method, seasons, players)
    info = {"season": season, "train_seasons": train, "method": method, "n_train": int(len(players)),
            "weighted": weight_by_poss, "features": features}
    artifacts = {}
    for side in ("off", "def"):
        X = np.vstack([r[f"X_{side}"] for r in rows])
        y = np.concatenate([r[f"y_{side}"] for r in rows])
        idx = feature_index(side, features)
        if idx is not None:
            X = X[:, idx]
        errs = cv_fold_errors(X, y, w, folds, alphas)
        alpha, mean, se = one_se_choice(alphas, errs)
        model = fit_ridge(X, y, w, alpha)
        artifacts[f"{side}_pipeline"] = model if idx is None else SelectColumns(idx, model)
        info[f"{side}_n_features"] = int(X.shape[1])
        info[f"{side}_alpha"] = alpha
        info[f"{side}_alpha_min_error"] = float(alphas[int(np.argmin(mean))])
        info[f"{side}_cv_mean"] = [round(float(m), 5) for m in mean]
        info[f"{side}_cv_se"] = [round(float(e), 5) for e in se]
    return artifacts, info


# ── database loading (same inputs as nba_compute_box_bpr at blend 0) ──────────

def load_season(season: int, career_floor: int) -> dict:
    from nba.models import NBAPlayerSeasonStats

    stats = list(NBAPlayerSeasonStats.objects.filter(
        season__year=season, season_type="regular").values(*STATS_FIELDS))
    if not stats:
        raise CommandError(f"No stats found for season {season}.")
    stats, _ = _merge_player_rows(stats)
    opp = compute_opp_quality_map(season)
    team = compute_team_adj_em_map(season)
    career = build_career_stats_map(target_season_year=season, min_season_year=career_floor)
    feats = extract_nba_box_features(stats, opp, team, career)

    by_pid = {p["player_id"]: p for p in stats}
    pids = [pid for pid in feats
            if by_pid[pid].get("baseline_obpr") is not None and by_pid[pid].get("baseline_dbpr") is not None]
    return {
        "inputs": (stats, opp, team, career),
        "X_off": np.array([feats[p]["off"] for p in pids]),
        "X_def": np.array([feats[p]["def"] for p in pids]),
        "y_off": np.array([by_pid[p]["baseline_obpr"] for p in pids], dtype=float),
        "y_def": np.array([by_pid[p]["baseline_dbpr"] for p in pids], dtype=float),
        "poss": np.array([float(by_pid[p].get("on_court_poss") or 0.0) for p in pids]),
        "pids": pids,
    }


def nba_ids_for(pks) -> dict[int, int]:
    from nba.models import NBAPlayer

    return dict(NBAPlayer.objects.filter(pk__in=list(pks)).values_list("pk", "player_id"))


class Command(BaseCommand):
    help = "Box BPR from pooled past seasons with CV-chosen alpha; writes JSON only (no DB writes)."

    def add_arguments(self, parser):
        parser.add_argument("--seasons", nargs="+", type=int, required=True)
        parser.add_argument("--weight-by-poss", action="store_true",
                            help="Weight rows by on_court_poss / its mean over the training rows")
        parser.add_argument("--features", choices=FEATURE_SETS, default="all",
                            help="box_only drops the features built from on-court results")
        parser.add_argument("--out-dir", type=str, required=True,
                            help="Writes box_<Y>.json per season and alphas.json")
        parser.add_argument("--history-start", type=int, default=HISTORY_START,
                            help=f"First season training may use (default {HISTORY_START})")
        parser.add_argument("--career-floor", type=int, default=2016,
                            help="Oldest season in the career-stabilized stats window (default 2016)")

    def handle(self, *args, **opts):
        out_dir = Path(opts["out_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        weighted = opts["weight_by_poss"]
        start = opts["history_start"]
        cache: dict[int, dict] = {}

        def get(season):
            if season not in cache:
                self.stdout.write(f"Loading season {season}...")
                cache[season] = load_season(season, opts["career_floor"])
            return cache[season]

        all_info = []
        for season in sorted(opts["seasons"]):
            if season < start:
                raise CommandError(f"Season {season} is before --history-start {start}")
            train, _ = plan_training(season, start)
            data = {s: get(s) for s in train}
            artifacts, info = fit_season(season, data, weighted, start, features=opts["features"])
            stats, opp, team, career = get(season)["inputs"]
            preds = predict_nba_box_bpr(stats, opp, team, artifacts, career)
            nba_ids = nba_ids_for(preds)
            out = {str(nba_ids[pk]): [p["box_obpr"], p["box_dbpr"]] for pk, p in preds.items()}
            path = out_dir / f"box_{season}.json"
            with open(path, "w") as f:
                json.dump(out, f)
            info["n_predicted"] = len(out)
            all_info.append(info)
            self.stdout.write(
                f"  {season}: train {train[0]}-{train[-1]} ({info['method']}, n={info['n_train']}"
                f"{', weighted' if weighted else ''}, features={opts['features']})  off alpha={info['off_alpha']:g}  "
                f"def alpha={info['def_alpha']:g}  → {len(out)} players {path}")

        with open(out_dir / "alphas.json", "w") as f:
            json.dump(all_info, f, indent=2)
        self.stdout.write(self.style.SUCCESS(f"Done. No DB writes. Alphas → {out_dir / 'alphas.json'}"))
