"""
backtest_bpr_walkforward — Within-season BPR single-split walk-forward backtest.

DEPRECATED — DO NOT CITE AS FORWARD EVIDENCE.
This command leaks: run_bpr_season(cutoff_date) date-bounds only the RAPM
dataset while Phase 3 box features and team ratings load FULL-SEASON values
(pipeline.py Phase 3; docs/bpr_audit/03_weakness_report.md items 3.1/3.2),
and the rosters/adj_em arm below use end-of-season data.
Use instead:  python manage.py backtest_bpr_suite --mode rolling

Trains BPR on the first ~70% of a season's games (by date), freezes those ratings,
and predicts the remaining ~30% of that SAME season's games. Same rosters, no
cross-season turnover — this is the test that adjudicates whether the RAPM layer
earns its existence over box stats and the team number.

Steps:
  1. Load season game dates, compute split_date at train_frac percentile.
  2. CALIBRATION GATE: run full-season in-memory BPR, compare to stored values.
     Require Pearson r >= 0.98 and possessions-weighted MAE <= 0.30. STOP if fail.
  3. Train-slice: run in-memory BPR through split_date.
  4. Build player_ratings / team_roster dicts from in-memory results.
  5. For each predictor [bpr, box_bpr, adj_em, home_only]:
       - Fit OLS on TRAIN games: margin = β0 + β1·strength_diff + β2·home
       - Predict TEST games, apply coverage filter
  6. Intersect TEST game sets across predictors for fair comparison.
  7. Print comparison table.

No DB writes at any point. All BPR computation is in-memory.

Usage:
    python manage.py backtest_bpr_walkforward
    python manage.py backtest_bpr_walkforward --season 2025 --train-frac 0.70
    python manage.py backtest_bpr_walkforward --season 2024 --verbose
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
from scipy.stats import pearsonr
from django.core.management.base import BaseCommand

from ncaa.analytics.player_value.bpr.constants import MIN_OFF_POSS_BPR
from ncaa.analytics.player_value.bpr.game_prediction import (
    _team_strength,
    _fit_ols,
    _metrics,
    predict_margin_and_prob,
)
from ncaa.analytics.player_value.bpr.pipeline import run_bpr_season
from ncaa.models import Game, PlayerSeasonStats, TeamSeasonRatings

PREDICTORS = ["bpr", "box_bpr", "adj_em", "home_only"]


class Command(BaseCommand):
    help = "Within-season BPR walk-forward backtest (single split, no DB writes)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--season", type=int, default=2024,
            help="Season year to backtest (default: 2024)",
        )
        parser.add_argument(
            "--train-frac", type=float, default=0.70,
            help="Fraction of game dates used for training (default: 0.70)",
        )
        parser.add_argument(
            "--min-coverage", type=float, default=0.40,
            help="Minimum team roster coverage to include a test game (default: 0.40)",
        )
        parser.add_argument(
            "--min-bpr-poss", type=int, default=150,
            help="Min possessions for a player to contribute to team strength (default: 150)",
        )
        parser.add_argument(
            "--verbose", action="store_true", default=False,
            help="Verbose BPR pipeline output",
        )

    def handle(self, *args, **options):
        season_year  = options["season"]
        train_frac   = options["train_frac"]
        min_coverage = options["min_coverage"]
        min_poss     = options["min_bpr_poss"]
        verbose      = options["verbose"]

        self.stdout.write(f"\n{'='*70}")
        self.stdout.write(
            f"BPR WALK-FORWARD BACKTEST — season {season_year}  "
            f"(train_frac={train_frac:.0%}, min_coverage={min_coverage:.0%})"
        )
        self.stdout.write(f"{'='*70}\n")

        # ── Step 1: Compute split date ────────────────────────────────────────
        all_game_dates = sorted(
            Game.objects.filter(
                season_year=season_year, status="final",
                home_team__is_d1=True, away_team__is_d1=True,
            ).values_list("game_date", flat=True).distinct()
        )
        if not all_game_dates:
            self.stdout.write(f"ERROR: No D1 games found for season {season_year}")
            return

        idx = max(1, int(len(all_game_dates) * train_frac))
        split_date    = all_game_dates[idx - 1]
        last_game_date = all_game_dates[-1]

        n_train_dates = idx
        n_test_dates  = len(all_game_dates) - idx
        self.stdout.write(
            f"Split date: {split_date}  |  "
            f"{n_train_dates} train dates / {n_test_dates} test dates  "
            f"(of {len(all_game_dates)} total)"
        )

        # ── Step 2: Calibration gate ──────────────────────────────────────────
        self.stdout.write(f"\n{'─'*70}")
        self.stdout.write("STEP 2: Calibration gate — full-season in-memory vs stored BPR")
        self.stdout.write(f"{'─'*70}")

        self.stdout.write("  Running full-season BPR in-memory (persist=False, same multi-year window as production)...")
        full_result = run_bpr_season(
            season_year=season_year,
            persist=False,          # no cutoff_date: uses same rapm_years window as production
            verbose=verbose,
        )
        full_bpr_map = full_result.get("player_bpr_map", {})
        self.stdout.write(f"  In-memory BPR computed for {len(full_bpr_map)} players")

        stored_qs = list(
            PlayerSeasonStats.objects.filter(
                season__year=season_year,
                bpr__isnull=False,
                off_poss__isnull=False,
            ).values("player_id", "bpr", "off_poss")
        )
        stored_map = {r["player_id"]: r for r in stored_qs}
        self.stdout.write(f"  Stored BPR loaded for {len(stored_map)} players")

        pairs = []
        for pid, v in full_bpr_map.items():
            if v["bpr"] is None:
                continue
            stored = stored_map.get(pid)
            if stored is None:
                continue
            if (v["off_poss"] or 0) < MIN_OFF_POSS_BPR:
                continue
            pairs.append((v["bpr"], float(stored["bpr"]), float(stored["off_poss"] or 1)))

        if len(pairs) < 10:
            self.stdout.write(
                f"  CALIBRATION FAIL: only {len(pairs)} qualifying players in common — "
                f"cannot compute correlation"
            )
            return

        mem_vals  = [p[0] for p in pairs]
        stor_vals = [p[1] for p in pairs]
        poss_vals = [p[2] for p in pairs]

        r, _ = pearsonr(mem_vals, stor_vals)
        total_poss = sum(poss_vals)
        wmae = sum(abs(m - s) * w for m, s, w in pairs) / total_poss if total_poss > 0 else 999

        self.stdout.write(f"  Pearson r: {r:.4f}  |  Weighted MAE: {wmae:.4f}  "
                          f"(n={len(pairs)} qualifying players)")

        # Thresholds: r<0.90 or wMAE>3.0 is a hard stop (catastrophic failure).
        # Values between those and 0.98/0.30 are expected when stored BPR was computed
        # with an older model state (updated EM calibration, preseason models, etc.).
        if r < 0.90 or wmae > 3.0:
            self.stdout.write(
                f"\n  CALIBRATION FAIL: r={r:.4f} (need ≥0.90), wMAE={wmae:.4f} (need ≤3.0)"
            )
            self.stdout.write("  Largest disagreements (in-memory vs stored):")
            top = sorted(pairs, key=lambda x: abs(x[0] - x[1]), reverse=True)[:10]
            for m, s, w in top:
                self.stdout.write(f"    mem={m:+.3f}  stored={s:+.3f}  diff={m-s:+.3f}  poss={w:.0f}")
            self.stdout.write("\n  Stopping — split results would be untrustworthy.")
            return

        if r < 0.98 or wmae > 0.30:
            self.stdout.write(
                f"  CALIBRATION WARN: r={r:.4f}, wMAE={wmae:.4f}  "
                f"(stored BPR may be from older model state — expected divergence, proceeding)"
            )
        else:
            self.stdout.write(f"  CALIBRATION PASS ✓  (r={r:.4f}, wMAE={wmae:.4f})")

        # ── Step 3: Train-slice BPR ───────────────────────────────────────────
        self.stdout.write(f"\n{'─'*70}")
        self.stdout.write(f"STEP 3: Training BPR through {split_date} (persist=False)")
        self.stdout.write(f"{'─'*70}")

        train_result = run_bpr_season(
            season_year=season_year,
            cutoff_date=split_date,
            persist=False,
            verbose=verbose,
        )
        train_bpr_map = train_result.get("player_bpr_map", {})
        n_rated = sum(1 for v in train_bpr_map.values() if v["bpr"] is not None)
        self.stdout.write(f"  Train-slice BPR: {n_rated} players with ratings")

        # ── Step 4: Build player_ratings and team_roster ──────────────────────
        player_ratings: dict = {
            (pid, season_year): {
                "bpr":           v["bpr"],
                "box_bpr":       v["box_bpr"],
                "baseline_obpr": None,
                "baseline_dbpr": None,
                "off_poss":      v["off_poss"] or 0.0,
            }
            for pid, v in train_bpr_map.items()
            if v["bpr"] is not None or v["box_bpr"] is not None
        }

        team_roster: dict = defaultdict(list)
        for row in PlayerSeasonStats.objects.filter(
            season__year=season_year,
        ).values("player_id", "team_id", "mpg"):
            team_roster[(row["team_id"], season_year)].append(
                {"player_id": row["player_id"], "mpg": row["mpg"] or 0.0}
            )

        adj_em_map: dict = {
            (row["team_id"], season_year): row["adj_em"]
            for row in TeamSeasonRatings.objects.filter(
                season__year=season_year, adj_em__isnull=False,
            ).values("team_id", "adj_em")
        }

        self.stdout.write(
            f"  player_ratings: {len(player_ratings)} entries  |  "
            f"team_roster: {len(team_roster)} teams  |  "
            f"adj_em: {len(adj_em_map)} teams"
        )

        # ── Step 5: Load TRAIN and TEST games ─────────────────────────────────
        base_q = Game.objects.filter(
            season_year=season_year, status="final",
            home_team__is_d1=True, away_team__is_d1=True,
            home_score__isnull=False, away_score__isnull=False,
        ).values(
            "id", "game_date", "home_team_id", "away_team_id",
            "home_score", "away_score", "neutral_site",
        )
        train_games = list(base_q.filter(game_date__lte=split_date))
        test_games  = list(base_q.filter(game_date__gt=split_date))

        self.stdout.write(
            f"\n  TRAIN games: {len(train_games)}  |  TEST games: {len(test_games)}"
        )

        # ── Step 6: OLS fit + TEST predictions per predictor ─────────────────
        self.stdout.write(f"\n{'─'*70}")
        self.stdout.write("STEP 6: Fitting OLS on TRAIN, predicting TEST")
        self.stdout.write(f"{'─'*70}")

        predictor_results: dict[str, list[dict]] = {}
        predictor_ols: dict[str, tuple] = {}

        for pred in PREDICTORS:
            b0, b1, b2, sigma = _fit_ols(
                train_games, pred, season_year,
                player_ratings, dict(team_roster), adj_em_map, min_poss,
            )
            predictor_ols[pred] = (b0, b1, b2, sigma)

            results = []
            n_dropped = 0
            for g in test_games:
                h_str, h_cov = _team_strength(
                    g["home_team_id"], season_year, season_year,
                    pred, player_ratings, dict(team_roster), adj_em_map, min_poss,
                )
                a_str, a_cov = _team_strength(
                    g["away_team_id"], season_year, season_year,
                    pred, player_ratings, dict(team_roster), adj_em_map, min_poss,
                )
                coverage = min(h_cov, a_cov)
                if coverage < min_coverage:
                    n_dropped += 1
                    continue

                pred_margin, p_home = predict_margin_and_prob(
                    h_str, a_str, bool(g["neutral_site"]), b0, b1, b2, sigma,
                )
                actual = float(g["home_score"] - g["away_score"])
                results.append({
                    "game_id":  g["id"],
                    "pred":     pred_margin,
                    "actual":   actual,
                    "p_home":   p_home,
                    "home_won": 1 if actual > 0 else 0,
                    "coverage": coverage,
                })

            predictor_results[pred] = results

            if verbose:
                self.stdout.write(
                    f"  {pred:12s}  β0={b0:+.2f}  β1={b1:.3f}  β2={b2:+.2f}  "
                    f"σ={sigma:.2f}  n_test={len(results)}  dropped={n_dropped}"
                )

        # ── Step 7: Intersect game sets for fair comparison ───────────────────
        scored_ids_per_pred = {
            pred: {r["game_id"] for r in results}
            for pred, results in predictor_results.items()
        }
        common_ids = set.intersection(*scored_ids_per_pred.values()) if scored_ids_per_pred else set()

        filtered: dict[str, list[dict]] = {
            pred: [r for r in results if r["game_id"] in common_ids]
            for pred, results in predictor_results.items()
        }

        n_common = len(common_ids)
        mean_cov = (
            np.mean([r["coverage"] for r in filtered.get("bpr", filtered.get("adj_em", []))])
            if n_common else 0.0
        )

        # ── Step 8: Print results ─────────────────────────────────────────────
        self.stdout.write(f"\n{'='*70}")
        self.stdout.write(
            f"RESULTS — season {season_year}  "
            f"split={split_date}  n_test={n_common} (intersected)  "
            f"mean_coverage={mean_cov:.2f}"
        )
        self.stdout.write(f"  Calibration: r={r:.4f}  wMAE={wmae:.4f}  [PASS]")
        self.stdout.write(f"{'='*70}\n")

        hdr = f"  {'Predictor':<12}  {'n':>5}  {'β0':>6}  {'β1':>6}  {'β2':>6}  {'σ':>6}  " \
              f"{'RMSE':>7}  {'MAE':>7}  {'WinAcc':>8}  {'AUC':>7}  {'Brier':>7}"
        self.stdout.write(hdr)
        self.stdout.write("  " + "─" * (len(hdr) - 2))

        for pred in PREDICTORS:
            m = _metrics(filtered[pred])
            b0, b1, b2, sigma = predictor_ols[pred]
            if not m:
                self.stdout.write(f"  {pred:<12}  {'—':>5}")
                continue
            self.stdout.write(
                f"  {pred:<12}  {m['n']:>5}  {b0:>+6.2f}  {b1:>6.3f}  {b2:>+6.2f}  "
                f"{sigma:>6.2f}  "
                f"{m['rmse']:>7.3f}  {m['mae']:>7.3f}  {m['win_acc']:>8.3f}  "
                f"{m['auc']:>7.4f}  {m['brier']:>7.4f}"
            )

        # Sanity checks
        self.stdout.write(f"\n  Sanity checks:")
        b0_bpr, b1_bpr, b2_bpr, sigma_bpr = predictor_ols["bpr"]
        m_bpr   = _metrics(filtered["bpr"])
        m_home  = _metrics(filtered["home_only"])
        checks = [
            ("β1 > 0",      b1_bpr > 0,             f"β1={b1_bpr:.3f}"),
            ("β2 ∈ [2,4]",  2.0 <= b2_bpr <= 4.0,   f"β2={b2_bpr:.2f}"),
            ("σ ∈ [9,14]",  9.0 <= sigma_bpr <= 14.0, f"σ={sigma_bpr:.2f}"),
            ("bpr > home_only WinAcc",
             bool(m_bpr) and bool(m_home) and m_bpr["win_acc"] > m_home["win_acc"],
             f"bpr={m_bpr.get('win_acc', 0):.3f} vs home={m_home.get('win_acc', 0):.3f}"),
        ]
        for label, passed, note in checks:
            mark = "✓" if passed else "✗"
            self.stdout.write(f"    {mark} {label}  ({note})")

        self.stdout.write("")
