"""
backtest_bpr_game_prediction — Tests how well BPR predicts NCAA game outcomes.

Methodology:
  1. Build team BPR each season: minutes-weighted sum of player BPR across the roster.
     team_bpr = Σ(player_bpr × mpg/40) — approximates expected efficiency margin
     vs an average D1 team over a full game's possessions.
  2. For each completed game: BPR_diff = home_team_bpr − away_team_bpr.
     Neutral site: BPR_diff used raw (no HCA adjustment, so small HCA bias expected).
  3. Predict home team wins when BPR_diff > 0 (threshold-based) and via logistic
     regression calibration for probability estimates.
  4. Measure: accuracy, AUC (discrimination), Brier score (calibration).

Targets (professional-grade prediction system):
  Accuracy  > 72%   (naive home-wins baseline: ~57%)
  AUC       > 0.72  (random baseline: 0.50)
  Brier     < 0.21  (uncalibrated baseline: ~0.245)

  A system hitting these targets is comparable to published power-rating systems
  (KenPom-style) and can be used professionally for scheduling, projections, etc.

Usage:
    python manage.py backtest_bpr_game_prediction
    python manage.py backtest_bpr_game_prediction --seasons 2024 2025 2026
    python manage.py backtest_bpr_game_prediction --min-bpr-poss 200 --verbose
    python manage.py backtest_bpr_game_prediction --use-adj-em   # compare vs adj_em
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

# ── Quality targets ───────────────────────────────────────────────────────────
TARGET_ACCURACY = 0.72
TARGET_AUC      = 0.72
TARGET_BRIER    = 0.21


# ── Stats helpers ─────────────────────────────────────────────────────────────

def _mean(v): return sum(v) / len(v) if v else 0.0


def _brier(probs: list[float], outcomes: list[int]) -> float:
    """Mean squared error between predicted probability and binary outcome."""
    return sum((p - o) ** 2 for p, o in zip(probs, outcomes)) / len(probs)


def _auc(scores: list[float], labels: list[int]) -> float:
    """
    ROC-AUC via Mann-Whitney U statistic.
    O(n log n) — sufficient for game-count scale.
    """
    pos = [s for s, l in zip(scores, labels) if l == 1]
    neg = [s for s, l in zip(scores, labels) if l == 0]
    if not pos or not neg:
        return float("nan")
    u = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return u / (len(pos) * len(neg))


def _logistic(x: float) -> float:
    """Sigmoid function, numerically stable."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def _ols_logistic_fit(xs: list[float], ys: list[int]) -> tuple[float, float]:
    """
    Simple 1D logistic regression via gradient descent.
    Returns (intercept, slope) for P(y=1 | x) = sigmoid(intercept + slope * x).
    """
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


def _section(t, w=70): return f"\n{'─'*w}\n  {t}\n{'─'*w}"


def _pass_fail(val: float, target: float, higher_is_better: bool = True) -> str:
    ok = val >= target if higher_is_better else val <= target
    return "✓ PASS" if ok else "✗ FAIL"


