"""
Backtest: evaluate importance-weighting configurations against out-of-sample accuracy.

Runs in three modes, intended to be used sequentially:

  Stage 1 (default)  — ON vs OFF baseline
  Stage 2            — sweep IMP_C (--imp-c-vals)
  Stage 3            — cross-product sweep of CLOSE_M × BOOST_MAX (--close-m-vals + --boost-max-vals)

All other parameters held fixed: k=150, λ=0.004, hca from DB.

Primary metric   : spread MAE / RMSE
Secondary metric : win-prob log-loss / Brier
Diagnostic       : mean w_imp, median w_imp, floor-hit rate (per combo)
                   so you can sanity-check that tuning doesn't over-compress weights

Usage:
    # Stage 1: ON vs OFF
    python manage.py backtest_importance --season 2026

    # Stage 2: sweep IMP_C (OFF baseline always included)
    python manage.py backtest_importance --season 2026 --imp-c-vals 30 40 50 60

    # Stage 3: cross-product CLOSE_M × BOOST_MAX (fix best IMP_C first)
    python manage.py backtest_importance --season 2026 --imp-c 50 \\
        --close-m-vals 8 12 16 --boost-max-vals 1.10 1.25 1.40
"""

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from scipy import stats as scipy_stats

from django.core.management.base import BaseCommand

from backtesting.rating_replay import (
    BOOST_MAX,
    CLOSE_M,
    IMP_C,
    IMP_FLOOR,
    RECENCY_LAMBDA,
    ImportanceParams,
    predict_margin,
    run_ratings_with_importance_weights,
    time_weights,
)
from ncaa.models import Game, NationalAverages, Team, TeamGameStats

# Default importance constants (production values)
DEFAULT_IMP_C     = IMP_C
DEFAULT_IMP_FLOOR = IMP_FLOOR
DEFAULT_CLOSE_M   = CLOSE_M
DEFAULT_BOOST_MAX = BOOST_MAX

PHASES = {
    "Nov–Dec": (11, 12),
    "Jan":     (1,  1),
    "Feb–Mar": (2,  3),
}


def _phase(d: date) -> str:
    for name, (lo, hi) in PHASES.items():
        if lo <= d.month <= hi:
            return name
    return "other"


# ── Combo descriptor ───────────────────────────────────────────────────────

@dataclass
class Combo:
    label:       str
    imp_enabled: bool
    imp_c:       float = DEFAULT_IMP_C
    imp_floor:   float = DEFAULT_IMP_FLOOR
    close_m:     float = DEFAULT_CLOSE_M
    boost_max:   float = DEFAULT_BOOST_MAX

    def importance_params(self) -> ImportanceParams:
        return ImportanceParams(
            enabled=self.imp_enabled, c=self.imp_c, floor=self.imp_floor,
            close_m=self.close_m, boost_max=self.boost_max,
        )


