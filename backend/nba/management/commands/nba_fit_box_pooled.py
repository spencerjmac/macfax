"""
Management command: nba_fit_box_pooled

Box BPR fitted on pooled past seasons. With --seasons it is read-only (writes
JSON files only); with --season Y --write it is the production box BPR.

Defaults are the final recipe (Phase 4/T.1): --features box_only, a 3-season
pooled RAPM target (--target-window 3) at --target-lambda 300, alphas up to
--alpha-max 1000, the opp_quality team feature, and history start and career
floor 2006. Every option below can still be set the other way.

For each season Y in --seasons: one offense and one defense ridge model are
trained on the seasons BEFORE Y only (from --history-start, default 2006), on
the same features and targets as nba_compute_box_bpr at --lebron-blend-w 0
(no LEBRON). Then season Y is predicted and written to OUT_DIR/box_<Y>.json as
{nba_id: [box_obpr, box_dbpr]}, the format nba_experiment_final_bpr
--box-json-dir reads.

--season Y --write fits Y the same way, then clears box_obpr, box_dbpr,
box_bpr and nba_archetype on Y's regular-season rows and writes this fit's
values (box_bpr = box_obpr + box_dbpr; nba_archetype from the existing
archetype assignment in box_bpr) to every row of each predicted player.
--season Y --dry-run fits Y and prints the top 20 without writing; its values
are the ones --seasons Y --out-dir DIR writes to DIR/box_<Y>.json.

Alpha is chosen from ALPHAS up to --alpha-max (default 1000, the grid task 3.5b
used; up to 30000 is available) separately for offense and defense with the
one-standard-error rule (the largest alpha whose mean CV error is within one
standard error of the best mean):
  - 3 or more training seasons: leave-one-season-out CV inside them
  - fewer: 5-fold CV over players (a player's rows stay in one fold)
The history-start season has no history: it is fitted on itself (as
nba_compute_box_bpr does), with alpha from 5-fold CV over players.

--weight-by-poss weights each training row by on_court_poss divided by its
mean over the training rows (weights average 1), in the fits and in the CV
error. OUT_DIR/alphas.json records each season's plan, alphas and CV errors.

--target-window K (default 3) trains on pooled RAPM over seasons s-K+1..s (from
--history-start on; one column per player, rapm.fit_pooled_player_rapm) as season
s's target. --target window3 is an alias for --target-window 3; --target baseline
trains on s's single-season baseline RAPM instead. --target-lambda X (default 300)
fixes that pooled RAPM's lambda at X; --target-lambda cv chooses it by game CV.
Season Y's model still trains on seasons before Y only, so nothing from Y enters
it (the history-start season fits itself, on its own one-season window).

--newcomer-means (window targets only; default off) also writes
OUT_DIR/newcomer_means.json: for each season Y, the possession-weighted mean
window target (offense and defense separately) of players who were newcomers in
their own season s, over seasons s before Y only. A newcomer in s played in s
(stints), has no box prediction in s and no regular-season minutes in s-1;
weights are their on-court possessions in s. nba_experiment_final_bpr
--newcomer-prior reads it. A season with no earlier seasons gets mean 0.

--team-feature {opp_quality,team_adj_net,none} (default opp_quality) sets what
the opp_quality column holds: the mean opponent adj_net (as today), the
player's own team's season adj_net, or nothing (the column is dropped, offense
and defense).

--features box_only (default) drops every feature built from on-court results
(NBA.com's E_OFF/E_DEF/E_NET ratings: on_court_adj_*, d_mpir and what is derived
from them) instead of the player's own box score. That includes the three
archetype one-hots whose split depends on d_mpir (three_and_d / stretch /
connector); creator, scorer and interior depend on box inputs only and stay.
--features all keeps them.

--season Y (write or dry run) caches the trained model: BOX_CACHE_DIR/<Y>.pkl under
settings.NBA_CACHE_DIR holds the offense and defense pipelines and their info, keyed by a
SHA-256 over this command's settings, the library versions and a database-side content hash of
everything training reads (box_model_inputs_fingerprint): the stints of seasons history start..
Y-1 and the game, player-season (the columns used), team-rating, player and team rows behind
them. A matching key skips the targets, loading and fitting of every training season; season
Y's own inputs are always read fresh. Anything else refits and replaces the file. --no-cache
neither reads nor writes it. --seasons never uses it.

Usage:
  python manage.py nba_fit_box_pooled --season 2026 --dry-run
  python manage.py nba_fit_box_pooled --season 2026 --write
  python manage.py nba_fit_box_pooled --seasons 2006 2007 2008 --out-dir box_recipe
  python manage.py nba_fit_box_pooled --seasons 2025 --target baseline --features all --out-dir box_pooled
  python manage.py nba_fit_box_pooled --seasons 2025 --target-window 5 --target-lambda cv --out-dir box_w5
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import time
from pathlib import Path

import numpy as np
import sklearn
from django.conf import settings
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
from nba.analytics.rapm import build_nba_observations, fit_pooled_player_rapm
from nba.management.commands.nba_compute_box_bpr import _merge_player_rows

ALPHAS = [1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0, 3000.0, 10000.0, 30000.0]
DEFAULT_ALPHA_MAX = 1000.0
TARGETS = ("baseline", "window3")
WINDOW = 3
DEFAULT_TARGET_LAMBDA = 300.0
HISTORY_START = 2006
DEFAULT_FEATURES = "box_only"
TOP_N = 20
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
TEAM_FEATURES = ("opp_quality", "team_adj_net", "none")

# Trained models for --season Y, under settings.NBA_CACHE_DIR (a Docker volume on prod).
BOX_CACHE_DIR = settings.NBA_CACHE_DIR / "box_model_cache"
BOX_CACHE_VERSION = 1           # bump when training code changes what a key's inputs produce

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


def feature_index(side: str, features: str, team_feature: str = "opp_quality") -> list[int] | None:
    """Columns kept: None (all) or the indices left after the feature set and team feature drops."""
    if features not in FEATURE_SETS:
        raise ValueError(f"unknown feature set {features!r}")
    if team_feature not in TEAM_FEATURES:
        raise ValueError(f"unknown team feature {team_feature!r}")
    drop = set(ON_COURT_FEATURES[side]) if features == "box_only" else set()
    if team_feature == "none":
        drop.add("opp_quality")
    if not drop:
        return None
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


def alpha_grid(alpha_max: float = DEFAULT_ALPHA_MAX) -> list[float]:
    """ALPHAS up to alpha_max."""
    grid = [a for a in ALPHAS if a <= alpha_max]
    if not grid:
        raise ValueError(f"--alpha-max {alpha_max} is below the smallest alpha {ALPHAS[0]}")
    return grid


def window_years(season: int, history_start: int = HISTORY_START, k: int = WINDOW) -> list[int]:
    """Seasons s-k+1..s, not before history_start."""
    return list(range(max(history_start, season - k + 1), season + 1))


def resolve_window(target: str | None, target_window: int | None) -> int | None:
    """
    Window length K for the training target, or None for single-season baseline RAPM.
    target None (the default) is the recipe's window of WINDOW seasons unless --target-window says otherwise.
    """
    if target == "window3":
        if target_window not in (None, WINDOW):
            raise CommandError(f"--target window3 conflicts with --target-window {target_window}")
        return WINDOW
    if target_window is not None and target_window < 1:
        raise CommandError("--target-window must be at least 1")
    if target is None and target_window is None:
        return WINDOW
    return target_window


def target_lambda_arg(value: str) -> float | str:
    """--target-lambda: a number, or 'cv' for game-CV lambda."""
    if value.strip().lower() == "cv":
        return "cv"
    try:
        return float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a number or 'cv', got {value!r}")


def resolve_target_lambda(k: int | None, given: float | str | None) -> float | None:
    """Fixed pooled-RAPM lambda for window targets (default DEFAULT_TARGET_LAMBDA), or None for game CV."""
    if k is None:
        if given is not None:
            raise CommandError("--target-lambda needs a window target (--target-window K) and a positive value")
        return None
    if given is None:
        return DEFAULT_TARGET_LAMBDA
    if given == "cv":
        return None
    if given <= 0:
        raise CommandError("--target-lambda needs a window target (--target-window K) and a positive value")
    return float(given)


def top_lines(preds: dict[int, dict], labels: dict[int, tuple[str, int]], n: int = TOP_N) -> list[str]:
    """The n highest box_obpr + box_dbpr, one line each (labels: pk -> (name, NBA.com id))."""
    ranked = sorted(preds.items(), key=lambda kv: kv[1]["box_obpr"] + kv[1]["box_dbpr"], reverse=True)
    lines = []
    for rank, (pk, p) in enumerate(ranked[:n], start=1):
        name, nba_id = labels.get(pk, (f"pk={pk}", None))
        lines.append(f"  {rank:2d}. {name:28s} nba_id={nba_id!s:<8} obpr={p['box_obpr']:+.4f}  "
                     f"dbpr={p['box_dbpr']:+.4f}  box_bpr={p['box_obpr'] + p['box_dbpr']:+.4f}  "
                     f"[{p['archetype']}]")
    return lines


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
               history_start: int = HISTORY_START, alphas: list[float] | None = None,
               features: str = "all", team_feature: str = "opp_quality") -> tuple[dict, dict]:
    """
    data[s]: {"X_off", "X_def", "y_off", "y_def", "poss", "pids"} training rows of season s
    (full-width feature rows). Returns (artifacts {"off_pipeline", "def_pipeline"}, info for
    alphas.json); the artifacts take full-width rows. Only the seasons plan_training gives are used.
    """
    if alphas is None:
        alphas = alpha_grid()
    train, method = plan_training(season, history_start)
    rows = [data[s] for s in train]
    seasons = np.concatenate([np.full(len(r["pids"]), s) for s, r in zip(train, rows)])
    players = np.concatenate([np.asarray(r["pids"]) for r in rows])
    w = poss_weights(np.concatenate([r["poss"] for r in rows])) if weight_by_poss else None
    folds = fold_labels(method, seasons, players)
    info = {"season": season, "train_seasons": train, "method": method, "n_train": int(len(players)),
            "weighted": weight_by_poss, "features": features, "team_feature": team_feature}
    artifacts = {}
    for side in ("off", "def"):
        X = np.vstack([r[f"X_{side}"] for r in rows])
        y = np.concatenate([r[f"y_{side}"] for r in rows])
        idx = feature_index(side, features, team_feature)
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

def window_targets(season: int, history_start: int = HISTORY_START, k: int = WINDOW,
                   lam: float | None = None) -> dict:
    """
    Pooled RAPM over window_years(season, k): {"obpr", "dbpr"} keyed by NBA.com id, plus
    "lambda", "years". lam fixes the RAPM lambda; None chooses it by game CV.
    """
    years = window_years(season, history_start, k)
    observations = build_nba_observations(season, rapm_years=years)
    res = fit_pooled_player_rapm(observations, lambda_override=lam)
    return {"obpr": res["obpr"], "dbpr": res["dbpr"], "lambda": res["lambda"], "years": years,
            "poss_season": season_possessions(observations, season)}


def season_possessions(observations: list[dict], season: int) -> dict[int, float]:
    """On-court possessions per player in one season: (home_poss + away_poss) / 2 per stint."""
    poss: dict[int, float] = {}
    for obs in observations:
        if obs["season_year"] != season:
            continue
        p = (obs["home_poss"] + obs["away_poss"]) / 2.0
        for pid in obs["home_player_ids"] + obs["away_player_ids"]:
            poss[pid] = poss.get(pid, 0.0) + p
    return poss


def newcomer_stats(poss_season: dict[int, float], box_ids: set[int], prev_minute_ids: set[int],
                   targets: dict) -> dict:
    """
    One season's newcomers: played (possessions > 0), no box prediction, no minutes the season
    before, and a target. Returns {"n", "poss", "sum_o", "sum_d", "obpr", "dbpr"} (poss-weighted).
    """
    rows = [(p, w) for p, w in poss_season.items()
            if w > 0 and p not in box_ids and p not in prev_minute_ids
            and p in targets["obpr"] and p in targets["dbpr"]]
    W = sum(w for _, w in rows)
    so = sum(w * targets["obpr"][p] for p, w in rows)
    sd = sum(w * targets["dbpr"][p] for p, w in rows)
    return {"n": len(rows), "poss": W, "sum_o": so, "sum_d": sd,
            "obpr": so / W if W else 0.0, "dbpr": sd / W if W else 0.0}


def newcomer_mean_for(season: int, stats_by_season: dict[int, dict], history_start: int = HISTORY_START) -> dict:
    """Pooled newcomer mean for season Y over seasons history_start..Y-1 only (0 when there are none)."""
    used = [s for s in range(history_start, season) if s in stats_by_season]
    missing = [s for s in range(history_start, season) if s not in stats_by_season]
    if missing:
        raise ValueError(f"newcomer stats missing for seasons {missing}")
    W = sum(stats_by_season[s]["poss"] for s in used)
    so = sum(stats_by_season[s]["sum_o"] for s in used)
    sd = sum(stats_by_season[s]["sum_d"] for s in used)
    return {"obpr": so / W if W else 0.0, "dbpr": sd / W if W else 0.0,
            "n": sum(stats_by_season[s]["n"] for s in used), "poss": W, "from_seasons": used}


def prev_minute_ids(season: int) -> set[int]:
    """NBA.com ids with regular-season minutes in season-1."""
    from nba.models import NBAPlayerSeasonStats

    out = set()
    for r in NBAPlayerSeasonStats.objects.filter(season__year=season - 1, season_type="regular").values(
            "player__player_id", "mpg", "gp"):
        if (r["mpg"] or 0.0) * (r["gp"] or 0) > 0:
            out.add(r["player__player_id"])
    return out


def load_season(season: int, career_floor: int, targets: dict | None = None,
                team_feature: str = "opp_quality") -> dict:
    """
    One season's inputs and training rows. targets None: baseline RAPM (players with
    both baseline O and D); else {"obpr", "dbpr"} keyed by NBA.com id (players in both).
    """
    from nba.models import NBAPlayerSeasonStats

    stats = list(NBAPlayerSeasonStats.objects.filter(
        season__year=season, season_type="regular").values(*STATS_FIELDS))
    if not stats:
        raise CommandError(f"No stats found for season {season}.")
    stats, _ = _merge_player_rows(stats)
    team = compute_team_adj_em_map(season)
    # The opp_quality column holds opponents' mean adj_net, or the team's own adj_net
    # (team_feature none drops the column at fit time, so its value does not matter).
    opp = team if team_feature == "team_adj_net" else compute_opp_quality_map(season)
    career = build_career_stats_map(target_season_year=season, min_season_year=career_floor)
    feats = extract_nba_box_features(stats, opp, team, career)

    by_pid = {p["player_id"]: p for p in stats}
    if targets is None:
        pids = [pid for pid in feats
                if by_pid[pid].get("baseline_obpr") is not None and by_pid[pid].get("baseline_dbpr") is not None]
        y_off = [by_pid[p]["baseline_obpr"] for p in pids]
        y_def = [by_pid[p]["baseline_dbpr"] for p in pids]
    else:
        nba = nba_ids_for(feats)
        feature_nba_ids = {nba[p] for p in feats if p in nba}
        pids = [pid for pid in feats
                if nba.get(pid) in targets["obpr"] and nba.get(pid) in targets["dbpr"]]
        y_off = [targets["obpr"][nba[p]] for p in pids]
        y_def = [targets["dbpr"][nba[p]] for p in pids]
    return {
        "inputs": (stats, opp, team, career),
        "X_off": np.array([feats[p]["off"] for p in pids]),
        "X_def": np.array([feats[p]["def"] for p in pids]),
        "y_off": np.array(y_off, dtype=float),
        "y_def": np.array(y_def, dtype=float),
        "poss": np.array([float(by_pid[p].get("on_court_poss") or 0.0) for p in pids]),
        "pids": pids,
        "feature_nba_ids": feature_nba_ids if targets is not None else None,
    }


def nba_ids_for(pks) -> dict[int, int]:
    from nba.models import NBAPlayer

    return dict(NBAPlayer.objects.filter(pk__in=list(pks)).values_list("pk", "player_id"))


def player_labels(pks) -> dict[int, tuple[str, int]]:
    from nba.models import NBAPlayer

    return {pk: (name, nba_id) for pk, name, nba_id in
            NBAPlayer.objects.filter(pk__in=list(pks)).values_list("pk", "name", "player_id")}


def write_season_box(season: int, preds: dict[int, dict]) -> dict:
    """
    Clear box_obpr, box_dbpr, box_bpr and nba_archetype on season's regular rows, then write
    preds (keyed by NBAPlayer pk) to every row of each predicted player. One transaction.
    """
    from django.db import transaction
    from nba.models import NBAPlayerSeasonStats

    qs = NBAPlayerSeasonStats.objects.filter(season__year=season, season_type="regular")
    updated = skipped = 0
    with transaction.atomic():
        cleared = qs.update(box_obpr=None, box_dbpr=None, box_bpr=None, nba_archetype=None)
        for row in qs:
            p = preds.get(row.player_id)
            if p is None:
                skipped += 1
                continue
            row.box_obpr = p["box_obpr"]
            row.box_dbpr = p["box_dbpr"]
            row.box_bpr = round(p["box_obpr"] + p["box_dbpr"], 3)
            row.nba_archetype = p["archetype"]
            row.save(update_fields=["box_obpr", "box_dbpr", "box_bpr", "nba_archetype"])
            updated += 1
    return {"cleared": cleared, "updated": updated, "skipped": skipped}


# ── trained-model cache (--season Y) ──────────────────────────────────────────

# Player-season columns training reads: load_season's STATS_FIELDS plus build_career_stats_map's.
CAREER_FIELDS = ("gp", "mpg", "on_court_poss", "ts_pct", "efg_pct", "fg3_pct", "ft_pct", "ast_pct",
                 "stl_pct", "blk_pct", "oreb_pct", "usg_pct", "tov_pct", "dreb_pct", "pts", "ast", "stl",
                 "blk", "tov", "oreb_pg", "dreb_pg", "fga_pg", "fg3a_pg", "fta_pg")
FINGERPRINT_STATS_COLUMNS = tuple(sorted(set(STATS_FIELDS) | set(CAREER_FIELDS)))


def box_model_inputs_fingerprint(lo: int, hi: int) -> dict | None:
    """
    Content hash of every row training for seasons lo..hi reads: per season, the count and the sum
    of hashtextextended over the row text of its stints (whole rows), games (the columns the RAPM
    observations and opponent quality use), regular player-season rows (FINGERPRINT_STATS_COLUMNS)
    and regular team ratings (team, adj_net); plus the players in those seasons (pk -> NBA.com id)
    and all teams (pk -> NBA.com id). None off Postgres (no hashtextextended): the cache is then not used.
    """
    from django.db import connection

    if connection.vendor != "postgresql":
        return None
    h = "COALESCE(SUM(hashtextextended({}::text, 0)::numeric), 0)::text"
    stats_cols = ", ".join(f"p.{c}" for c in FINGERPRINT_STATS_COLUMNS)
    per_season = {
        "stints": (f"SELECT s.year, count(*), {h.format('t')} FROM nba_nbaplayergamestint t "
                   "JOIN nba_nbagame g ON g.id = t.game_id JOIN nba_nbaseason s ON s.id = g.season_id "
                   "WHERE s.year BETWEEN %s AND %s GROUP BY 1"),
        "games": (f"SELECT s.year, count(*), "
                  f"{h.format('row(g.id, g.game_id, g.date, g.home_team_id, g.away_team_id, g.pbp_quality_flag, g.counts_toward_regular_season, g.status)')} "
                  "FROM nba_nbagame g JOIN nba_nbaseason s ON s.id = g.season_id "
                  "WHERE s.year BETWEEN %s AND %s GROUP BY 1"),
        "player_seasons": (f"SELECT s.year, count(*), {h.format(f'row({stats_cols})')} "
                           "FROM nba_nbaplayerseasonstats p JOIN nba_nbaseason s ON s.id = p.season_id "
                           "WHERE p.season_type = 'regular' AND s.year BETWEEN %s AND %s GROUP BY 1"),
        "team_ratings": (f"SELECT s.year, count(*), {h.format('row(r.team_id, r.adj_net)')} "
                         "FROM nba_nbateamseasonratings r JOIN nba_nbaseason s ON s.id = r.season_id "
                         "WHERE r.season_type = 'regular' AND s.year BETWEEN %s AND %s GROUP BY 1"),
    }
    out: dict = {}
    with connection.cursor() as cur:
        for name, sql in per_season.items():
            cur.execute(sql, [lo, hi])
            out[name] = {str(y): [n, v] for y, n, v in sorted(cur.fetchall())}
        # Only players in seasons lo..hi: a player added later (a new season's rookie) leaves the key alone.
        cur.execute(f"SELECT count(*), {h.format('row(id, player_id)')} FROM nba_nbaplayer WHERE id IN ("
                    "SELECT t.player_id FROM nba_nbaplayergamestint t JOIN nba_nbagame g ON g.id = t.game_id "
                    "JOIN nba_nbaseason s ON s.id = g.season_id WHERE s.year BETWEEN %s AND %s "
                    "UNION SELECT p.player_id FROM nba_nbaplayerseasonstats p JOIN nba_nbaseason s "
                    "ON s.id = p.season_id WHERE s.year BETWEEN %s AND %s)", [lo, hi, lo, hi])
        out["players"] = list(cur.fetchone())
        cur.execute(f"SELECT count(*), {h.format('row(id, nba_team_id)')} FROM nba_nbateam")
        out["teams"] = list(cur.fetchone())
    return out


def box_cache_key(season: int, train: list[int], fit_settings: dict, fingerprint: dict) -> str:
    """SHA-256 over everything that decides season's trained model."""
    payload = {"version": BOX_CACHE_VERSION, "season": season, "train": train, "settings": fit_settings,
               "sklearn": sklearn.__version__, "numpy": np.__version__, "inputs": fingerprint}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def load_cached_model(season: int, key: str, cache_dir: Path | None = None) -> tuple[dict, dict] | None:
    """(artifacts, info) stored for season under key; None when missing, stale or unreadable."""
    path = Path(cache_dir or BOX_CACHE_DIR) / f"{season}.pkl"
    try:
        with open(path, "rb") as f:
            blob = pickle.load(f)
    except (OSError, EOFError, pickle.UnpicklingError, AttributeError, ImportError):
        return None
    if not isinstance(blob, dict) or blob.get("key") != key:
        return None
    return blob["artifacts"], blob["info"]


