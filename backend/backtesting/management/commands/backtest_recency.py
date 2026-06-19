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

from ncaa.models import Game, NationalAverages, Team, TeamGameStats

# ── Fixed constants (same as production / other backtests) ─────────────────
CONVERGENCE = 0.001
MAX_ITERATIONS = 50
IMP_C = 40.0
IMP_FLOOR = 0.35
CLOSE_M = 12.0
BOOST_MAX = 1.40
FREEZE_ITERATION = 6

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


# ── Recency weights — parameterised by lam ────────────────────────────────

def _time_weights(train_stats, game_dates, ref_date, lam):
    """
    Compute per-game recency weights and per-team rescale factors anchored
    to ref_date (the cutoff). When lam=0 all weights are 1.0.
    """
    if lam == 0.0:
        gtw = {gs.game_id: 1.0 for gs in train_stats}
        tts = {gs.team_id: 1.0 for gs in train_stats}
        return gtw, tts

    gtw = {
        gs.game_id: math.exp(-lam * max(0, (ref_date - game_dates[gs.game_id]).days))
        for gs in train_stats
    }

    sum_p: defaultdict = defaultdict(float)
    sum_pw: defaultdict = defaultdict(float)
    for gs in train_stats:
        p = gs.poss_team
        if not p or p <= 0:
            continue
        sum_p[gs.team_id] += p
        sum_pw[gs.team_id] += p * gtw.get(gs.game_id, 1.0)

    tts = {
        tid: (sum_p[tid] / sum_pw[tid]) if sum_pw[tid] > 0 else 1.0
        for tid in sum_p
    }
    return gtw, tts


# ── Iterative ratings (parameterised by lam via pre-computed gtw/tts) ──────

def _run_ratings(by_team_train, train_stats, stats_lookup,
                 team_ids, nat_avg, gtw, tts, k, use_importance=True):
    """Iterative opponent-adjusted ratings — identical to other backtests."""
    ratings = {
        tid: {"aor": nat_avg.avg_ortg, "adr": nat_avg.avg_ortg, "pace": nat_avg.avg_pace}
        for tid in team_ids
    }
    frozen_imp: dict = {}
    imp_scale: dict = {}

    for iteration in range(1, MAX_ITERATIONS + 1):
        cur_imp: dict = {}
        new_r: dict = {}
        max_change = 0.0

        for tid in team_ids:
            sw_aor = sw_adr = sw_pace = sw = 0.0

            for gs in by_team_train.get(tid, []):
                poss_g = gs.poss_team
                if not poss_g or poss_g <= 0:
                    continue
                opp_id = gs.opponent_id
                if opp_id not in ratings:
                    continue
                opp_st = stats_lookup.get((gs.game_id, opp_id))
                if not opp_st:
                    continue

                minutes = gs.game_minutes or 40
                raw_oe = 100 * gs.pts / poss_g
                raw_de = 100 * opp_st.pts / poss_g
                raw_pace = 40 * poss_g / minutes

                opp_aor = ratings[opp_id]["aor"]
                opp_adr = ratings[opp_id]["adr"]
                opp_pace = ratings[opp_id]["pace"]

                aor_g = raw_oe * (nat_avg.avg_ortg / opp_adr) * gs.site_factor if opp_adr > 0 else raw_oe
                adr_g = raw_de * (nat_avg.avg_ortg / opp_aor) * gs.defensive_site_factor if opp_aor > 0 else raw_de
                blend = (opp_pace + nat_avg.avg_pace) / 2
                pace_g = raw_pace * (nat_avg.avg_pace / blend) if blend > 0 else raw_pace

                w_time = gtw.get(gs.game_id, 1.0) * tts.get(tid, 1.0)

                imp_key = (tid, gs.game_id)
                if not use_importance:
                    w_imp = 1.0
                elif iteration <= FREEZE_ITERATION:
                    t_aem = ratings[tid]["aor"] - ratings[tid]["adr"]
                    o_aem = opp_aor - opp_adr
                    gap = abs(t_aem - o_aem)
                    base = max(IMP_FLOOR, 1.0 / (1.0 + (gap / IMP_C) ** 2))
                    closer = max(0.0, abs(t_aem - o_aem) - abs(aor_g - adr_g))
                    cf = 1.0 - math.exp(-closer / CLOSE_M)
                    w_imp = min(1.0, base * (1.0 + (BOOST_MAX - 1.0) * cf))
                    cur_imp[imp_key] = w_imp
                else:
                    w_imp = frozen_imp.get(imp_key, 1.0)

                wt = poss_g * w_time * w_imp * imp_scale.get(tid, 1.0)
                sw_aor += wt * aor_g
                sw_adr += wt * adr_g
                sw_pace += wt * pace_g
                sw += wt

            if sw > 0:
                aor_s = (sw_aor + k * nat_avg.avg_ortg) / (sw + k)
                adr_s = (sw_adr + k * nat_avg.avg_ortg) / (sw + k)
                pace_s = (sw_pace + k * nat_avg.avg_pace) / (sw + k)
            else:
                aor_s = adr_s = nat_avg.avg_ortg
                pace_s = nat_avg.avg_pace

            old_aem = ratings[tid]["aor"] - ratings[tid]["adr"]
            new_aem = aor_s - adr_s
            max_change = max(max_change, abs(new_aem - old_aem))
            new_r[tid] = {"aor": aor_s, "adr": adr_s, "pace": pace_s}

        if use_importance and iteration == FREEZE_ITERATION:
            frozen_imp = dict(cur_imp)
            sb: defaultdict = defaultdict(float)
            si: defaultdict = defaultdict(float)
            for gs in train_stats:
                p = gs.poss_team
                if not p or p <= 0:
                    continue
                wt = gtw.get(gs.game_id, 1.0) * tts.get(gs.team_id, 1.0)
                wi = frozen_imp.get((gs.team_id, gs.game_id), 1.0)
                sb[gs.team_id] += p * wt
                si[gs.team_id] += p * wt * wi
            imp_scale = {
                t: max(0.85, min(1.30, (sb[t] / si[t]) if si[t] > 0 else 1.0))
                for t in sb
            }

        ratings = new_r
        if max_change < CONVERGENCE:
            break

    return ratings


def _predict_margin(home_r, away_r, nat_avg, neutral_site):
    """Multiplicative efficiency model using stored hca_points."""
    hp, ap = home_r["pace"], away_r["pace"]
    pace = (2 * hp * ap) / (hp + ap) if hp > 0 and ap > 0 else nat_avg.avg_pace

    exp_oe_home = (home_r["aor"] * away_r["adr"]) / nat_avg.avg_ortg
    exp_oe_away = (away_r["aor"] * home_r["adr"]) / nat_avg.avg_ortg

    pts_home = exp_oe_home * (pace / 100)
    pts_away = exp_oe_away * (pace / 100)

    hca = nat_avg.hca_points or 3.20
    if not neutral_site:
        pts_home += hca / 2
        pts_away -= hca / 2

    return pts_home - pts_away


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
                    gtw, tts = _time_weights(train_stats, game_dates, cutoff, lam)
                    ratings = _run_ratings(
                        by_team_train, train_stats, stats_lookup,
                        team_ids, nat_avg, gtw, tts, k,
                        use_importance=use_importance,
                    )

                    for g in test_spread:
                        home_r = ratings.get(g["home_team_id"])
                        away_r = ratings.get(g["away_team_id"])
                        if not home_r or not away_r:
                            continue
                        pred   = _predict_margin(home_r, away_r, nat_avg, g["neutral_site"])
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
                        pred_margin = _predict_margin(home_r, away_r, nat_avg, g["neutral_site"])
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
