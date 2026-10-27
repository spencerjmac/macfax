"""
Backtest: evaluate recency-decay lambda values against out-of-sample accuracy.

Holds all other parameters fixed (k=150, hca from DB) and sweeps a grid of
RECENCY_LAMBDA values. Unlike the HCA backtest, ratings must be re-run for
each lambda at every cutoff because the lambda changes the weighting inside
the rating computation itself.

Primary metric   : SU accuracy + Brier (win-prob, all games incl. OT)
Secondary metrics: spread MAE (regulation), phase breakdown (Nov–Dec / Jan / Feb–Mar)
Decision signal  : Feb–Mar SU accuracy vs KenPom benchmark 70.4%

Usage:
    python manage.py backtest_recency --season 2026
    python manage.py backtest_recency --seasons 2016 2017 2018 2019 2020 2022 2023 2024 2025 2026
    python manage.py backtest_recency --seasons 2016 ... 2026 --lam-vals 0 0.002 0.004 0.006 0.010
    python manage.py backtest_recency --seasons 2016 ... 2026 --no-importance
"""

import math
import statistics
from collections import defaultdict
from datetime import date, timedelta

from scipy import stats as scipy_stats

from django.core.management.base import BaseCommand

from backtesting.rating_replay import (
    NO_IMPORTANCE,
    PRODUCTION_IMPORTANCE,
    predict_margin,
    run_ratings,
    time_weights,
)
from ncaa.models import Game, NationalAverages, Team, TeamGameStats

# Season-phase boundaries (month ranges, inclusive)
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


def _empty_acc(lam_values, phase_keys):
    return {
        lam: {
            "spread_ae":  [],
            "spread_se":  [],
            "spread_err": [],
            "brier":      [],
            "logloss":    [],
            "correct":    [],
            "phase": {
                ph: {"ae": [], "se": [], "err": [], "correct": []}
                for ph in phase_keys
            },
        }
        for lam in lam_values
    }