# ── management command ─────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "Backtest importance-weighting configurations (Stage 1/2/3)"

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument(
            "--imp-c-vals",
            type=float, nargs="+", default=None,
            help="Stage 2: IMP_C values to sweep (e.g. 30 40 50 60). "
                 "OFF baseline always added.",
        )
        parser.add_argument(
            "--close-m-vals",
            type=float, nargs="+", default=None,
            help="Stage 3: CLOSE_M values (cross-product with --boost-max-vals).",
        )
        parser.add_argument(
            "--boost-max-vals",
            type=float, nargs="+", default=None,
            help="Stage 3: BOOST_MAX values (cross-product with --close-m-vals).",
        )
        # Fixed-point overrides for Stage 3 (lock other params)
        parser.add_argument("--imp-c",    type=float, default=DEFAULT_IMP_C,
                            help=f"Fixed IMP_C for Stage 3 (default: {DEFAULT_IMP_C})")
        parser.add_argument("--imp-floor", type=float, default=DEFAULT_IMP_FLOOR,
                            help=f"Fixed IMP_FLOOR (default: {DEFAULT_IMP_FLOOR})")
        parser.add_argument(
            "--k",     type=float, default=150.0, help="Shrinkage k (default: 150)")
        parser.add_argument(
            "--start", type=str,   default=None)
        parser.add_argument(
            "--end",   type=str,   default=None)
        parser.add_argument(
            "--step",  type=int,   default=7)
        parser.add_argument(
            "--window", type=int,  default=7)

    # ── Build combo list ──────────────────────────────────────────────────

    def _build_combos(self, options) -> list:
        imp_c_vals    = options["imp_c_vals"]
        close_m_vals  = options["close_m_vals"]
        boost_max_vals = options["boost_max_vals"]
        fixed_imp_c   = options["imp_c"]
        fixed_floor   = options["imp_floor"]

        off_baseline = Combo("OFF", imp_enabled=False)

        if imp_c_vals:
            # Stage 2: sweep IMP_C
            combos = [off_baseline]
            for c in imp_c_vals:
                combos.append(Combo(
                    f"C={c:.0f}", True,
                    imp_c=c, imp_floor=fixed_floor,
                    close_m=DEFAULT_CLOSE_M, boost_max=DEFAULT_BOOST_MAX,
                ))
            return combos

        if close_m_vals or boost_max_vals:
            # Stage 3: cross-product CLOSE_M × BOOST_MAX
            cms  = close_m_vals  or [DEFAULT_CLOSE_M]
            bms  = boost_max_vals or [DEFAULT_BOOST_MAX]
            combos = [
                off_baseline,
                Combo("ON(def)", True,
                      imp_c=fixed_imp_c, imp_floor=fixed_floor,
                      close_m=DEFAULT_CLOSE_M, boost_max=DEFAULT_BOOST_MAX),
            ]
            for cm in cms:
                for bm in bms:
                    label = f"M={cm:.0f}/B={bm:.2f}"
                    combos.append(Combo(
                        label, True,
                        imp_c=fixed_imp_c, imp_floor=fixed_floor,
                        close_m=cm, boost_max=bm,
                    ))
            return combos

        # Stage 1 (default): ON vs OFF
        return [
            off_baseline,
            Combo("ON(def)", True),
        ]

    # ── Main ─────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        season_year = options["season"]
        k           = options["k"]
        step        = options["step"]
        window      = options["window"]

        combos = self._build_combos(options)

        nat_avg = NationalAverages.objects.get(season__year=season_year)
        sigma   = nat_avg.prediction_sigma or 11.08
        EPS     = 1e-9

        # ── Load all data once ───────────────────────────────────────────── #
        self.stdout.write(
            f"Loading data...  (k={k:.0f}, λ={RECENCY_LAMBDA}, "
            f"σ={sigma:.3f}, hca={nat_avg.hca_points or 3.20:.4f})"
        )

        all_stats = list(
            TeamGameStats.objects.filter(
                game__season_year=season_year,
                game__status="final",
                team__is_d1=True,
                opponent__is_d1=True,
            ).select_related("game", "opponent", "team")
        )
        self.stdout.write(f"  {len(all_stats)} team-game stats loaded")

        all_game_ids = list({gs.game_id for gs in all_stats})
        stats_lookup = {
            (gs.game_id, gs.team_id): gs
            for gs in TeamGameStats.objects.filter(
                game_id__in=all_game_ids
            ).select_related("team")
        }

        game_dates = {gs.game_id: gs.game.game_date for gs in all_stats}

        spread_all = list(
            Game.objects.filter(
                season_year=season_year,
                status="final",
                home_team__is_d1=True,
                away_team__is_d1=True,
                home_score__isnull=False,
                away_score__isnull=False,
                went_to_ot=False,
            ).values(
                "id", "game_date", "home_team_id", "away_team_id",
                "home_score", "away_score", "neutral_site", "went_to_ot",
            )
        )
        wp_all = list(
            Game.objects.filter(
                season_year=season_year,
                status="final",
                home_team__is_d1=True,
                away_team__is_d1=True,
                home_score__isnull=False,
                away_score__isnull=False,
            ).values(
                "id", "game_date", "home_team_id", "away_team_id",
                "home_score", "away_score", "neutral_site", "went_to_ot",
            )
        )
        self.stdout.write(
            f"  {len(spread_all)} spread games (reg, D1vD1)  |  "
            f"{len(wp_all)} win-prob games (D1vD1)"
        )

        team_ids = [t.id for t in Team.objects.filter(is_d1=True)]

        # ── Cutoff schedule ───────────────────────────────────────────────── #
        all_dates = sorted(game_dates.values())
        if not all_dates:
            self.stderr.write("No games found.")
            return

        start_cutoff = (
            date.fromisoformat(options["start"])
            if options["start"]
            else all_dates[0] + timedelta(days=14)
        )
        end_cutoff = (
            date.fromisoformat(options["end"])
            if options["end"]
            else all_dates[-1] - timedelta(days=window)
        )

        cutoffs = []
        c = start_cutoff
        while c <= end_cutoff:
            cutoffs.append(c)
            c += timedelta(days=step)

        self.stdout.write(
            f"  {len(cutoffs)} cutoffs: {cutoffs[0]} → {cutoffs[-1]}  "
            f"(step={step}d, window={window}d)"
        )
        stage = (
            "1 (ON vs OFF)"
            if len(combos) == 2 and combos[0].label == "OFF" and combos[-1].label == "ON(def)"
            else "2 (IMP_C sweep)"
            if any("C=" in c.label for c in combos)
            else "3 (CLOSE_M×BOOST_MAX)"
        )
        self.stdout.write(f"  Stage {stage}")
        self.stdout.write(f"  Combos: {[c.label for c in combos]}\n")

        # ── Accumulators ─────────────────────────────────────────────────── #
        phase_keys = list(PHASES.keys()) + ["other"]
        acc = {
            combo.label: {
                "spread_ae":  [],
                "spread_se":  [],
                "spread_err": [],
                "brier":      [],
                "logloss":    [],
                "correct":    [],
                "phase":      {ph: {"ae": [], "se": []} for ph in phase_keys},
                "imp_weights":[],   # all w_imp values across all training cutoffs
                "per_cutoff": {},
            }
            for combo in combos
        }

        # ── Main loop ─────────────────────────────────────────────────────── #
        for ci, cutoff in enumerate(cutoffs):
            wend = cutoff + timedelta(days=window)

            train_stats = [gs for gs in all_stats if game_dates[gs.game_id] < cutoff]
            if len(train_stats) < 20:
                self.stdout.write(
                    f"  [{ci+1:2d}/{len(cutoffs)}] {cutoff}  "
                    f"skip (only {len(train_stats)} train rows)"
                )
                continue

            by_team_train: defaultdict = defaultdict(list)
            for gs in train_stats:
                by_team_train[gs.team_id].append(gs)

            gtw, tts = time_weights(train_stats, game_dates, cutoff)

            test_spread = [g for g in spread_all if cutoff <= g["game_date"] < wend]
            test_wp     = [g for g in wp_all     if cutoff <= g["game_date"] < wend]

            self.stdout.write(
                f"  [{ci+1:2d}/{len(cutoffs)}] {cutoff}  "
                f"train={len(train_stats):5d}  "
                f"spread={len(test_spread):3d}  wp={len(test_wp):3d}",
                ending="",
            )

            for combo in combos:
                ratings, imp_wts = run_ratings_with_importance_weights(
                    by_team_train, train_stats, stats_lookup,
                    team_ids, nat_avg, gtw, tts, k, combo.importance_params(),
                )
                acc[combo.label]["imp_weights"].extend(imp_wts)

                pc = {"n_s": 0, "ae_sum": 0.0, "se_sum": 0.0,
                      "n_w": 0, "brier_sum": 0.0}

                for g in test_spread:
                    home_r = ratings.get(g["home_team_id"])
                    away_r = ratings.get(g["away_team_id"])
                    if not home_r or not away_r:
                        continue

                    pred   = predict_margin(home_r, away_r, nat_avg, g["neutral_site"])
                    actual = g["home_score"] - g["away_score"]
                    err    = pred - actual
                    ae     = abs(err)

                    acc[combo.label]["spread_ae"].append(ae)
                    acc[combo.label]["spread_se"].append(err ** 2)
                    acc[combo.label]["spread_err"].append(err)

                    ph = _phase(g["game_date"])
                    acc[combo.label]["phase"][ph]["ae"].append(ae)
                    acc[combo.label]["phase"][ph]["se"].append(err ** 2)

                    pc["n_s"]   += 1
                    pc["ae_sum"] += ae
                    pc["se_sum"] += err ** 2

                for g in test_wp:
                    home_r = ratings.get(g["home_team_id"])
                    away_r = ratings.get(g["away_team_id"])
                    if not home_r or not away_r:
                        continue

                    pred_margin = predict_margin(home_r, away_r, nat_avg, g["neutral_site"])
                    prob_home   = scipy_stats.norm.cdf(pred_margin / sigma)
                    prob_home   = max(EPS, min(1.0 - EPS, prob_home))

                    y = 1.0 if g["home_score"] > g["away_score"] else 0.0
                    acc[combo.label]["brier"].append((prob_home - y) ** 2)
                    acc[combo.label]["logloss"].append(
                        -(y * math.log(prob_home) + (1 - y) * math.log(1 - prob_home))
                    )
                    acc[combo.label]["correct"].append(
                        1 if (prob_home >= 0.5) == (y >= 0.5) else 0
                    )
                    pc["n_w"]      += 1
                    pc["brier_sum"] += (prob_home - y) ** 2

                acc[combo.label]["per_cutoff"][cutoff] = pc

            self.stdout.write("")

        # ── Output ────────────────────────────────────────────────────────── #
        W = 90
        self.stdout.write("\n" + "=" * W)
        self.stdout.write(
            f"BACKTEST RESULTS — season {season_year}  "
            f"(k={k:.0f}, λ={RECENCY_LAMBDA}, hca={nat_avg.hca_points or 3.20:.4f})"
        )
        self.stdout.write("=" * W)

        # Spread table sorted by MAE
        rows = []
        for combo in combos:
            r = acc[combo.label]
            if not r["spread_ae"]:
                continue
            mae  = statistics.fmean(r["spread_ae"])
            rmse = math.sqrt(statistics.fmean(r["spread_se"]))
            bias = statistics.fmean(r["spread_err"])
            rows.append((combo.label, len(r["spread_ae"]), mae, rmse, bias))

        rows_by_mae = sorted(rows, key=lambda x: x[2])
        best_mae = rows_by_mae[0][2] if rows_by_mae else 0.0

        self.stdout.write("\nFULL-SEASON SPREAD ACCURACY  (regulation, D1vD1) — sorted by MAE")
        hdr = f"  {'combo':<14}  {'n':>6}  {'MAE':>8}  {'RMSE':>8}  {'bias':>8}  Δmae"
        self.stdout.write(hdr)
        self.stdout.write("-" * len(hdr))
        for label, n, mae, rmse, bias in rows_by_mae:
            marker = " ◄" if mae == best_mae else ""
            self.stdout.write(
                f"  {label:<14}  {n:>6}  {mae:>8.3f}  {rmse:>8.3f}  "
                f"{bias:>+8.3f}  {mae - best_mae:>+.3f}{marker}"
            )

        # Win-prob table
        self.stdout.write("\nWIN PROBABILITY ACCURACY  (all D1vD1 incl. OT)")
        hdr2 = f"  {'combo':<14}  {'n':>6}  {'Brier':>8}  {'LogLoss':>9}  {'Acc%':>6}"
        self.stdout.write(hdr2)
        self.stdout.write("-" * len(hdr2))
        for combo in combos:
            r = acc[combo.label]
            if not r["brier"]:
                continue
            self.stdout.write(
                f"  {combo.label:<14}  {len(r['brier']):>6}  "
                f"{statistics.fmean(r['brier']):>8.4f}  "
                f"{statistics.fmean(r['logloss']):>9.4f}  "
                f"{100*statistics.fmean(r['correct']):>6.1f}"
            )

        # Phase breakdown
        self.stdout.write("\nSPREAD MAE BY SEASON PHASE")
        phase_names = list(PHASES.keys())
        col = 10
        hdr3 = f"  {'combo':<14}"
        for ph in phase_names:
            hdr3 += f"  {ph:>{col}}"
        hdr3 += f"  {'full':>{col}}"
        self.stdout.write(hdr3)
        self.stdout.write("-" * (len(hdr3) + 2))
        for combo in combos:
            r = acc[combo.label]
            row = f"  {combo.label:<14}"
            for ph in phase_names:
                vals = r["phase"][ph]["ae"]
                row += f"  {statistics.fmean(vals):>{col}.3f}" if vals else f"  {'—':>{col}}"
            full = statistics.fmean(r["spread_ae"]) if r["spread_ae"] else float("nan")
            row += f"  {full:>{col}.3f}"
            self.stdout.write(row)

        # Importance weight diagnostics
        self.stdout.write("\nIMPORTANCE WEIGHT DIAGNOSTICS  (from freeze-iteration training weights)")
        hdr4 = f"  {'combo':<14}  {'n_weights':>10}  {'mean':>8}  {'median':>8}  {'floor_hits':>12}  {'floor%':>8}"
        self.stdout.write(hdr4)
        self.stdout.write("-" * len(hdr4))
        for combo in combos:
            wts = acc[combo.label]["imp_weights"]
            if not wts:
                # OFF combo
                self.stdout.write(f"  {combo.label:<14}  {'(disabled)':>10}")
                continue
            mean_w   = statistics.fmean(wts)
            median_w = statistics.median(wts)
            n_floor  = sum(1 for w in wts if w <= combo.imp_floor + 1e-6)
            floor_pct = 100 * n_floor / len(wts)
            self.stdout.write(
                f"  {combo.label:<14}  {len(wts):>10}  {mean_w:>8.4f}  "
                f"{median_w:>8.4f}  {n_floor:>12}  {floor_pct:>8.2f}%"
            )

        # Per-cutoff MAE detail
        self.stdout.write("\nPER-CUTOFF SPREAD MAE")
        hdr5 = f"  {'cutoff':<12}  {'phase':<8}  {'n':>5}"
        for combo in combos:
            hdr5 += f"  {combo.label:>14}"
        self.stdout.write(hdr5)
        self.stdout.write("-" * (len(hdr5) + 2))
        for cutoff in cutoffs:
            ph = _phase(cutoff)
            n_reg = next(
                (acc[c.label]["per_cutoff"][cutoff]["n_s"]
                 for c in combos
                 if acc[c.label]["per_cutoff"].get(cutoff, {}).get("n_s", 0) > 0),
                0,
            )
            row = f"  {str(cutoff):<12}  {ph:<8}  {n_reg:>5}"
            for combo in combos:
                pc  = acc[combo.label]["per_cutoff"].get(cutoff, {})
                n_s = pc.get("n_s", 0)
                row += (
                    f"  {pc['ae_sum']/n_s:>14.3f}" if n_s > 0 else f"  {'—':>14}"
                )
            self.stdout.write(row)

        # Recommendation
        self.stdout.write(f"\n{'─' * W}")
        if rows_by_mae:
            best_label, _, best_m, _, best_b = rows_by_mae[0]
            self.stdout.write(
                f"RECOMMENDATION: {best_label}  MAE={best_m:.3f}  bias={best_b:+.3f}"
            )
        self.stdout.write("")
