"""
backtest_bpr_margin — temporally-honest NCAA BPR out-of-sample margin backtest.

Train on season Y player ratings → predict season Y+1 game margins using Y ratings
on Y+1 rosters.  No Y+1 outcome ever touches model fitting.

Walk-forward / within-season refitting is the planned Layer-2 extension.
It requires a temporal cutoff in the dataset builder so that team strengths
at game-time only use stints/stats from before that date.  Not implemented here.

Usage:
    python manage.py backtest_bpr_margin
    python manage.py backtest_bpr_margin --predictor box_bpr
    python manage.py backtest_bpr_margin --compare
    python manage.py backtest_bpr_margin --compare --seasons 2022 2023 2024
    python manage.py backtest_bpr_margin --predictor adj_em --verbose
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
from django.core.management.base import BaseCommand, CommandError

from ncaa.models import Game, PlayerSeasonStats, TeamSeasonRatings

# ─── Constants ────────────────────────────────────────────────────────────────

COMPARE_PREDICTORS = ["bpr", "box_bpr", "adj_em", "home_only"]

_CALIB_EDGES = [-15.0, -10.0, -5.0, -2.0, 0.0, 2.0, 5.0, 10.0, 15.0]
_CALIB_LABELS = [
    "<-15", "-15:-10", "-10:-5", "-5:-2", "-2:0",
    "0:2", "2:5", "5:10", "10:15", ">15",
]


# ─── Data loading ─────────────────────────────────────────────────────────────

def _load_player_data() -> tuple[dict, dict]:
    """
    Returns:
        player_ratings[(player_id, year)] → {bpr, box_bpr, baseline_obpr,
                                              baseline_dbpr, off_poss}
        team_roster[(team_id, year)]       → list of {player_id, mpg, off_poss}
    """
    player_ratings: dict = {}
    team_roster: dict = defaultdict(list)

    for row in PlayerSeasonStats.objects.values(
        "player_id", "team_id", "season__year",
        "bpr", "box_bpr", "baseline_obpr", "baseline_dbpr",
        "mpg", "off_poss",
    ):
        yr  = row["season__year"]
        pid = row["player_id"]
        player_ratings[(pid, yr)] = {
            "bpr":           row["bpr"],
            "box_bpr":       row["box_bpr"],
            "baseline_obpr": row["baseline_obpr"],
            "baseline_dbpr": row["baseline_dbpr"],
            "off_poss":      row["off_poss"] or 0.0,
        }
        team_roster[(row["team_id"], yr)].append({
            "player_id": pid,
            "mpg":       row["mpg"] or 0.0,
        })

    return player_ratings, dict(team_roster)


def _load_adj_em() -> dict:
    """adj_em_map[(team_id, year)] → float"""
    adj_em_map: dict = {}
    for row in TeamSeasonRatings.objects.values("team_id", "season__year", "adj_em"):
        if row["adj_em"] is not None:
            adj_em_map[(row["team_id"], row["season__year"])] = float(row["adj_em"])
    return adj_em_map


def _load_games() -> dict:
    """games_by_year[year] → list of game dicts"""
    games_by_year: dict = defaultdict(list)
    for g in Game.objects.filter(
        status="final",
        home_score__isnull=False,
        away_score__isnull=False,
    ).values("id", "season_year", "home_team_id", "away_team_id",
             "home_score", "away_score", "neutral_site"):
        games_by_year[g["season_year"]].append(g)
    return dict(games_by_year)


# ─── Team strength ────────────────────────────────────────────────────────────

def _team_strength(
    team_id: int,
    rating_year: int,
    roster_year: int,
    predictor: str,
    player_ratings: dict,
    team_roster: dict,
    adj_em_map: dict,
    min_poss: int,
) -> tuple[float, float]:
    """
    Returns (strength, coverage).

    rating_year: which season's ratings to use.
    roster_year: which season's roster / mpg weights to use.
    coverage = Σ minshare(players WITH prior rating) / Σ minshare(all rostered).
    """
    if predictor == "home_only":
        return 0.0, 1.0

    if predictor == "adj_em":
        val = adj_em_map.get((team_id, rating_year))
        return (float(val) if val is not None else 0.0), (1.0 if val is not None else 0.0)

    # Player-level: bpr, box_bpr, baseline
    roster = team_roster.get((team_id, roster_year), [])
    if not roster:
        return 0.0, 0.0

    total_w = 0.0
    covered_w = 0.0
    wt_sum = 0.0

    for p in roster:
        w = min(p["mpg"] / 40.0, 1.0)
        total_w += w
        pr = player_ratings.get((p["player_id"], rating_year))
        if pr and pr["off_poss"] >= min_poss:
            if predictor == "baseline":
                val = (pr["baseline_obpr"] or 0.0) + (pr["baseline_dbpr"] or 0.0)
            elif predictor == "box_bpr":
                val = pr["box_bpr"] or 0.0
            else:  # bpr
                val = pr["bpr"] or 0.0
            wt_sum += val * w
            covered_w += w
        # else: league average = 0; player counted in total_w (lowers coverage)

    if total_w == 0.0:
        return 0.0, 0.0

    # Scale by minute-share so team_strength ≈ Σ(per-player contribution)
    scale = min(total_w, 5.0)
    return (wt_sum / total_w) * scale, covered_w / total_w


# ─── Folds ────────────────────────────────────────────────────────────────────

def _valid_rating_years(player_ratings: dict, predictor: str) -> set[int]:
    """Years where at least one PlayerSeasonStats row has a non-null predictor value."""
    if predictor == "baseline":
        return {yr for (_, yr), v in player_ratings.items()
                if v.get("baseline_obpr") is not None}
    if predictor == "box_bpr":
        return {yr for (_, yr), v in player_ratings.items()
                if v.get("box_bpr") is not None}
    # bpr (default)
    return {yr for (_, yr), v in player_ratings.items() if v.get("bpr") is not None}


def _build_folds(
    predictor: str,
    player_ratings: dict,
    adj_em_map: dict,
    games_by_year: dict,
    seasons_filter: list[int] | None,
) -> list[tuple[int, int]]:
    """
    Return sorted list of (train_year, test_year) consecutive pairs where
    the TRAINING year has actual non-null predictor data AND both years have games.
    For player-level predictors, 'data' means ≥1 non-null bpr/box_bpr/baseline row.
    """
    if predictor in ("adj_em", "home_only"):
        data_years = {yr for (_, yr) in adj_em_map}
    else:
        data_years = _valid_rating_years(player_ratings, predictor)

    game_years = set(games_by_year)
    all_years = sorted(data_years & game_years)

    if seasons_filter:
        season_set = set(seasons_filter)
        all_years = [y for y in all_years if y in season_set]

    year_set = set(all_years)
    return [(y, y + 1) for y in all_years if y + 1 in year_set]


# ─── OLS margin model ─────────────────────────────────────────────────────────

def _fit_ols(
    train_games: list[dict],
    predictor: str,
    train_year: int,
    player_ratings: dict,
    team_roster: dict,
    adj_em_map: dict,
    min_poss: int,
) -> tuple[float, float, float, float]:
    """
    Fit actual_margin = β0 + β1·strength_diff + β2·home_indicator on TRAIN games.
    Returns (beta0, beta1, beta2, sigma).
    Fitting is in-sample on train games — only estimates structural constants.
    """
    diffs = []
    hinds = []
    margins = []

    for g in train_games:
        h_str, _ = _team_strength(
            g["home_team_id"], train_year, train_year,
            predictor, player_ratings, team_roster, adj_em_map, min_poss,
        )
        a_str, _ = _team_strength(
            g["away_team_id"], train_year, train_year,
            predictor, player_ratings, team_roster, adj_em_map, min_poss,
        )
        diffs.append(h_str - a_str)
        hinds.append(0.0 if g["neutral_site"] else 1.0)
        margins.append(float(g["home_score"] - g["away_score"]))

    if not margins:
        return 0.0, 1.0, 3.0, 11.0  # safe fallback

    y = np.array(margins)
    X = np.column_stack([np.ones(len(margins)), diffs, hinds])
    coeffs, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    beta0, beta1, beta2 = float(coeffs[0]), float(coeffs[1]), float(coeffs[2])
    sigma = float(np.std(y - X @ coeffs))
    if sigma < 0.5:   # degenerate fit guard
        sigma = 11.0
    return beta0, beta1, beta2, sigma


def _predict_test(
    test_games: list[dict],
    train_year: int,
    test_year: int,
    predictor: str,
    beta0: float,
    beta1: float,
    beta2: float,
    sigma: float,
    player_ratings: dict,
    team_roster: dict,
    adj_em_map: dict,
    min_poss: int,
    min_coverage: float,
) -> tuple[list[dict], int]:
    """
    Predict test-season games using prior-season strengths.
    Returns (results, n_dropped).
    Coverage filter: drop game if min(home_cov, away_cov) < min_coverage.
    """
    results = []
    n_dropped = 0
    sq2 = math.sqrt(2.0)

    for g in test_games:
        h_str, h_cov = _team_strength(
            g["home_team_id"], train_year, test_year,
            predictor, player_ratings, team_roster, adj_em_map, min_poss,
        )
        a_str, a_cov = _team_strength(
            g["away_team_id"], train_year, test_year,
            predictor, player_ratings, team_roster, adj_em_map, min_poss,
        )
        game_cov = min(h_cov, a_cov)
        if game_cov < min_coverage:
            n_dropped += 1
            continue

        diff    = h_str - a_str
        home_ind = 0.0 if g["neutral_site"] else 1.0
        pred    = beta0 + beta1 * diff + beta2 * home_ind
        actual  = float(g["home_score"] - g["away_score"])
        p_home  = 0.5 * (1.0 + math.erf(pred / (sigma * sq2)))
        results.append({
            "game_id":   g["id"],
            "pred":      pred,
            "actual":    actual,
            "p_home":    p_home,
            "home_won":  1 if actual > 0 else 0,
            "coverage":  game_cov,
        })

    return results, n_dropped


# ─── Metrics ──────────────────────────────────────────────────────────────────

def _metrics(results: list[dict]) -> dict:
    if not results:
        return {}
    preds     = np.array([r["pred"]     for r in results])
    actuals   = np.array([r["actual"]   for r in results])
    p_homes   = np.array([r["p_home"]   for r in results])
    home_wons = np.array([r["home_won"] for r in results])

    rmse    = float(np.sqrt(np.mean((preds - actuals) ** 2)))
    mae     = float(np.mean(np.abs(preds - actuals)))
    win_acc = float(np.mean((preds > 0) == (actuals > 0)))
    brier   = float(np.mean((p_homes - home_wons) ** 2))
    auc     = _auc(preds, home_wons)
    mean_cov = float(np.mean([r["coverage"] for r in results]))

    return dict(n=len(results), rmse=rmse, mae=mae,
                win_acc=win_acc, brier=brier, auc=auc, mean_cov=mean_cov)


def _auc(scores: np.ndarray, labels: np.ndarray) -> float:
    wins   = scores[labels == 1]
    losses = scores[labels == 0]
    if not len(wins) or not len(losses):
        return float("nan")
    # numpy broadcasting — avoids O(n²) Python loop (~6M ops per fold)
    concordant = float(np.sum(wins[:, None] > losses[None, :]))
    tied       = float(np.sum(wins[:, None] == losses[None, :])) * 0.5
    return (concordant + tied) / (len(wins) * len(losses))


# ─── Calibration table ────────────────────────────────────────────────────────

def _calibration(results: list[dict]) -> list[tuple]:
    rows = []
    preds_arr = [r["pred"] for r in results]
    for i, label in enumerate(_CALIB_LABELS):
        lo = -math.inf if i == 0 else _CALIB_EDGES[i - 1]
        hi = math.inf  if i == len(_CALIB_LABELS) - 1 else _CALIB_EDGES[i]
        bucket = [r for r, p in zip(results, preds_arr) if lo <= p < hi]
        if not bucket:
            rows.append((label, 0, None, None, None))
        else:
            rows.append((
                label,
                len(bucket),
                sum(r["pred"]     for r in bucket) / len(bucket),
                sum(r["home_won"] for r in bucket) / len(bucket),
                sum(r["actual"]   for r in bucket) / len(bucket),
            ))
    return rows


# ─── Management command ───────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "Temporally-honest NCAA BPR out-of-sample margin backtest (train Y → test Y+1)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--predictor",
            choices=["bpr", "box_bpr", "baseline", "adj_em", "home_only"],
            default="bpr",
            help="Player/team rating to use as predictor (default: bpr)",
        )
        parser.add_argument(
            "--compare",
            action="store_true",
            help="Run bpr / box_bpr / adj_em / home_only on identical game sets and print comparison table",
        )
        parser.add_argument(
            "--seasons",
            type=int,
            nargs="+",
            default=None,
            help="Restrict to these season years, e.g. --seasons 2022 2023 2024",
        )
        parser.add_argument(
            "--min-coverage",
            type=float,
            default=0.40,
            help="Min prior-season minute-share coverage per team (default 0.40)",
        )
        parser.add_argument(
            "--min-bpr-poss",
            type=int,
            default=150,
            help="Min off_poss for a player to contribute team strength (default 150)",
        )
        parser.add_argument("--verbose", action="store_true")

    # ── entry point ───────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        predictor  = options["predictor"]
        compare    = options["compare"]
        seasons    = options["seasons"]
        min_cov    = options["min_coverage"]
        min_poss   = options["min_bpr_poss"]
        verbose    = options["verbose"]

        self.stdout.write("\nLoading data...")
        player_ratings, team_roster = _load_player_data()
        adj_em_map    = _load_adj_em()
        games_by_year = _load_games()
        self.stdout.write(
            f"  {len(player_ratings):,} player-season ratings  |  "
            f"{len(adj_em_map):,} team adj_em entries  |  "
            f"{sum(len(v) for v in games_by_year.values()):,} completed games\n"
        )

        if compare:
            self._run_compare(
                player_ratings, team_roster, adj_em_map, games_by_year,
                seasons, min_cov, min_poss, verbose,
            )
        else:
            self._run_single(
                predictor, player_ratings, team_roster, adj_em_map, games_by_year,
                seasons, min_cov, min_poss, verbose,
            )

    # ── single predictor ─────────────────────────────────────────────────────

    def _run_single(self, predictor, player_ratings, team_roster, adj_em_map,
                    games_by_year, seasons, min_cov, min_poss, verbose):
        folds = _build_folds(predictor, player_ratings, adj_em_map,
                             games_by_year, seasons)
        if not folds:
            raise CommandError("No valid (train, test) consecutive fold pairs found.")

        self.stdout.write(f"[{predictor.upper()}]  {len(folds)} folds\n")

        all_results: list[dict] = []

        for train_year, test_year in folds:
            b0, b1, b2, sig = _fit_ols(
                games_by_year.get(train_year, []), predictor, train_year,
                player_ratings, team_roster, adj_em_map, min_poss,
            )
            results, n_dropped = _predict_test(
                games_by_year.get(test_year, []),
                train_year, test_year, predictor,
                b0, b1, b2, sig,
                player_ratings, team_roster, adj_em_map,
                min_poss, min_cov,
            )
            m = _metrics(results)
            all_results.extend(results)

            line = (
                f"  {train_year}→{test_year}  n={m.get('n', 0):5d}  "
                f"dropped={n_dropped:4d}  "
                f"β1={b1:+.3f}  β2={b2:+.3f}  σ={sig:.2f}  "
                f"RMSE={m.get('rmse', 0):.3f}  MAE={m.get('mae', 0):.3f}  "
                f"WinAcc={m.get('win_acc', 0):.3f}  AUC={m.get('auc', 0):.3f}  "
                f"Brier={m.get('brier', 0):.4f}  cov={m.get('mean_cov', 0):.2f}"
            )
            self.stdout.write(line)

            if verbose and results:
                self._print_calib(results)

        if all_results:
            pm = _metrics(all_results)
            self.stdout.write(
                f"\n  POOLED ({len(folds)} folds)  n={pm['n']:,}  "
                f"RMSE={pm['rmse']:.3f}  MAE={pm['mae']:.3f}  "
                f"WinAcc={pm['win_acc']:.3f}  AUC={pm['auc']:.3f}  "
                f"Brier={pm['brier']:.4f}"
            )
            if verbose:
                self._print_calib(all_results, header="Pooled calibration:")

    # ── compare mode ─────────────────────────────────────────────────────────

    def _run_compare(self, player_ratings, team_roster, adj_em_map,
                     games_by_year, seasons, min_cov, min_poss, verbose):
        # Folds driven by bpr (most restrictive — starts 2015, no 2025)
        folds = _build_folds("bpr", player_ratings, adj_em_map,
                             games_by_year, seasons)
        if not folds:
            raise CommandError("No valid folds for bpr — cannot build compare intersection.")

        self.stdout.write(f"[COMPARE]  {len(folds)} folds  (intersection of bpr-covered games)\n")

        pred_results: dict[str, list] = {p: [] for p in COMPARE_PREDICTORS}
        sanity_rows: list[dict] = []

        for train_year, test_year in folds:
            train_games = games_by_year.get(train_year, [])
            test_games  = games_by_year.get(test_year, [])

            # Fit a margin model per predictor
            models: dict[str, tuple] = {}
            for pred in COMPARE_PREDICTORS:
                models[pred] = _fit_ols(
                    train_games, pred, train_year,
                    player_ratings, team_roster, adj_em_map, min_poss,
                )

            # Predict all test games per predictor (coverage filter deferred to intersection)
            fold_by_game: dict[str, dict] = {}
            for pred in COMPARE_PREDICTORS:
                b0, b1, b2, sig = models[pred]
                raw, _ = _predict_test(
                    test_games, train_year, test_year, pred,
                    b0, b1, b2, sig,
                    player_ratings, team_roster, adj_em_map,
                    min_poss, min_coverage=0.0,
                )
                fold_by_game[pred] = {r["game_id"]: r for r in raw}

            # Intersect: pass only if bpr AND box_bpr both meet min_coverage
            bpr_pass    = {gid for gid, r in fold_by_game["bpr"].items()
                           if r["coverage"] >= min_cov}
            boxbpr_pass = {gid for gid, r in fold_by_game["box_bpr"].items()
                           if r["coverage"] >= min_cov}
            valid_gids  = bpr_pass & boxbpr_pass

            for pred in COMPARE_PREDICTORS:
                gmap = fold_by_game[pred]
                for gid in valid_gids:
                    if gid in gmap:
                        pred_results[pred].append(gmap[gid])

            b0_bpr, b1_bpr, b2_bpr, sig_bpr = models["bpr"]
            sanity_rows.append(dict(
                train=train_year, test=test_year,
                beta1=b1_bpr, beta2=b2_bpr, sigma=sig_bpr, n=len(valid_gids),
            ))
            if verbose:
                self.stdout.write(
                    f"  {train_year}→{test_year}  n={len(valid_gids):5d}  "
                    f"β1={b1_bpr:+.3f}  β2={b2_bpr:+.3f}  σ={sig_bpr:.2f}"
                )

        # Print comparison table
        W = 74
        self.stdout.write("\n" + "─" * W)
        self.stdout.write(
            f"  {'Predictor':<12} {'n_games':>8}  {'MarginRMSE':>11}  "
            f"{'MarginMAE':>10}  {'WinAcc':>7}  {'AUC':>7}  {'Brier':>7}"
        )
        self.stdout.write("─" * W)
        for pred in COMPARE_PREDICTORS:
            m = _metrics(pred_results[pred])
            if not m:
                self.stdout.write(f"  {pred:<12}  no data")
                continue
            self.stdout.write(
                f"  {pred:<12} {m['n']:>8,}  {m['rmse']:>11.3f}  "
                f"{m['mae']:>10.3f}  {m['win_acc']:>7.3f}  "
                f"{m['auc']:>7.3f}  {m['brier']:>7.4f}"
            )
        self.stdout.write("─" * W)

        # Step 6 sanity checks (bpr model coefficients)
        if sanity_rows:
            nb   = len(sanity_rows)
            ab1  = sum(r["beta1"] for r in sanity_rows) / nb
            ab2  = sum(r["beta2"] for r in sanity_rows) / nb
            asig = sum(r["sigma"] for r in sanity_rows) / nb
            an   = sum(r["n"]     for r in sanity_rows) / nb
            self.stdout.write(
                f"\n  Sanity — bpr model avg across {nb} folds:\n"
                f"    β1={ab1:+.3f}  β2={ab2:+.3f}  σ={asig:.2f}  "
                f"avg_n_per_fold={an:.0f}"
            )
            issues = []
            if ab1 <= 0:
                issues.append(f"β1={ab1:+.3f} not positive — harness bug?")
            if not (2.0 <= ab2 <= 4.0):
                issues.append(f"β2={ab2:+.3f} outside expected [2, 4] — check neutral_site")
            if not (9.0 <= asig <= 14.0):
                issues.append(f"σ={asig:.2f} outside expected [9, 14] — check score fields")
            if an < 3000:
                issues.append(f"avg n/fold={an:.0f} below 3 000 — low coverage")
            rmse_bpr     = _metrics(pred_results["bpr"]).get("rmse", 9999)
            rmse_ho      = _metrics(pred_results["home_only"]).get("rmse", 9999)
            if rmse_bpr >= rmse_ho:
                issues.append(
                    f"bpr RMSE ({rmse_bpr:.3f}) ≥ home_only RMSE ({rmse_ho:.3f}) — no signal"
                )
            if issues:
                for issue in issues:
                    self.stdout.write(self.style.WARNING(f"  ⚠  {issue}"))
            else:
                self.stdout.write(self.style.SUCCESS("  ✓  All sanity checks pass"))

        if verbose:
            self.stdout.write("")
            self._print_calib(pred_results["bpr"], header="Pooled calibration (bpr):")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _print_calib(self, results: list[dict], header: str = "Calibration:") -> None:
        self.stdout.write(f"\n  {header}")
        self.stdout.write(
            f"  {'Bucket':<12} {'n':>5}  {'MeanPred':>9}  {'HomeWin%':>9}  {'MeanActual':>11}"
        )
        for label, n, mp, wr, ma in _calibration(results):
            if n == 0:
                self.stdout.write(f"  {label:<12} {'—':>5}")
            else:
                self.stdout.write(
                    f"  {label:<12} {n:>5}  {mp:>+9.2f}  {wr:>9.1%}  {ma:>+11.2f}"
                )