# ── Command ───────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        "Backtest BPR game prediction accuracy. "
        "Measures how well player BPR aggregated to team level predicts game outcomes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--seasons", nargs="+", type=int, default=None,
            help="Season years to evaluate (default: all with BPR data).",
        )
        parser.add_argument(
            "--min-bpr-poss", type=int, default=150,
            help="Min off_poss for a player to contribute to team BPR (default: 150).",
        )
        parser.add_argument(
            "--min-players", type=int, default=5,
            help="Min players with BPR for a team to get a team BPR estimate (default: 5).",
        )
        parser.add_argument(
            "--use-adj-em", action="store_true", default=False,
            help="Also evaluate using TeamSeasonRatings.adj_em as predictor (comparison baseline).",
        )
        parser.add_argument(
            "--verbose", action="store_true", default=False,
        )

    def handle(self, *args, **options):
        from ncaa.models import PlayerSeasonStats, Season, Game, TeamSeasonRatings

        min_bpr_poss = options["min_bpr_poss"]
        min_players  = options["min_players"]
        use_adj_em   = options["use_adj_em"]
        verbose      = options["verbose"]

        # Determine seasons
        all_seasons = list(
            Season.objects.filter(
                player_season_stats__bpr__isnull=False
            ).values_list("year", flat=True).distinct().order_by("year")
        )
        seasons = options["seasons"] if options["seasons"] else all_seasons
        seasons = [y for y in seasons if y in all_seasons]

        if not seasons:
            self.stdout.write("No seasons with BPR data.")
            return

        self.stdout.write(f"\nSeasons: {seasons}")
        self.stdout.write(
            f"Min player possessions for team BPR: {min_bpr_poss}  |  "
            f"Min players per team: {min_players}"
        )

        # ── Build team BPR maps per season ────────────────────────────────────
        team_bpr_map: dict[int, dict[int, float]] = {}   # season → team_id → team_bpr
        team_adj_em_map: dict[int, dict[int, float]] = {}

        for yr in seasons:
            # Minutes-weighted player BPR → team BPR
            qs = list(
                PlayerSeasonStats.objects.filter(
                    season__year=yr,
                    bpr__isnull=False,
                    off_poss__gte=min_bpr_poss,
                ).values("player_id", "team_id", "bpr", "obpr", "dbpr", "mpg", "gp")
            )

            team_players: dict[int, list] = defaultdict(list)
            for row in qs:
                team_players[row["team_id"]].append(row)

            yr_map: dict[int, float] = {}
            for tid, players in team_players.items():
                if len(players) < min_players:
                    continue
                total_min_share = sum(min(p["mpg"] / 40.0, 1.0) for p in players)
                if total_min_share <= 0:
                    continue
                # Weight by minutes share; normalise so weights sum to ~5 (5 players on court)
                # This gives team BPR in pts/100 poss above D1 avg
                team_bpr = sum(
                    p["bpr"] * min(p["mpg"] / 40.0, 1.0)
                    for p in players
                ) / total_min_share * min(total_min_share, 5.0)
                yr_map[tid] = team_bpr

            team_bpr_map[yr] = yr_map

            if use_adj_em:
                team_adj_em_map[yr] = {
                    r["team_id"]: r["adj_em"]
                    for r in TeamSeasonRatings.objects.filter(
                        season__year=yr, adj_em__isnull=False
                    ).values("team_id", "adj_em")
                }

        # ── Evaluate game predictions ─────────────────────────────────────────
        all_diffs:    list[float] = []
        all_outcomes: list[int]   = []
        season_results: dict[int, dict] = {}

        adj_em_diffs:    list[float] = []
        adj_em_outcomes: list[int]   = []

        for yr in seasons:
            yr_map    = team_bpr_map.get(yr, {})
            adj_em_yr = team_adj_em_map.get(yr, {})

            games = list(
                Game.objects.filter(
                    season_year=yr,
                    status="final",
                    home_score__isnull=False,
                    away_score__isnull=False,
                ).values("id", "home_team_id", "away_team_id",
                         "home_score", "away_score", "neutral_site")
            )

            yr_diffs, yr_outcomes = [], []
            yr_adj_diffs: list[float] = []
            n_skipped = 0

            for g in games:
                htid = g["home_team_id"]
                atid = g["away_team_id"]
                if htid not in yr_map or atid not in yr_map:
                    n_skipped += 1
                    continue

                bpr_diff = yr_map[htid] - yr_map[atid]
                home_won = 1 if g["home_score"] > g["away_score"] else 0

                yr_diffs.append(bpr_diff)
                yr_outcomes.append(home_won)

                if use_adj_em and htid in adj_em_yr and atid in adj_em_yr:
                    yr_adj_diffs.append(adj_em_yr[htid] - adj_em_yr[atid])

            if len(yr_diffs) < 10:
                if verbose:
                    self.stdout.write(f"  {yr}: <10 games with team BPR — skipped")
                continue

            # Fit logistic calibration on this season (in-sample) for probability estimates
            intercept, slope = _ols_logistic_fit(yr_diffs, yr_outcomes)
            probs = [_logistic(intercept + slope * d) for d in yr_diffs]

            threshold_preds = [1 if d > 0 else 0 for d in yr_diffs]
            accuracy  = sum(p == o for p, o in zip(threshold_preds, yr_outcomes)) / len(yr_outcomes)
            auc_score = _auc(yr_diffs, yr_outcomes)
            brier     = _brier(probs, yr_outcomes)
            home_rate = _mean(yr_outcomes)
            naive_acc = max(home_rate, 1 - home_rate)  # always pick more common outcome

            season_results[yr] = {
                "n_games":   len(yr_diffs),
                "n_skipped": n_skipped,
                "accuracy":  accuracy,
                "auc":       auc_score,
                "brier":     brier,
                "home_rate": home_rate,
                "naive_acc": naive_acc,
                "intercept": intercept,
                "slope":     slope,
            }

            all_diffs.extend(yr_diffs)
            all_outcomes.extend(yr_outcomes)

            if use_adj_em and yr_adj_diffs:
                adj_em_diffs.extend(yr_adj_diffs[:len(yr_diffs)])   # parallel
                adj_em_outcomes.extend(yr_outcomes[:len(yr_adj_diffs)])

            if verbose:
                self.stdout.write(
                    f"  {yr}: {len(yr_diffs)} games  "
                    f"acc={accuracy:.3f}  AUC={auc_score:.3f}  "
                    f"Brier={brier:.4f}  naive={naive_acc:.3f}  "
                    f"logit: σ({intercept:+.3f} + {slope:.4f}×diff)"
                )

        # ── Per-season report ─────────────────────────────────────────────────
        self.stdout.write(_section("Per-Season Prediction Accuracy"))
        header = (
            f"  {'Season':>6}  {'Games':>5}  {'Accuracy':>8}  {'Naive':>5}  "
            f"{'Lift':>5}  {'AUC':>5}  {'Brier':>6}  {'HomeRate':>8}"
        )
        self.stdout.write(header)
        self.stdout.write("  " + "─" * (len(header) - 2))

        for yr in seasons:
            if yr not in season_results:
                continue
            r = season_results[yr]
            lift = r["accuracy"] - r["naive_acc"]
            self.stdout.write(
                f"  {yr:6d}  {r['n_games']:5d}  "
                f"{r['accuracy']:8.3f}  {r['naive_acc']:5.3f}  "
                f"{lift:+5.3f}  {r['auc']:5.3f}  {r['brier']:6.4f}  "
                f"{r['home_rate']:8.3f}"
            )

        # ── Pooled evaluation ─────────────────────────────────────────────────
        self.stdout.write(_section("Pooled Evaluation (all seasons)"))

        if len(all_diffs) < 10:
            self.stdout.write("  Insufficient data for pooled evaluation.")
            return

        intercept_all, slope_all = _ols_logistic_fit(all_diffs, all_outcomes)
        probs_all     = [_logistic(intercept_all + slope_all * d) for d in all_diffs]
        acc_all       = sum((1 if d > 0 else 0) == o for d, o in zip(all_diffs, all_outcomes)) / len(all_outcomes)
        auc_all       = _auc(all_diffs, all_outcomes)
        brier_all     = _brier(probs_all, all_outcomes)
        home_rate_all = _mean(all_outcomes)
        naive_all     = max(home_rate_all, 1 - home_rate_all)
        lift_all      = acc_all - naive_all

        self.stdout.write(f"  Games evaluated:  {len(all_diffs)}")
        self.stdout.write(f"  Home win rate:    {home_rate_all:.3f}  (naive baseline: {naive_all:.3f})")
        self.stdout.write(f"  Accuracy:         {acc_all:.3f}  lift vs naive: {lift_all:+.3f}")
        self.stdout.write(f"  AUC:              {auc_all:.3f}")
        self.stdout.write(f"  Brier score:      {brier_all:.4f}")
        self.stdout.write(f"  Logistic fit:     σ({intercept_all:+.3f} + {slope_all:.4f} × BPR_diff)")

        # adj_em comparison
        if use_adj_em and len(adj_em_diffs) >= 10:
            self.stdout.write(f"\n  ── adj_em baseline comparison ──")
            ai, as_ = _ols_logistic_fit(adj_em_diffs, adj_em_outcomes)
            adj_probs = [_logistic(ai + as_ * d) for d in adj_em_diffs]
            self.stdout.write(
                f"  adj_em accuracy:  "
                f"{sum((1 if d>0 else 0)==o for d,o in zip(adj_em_diffs,adj_em_outcomes))/len(adj_em_outcomes):.3f}"
            )
            self.stdout.write(f"  adj_em AUC:       {_auc(adj_em_diffs, adj_em_outcomes):.3f}")
            self.stdout.write(f"  adj_em Brier:     {_brier(adj_probs, adj_em_outcomes):.4f}")

        # ── BPR diff calibration by bucket ───────────────────────────────────
        self.stdout.write(_section("BPR Differential Calibration"))
        self.stdout.write("  How win rate changes as BPR advantage grows:\n")
        buckets = [(-999, -10), (-10, -5), (-5, -2), (-2, 0), (0, 2), (2, 5), (5, 10), (10, 999)]
        hdr = f"  {'BPR diff range':>16}  {'n':>4}  {'Home win%':>9}  {'Avg diff':>8}"
        self.stdout.write(hdr)
        self.stdout.write("  " + "─" * (len(hdr) - 2))
        for lo, hi in buckets:
            idx = [i for i, d in enumerate(all_diffs) if lo <= d < hi]
            if not idx:
                continue
            wr = sum(all_outcomes[i] for i in idx) / len(idx)
            ad = sum(all_diffs[i] for i in idx) / len(idx)
            label = f"[{lo:+.0f}, {hi:+.0f})" if hi != 999 else f"[{lo:+.0f}, +∞)"
            if lo == -999:
                label = f"(−∞, {hi:+.0f})"
            self.stdout.write(f"  {label:>16}  {len(idx):4d}  {wr:9.3f}  {ad:8.2f}")

        # ── Target scorecard ─────────────────────────────────────────────────
        self.stdout.write(_section("Quality Targets — Professional Grade"))
        self.stdout.write(
            "  A system hitting all targets is comparable to published power-rating\n"
            "  systems (KenPom-style) and suitable for professional use.\n"
        )

        checks = [
            ("Accuracy",   acc_all,   TARGET_ACCURACY, True,  f"{acc_all:.3f} (target >{TARGET_ACCURACY})"),
            ("AUC",        auc_all,   TARGET_AUC,      True,  f"{auc_all:.3f} (target >{TARGET_AUC})"),
            ("Brier score",brier_all, TARGET_BRIER,    False, f"{brier_all:.4f} (target <{TARGET_BRIER})"),
        ]
        all_pass = True
        for name, val, target, hib, display in checks:
            pf = _pass_fail(val, target, hib)
            self.stdout.write(f"  {pf}  {name:14s}  {display}")
            if "FAIL" in pf:
                all_pass = False

        self.stdout.write(
            f"\n  {'✓ ALL TARGETS MET' if all_pass else '✗ NOT ALL TARGETS MET — see per-season breakdown'}"
        )

        # ── Team BPR coverage ─────────────────────────────────────────────────
        if verbose:
            self.stdout.write(_section("Team BPR Coverage"))
            for yr in seasons:
                n_teams = len(team_bpr_map.get(yr, {}))
                r = season_results.get(yr, {})
                self.stdout.write(
                    f"  {yr}: {n_teams} teams with BPR  |  "
                    f"{r.get('n_skipped', 0)} games skipped (missing team BPR)"
                )

        self.stdout.write("\n")
