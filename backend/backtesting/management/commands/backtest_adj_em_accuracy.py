"""
backtest_adj_em_accuracy — Measures AdjEM/AdjO/AdjD game prediction accuracy
against KenPom/EvanMiya benchmarks.

Methodology:
  Uses end-of-season TeamSeasonRatings (in-sample) to predict all completed
  D1 vs D1 games via forecast_game(). This is the ceiling estimate — true
  out-of-sample accuracy will be ~1-2% lower (use backtest_shrinkage for OOS).

  Per game:
    - site determined from Game.neutral_site / home/away teams
    - forecast_game() → prob_home, predicted_margin
    - SU correct if predicted winner == actual winner
    - Brier = (prob_home - actual_home_outcome)^2

Segments (mirrors KenPom published benchmarks):
  - Overall
  - Close games: |actual_margin| <= 7 (KenPom: 60.5%)
  - Very close:  |actual_margin| <= 3 (KenPom: 52.7%)
  - Early season: game_number_for_team <= 10
  - Late season:  game in final 14 days of regular season

Benchmarks (from user research, 2026):
  KenPom:       ~73.0% SU
  Torvik:       ~73.0% SU
  EvanMiya:     ~74-75% SU, ~0.175 Brier
  Top ensemble: ~74-75% SU, 0.170-0.175 Brier
  OddsGods:      72.6% SU, 0.183 Brier

Macfax targets:
  Floor:  70-73% SU  (KenPom/Torvik tier)
  Elite:  74-75% SU  (EvanMiya tier)
  Brier:  <0.183 (good), <0.175 (elite)

Usage:
    python manage.py backtest_adj_em_accuracy
    python manage.py backtest_adj_em_accuracy --seasons 2024 2025 2026
    python manage.py backtest_adj_em_accuracy --verbose
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand


# ── Stat helpers (mirrors backtest_bpr_game_prediction) ───────────────────────

def _mean(v): return sum(v) / len(v) if v else 0.0

def _brier(probs, outcomes):
    return sum((p - o) ** 2 for p, o in zip(probs, outcomes)) / len(probs)

def _auc(scores, labels):
    pos = [s for s, l in zip(scores, labels) if l == 1]
    neg = [s for s, l in zip(scores, labels) if l == 0]
    if not pos or not neg:
        return float("nan")
    u = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return u / (len(pos) * len(neg))

def _logistic(x):
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)

def _ols_logistic_fit(xs, ys):
    a, b = 0.0, 0.01
    lr = 0.01
    for _ in range(500):
        da = db = 0.0
        for x, y in zip(xs, ys):
            pred = _logistic(a + b * x)
            err = pred - y
            da += err
            db += err * x
        n = len(xs)
        a -= lr * da / n
        b -= lr * db / n
    return a, b

def _rmse(errs):
    return math.sqrt(sum(e ** 2 for e in errs) / len(errs)) if errs else 0.0

def _section(t, w=72): return f"\n{'═'*w}\n  {t}\n{'═'*w}"

def _pass_fail(val, target, higher_is_better=True):
    ok = val >= target if higher_is_better else val <= target
    return "✓ PASS" if ok else "✗ FAIL"


# ── Accuracy metrics for a slice of predictions ───────────────────────────────

def _metrics(probs_home, outcomes_home, margins_pred, margins_actual):
    """
    Returns dict of accuracy metrics for a set of predictions.
    probs_home: list[float] — P(home wins) from forecast_game
    outcomes_home: list[int] — 1 if home actually won
    margins_pred: list[float] — predicted home margin
    margins_actual: list[float] — actual home margin
    """
    n = len(probs_home)
    if n == 0:
        return None

    # Re-calibrate probabilities with logistic fit for Brier/AUC
    # (mirrors backtest_bpr approach — in-season fit, slight overfit but diagnostic)
    try:
        a, b = _ols_logistic_fit(margins_pred, outcomes_home)
        cal_probs = [_logistic(a + b * m) for m in margins_pred]
    except Exception:
        cal_probs = probs_home

    # SU accuracy: pick higher-prob team
    su_preds = [1 if p >= 0.5 else 0 for p in probs_home]
    accuracy = sum(p == o for p, o in zip(su_preds, outcomes_home)) / n

    home_rate = _mean(outcomes_home)
    naive_acc = max(home_rate, 1 - home_rate)

    auc_score = _auc(probs_home, outcomes_home)
    brier_score = _brier(cal_probs, outcomes_home)

    errs = [mp - ma for mp, ma in zip(margins_pred, margins_actual)]
    spread_mae = _mean([abs(e) for e in errs])
    spread_rmse = _rmse(errs)
    spread_bias = _mean(errs)

    return {
        "n": n,
        "accuracy": accuracy,
        "naive": naive_acc,
        "lift": accuracy - naive_acc,
        "auc": auc_score,
        "brier": brier_score,
        "spread_mae": spread_mae,
        "spread_rmse": spread_rmse,
        "spread_bias": spread_bias,
        "home_rate": home_rate,
    }


# ── Command ───────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        "Backtest AdjEM/AdjO/AdjD game prediction accuracy vs KenPom/EvanMiya benchmarks. "
        "Uses end-of-season ratings (in-sample ceiling estimate)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--seasons", nargs="+", type=int, default=None,
            help="Season years to evaluate (default: all with TeamSeasonRatings data).",
        )
        parser.add_argument(
            "--verbose", action="store_true", default=False,
        )
        parser.add_argument(
            "--min-games", type=int, default=5,
            help="Min games a team needs in TeamSeasonRatings to be included (default: 5).",
        )

    def handle(self, *args, **options):
        from ncaa.models import Game, NationalAverages, Season, TeamSeasonRatings
        from api.matchup_engine import forecast_game

        verbose = options["verbose"]
        min_games = options["min_games"]

        # ── Determine seasons ─────────────────────────────────────────────────
        all_seasons = list(
            Season.objects.filter(
                team_ratings__adj_o__isnull=False,
                team_ratings__adj_d__isnull=False,
            ).values_list("year", flat=True).distinct().order_by("year")
        )
        requested = options["seasons"]
        seasons = [y for y in (requested or all_seasons) if y in all_seasons]

        if not seasons:
            self.stdout.write("No seasons with TeamSeasonRatings. Run compute_adjusted_ratings first.")
            return

        self.stdout.write(_section(f"ADJUSTED RATINGS GAME PREDICTION ACCURACY — in-sample"))
        self.stdout.write(
            "  NOTE: end-of-season ratings used to predict all season games.\n"
            "  This is the ceiling estimate (~1-2% above true OOS). Use\n"
            "  backtest_shrinkage for rigorous out-of-sample spread MAE.\n"
        )
        self.stdout.write(f"  Seasons: {seasons}  |  min team games: {min_games}\n")

        # ── Per-season evaluation ─────────────────────────────────────────────
        all_probs:    list[float] = []
        all_outcomes: list[int]   = []
        all_mpred:    list[float] = []
        all_mactual:  list[float] = []

        # For segmentation across all seasons
        seg_close:   dict = {"probs": [], "outcomes": [], "mpred": [], "mactual": []}
        seg_vclose:  dict = {"probs": [], "outcomes": [], "mpred": [], "mactual": []}
        seg_early:   dict = {"probs": [], "outcomes": [], "mpred": [], "mactual": []}
        seg_late:    dict = {"probs": [], "outcomes": [], "mpred": [], "mactual": []}

        season_results = {}

        for yr in seasons:
            # Load ratings for this season
            ratings_qs = list(
                TeamSeasonRatings.objects.filter(
                    season__year=yr,
                    adj_o__isnull=False,
                    adj_d__isnull=False,
                    adj_em__isnull=False,
                    adj_tempo__isnull=False,
                    games_played__gte=min_games,
                ).values("team_id", "adj_o", "adj_d", "adj_em", "adj_tempo")
            )

            if not ratings_qs:
                if verbose:
                    self.stdout.write(f"  {yr}: no ratings — skip")
                continue

            ratings = {r["team_id"]: r for r in ratings_qs}

            # Load national averages
            try:
                nat = NationalAverages.objects.get(season__year=yr)
                nat_ortg = nat.avg_ortg or 108.0
                hca = nat.hca_points or 1.85
                sigma = nat.prediction_sigma or 11.08
            except NationalAverages.DoesNotExist:
                nat_ortg, hca, sigma = 108.0, 1.85, 11.08

            # Load completed D1 vs D1 games
            games = list(
                Game.objects.filter(
                    season_year=yr,
                    status="final",
                    home_score__isnull=False,
                    away_score__isnull=False,
                    home_team__is_d1=True,
                    away_team__is_d1=True,
                ).values(
                    "id", "game_date",
                    "home_team_id", "away_team_id",
                    "home_score", "away_score",
                    "neutral_site",
                ).order_by("game_date")
            )

            if not games:
                if verbose:
                    self.stdout.write(f"  {yr}: no final games — skip")
                continue

            # Compute per-team game sequence numbers (for early/late segmentation)
            team_game_count: dict[int, int] = defaultdict(int)
            # Determine late-season cutoff: last 14 days of regular season
            # Use the final game date in the season as anchor
            max_date = max(g["game_date"] for g in games)
            late_cutoff = max_date - timedelta(days=14)

            yr_probs, yr_outcomes, yr_mpred, yr_mactual = [], [], [], []
            yr_close_p, yr_close_o = [], []
            yr_vclose_p, yr_vclose_o = [], []
            yr_close_mp, yr_close_ma = [], []
            yr_vclose_mp, yr_vclose_ma = [], []
            yr_early_p, yr_early_o = [], []
            yr_late_p, yr_late_o = [], []
            yr_early_mp, yr_early_ma = [], []
            yr_late_mp, yr_late_ma = [], []
            n_skipped = 0

            for g in games:
                htid = g["home_team_id"]
                atid = g["away_team_id"]

                if htid not in ratings or atid not in ratings:
                    n_skipped += 1
                    continue

                rh = ratings[htid]
                ra = ratings[atid]

                site = "neutral" if g["neutral_site"] else "home"

                try:
                    result = forecast_game(
                        adj_o_a=rh["adj_o"], adj_d_a=rh["adj_d"],
                        adj_em_a=rh["adj_em"], tempo_a=rh["adj_tempo"],
                        adj_o_b=ra["adj_o"], adj_d_b=ra["adj_d"],
                        adj_em_b=ra["adj_em"], tempo_b=ra["adj_tempo"],
                        nat_avg_ortg=nat_ortg, hca_points=hca,
                        sigma=sigma, site=site,
                    )
                except Exception as e:
                    if verbose:
                        self.stdout.write(f"    [WARN] game {g['id']}: {e}")
                    n_skipped += 1
                    continue

                prob_home = result["prob_a"]
                pred_margin = result["margin"]
                actual_margin = g["home_score"] - g["away_score"]
                home_won = 1 if actual_margin > 0 else 0

                yr_probs.append(prob_home)
                yr_outcomes.append(home_won)
                yr_mpred.append(pred_margin)
                yr_mactual.append(actual_margin)

                # Close / very close segmentation (by actual margin)
                abs_margin = abs(actual_margin)
                if abs_margin <= 7:
                    yr_close_p.append(prob_home)
                    yr_close_o.append(home_won)
                    yr_close_mp.append(pred_margin)
                    yr_close_ma.append(actual_margin)
                    seg_close["probs"].append(prob_home)
                    seg_close["outcomes"].append(home_won)
                    seg_close["mpred"].append(pred_margin)
                    seg_close["mactual"].append(actual_margin)
                if abs_margin <= 3:
                    yr_vclose_p.append(prob_home)
                    yr_vclose_o.append(home_won)
                    yr_vclose_mp.append(pred_margin)
                    yr_vclose_ma.append(actual_margin)
                    seg_vclose["probs"].append(prob_home)
                    seg_vclose["outcomes"].append(home_won)
                    seg_vclose["mpred"].append(pred_margin)
                    seg_vclose["mactual"].append(actual_margin)

                # Early / late segmentation
                team_game_count[htid] += 1
                team_game_count[atid] += 1
                avg_game_n = (team_game_count[htid] + team_game_count[atid]) / 2
                if avg_game_n <= 10:
                    yr_early_p.append(prob_home)
                    yr_early_o.append(home_won)
                    yr_early_mp.append(pred_margin)
                    yr_early_ma.append(actual_margin)
                    seg_early["probs"].append(prob_home)
                    seg_early["outcomes"].append(home_won)
                    seg_early["mpred"].append(pred_margin)
                    seg_early["mactual"].append(actual_margin)
                if g["game_date"] >= late_cutoff:
                    yr_late_p.append(prob_home)
                    yr_late_o.append(home_won)
                    yr_late_mp.append(pred_margin)
                    yr_late_ma.append(actual_margin)
                    seg_late["probs"].append(prob_home)
                    seg_late["outcomes"].append(home_won)
                    seg_late["mpred"].append(pred_margin)
                    seg_late["mactual"].append(actual_margin)

            if len(yr_probs) < 10:
                if verbose:
                    self.stdout.write(f"  {yr}: <10 evaluable games — skip")
                continue

            all_probs.extend(yr_probs)
            all_outcomes.extend(yr_outcomes)
            all_mpred.extend(yr_mpred)
            all_mactual.extend(yr_mactual)

            m = _metrics(yr_probs, yr_outcomes, yr_mpred, yr_mactual)
            m_close  = _metrics(yr_close_p,  yr_close_o,  yr_close_mp,  yr_close_ma)
            m_vclose = _metrics(yr_vclose_p, yr_vclose_o, yr_vclose_mp, yr_vclose_ma)
            m_early  = _metrics(yr_early_p, yr_early_o, yr_early_mp, yr_early_ma)
            m_late   = _metrics(yr_late_p, yr_late_o, yr_late_mp, yr_late_ma)

            season_results[yr] = {
                "overall": m,
                "close": m_close,
                "vclose": m_vclose,
                "early": m_early,
                "late": m_late,
                "n_skipped": n_skipped,
                "nat_sigma": sigma,
                "nat_hca": hca,
            }

        # ── Per-season summary table ───────────────────────────────────────────
        self.stdout.write(_section("Per-Season Results"))
        hdr = (
            f"  {'Season':>6}  {'Games':>5}  {'SU Acc':>6}  {'Naive':>5}  "
            f"{'Lift':>5}  {'AUC':>5}  {'Brier':>6}  {'SprdMAE':>7}  {'σ':>5}  {'HCA':>4}"
        )
        self.stdout.write(hdr)
        self.stdout.write("  " + "─" * (len(hdr) - 2))

        for yr in seasons:
            if yr not in season_results:
                continue
            sr = season_results[yr]
            m = sr["overall"]
            self.stdout.write(
                f"  {yr:6d}  {m['n']:5d}  {m['accuracy']:6.3f}  {m['naive']:5.3f}  "
                f"{m['lift']:+5.3f}  {m['auc']:5.3f}  {m['brier']:6.4f}  "
                f"{m['spread_mae']:7.2f}  {sr['nat_sigma']:5.2f}  {sr['nat_hca']:4.2f}"
            )

        # ── Pooled evaluation ─────────────────────────────────────────────────
        if len(all_probs) < 10:
            self.stdout.write("  Insufficient pooled data.")
            return

        self.stdout.write(_section("Pooled Evaluation — All Seasons"))

        pool = _metrics(all_probs, all_outcomes, all_mpred, all_mactual)
        pool_close  = _metrics(seg_close["probs"],  seg_close["outcomes"],  seg_close["mpred"],  seg_close["mactual"])
        pool_vclose = _metrics(seg_vclose["probs"], seg_vclose["outcomes"], seg_vclose["mpred"], seg_vclose["mactual"])
        pool_early  = _metrics(seg_early["probs"],  seg_early["outcomes"],  seg_early["mpred"],  seg_early["mactual"])
        pool_late   = _metrics(seg_late["probs"],   seg_late["outcomes"],   seg_late["mpred"],   seg_late["mactual"])

        self.stdout.write(f"\n  {'Segment':<30}  {'N':>5}  {'SU Acc':>6}  {'Brier':>6}  {'SprdMAE':>7}  {'AUC':>5}")
        self.stdout.write("  " + "─" * 68)

        def _row(label, m, kenpom_ref=None):
            if m is None or m["n"] == 0:
                self.stdout.write(f"  {label:<30}  {'—':>5}")
                return
            ref = f"  [KenPom: {kenpom_ref}]" if kenpom_ref else ""
            self.stdout.write(
                f"  {label:<30}  {m['n']:5d}  {m['accuracy']:6.3f}  "
                f"{m['brier']:6.4f}  {m['spread_mae']:7.2f}  {m['auc']:5.3f}{ref}"
            )

        _row("All games (overall)", pool)
        _row("Close games (|margin| ≤ 7)", pool_close, "60.5%")
        _row("Very close (|margin| ≤ 3)", pool_vclose, "52.7%")
        _row("Early season (avg ≤ 10 games)", pool_early)
        _row("Late season (final 14 days)", pool_late, "70.4%")

        # ── Benchmark comparison ───────────────────────────────────────────────
        self.stdout.write(_section("Benchmark Comparison"))
        self.stdout.write(
            f"\n  {'Model':<22}  {'SU Acc':>7}  {'Brier':>7}  {'Notes'}"
        )
        self.stdout.write("  " + "─" * 72)
        benchmarks = [
            ("KenPom",        "~73.0%",   "  —   ", "Academic baseline (NYT 2011)"),
            ("Bart Torvik",   "~73.0%",   "  —   ", "KenPom+recency; NCAA-recognized"),
            ("ESPN BPI",      "~73.0%",   "  —   ", "ML; travel/rest/altitude"),
            ("OddsGods",      " 72.6%",   "0.183 ", "Good single model (2025)"),
            ("Top ensemble",  "~74-75%",  "0.170 ", "Kaggle consensus; EvanMiya-tier"),
            ("EvanMiya",      "~74-75%",  "~0.175", "Injury adj + BPR-driven ratings"),
        ]
        for name, acc, brier, note in benchmarks:
            self.stdout.write(f"  {name:<22}  {acc:>7}  {brier:>7}  {note}")
        self.stdout.write("  " + "─" * 72)
        our_acc = f"{pool['accuracy']*100:5.1f}%"
        our_brier = f"{pool['brier']:.3f} "
        self.stdout.write(f"  {'Macfax AdjEM (in-smpl)':<22}  {our_acc:>7}  {our_brier:>7}  ← our number")
        self.stdout.write("  " + "─" * 72)
        self.stdout.write(f"  {'Floor target':<22}  {'70-73%':>7}  {'—':>7}  KenPom/Torvik tier")
        self.stdout.write(f"  {'Elite target':<22}  {'74-75%':>7}  {'<0.175':>7}  EvanMiya / ensemble tier")

        # ── Spread error distribution ─────────────────────────────────────────
        self.stdout.write(_section("Actual Margin Distribution — SU Accuracy"))
        self.stdout.write("  How SU accuracy varies by actual game closeness:\n")
        self.stdout.write(f"  {'Actual margin':>16}  {'N':>5}  {'SU Acc':>6}  {'% of games':>10}")
        self.stdout.write("  " + "─" * 44)
        buckets = [(0, 3), (3, 7), (7, 12), (12, 20), (20, 999)]
        total_n = len(all_mactual)
        for lo, hi in buckets:
            idx = [i for i, m in enumerate(all_mactual) if lo <= abs(m) < hi]
            if not idx:
                continue
            n_b = len(idx)
            acc_b = sum(
                (1 if all_probs[i] >= 0.5 else 0) == all_outcomes[i]
                for i in idx
            ) / n_b
            label = f"[{lo}–{hi})" if hi < 999 else f"[{lo}+)"
            pct = 100 * n_b / total_n
            self.stdout.write(f"  {label:>16}  {n_b:5d}  {acc_b:6.3f}  {pct:9.1f}%")

        # ── Quality scorecard ─────────────────────────────────────────────────
        self.stdout.write(_section("Quality Scorecard vs Macfax Targets"))
        self.stdout.write(
            "  Floor = KenPom/Torvik tier  |  Elite = EvanMiya tier\n"
            "  Note: in-sample accuracy is ~1-2% above true OOS performance.\n"
        )

        checks = [
            ("SU Accuracy (floor)",  pool["accuracy"], 0.70,  True,  f"{pool['accuracy']:.3f} (floor ≥0.700)"),
            ("SU Accuracy (KenPom)", pool["accuracy"], 0.730, True,  f"{pool['accuracy']:.3f} (KenPom tier ≥0.730)"),
            ("SU Accuracy (elite)",  pool["accuracy"], 0.740, True,  f"{pool['accuracy']:.3f} (EvanMiya tier ≥0.740)"),
            ("AUC",                  pool["auc"],      0.730, True,  f"{pool['auc']:.3f} (target ≥0.730)"),
            ("Brier (good)",         pool["brier"],    0.183, False, f"{pool['brier']:.4f} (good <0.183)"),
            ("Brier (elite)",        pool["brier"],    0.175, False, f"{pool['brier']:.4f} (elite <0.175)"),
        ]
        for name, val, target, hib, display in checks:
            pf = _pass_fail(val, target, hib)
            self.stdout.write(f"  {pf}  {name:<26}  {display}")

        self.stdout.write("\n")
