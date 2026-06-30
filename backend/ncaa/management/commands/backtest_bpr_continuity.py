"""
backtest_bpr_continuity — Roster-continuity split of the cross-season BPR backtest.

Hypothesis: last season's TEAM rating (adj_em) goes stale faster than last season's
PLAYER ratings (BPR) when roster turnover is high. Tests whether Δ(bpr_RMSE −
adj_em_RMSE) shrinks — or flips in BPR's favor — as continuity falls.

The falsifiable verdict metric is ΔRMSE = bpr_RMSE − adj_em_RMSE per continuity
bucket. This differences-out program-quality confounds: blue-bloods churn rosters
AND reload with elite talent, so raw RMSE per bucket would conflate program quality
with the continuity effect. The gap between predictors on IDENTICAL games isolates
the continuity signal.

Continuity definition (minutes-weighted, not headcount):
  continuity(team, Y+1) = Σ actual_minutes(player, Y+1) for returning players
                          / Σ actual_minutes(player, Y+1) for all players
  "returning" = played in season Y on ANY team (transfers still carry BPR history).

game_continuity = MIN(home_continuity, away_continuity).

Buckets: [0.0, 0.4) low | [0.4, 0.6) mid-low | [0.6, 0.8) mid-high | [0.8, 1.0] high
Verdict only from buckets with ≥ min_bucket_games games.

Reuses:
  - _load_player_data, _load_adj_em, _load_games, _build_folds (backtest_bpr_margin)
  - _team_strength, _fit_ols, _auc, _metrics, predict_margin_and_prob (game_prediction)

No DB writes. Read-only.

Usage:
    python manage.py backtest_bpr_continuity
    python manage.py backtest_bpr_continuity --min-bucket-games 500 --verbose
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
from django.core.management.base import BaseCommand

from ncaa.analytics.player_value.bpr.game_prediction import (
    _team_strength,
    _fit_ols,
    _auc,
    _metrics,
    predict_margin_and_prob,
)
from ncaa.management.commands.backtest_bpr_margin import (
    _load_player_data,
    _load_adj_em,
    _load_games,
    _build_folds,
    COMPARE_PREDICTORS,
)
from ncaa.models import PlayerSeasonStats

BUCKET_EDGES = [
    (0.0,  0.40, "low"),
    (0.40, 0.60, "mid-low"),
    (0.60, 0.80, "mid-high"),
    (0.80, 1.01, "high"),
]


def _bucket_for(cont: float) -> str:
    for lo, hi, label in BUCKET_EDGES:
        if lo <= cont < hi:
            return label
    return "high"


def _pct(arr, q):
    return float(np.percentile(arr, q)) if len(arr) else float("nan")


class Command(BaseCommand):
    help = "Cross-season BPR backtest split by roster continuity (ΔRMSE hypothesis test)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--min-bucket-games", type=int, default=1000,
            help="Minimum games per bucket to count toward verdict (default: 1000)",
        )
        parser.add_argument(
            "--min-coverage", type=float, default=0.40,
            help="Min BPR roster coverage to include a game (default: 0.40)",
        )
        parser.add_argument(
            "--min-bpr-poss", type=int, default=150,
            help="Min player possessions to contribute to team strength (default: 150)",
        )
        parser.add_argument(
            "--verbose", action="store_true", default=False,
        )

    def handle(self, *args, **options):
        min_bucket  = options["min_bucket_games"]
        min_cov     = options["min_coverage"]
        min_poss    = options["min_bpr_poss"]
        verbose     = options["verbose"]

        # ── Load data ──────────────────────────────────────────────────────────
        self.stdout.write("\nLoading data...")
        player_ratings, team_roster = _load_player_data()
        adj_em_map    = _load_adj_em()
        games_by_year = _load_games()
        self.stdout.write(
            f"  {len(player_ratings):,} player-season ratings  |  "
            f"{len(adj_em_map):,} team adj_em entries  |  "
            f"{sum(len(v) for v in games_by_year.values()):,} completed games"
        )

        # ── Build folds (driven by bpr — most restrictive) ────────────────────
        folds = _build_folds("bpr", player_ratings, adj_em_map, games_by_year, None)
        if not folds:
            self.stdout.write("ERROR: No valid BPR folds found.")
            return

        test_years = [ty for _, ty in folds]
        train_years = [ty for ty, _ in folds]
        self.stdout.write(
            f"  {len(folds)} folds: {[(tr, te) for tr, te in folds]}"
        )

        # ── Compute continuity per (team, test_year) ──────────────────────────
        self.stdout.write("\nComputing roster continuity (minutes-weighted)...")

        # Which players were active in each train year?
        prior_pid_set: dict[int, set] = {}
        for train_year in train_years:
            prior_pid_set[train_year] = set(
                PlayerSeasonStats.objects.filter(season__year=train_year)
                .values_list("player_id", flat=True)
            )

        # Accumulate minutes per (team, test_year)
        team_total:     dict[tuple, float] = defaultdict(float)
        team_returning: dict[tuple, float] = defaultdict(float)

        pss_rows = list(
            PlayerSeasonStats.objects.filter(
                season__year__in=test_years,
                mpg__isnull=False, gp__isnull=False,
            ).values("player_id", "team_id", "season__year", "mpg", "gp")
        )
        for r in pss_rows:
            yr = r["season__year"]
            mins = (r["mpg"] or 0.0) * (r["gp"] or 0)
            if mins <= 0:
                continue
            key = (r["team_id"], yr)
            team_total[key] += mins
            prior_year = yr - 1
            if r["player_id"] in prior_pid_set.get(prior_year, set()):
                team_returning[key] += mins

        continuity: dict[tuple, float] = {
            key: team_returning[key] / team_total[key]
            for key in team_total
        }

        cont_vals = list(continuity.values())
        self.stdout.write(
            f"  {len(continuity)} (team, year) pairs  |  "
            f"min={_pct(cont_vals, 0):.3f}  p25={_pct(cont_vals, 25):.3f}  "
            f"median={_pct(cont_vals, 50):.3f}  p75={_pct(cont_vals, 75):.3f}  "
            f"max={_pct(cont_vals, 100):.3f}"
        )

        # ── Run folds, collect results with team metadata ─────────────────────
        self.stdout.write(f"\nRunning {len(folds)} cross-season folds...")

        # pred_results[predictor] = list of result dicts (with team IDs + continuity)
        pred_results: dict[str, list] = {p: [] for p in COMPARE_PREDICTORS}

        for train_year, test_year in folds:
            train_games = games_by_year.get(train_year, [])
            test_games  = games_by_year.get(test_year, [])

            # Fit OLS per predictor on FULL train games (not per bucket)
            models: dict[str, tuple] = {
                pred: _fit_ols(
                    train_games, pred, train_year,
                    player_ratings, team_roster, adj_em_map, min_poss,
                )
                for pred in COMPARE_PREDICTORS
            }

            # Predict all test games (coverage=0.0 deferred; store team IDs)
            fold_by_game: dict[str, dict] = {}
            for pred in COMPARE_PREDICTORS:
                b0, b1, b2, sig = models[pred]
                fold_by_game[pred] = {}
                for g in test_games:
                    h_str, h_cov = _team_strength(
                        g["home_team_id"], train_year, test_year,
                        pred, player_ratings, team_roster, adj_em_map, min_poss,
                    )
                    a_str, a_cov = _team_strength(
                        g["away_team_id"], train_year, test_year,
                        pred, player_ratings, team_roster, adj_em_map, min_poss,
                    )
                    game_cov = min(h_cov, a_cov)
                    pred_margin, p_home = predict_margin_and_prob(
                        h_str, a_str, bool(g["neutral_site"]), b0, b1, b2, sig,
                    )
                    actual = float(g["home_score"] - g["away_score"])
                    fold_by_game[pred][g["id"]] = {
                        "game_id":      g["id"],
                        "home_team_id": g["home_team_id"],
                        "away_team_id": g["away_team_id"],
                        "test_year":    test_year,
                        "pred":         pred_margin,
                        "actual":       actual,
                        "p_home":       p_home,
                        "home_won":     1 if actual > 0 else 0,
                        "coverage":     game_cov,
                    }

            # Intersect: game passes only if bpr AND box_bpr both meet min_coverage
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

            if verbose:
                b0b, b1b, b2b, sigb = models["bpr"]
                self.stdout.write(
                    f"  {train_year}→{test_year}  n_valid={len(valid_gids):5d}  "
                    f"β1={b1b:+.3f}  β2={b2b:+.3f}  σ={sigb:.2f}"
                )

        # ── Assign continuity buckets ─────────────────────────────────────────
        # Use bpr results (largest intersection); annotate all predictors by game_id
        game_buckets: dict[int, str] = {}
        game_cont_vals: list[float] = []

        for r in pred_results["bpr"]:
            h_cont = continuity.get((r["home_team_id"], r["test_year"]), 0.0)
            a_cont = continuity.get((r["away_team_id"], r["test_year"]), 0.0)
            gc = min(h_cont, a_cont)
            game_buckets[r["game_id"]] = _bucket_for(gc)
            game_cont_vals.append(gc)

        # Add bucket to ALL predictor results
        for pred in COMPARE_PREDICTORS:
            for r in pred_results[pred]:
                r["bucket"] = game_buckets.get(r["game_id"], "unknown")

        # ── Count per bucket (before metrics) ─────────────────────────────────
        bucket_order = [label for _, _, label in BUCKET_EDGES]
        bucket_n: dict[str, int] = defaultdict(int)
        for r in pred_results["bpr"]:
            bucket_n[r["bucket"]] += 1

        self.stdout.write(f"\nPer-bucket game counts (min_coverage={min_cov:.0%}):")
        for bucket in bucket_order:
            n = bucket_n[bucket]
            status = "VALID" if n >= min_bucket else f"INSUFFICIENT (<{min_bucket})"
            self.stdout.write(f"  {bucket:<12}  {n:6,}  [{status}]")

        valid_buckets = [b for b in bucket_order if bucket_n[b] >= min_bucket]
        if len(valid_buckets) < 2:
            self.stdout.write(
                f"\nWARNING: Only {len(valid_buckets)} bucket(s) meet the {min_bucket}-game "
                f"floor — cannot evaluate monotone trend. Verdict is INCONCLUSIVE."
            )

        # ── Compute metrics per bucket per predictor ───────────────────────────
        W = 100
        self.stdout.write(f"\n{'='*W}")
        self.stdout.write("HEADLINE: Δ(bpr − adj_em) RMSE by continuity bucket")
        self.stdout.write(f"  Positive Δ = adj_em beats bpr.  Hypothesis: Δ shrinks as continuity falls.")
        self.stdout.write(f"{'='*W}")
        hdr = (
            f"  {'Bucket':<10}  {'n':>6}  "
            f"{'bpr_RMSE':>9}  {'adj_RMSE':>9}  {'Δ(b-a)':>8}  "
            f"{'box_RMSE':>9}  {'Δ(b-x)':>8}  "
            f"{'bpr_WA':>7}  {'adj_WA':>7}  "
            f"{'bpr_AUC':>8}  {'adj_AUC':>8}"
        )
        self.stdout.write(hdr)
        self.stdout.write("  " + "─" * (len(hdr) - 2))

        bucket_metrics: dict[str, dict] = {}
        for bucket in bucket_order:
            metrics_per: dict[str, dict] = {}
            for pred in COMPARE_PREDICTORS:
                subset = [r for r in pred_results[pred] if r["bucket"] == bucket]
                metrics_per[pred] = _metrics(subset)
            bucket_metrics[bucket] = metrics_per

            n = bucket_n[bucket]
            if n == 0:
                self.stdout.write(f"  {bucket:<10}  {'—':>6}")
                continue

            mb  = metrics_per["bpr"]
            ma  = metrics_per["adj_em"]
            mx  = metrics_per["box_bpr"]
            if not mb or not ma:
                self.stdout.write(f"  {bucket:<10}  {n:>6,}  (insufficient data)")
                continue

            delta_ba = mb["rmse"] - ma["rmse"]
            delta_bx = mb["rmse"] - mx.get("rmse", float("nan"))
            valid_marker = "" if n >= min_bucket else " *"

            self.stdout.write(
                f"  {bucket:<10}  {n:>6,}  "
                f"{mb['rmse']:>9.3f}  {ma['rmse']:>9.3f}  {delta_ba:>+8.3f}  "
                f"{mx.get('rmse', float('nan')):>9.3f}  {delta_bx:>+8.3f}  "
                f"{mb['win_acc']:>7.3f}  {ma['win_acc']:>7.3f}  "
                f"{mb['auc']:>8.4f}  {ma['auc']:>8.4f}"
                + valid_marker
            )

        self.stdout.write(f"  (* bucket below {min_bucket}-game floor — excluded from verdict)")

        # ── Robustness: adj_em raw RMSE by bucket ────────────────────────────
        self.stdout.write(f"\nadj_em RMSE by bucket (raw — does adj_em degrade in low-continuity?):")
        for bucket in bucket_order:
            ma = bucket_metrics[bucket].get("adj_em", {})
            n = bucket_n[bucket]
            rmse_str = f"{ma['rmse']:.3f}" if ma else "—"
            self.stdout.write(f"  {bucket:<12}  n={n:6,}  adj_em_RMSE={rmse_str}")

        # ── Sanity: high-continuity ≈ pooled baseline ─────────────────────────
        pooled_bpr  = _metrics(pred_results["bpr"])
        pooled_adj  = _metrics(pred_results["adj_em"])
        high_bpr    = bucket_metrics.get("high", {}).get("bpr", {})
        high_adj    = bucket_metrics.get("high", {}).get("adj_em", {})

        self.stdout.write(f"\nSanity check (high-continuity ≈ pooled baseline):")
        self.stdout.write(
            f"  Pooled: bpr_RMSE={pooled_bpr.get('rmse', 0):.3f}  "
            f"adj_RMSE={pooled_adj.get('rmse', 0):.3f}  "
            f"Δ={pooled_bpr.get('rmse', 0) - pooled_adj.get('rmse', 0):+.3f}"
        )
        if high_bpr and high_adj:
            self.stdout.write(
                f"  High:   bpr_RMSE={high_bpr.get('rmse', 0):.3f}  "
                f"adj_RMSE={high_adj.get('rmse', 0):.3f}  "
                f"Δ={high_bpr.get('rmse', 0) - high_adj.get('rmse', 0):+.3f}"
            )
            expected_delta = pooled_bpr.get("rmse", 0) - pooled_adj.get("rmse", 0)
            high_delta = high_bpr.get("rmse", 0) - high_adj.get("rmse", 0)
            if abs(high_delta - expected_delta) > 1.5:
                self.stdout.write(
                    f"  WARNING: high-continuity Δ ({high_delta:+.3f}) diverges from pooled "
                    f"({expected_delta:+.3f}) by >{1.5:.1f} — check for season subset bias."
                )

        # ── Verdict ───────────────────────────────────────────────────────────
        self.stdout.write(f"\n{'='*W}")
        self.stdout.write("VERDICT")
        self.stdout.write(f"{'='*W}")

        if len(valid_buckets) < 2:
            self.stdout.write("  INCONCLUSIVE — fewer than 2 buckets meet the game-count floor.")
            self.stdout.write(f"  Valid buckets: {valid_buckets or ['none']}")
        else:
            valid_deltas = [
                (bucket, bucket_metrics[bucket]["bpr"]["rmse"] - bucket_metrics[bucket]["adj_em"]["rmse"])
                for bucket in valid_buckets
                if bucket_metrics[bucket].get("bpr") and bucket_metrics[bucket].get("adj_em")
            ]
            # Order from low continuity to high
            ordered = [(b, d) for b, d in valid_deltas if b in bucket_order]
            ordered.sort(key=lambda x: bucket_order.index(x[0]))

            low_delta  = ordered[0][1]  if ordered else None
            high_delta = ordered[-1][1] if ordered else None

            if low_delta is not None and high_delta is not None:
                # Monotone check: each successive bucket should have higher Δ (bpr falls further behind)
                deltas_ordered = [d for _, d in ordered]
                is_monotone = all(
                    deltas_ordered[i] <= deltas_ordered[i + 1]
                    for i in range(len(deltas_ordered) - 1)
                )

                if low_delta < 0:
                    verdict = "CONFIRMED + FLIP — BPR BEATS adj_em in low-continuity bucket"
                elif low_delta < high_delta:
                    verdict = "CONFIRMED — gap shrinks as continuity falls (BPR more competitive at low continuity)"
                else:
                    verdict = "NOT CONFIRMED — gap flat or widening toward low continuity"

                self.stdout.write(f"  {verdict}")
                self.stdout.write(f"  Δ values (low→high continuity): "
                                  + "  →  ".join(f"{b}={d:+.3f}" for b, d in ordered))
                self.stdout.write(f"  Δ at low continuity: {low_delta:+.3f}  |  "
                                  f"Δ at high continuity: {high_delta:+.3f}  |  "
                                  f"Monotone: {'YES' if is_monotone else 'NO'}")

                # WinAcc robustness check
                wa_agrees = []
                for i in range(len(ordered) - 1):
                    b_lo, _ = ordered[i]
                    b_hi, _ = ordered[i + 1]
                    wa_lo = (bucket_metrics[b_lo]["bpr"].get("win_acc", 0)
                             - bucket_metrics[b_lo]["adj_em"].get("win_acc", 0))
                    wa_hi = (bucket_metrics[b_hi]["bpr"].get("win_acc", 0)
                             - bucket_metrics[b_hi]["adj_em"].get("win_acc", 0))
                    wa_agrees.append(wa_lo <= wa_hi)

                self.stdout.write(
                    f"  WinAcc Δ directional agreement with RMSE: "
                    + ("YES — consistent" if all(wa_agrees) else "PARTIAL/NO — check WinAcc columns above")
                )
            else:
                self.stdout.write("  INCONCLUSIVE — missing metrics for comparison.")

        self.stdout.write("")