def store_cached_model(season: int, key: str, artifacts: dict, info: dict, cache_dir: Path | None = None) -> Path:
    """Write season's model under key (atomically: a temp file, then rename)."""
    d = Path(cache_dir or BOX_CACHE_DIR)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{season}.pkl"
    tmp = d / f".{season}.pkl.{os.getpid()}.tmp"
    with open(tmp, "wb") as f:
        pickle.dump({"key": key, "artifacts": artifacts, "info": info}, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, path)
    return path


class Command(BaseCommand):
    help = ("Box BPR from pooled past seasons with CV-chosen alpha (final recipe by default): "
            "--seasons writes JSON only; --season Y --write writes Y's box fields.")

    def add_arguments(self, parser):
        which = parser.add_mutually_exclusive_group(required=True)
        which.add_argument("--seasons", nargs="+", type=int,
                           help="Seasons to fit; writes OUT_DIR/box_<Y>.json (no DB writes)")
        which.add_argument("--season", type=int,
                           help="One season to fit for --write or --dry-run")
        parser.add_argument("--write", action="store_true",
                            help="With --season Y: clear and write box_obpr/box_dbpr/box_bpr/nba_archetype "
                                 "on Y's regular rows")
        parser.add_argument("--dry-run", action="store_true",
                            help="With --season Y: fit and print the top 20, write nothing")
        parser.add_argument("--weight-by-poss", action="store_true",
                            help="Weight rows by on_court_poss / its mean over the training rows")
        parser.add_argument("--team-feature", choices=TEAM_FEATURES, default="opp_quality",
                            help="What the opp_quality column holds: opponents' mean adj_net "
                                 "(default), the team's own adj_net, or none (dropped)")
        parser.add_argument("--features", choices=FEATURE_SETS, default=DEFAULT_FEATURES,
                            help=f"box_only (default) drops the features built from on-court results; all keeps them")
        parser.add_argument("--target", choices=TARGETS, default=None,
                            help="baseline: single-season baseline RAPM; window3: alias for --target-window 3 "
                                 f"(default: --target-window, {WINDOW} seasons)")
        parser.add_argument("--target-window", type=int, default=None, metavar="K",
                            help=f"Pooled RAPM over seasons s-K+1..s as season s's target (default {WINDOW})")
        parser.add_argument("--target-lambda", type=target_lambda_arg, default=None, metavar="X",
                            help=f"Window target's pooled RAPM lambda (default {DEFAULT_TARGET_LAMBDA:g}; "
                                 "'cv' chooses it by game CV)")
        parser.add_argument("--newcomer-means", action="store_true",
                            help="Also write newcomer_means.json (window targets only)")
        parser.add_argument("--alpha-max", type=float, default=DEFAULT_ALPHA_MAX,
                            help=f"Largest alpha in the grid (default {DEFAULT_ALPHA_MAX:g}; up to {ALPHAS[-1]:g})")
        parser.add_argument("--out-dir", type=str, default=None,
                            help="With --seasons (required): writes box_<Y>.json per season and alphas.json")
        parser.add_argument("--no-cache", action="store_true",
                            help="--season Y: fit from scratch; neither read nor write the trained-model cache")
        parser.add_argument("--history-start", type=int, default=HISTORY_START,
                            help=f"First season training may use (default {HISTORY_START})")
        parser.add_argument("--career-floor", type=int, default=HISTORY_START,
                            help=f"Oldest season in the career-stabilized stats window (default {HISTORY_START})")

    def handle(self, *args, **opts):
        single = opts.get("season")
        write, dry_run = opts.get("write", False), opts.get("dry_run", False)
        want_newcomers = opts.get("newcomer_means", False)
        if single is None:
            if write or dry_run:
                raise CommandError("--write and --dry-run take --season Y")
            if not opts.get("out_dir"):
                raise CommandError("--seasons needs --out-dir")
        else:
            if write == dry_run:
                raise CommandError("--season Y needs exactly one of --write or --dry-run")
            if opts.get("out_dir") or want_newcomers:
                raise CommandError("--season Y takes neither --out-dir nor --newcomer-means "
                                   "(use --seasons Y --out-dir DIR for the JSON)")
        out_dir = Path(opts["out_dir"]) if single is None else None
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
        weighted = opts["weight_by_poss"]
        start = opts["history_start"]
        alphas = alpha_grid(opts["alpha_max"])
        k = resolve_window(opts.get("target"), opts.get("target_window"))
        target_lambda = resolve_target_lambda(k, opts.get("target_lambda"))
        target = "baseline" if k is None else f"window{k}"
        if want_newcomers and k is None:
            raise CommandError("--newcomer-means needs a window target (--target-window K)")
        newcomer_by_season: dict[int, dict] = {}
        cache: dict[int, dict] = {}
        window_info: dict[int, dict] = {}

        def get(season):
            if season not in cache:
                self.stdout.write(f"Loading season {season}...")
                targets = None
                if k is not None:
                    targets = window_targets(season, start, k, target_lambda)
                    window_info[season] = {"years": targets["years"], "lambda": targets["lambda"],
                                           "n_players": len(targets["obpr"])}
                    self.stdout.write(f"  {target} target {targets['years']}: lambda={targets['lambda']:g}, "
                                      f"{len(targets['obpr'])} players")
                cache[season] = load_season(season, opts["career_floor"], targets,
                                            team_feature=opts["team_feature"])
                if want_newcomers:
                    newcomer_by_season[season] = newcomer_stats(
                        targets["poss_season"], cache[season]["feature_nba_ids"],
                        prev_minute_ids(season), targets)
                    st = newcomer_by_season[season]
                    self.stdout.write(f"  newcomers {season}: {st['n']} players, {st['poss']:.0f} poss, "
                                      f"O {st['obpr']:+.3f} D {st['dbpr']:+.3f}")
            return cache[season]

        seasons = [single] if single is not None else sorted(opts["seasons"])
        all_info = []
        preds = {}
        for season in seasons:
            if season < start:
                raise CommandError(f"Season {season} is before --history-start {start}")
            train, _ = plan_training(season, start)
            artifacts = info = key = None
            if single is not None and not opts.get("no_cache"):
                t0 = time.monotonic()
                fp = box_model_inputs_fingerprint(min(start, opts["career_floor"]), max(train))
                if fp is not None:
                    key = box_cache_key(season, train, {
                        "features": opts["features"], "team_feature": opts["team_feature"], "target": target,
                        "target_lambda": target_lambda, "weighted": weighted, "alphas": alphas,
                        "history_start": start, "career_floor": opts["career_floor"]}, fp)
                    hit = load_cached_model(season, key)
                    if hit is not None:
                        artifacts, info = hit
                    self.stdout.write(f"  box model cache {'hit' if hit else 'miss'} for {season} "
                                      f"(key {key[:12]}, inputs hashed in {time.monotonic() - t0:.1f}s)")
            if artifacts is None:
                data = {s: get(s) for s in train}
                artifacts, info = fit_season(season, data, weighted, start, alphas=alphas,
                                             features=opts["features"], team_feature=opts["team_feature"])
                info["target"] = target
                info["target_lambda_fixed"] = target_lambda
                info["alpha_max"] = alphas[-1]
                if k is not None:
                    info["target_windows"] = {str(s): window_info[s] for s in train}
                if key is not None:
                    path = store_cached_model(season, key, artifacts, info)
                    self.stdout.write(f"  box model stored: {path}")
            info = dict(info)
            # Season Y's own inputs only (features); its targets are never needed.
            if season in cache:
                stats, opp, team, career = cache[season]["inputs"]
            else:
                stats, opp, team, career = load_season(season, opts["career_floor"],
                                                       team_feature=opts["team_feature"])["inputs"]
            preds = predict_nba_box_bpr(stats, opp, team, artifacts, career)
            info["n_predicted"] = len(preds)
            all_info.append(info)
            if out_dir is not None:
                nba_ids = nba_ids_for(preds)
                out = {str(nba_ids[pk]): [p["box_obpr"], p["box_dbpr"]] for pk, p in preds.items()}
                path = out_dir / f"box_{season}.json"
                with open(path, "w") as f:
                    json.dump(out, f)
                dest = str(path)
            else:
                dest = "dry run" if dry_run else "database"
            self.stdout.write(
                f"  {season}: train {train[0]}-{train[-1]} ({info['method']}, n={info['n_train']}"
                f"{', weighted' if weighted else ''}, features={opts['features']}, target={target})  off alpha={info['off_alpha']:g}  "
                f"def alpha={info['def_alpha']:g}  → {len(preds)} players {dest}")

        if single is not None:
            self.stdout.write(f"\nTop {TOP_N} by box_bpr, {single}:")
            for line in top_lines(preds, player_labels(preds.keys())):
                self.stdout.write(line)
            counts: dict[str, int] = {}
            for p in preds.values():
                counts[p["archetype"]] = counts.get(p["archetype"], 0) + 1
            self.stdout.write("Archetypes: " + ", ".join(f"{a} {n}" for a, n in sorted(counts.items(), key=lambda x: -x[1])))
            if dry_run:
                self.stdout.write(self.style.SUCCESS(f"Dry run: {len(preds)} players, no DB writes."))
                return
            res = write_season_box(single, preds)
            self.stdout.write(self.style.SUCCESS(
                f"[OK] {single} box written: cleared {res['cleared']} regular rows, "
                f"{res['updated']} updated, {res['skipped']} rows without a prediction left null"))
            return

        with open(out_dir / "alphas.json", "w") as f:
            json.dump(all_info, f, indent=2)
        if want_newcomers:
            means = {}
            for season in sorted(opts["seasons"]):
                for s in range(start, season):   # every earlier season is a training season, so loaded
                    get(s)
                means[str(season)] = newcomer_mean_for(season, newcomer_by_season, start)
            means["per_season"] = {str(s): {k_: round(v, 5) if isinstance(v, float) else v
                                            for k_, v in st.items()}
                                   for s, st in sorted(newcomer_by_season.items())}
            with open(out_dir / "newcomer_means.json", "w") as f:
                json.dump(means, f, indent=2)
            self.stdout.write(f"Newcomer means → {out_dir / 'newcomer_means.json'}")
        self.stdout.write(self.style.SUCCESS(f"Done. No DB writes. Alphas → {out_dir / 'alphas.json'}"))