# ── management command ─────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "Backtest recency-decay lambda values (SU accuracy + Brier + phase breakdown, multi-season)"

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, default=None,
                            help="Single season year (use --seasons for multi-season)")
        parser.add_argument("--seasons", type=int, nargs="+", default=None,
                            help="List of season years to pool (e.g. 2016 2017 ... 2026)")
        parser.add_argument(
            "--lam-vals",
            type=float,
            nargs="+",
            default=[0.0000, 0.0020, 0.0030, 0.0040, 0.0050, 0.0060],
            help="Lambda values to test (default: 0 0.002 0.003 0.004 0.005 0.006)",
        )
        parser.add_argument("--no-importance", action="store_true", default=False,
                            help="Disable importance weighting (default: enabled)")
        parser.add_argument("--k", type=float, default=150.0,
                            help="Fixed shrinkage k (default: 150)")
        parser.add_argument("--start", type=str, default=None,
                            help="First cutoff date YYYY-MM-DD")
        parser.add_argument("--end",   type=str, default=None,
                            help="Last cutoff date YYYY-MM-DD")
        parser.add_argument("--step",  type=int, default=7,
                            help="Days between cutoffs (default: 7)")
        parser.add_argument("--window", type=int, default=7,
                            help="Test window in days after each cutoff (default: 7)")

    def handle(self, *args, **options):
        seasons = options["seasons"] or ([options["season"]] if options["season"] else None)
        if not seasons:
            self.stderr.write("Provide --season YEAR or --seasons YEAR [YEAR ...]")
            return

        use_importance = not options["no_importance"]
        importance = PRODUCTION_IMPORTANCE if use_importance else NO_IMPORTANCE
        lam_values = options["lam_vals"]
        k          = options["k"]
        step       = options["step"]
        window     = options["window"]
        EPS        = 1e-9

        phase_keys = list(PHASES.keys()) + ["other"]
        pooled = _empty_acc(lam_values, phase_keys)

        imp_label = "ON" if use_importance else "OFF"
        self.stdout.write(
            f"\nbacktest_recency  |  seasons={seasons}  "
            f"k={k:.0f}  importance={imp_label}  λ={lam_values}"
        )

        for season_year in seasons:
            self.stdout.write(f"\n{'─'*60} {season_year} {'─'*20}")

            nat_avg = NationalAverages.objects.get(season__year=season_year)
            sigma   = nat_avg.prediction_sigma or 11.08

            # Load all data for this season
            all_stats = list(
                TeamGameStats.objects.filter(
                    game__season_year=season_year,
                    game__status="final",
                    team__is_d1=True,
                    opponent__is_d1=True,
                ).select_related("game", "opponent", "team")
            )
            self.stdout.write(f"  {len(all_stats)} team-game stats  σ={sigma:.3f}  hca={nat_avg.hca_points or 3.20:.4f}")

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
                    season_year=season_year, status="final",
                    home_team__is_d1=True, away_team__is_d1=True,
                    home_score__isnull=False, away_score__isnull=False,
                    went_to_ot=False,
                ).values("id", "game_date", "home_team_id", "away_team_id",
                         "home_score", "away_score", "neutral_site", "went_to_ot")
            )
            wp_all = list(
                Game.objects.filter(
                    season_year=season_year, status="final",
                    home_team__is_d1=True, away_team__is_d1=True,
                    home_score__isnull=False, away_score__isnull=False,
                ).values("id", "game_date", "home_team_id", "away_team_id",
                         "home_score", "away_score", "neutral_site", "went_to_ot")
            )
            team_ids = [t.id for t in Team.objects.filter(is_d1=True)]

            # Build cutoff schedule
            all_dates = sorted(game_dates.values())
            if not all_dates:
                self.stdout.write(f"  No games found, skipping.")
                continue

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

            # Main loop
            for ci, cutoff in enumerate(cutoffs):
                wend = cutoff + timedelta(days=window)

                train_stats = [gs for gs in all_stats if game_dates[gs.game_id] < cutoff]
                if len(train_stats) < 20:
                    continue

                by_team_train: defaultdict = defaultdict(list)
                for gs in train_stats:
                    by_team_train[gs.team_id].append(gs)

                test_spread = [g for g in spread_all if cutoff <= g["game_date"] < wend]
                test_wp     = [g for g in wp_all     if cutoff <= g["game_date"] < wend]

                self.stdout.write(
                    f"  [{ci+1:2d}/{len(cutoffs)}] {cutoff}  "
                    f"train={len(train_stats):5d}  spread={len(test_spread):3d}  wp={len(test_wp):3d}",
                    ending="",
                )

                for lam in lam_values:
                    gtw, tts = time_weights(train_stats, game_dates, cutoff, lam)
                    ratings = run_ratings(
                        by_team_train, train_stats, stats_lookup,
                        team_ids, nat_avg, gtw, tts, k,
                        importance=importance,
                    )

                    for g in test_spread:
                        home_r = ratings.get(g["home_team_id"])
                        away_r = ratings.get(g["away_team_id"])
                        if not home_r or not away_r:
                            continue
                        pred   = predict_margin(home_r, away_r, nat_avg, g["neutral_site"])
                        actual = g["home_score"] - g["away_score"]
                        err    = pred - actual
                        ae     = abs(err)
                        pooled[lam]["spread_ae"].append(ae)
                        pooled[lam]["spread_se"].append(err ** 2)
                        pooled[lam]["spread_err"].append(err)

                        ph = _phase(g["game_date"])
                        pooled[lam]["phase"][ph]["ae"].append(ae)
                        pooled[lam]["phase"][ph]["se"].append(err ** 2)
                        pooled[lam]["phase"][ph]["err"].append(err)

                    for g in test_wp:
                        home_r = ratings.get(g["home_team_id"])
                        away_r = ratings.get(g["away_team_id"])
                        if not home_r or not away_r:
                            continue
                        pred_margin = predict_margin(home_r, away_r, nat_avg, g["neutral_site"])
                        prob_home = scipy_stats.norm.cdf(pred_margin / sigma)
                        prob_home = max(EPS, min(1.0 - EPS, prob_home))
                        y = 1.0 if g["home_score"] > g["away_score"] else 0.0
                        brier = (prob_home - y) ** 2
                        correct = 1 if (prob_home >= 0.5) == (y >= 0.5) else 0
                        pooled[lam]["brier"].append(brier)
                        pooled[lam]["logloss"].append(
                            -(y * math.log(prob_home) + (1 - y) * math.log(1 - prob_home))
                        )
                        pooled[lam]["correct"].append(correct)

                        ph = _phase(g["game_date"])
                        pooled[lam]["phase"][ph]["correct"].append(correct)

                self.stdout.write("")  # newline

        # ── Summary tables ───────────────────────────────────────────────── #
        season_label = (
            f"season {seasons[0]}" if len(seasons) == 1
            else f"{len(seasons)} seasons ({seasons[0]}–{seasons[-1]})"
        )
        W = 90
        self.stdout.write(f"\n{'='*W}")
        self.stdout.write(f"POOLED RESULTS — {season_label}  (k={k:.0f}, importance={imp_label})")
        self.stdout.write(f"{'='*W}")

        # Primary decision table: SU accuracy + Brier + Feb-Mar SU
        self.stdout.write(
            f"\n{'KenPom benchmark — Feb-Mar SU: 70.4%  |  Overall OOS ~69.5% baseline':^{W}}"
        )
        hdr = f"  {'λ':>7}  {'half-life':>10}  {'n_wp':>6}  {'SU Acc%':>8}  {'Brier':>8}  "
        hdr += f"{'Feb-Mar SU%':>12}  {'Feb-Mar MAE':>12}  {'Full MAE':>9}  Δsua"
        self.stdout.write(f"\n{hdr}")
        self.stdout.write("─" * (len(hdr) + 2))

        rows = []
        base_sua = None
        for lam in lam_values:
            r = pooled[lam]
            if not r["correct"]:
                continue
            sua     = 100 * statistics.fmean(r["correct"])
            brier   = statistics.fmean(r["brier"]) if r["brier"] else float("nan")
            fmsu_vals = r["phase"]["Feb–Mar"]["correct"]
            fmsu    = 100 * statistics.fmean(fmsu_vals) if fmsu_vals else float("nan")
            fmmae_vals = r["phase"]["Feb–Mar"]["ae"]
            fmmae   = statistics.fmean(fmmae_vals) if fmmae_vals else float("nan")
            mae     = statistics.fmean(r["spread_ae"]) if r["spread_ae"] else float("nan")
            rows.append((lam, len(r["correct"]), sua, brier, fmsu, fmmae, mae))
            if base_sua is None:
                base_sua = sua

        best_sua = max(r[2] for r in rows) if rows else 0.0

        for lam, n_wp, sua, brier, fmsu, fmmae, mae in rows:
            hl = f"{math.log(2)/lam:.0f}d" if lam > 0 else "∞"
            marker = " ◄" if sua == best_sua else ""
            fmsu_str  = f"{fmsu:>12.1f}%" if not math.isnan(fmsu) else f"{'—':>12}"
            fmmae_str = f"{fmmae:>12.3f}" if not math.isnan(fmmae) else f"{'—':>12}"
            self.stdout.write(
                f"  {lam:>7.4f}  {hl:>10}  {n_wp:>6}  "
                f"{sua:>7.1f}%  {brier:>8.4f}  "
                f"{fmsu_str}  {fmmae_str}  "
                f"{mae:>9.3f}  "
                f"{sua - (base_sua or sua):>+.1f}%{marker}"
            )

        # Phase breakdown table
        self.stdout.write(f"\n\nSPREAD MAE BY PHASE")
        phase_names = list(PHASES.keys())
        hdr2 = f"  {'λ':>7}"
        for ph in phase_names:
            hdr2 += f"  {ph:>10}"
        hdr2 += f"  {'full':>10}"
        self.stdout.write(hdr2)
        self.stdout.write("─" * (len(hdr2) + 2))
        for lam in lam_values:
            r = pooled[lam]
            row = f"  {lam:>7.4f}"
            for ph in phase_names:
                vals = r["phase"][ph]["ae"]
                row += f"  {statistics.fmean(vals):>10.3f}" if vals else f"  {'—':>10}"
            full_mae = statistics.fmean(r["spread_ae"]) if r["spread_ae"] else float("nan")
            row += f"  {full_mae:>10.3f}"
            self.stdout.write(row)

        # Phase SU breakdown
        self.stdout.write(f"\n\nSU ACCURACY BY PHASE  (%)")
        hdr3 = f"  {'λ':>7}"
        for ph in phase_names:
            hdr3 += f"  {ph:>10}"
        hdr3 += f"  {'full':>10}"
        self.stdout.write(hdr3)
        self.stdout.write("─" * (len(hdr3) + 2))
        for lam in lam_values:
            r = pooled[lam]
            row = f"  {lam:>7.4f}"
            for ph in phase_names:
                vals = r["phase"][ph]["correct"]
                row += f"  {100*statistics.fmean(vals):>9.1f}%" if vals else f"  {'—':>10}"
            full_su = 100 * statistics.fmean(r["correct"]) if r["correct"] else float("nan")
            row += f"  {full_su:>9.1f}%"
            self.stdout.write(row)

        # Phase n-counts
        self.stdout.write(f"\n  (wp-game counts per phase — same for all λ)")
        first_lam = lam_values[0]
        cnt_row = f"  {'n':>7}"
        for ph in phase_names:
            n_ph = len(pooled[first_lam]["phase"][ph]["correct"])
            cnt_row += f"  {n_ph:>10}"
        cnt_row += f"  {len(pooled[first_lam]['correct']):>10}"
        self.stdout.write(cnt_row)

        # Recommendation
        self.stdout.write(f"\n{'─'*W}")
        if rows:
            best_row = max(rows, key=lambda x: x[2])  # best SU accuracy
            best_lam, _, best_sua_val, best_brier, best_fmsu, _, best_mae = best_row
            hl = f"{math.log(2)/best_lam:.0f}d" if best_lam > 0 else "∞ (flat)"
            fmsu_note = f"  Feb-Mar SU={best_fmsu:.1f}%" if not math.isnan(best_fmsu) else ""
            self.stdout.write(
                f"BEST SU: λ={best_lam:.4f} (half-life {hl})  "
                f"SU={best_sua_val:.1f}%  Brier={best_brier:.4f}  "
                f"MAE={best_mae:.3f}{fmsu_note}"
            )
            best_brier_row = min(rows, key=lambda x: x[3])
            if best_brier_row[0] != best_lam:
                self.stdout.write(
                    f"BEST Brier: λ={best_brier_row[0]:.4f}  "
                    f"Brier={best_brier_row[3]:.4f}  SU={best_brier_row[2]:.1f}%"
                )
        self.stdout.write("")
