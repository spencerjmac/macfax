"""
backtest_em_bakeoff — Macfax BPR vs EvanMiya BPR fair predictive bake-off.

Both are full-season year-Y ratings predicting year-(Y+1) games (cross-season frame).
Neither metric has seen the test games. EM cannot be sliced to partial-season, so
cross-season is the only leakage-free frame.

FAIRNESS KEYSTONE: both predictors are built from the IDENTICAL matched player
universe — only players who appear in BOTH systems. One dict has Macfax BPR values,
the other has EM adj_bpr values, but the same player_ids, the same mpg weights,
the same coverage denominator. The only thing that varies is the rating number.

Read-only. No DB writes. Reuses validated margin core from backtest_bpr_margin.py.

Usage:
    python manage.py backtest_em_bakeoff
    python manage.py backtest_em_bakeoff --verbose
    python manage.py backtest_em_bakeoff --seasons 2022 2023 2024 --verbose
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
from django.core.management.base import BaseCommand

from ncaa.analytics.player_value.bpr.evan_miya_reference import (
    load_em_ratings,
    normalize_team_name,
)
from ncaa.analytics.player_value.bpr.game_prediction import (
    _team_strength,
    _fit_ols,
    _metrics,
    predict_margin_and_prob,
)
from ncaa.management.commands.backtest_bpr_margin import (
    _load_player_data,
    _load_adj_em,
    _load_games,
    _build_folds,
)
from ncaa.management.commands.backtest_bpr_vs_evan_miya import (
    _normalize,
    _name_match_score,
)
from ncaa.models import PlayerSeasonStats

# Ordered for output table
PRED_ORDER = ["macfax_bpr", "em_bpr", "macfax_box", "adj_em", "home_only"]
PRED_LABELS = {
    "macfax_bpr": "bpr (Macfax)",
    "em_bpr":     "em (EvanMiya)",
    "macfax_box": "box_bpr (Macfax)",
    "adj_em":     "adj_em",
    "home_only":  "home_only",
}
# Which "predictor" string _team_strength / _fit_ols expects
PRED_FIELD = {
    "macfax_bpr": "bpr",
    "em_bpr":     "bpr",     # em_pr["bpr"] = em_adj_bpr
    "macfax_box": "box_bpr",
    "adj_em":     "adj_em",
    "home_only":  "home_only",
}


def _match_em_to_macfax(em_records, macfax_rows):
    """
    Fuzzy-match EM players to Macfax PlayerSeasonStats rows.
    Reuses backtest_bpr_vs_evan_miya matching logic verbatim:
      score = name_match * 0.7 + team_match * 0.3, threshold 0.55.

    Returns (matched, unmatched_em) where matched is a list of dicts with:
      player_id, macfax_bpr, macfax_box_bpr, off_poss, em_adj_bpr
    """
    db_by_name = defaultdict(list)
    for row in macfax_rows:
        db_by_name[row["player__display_name"]].append(row)

    matched = []
    unmatched_em = []

    for em in em_records:
        em_team_norm = normalize_team_name(em["team"])
        best_row, best_score = None, 0.0

        for db_name, rows in db_by_name.items():
            score = _name_match_score(em["name"], db_name)
            if score < 0.5:
                continue
            for row in rows:
                team_score = _name_match_score(em_team_norm, row["team__name"] or "")
                combined = score * 0.7 + team_score * 0.3
                if combined > best_score:
                    best_score = combined
                    best_row = row

        if best_score < 0.55 or best_row is None:
            unmatched_em.append(em)
            continue

        matched.append({
            "player_id":      best_row["player_id"],
            "macfax_bpr":     best_row["bpr"],
            "macfax_box_bpr": best_row["box_bpr"],
            "off_poss":       best_row["off_poss"],
            "em_adj_bpr":     em["adj_bpr"],
        })

    return matched, unmatched_em


class Command(BaseCommand):
    help = "Fair predictive bake-off: Macfax BPR vs EvanMiya BPR (cross-season, matched universe)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--min-coverage", type=float, default=0.40,
            help="Minimum matched-universe roster coverage (default: 0.40)",
        )
        parser.add_argument(
            "--min-bpr-poss", type=int, default=150,
            help="Macfax possession floor for a rated player (default: 150)",
        )
        parser.add_argument(
            "--em-min-poss", type=int, default=400,
            help="EvanMiya possession floor for a rated player (default: 400)",
        )
        parser.add_argument(
            "--seasons", type=int, nargs="+", default=None,
            help="Restrict to specific training years",
        )
        parser.add_argument(
            "--verbose", action="store_true", default=False,
        )

    def handle(self, *args, **options):
        min_cov     = options["min_coverage"]
        min_poss    = options["min_bpr_poss"]
        em_min_poss = options["em_min_poss"]
        seasons     = options["seasons"]
        verbose     = options["verbose"]

        # ── Load global data ──────────────────────────────────────────────────
        self.stdout.write("\nLoading global data...")
        player_ratings, team_roster = _load_player_data()
        adj_em_map    = _load_adj_em()
        games_by_year = _load_games()
        self.stdout.write(
            f"  {len(player_ratings):,} player-season ratings  |  "
            f"{len(adj_em_map):,} team adj_em entries  |  "
            f"{sum(len(v) for v in games_by_year.values()):,} completed games"
        )

        # Folds driven by Macfax BPR availability
        folds = _build_folds("bpr", player_ratings, adj_em_map, games_by_year, seasons)
        if not folds:
            self.stdout.write("ERROR: No valid BPR folds.")
            return
        self.stdout.write(f"  {len(folds)} folds: {[(tr, te) for tr, te in folds]}")

        # ── Per-fold accumulators ─────────────────────────────────────────────
        all_results: dict[str, list] = {p: [] for p in PRED_ORDER}
        fold_summaries = []

        for train_year, test_year in folds:
            self.stdout.write(f"\n{'─'*60} {train_year}→{test_year}")

            # Load EM ratings for train year
            try:
                em_records = load_em_ratings(train_year)
            except KeyError:
                self.stdout.write(f"  SKIP: No EM data for {train_year}")
                continue
            em_records = [r for r in em_records if (r["possessions"] or 0) >= em_min_poss]

            # Load Macfax PSS with names for matching
            macfax_rows = list(
                PlayerSeasonStats.objects.filter(
                    season__year=train_year,
                    bpr__isnull=False,
                    off_poss__isnull=False,
                    off_poss__gte=min_poss,
                ).values(
                    "player_id", "player__display_name", "team__name",
                    "bpr", "box_bpr", "off_poss",
                )
            )

            # Match EM → Macfax
            matched, unmatched_em = _match_em_to_macfax(em_records, macfax_rows)

            n_em  = len(em_records)
            n_mat = len(matched)
            rate  = n_mat / n_em if n_em else 0.0
            self.stdout.write(
                f"  EM players (≥{em_min_poss} poss): {n_em}  |  "
                f"Matched: {n_mat}  |  Rate: {rate:.1%}  |  "
                f"Unmatched: {len(unmatched_em)}"
            )

            if rate < 0.50:
                self.stdout.write(
                    f"  WARNING: Match rate {rate:.1%} < 50% — name-matcher may be failing. "
                    f"Results from this fold are untrustworthy."
                )

            if verbose and unmatched_em:
                self.stdout.write(f"  Unmatched EM sample (first 5):")
                for em in unmatched_em[:5]:
                    self.stdout.write(f"    {em['name']!r:30s}  team={em['team']!r}")

            if not matched:
                self.stdout.write("  SKIP: No matched players.")
                continue

            # Build per-predictor rating dicts (matched universe only)
            macfax_pr: dict = {
                (m["player_id"], train_year): {
                    "bpr":           m["macfax_bpr"],
                    "box_bpr":       m["macfax_box_bpr"],
                    "off_poss":      m["off_poss"],
                    "baseline_obpr": None,
                    "baseline_dbpr": None,
                }
                for m in matched
            }
            em_pr: dict = {
                (m["player_id"], train_year): {
                    "bpr":           m["em_adj_bpr"],
                    "box_bpr":       None,
                    "off_poss":      m["off_poss"],  # Macfax poss for consistent coverage
                    "baseline_obpr": None,
                    "baseline_dbpr": None,
                }
                for m in matched
            }

            # Which player_ratings dict each predictor uses
            pr_map = {
                "macfax_bpr": macfax_pr,
                "em_bpr":     em_pr,
                "macfax_box": macfax_pr,
                "adj_em":     player_ratings,
                "home_only":  player_ratings,
            }

            train_games = games_by_year.get(train_year, [])
            test_games  = games_by_year.get(test_year, [])

            # Fit OLS per predictor on full train games
            # min_poss=0 because matched-universe filter already applied at match time
            models: dict[str, tuple] = {}
            for pred_key in PRED_ORDER:
                models[pred_key] = _fit_ols(
                    train_games, PRED_FIELD[pred_key], train_year,
                    pr_map[pred_key], team_roster, adj_em_map, min_poss=0,
                )

            if verbose:
                for pred_key in PRED_ORDER:
                    b0, b1, b2, sig = models[pred_key]
                    self.stdout.write(
                        f"  {PRED_LABELS[pred_key]:20s}  "
                        f"β0={b0:+.2f}  β1={b1:+.4f}  β2={b2:+.2f}  σ={sig:.2f}"
                    )

            # Predict all test games per predictor (coverage filter deferred)
            fold_by_game: dict[str, dict] = {}
            for pred_key in PRED_ORDER:
                b0, b1, b2, sig = models[pred_key]
                raw: dict = {}
                for g in test_games:
                    h_str, h_cov = _team_strength(
                        g["home_team_id"], train_year, test_year,
                        PRED_FIELD[pred_key], pr_map[pred_key], team_roster, adj_em_map, 0,
                    )
                    a_str, a_cov = _team_strength(
                        g["away_team_id"], train_year, test_year,
                        PRED_FIELD[pred_key], pr_map[pred_key], team_roster, adj_em_map, 0,
                    )
                    game_cov = min(h_cov, a_cov)
                    pred_m, p_home = predict_margin_and_prob(
                        h_str, a_str, bool(g["neutral_site"]), b0, b1, b2, sig,
                    )
                    actual = float(g["home_score"] - g["away_score"])
                    raw[g["id"]] = {
                        "pred": pred_m, "actual": actual, "p_home": p_home,
                        "home_won": 1 if actual > 0 else 0, "coverage": game_cov,
                    }
                fold_by_game[pred_key] = raw

            # Intersect: game passes if BOTH macfax_bpr AND em_bpr coverage ≥ min_cov
            macfax_pass = {gid for gid, r in fold_by_game["macfax_bpr"].items()
                           if r["coverage"] >= min_cov}
            em_pass     = {gid for gid, r in fold_by_game["em_bpr"].items()
                           if r["coverage"] >= min_cov}
            valid_gids  = macfax_pass & em_pass

            for pred_key in PRED_ORDER:
                gmap = fold_by_game[pred_key]
                for gid in valid_gids:
                    if gid in gmap:
                        all_results[pred_key].append(gmap[gid])

            fold_summaries.append({
                "train": train_year, "test": test_year,
                "n_em": n_em, "n_matched": n_mat, "rate": rate,
                "n_valid": len(valid_gids),
                "b0_m": models["macfax_bpr"][0], "b1_m": models["macfax_bpr"][1],
                "b2_m": models["macfax_bpr"][2], "sig_m": models["macfax_bpr"][3],
                "b1_em": models["em_bpr"][1], "sig_em": models["em_bpr"][3],
            })
            self.stdout.write(
                f"  Test games passing coverage filter: {len(valid_gids):,}"
            )

        if not fold_summaries:
            self.stdout.write("\nNo valid folds completed.")
            return

        # ── Pooled results ────────────────────────────────────────────────────
        W = 84
        self.stdout.write(f"\n{'='*W}")
        self.stdout.write(
            f"BAKE-OFF RESULTS — {len(fold_summaries)} folds  "
            f"(min_coverage={min_cov:.0%}, matched universe only)"
        )
        self.stdout.write(f"{'='*W}\n")

        hdr = (
            f"  {'Predictor':<22}  {'n':>7}  {'RMSE':>8}  {'MAE':>8}  "
            f"{'WinAcc':>7}  {'AUC':>7}  {'Brier':>8}"
        )
        self.stdout.write(hdr)
        self.stdout.write("  " + "─" * (len(hdr) - 2))

        pooled_metrics: dict[str, dict] = {}
        for pred_key in PRED_ORDER:
            m = _metrics(all_results[pred_key])
            pooled_metrics[pred_key] = m
            if not m:
                self.stdout.write(f"  {PRED_LABELS[pred_key]:<22}  no data")
                continue
            self.stdout.write(
                f"  {PRED_LABELS[pred_key]:<22}  {m['n']:>7,}  "
                f"{m['rmse']:>8.3f}  {m['mae']:>8.3f}  "
                f"{m['win_acc']:>7.3f}  {m['auc']:>7.4f}  {m['brier']:>8.4f}"
            )

        self.stdout.write("  " + "─" * (len(hdr) - 2))

        # ── Headline verdict ──────────────────────────────────────────────────
        m_mac = pooled_metrics.get("macfax_bpr", {})
        m_em  = pooled_metrics.get("em_bpr", {})
        self.stdout.write("")

        if m_mac and m_em:
            delta_rmse = m_mac["rmse"] - m_em["rmse"]
            delta_wa   = m_mac["win_acc"] - m_em["win_acc"]
            delta_auc  = m_mac["auc"] - m_em["auc"]

            if delta_rmse < -0.05:
                verdict = "MACFAX WINS — Macfax BPR predicts better"
            elif abs(delta_rmse) <= 0.05:
                verdict = "STATISTICAL TIE (|Δ| ≤ 0.05)"
            else:
                verdict = "EVANMIYA WINS — EM BPR predicts better"

            self.stdout.write(f"  HEADLINE:  Δ(bpr − em) RMSE = {delta_rmse:+.3f}")
            self.stdout.write(f"  VERDICT:   {verdict}")
            self.stdout.write(f"  WinAcc Δ:  {delta_wa:+.3f}  "
                              f"({'agrees' if (delta_wa < 0) == (delta_rmse < 0) or abs(delta_wa) < 0.002 else 'DISAGREES'} with RMSE verdict)")
            self.stdout.write(f"  AUC Δ:     {delta_auc:+.4f}  "
                              f"({'agrees' if (delta_auc > 0) == (delta_rmse < 0) or abs(delta_auc) < 0.001 else 'DISAGREES'} with RMSE verdict)")

        # ── Sanity gates ──────────────────────────────────────────────────────
        self.stdout.write(f"\n{'─'*W}")
        self.stdout.write("SANITY GATES")
        self.stdout.write(f"{'─'*W}")

        issues = []
        if fold_summaries:
            avg_b1_mac  = sum(f["b1_m"] for f in fold_summaries) / len(fold_summaries)
            avg_b2_mac  = sum(f["b2_m"] for f in fold_summaries) / len(fold_summaries)
            avg_sig_mac = sum(f["sig_m"] for f in fold_summaries) / len(fold_summaries)
            avg_b1_em   = sum(f["b1_em"] for f in fold_summaries) / len(fold_summaries)
            avg_rate    = sum(f["rate"] for f in fold_summaries) / len(fold_summaries)

            self.stdout.write(
                f"  Macfax BPR avg:   β1={avg_b1_mac:+.4f}  β2={avg_b2_mac:+.2f}  σ={avg_sig_mac:.2f}"
            )
            self.stdout.write(f"  EM BPR avg:       β1={avg_b1_em:+.4f}")
            self.stdout.write(f"  Avg match rate:   {avg_rate:.1%}")

            if avg_b1_mac <= 0:
                issues.append(f"Macfax β1={avg_b1_mac:+.4f} ≤ 0 — no signal")
            if avg_b1_em <= 0:
                issues.append(f"EM β1={avg_b1_em:+.4f} ≤ 0 — no signal")
            if not (2.0 <= avg_b2_mac <= 4.0):
                issues.append(f"Macfax β2={avg_b2_mac:+.2f} outside [2,4]")
            if avg_rate < 0.50:
                issues.append(f"Match rate {avg_rate:.1%} < 50% — matching suspect")

        m_mac = pooled_metrics.get("macfax_bpr", {})
        m_em  = pooled_metrics.get("em_bpr", {})
        m_ho  = pooled_metrics.get("home_only", {})
        m_adj = pooled_metrics.get("adj_em", {})

        if m_mac and m_ho and m_mac.get("rmse", 999) >= m_ho.get("rmse", 0):
            issues.append(f"Macfax RMSE ({m_mac['rmse']:.3f}) ≥ home_only ({m_ho['rmse']:.3f}) — no signal")
        if m_em and m_ho and m_em.get("rmse", 999) >= m_ho.get("rmse", 0):
            issues.append(f"EM RMSE ({m_em['rmse']:.3f}) ≥ home_only ({m_ho['rmse']:.3f}) — no signal")

        if m_adj and m_mac and m_adj.get("rmse", 0) > m_mac.get("rmse", 999):
            self.stdout.write(
                f"  NOTE: adj_em RMSE ({m_adj['rmse']:.3f}) > Macfax BPR ({m_mac['rmse']:.3f}) — "
                f"player metric beats team metric (surprising but not a bug; flag for investigation)"
            )

        if issues:
            for issue in issues:
                self.stdout.write(f"  ⚠  {issue}")
        else:
            self.stdout.write("  ✓  All sanity gates pass")

        # ── Per-fold summary ──────────────────────────────────────────────────
        if verbose:
            self.stdout.write(f"\n{'─'*W}")
            self.stdout.write("PER-FOLD MATCH SUMMARY")
            self.stdout.write(
                f"  {'Fold':<10}  {'n_EM':>6}  {'n_matched':>9}  "
                f"{'rate':>6}  {'n_test':>7}"
            )
            self.stdout.write("  " + "─" * 45)
            for f in fold_summaries:
                self.stdout.write(
                    f"  {f['train']}→{f['test']}  {f['n_em']:>6}  {f['n_matched']:>9}  "
                    f"{f['rate']:>5.1%}  {f['n_valid']:>7,}"
                )

        self.stdout.write("")
