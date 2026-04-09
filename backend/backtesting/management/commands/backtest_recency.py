"""
Backtest: evaluate recency-decay lambda values against out-of-sample accuracy.

Holds all other parameters fixed (k=150, hca from DB) and sweeps a grid of
RECENCY_LAMBDA values. Unlike the HCA backtest, ratings must be re-run for
each lambda at every cutoff because the lambda changes the weighting inside
the rating computation itself.

Primary metric   : spread MAE (full season)
Secondary metrics: spread RMSE, win-prob log-loss / Brier
Diagnostic       : metrics split by season phase (Nov–Dec / Jan / Feb–Mar)

Usage:
    python manage.py backtest_recency --season 2026
    python manage.py backtest_recency --season 2026 --lam-vals 0.000 0.002 0.004 0.006
    python manage.py backtest_recency --season 2026 --k 150
"""

import math
import statistics
from collections import defaultdict
from datetime import date, timedelta

from scipy import stats as scipy_stats

from django.core.management.base import BaseCommand

from core.models import Game, NationalAverages, Team, TeamGameStats

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
                 team_ids, nat_avg, gtw, tts, k):
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
                if iteration <= FREEZE_ITERATION:
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

        if iteration == FREEZE_ITERATION:
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


# ── management command ─────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "Backtest recency-decay lambda values (spread MAE + phase breakdown)"

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument(
            "--lam-vals",
            type=float,
            nargs="+",
            default=[0.0000, 0.0020, 0.0030, 0.0040, 0.0050, 0.0060],
            help="Lambda values to test (default: 0 0.002 0.003 0.004 0.005 0.006)",
        )
        parser.add_argument(
            "--k",
            type=float,
            default=150.0,
            help="Fixed shrinkage k (default: 150)",
        )
        parser.add_argument("--start", type=str, default=None,
                            help="First cutoff date YYYY-MM-DD")
        parser.add_argument("--end",   type=str, default=None,
                            help="Last cutoff date YYYY-MM-DD")
        parser.add_argument("--step",  type=int, default=7,
                            help="Days between cutoffs (default: 7)")
        parser.add_argument("--window", type=int, default=7,
                            help="Test window in days after each cutoff (default: 7)")

    def handle(self, *args, **options):
        season_year = options["season"]
        lam_values  = options["lam_vals"]
        k           = options["k"]
        step        = options["step"]
        window      = options["window"]

        nat_avg = NationalAverages.objects.get(season__year=season_year)
        sigma   = nat_avg.prediction_sigma or 11.08
        EPS     = 1e-9

        # ── Load all data once ───────────────────────────────────────────── #
        self.stdout.write(
            f"Loading data...  (k={k:.0f}, σ={sigma:.3f}, "
            f"hca={nat_avg.hca_points or 3.20:.4f})"
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

        # Spread test games: D1vD1, final, regulation (no OT), non-neutral
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
        # Win-prob games: D1vD1, final (OT included)
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

        # ── Build cutoff schedule ─────────────────────────────────────────── #
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
        self.stdout.write(
            f"  λ values: {lam_values}\n"
        )

        # ── Result accumulators ───────────────────────────────────────────── #
        # Full-season totals
        phase_keys = list(PHASES.keys()) + ["other"]
        acc = {
            lam: {
                "spread_ae":  [],
                "spread_se":  [],
                "spread_err": [],
                "brier":      [],
                "logloss":    [],
                "correct":    [],
                # Per-phase spread accumulators
                "phase": {ph: {"ae": [], "se": [], "err": []} for ph in phase_keys},
                # Per-cutoff store for the detail table
                "per_cutoff": {},
            }
            for lam in lam_values
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

            test_spread = [g for g in spread_all if cutoff <= g["game_date"] < wend]
            test_wp     = [g for g in wp_all     if cutoff <= g["game_date"] < wend]

            self.stdout.write(
                f"  [{ci+1:2d}/{len(cutoffs)}] {cutoff}  "
                f"train={len(train_stats):5d}  "
                f"spread_test={len(test_spread):3d}  wp_test={len(test_wp):3d}",
                ending="",
            )

            for lam in lam_values:
                gtw, tts = _time_weights(train_stats, game_dates, cutoff, lam)

                ratings = _run_ratings(
                    by_team_train, train_stats, stats_lookup,
                    team_ids, nat_avg, gtw, tts, k,
                )

                pc = {"n_s": 0, "ae_sum": 0.0, "se_sum": 0.0, "err_sum": 0.0,
                      "n_w": 0, "brier_sum": 0.0}

                for g in test_spread:
                    home_r = ratings.get(g["home_team_id"])
                    away_r = ratings.get(g["away_team_id"])
                    if not home_r or not away_r:
                        continue

                    pred   = _predict_margin(home_r, away_r, nat_avg, g["neutral_site"])
                    actual = g["home_score"] - g["away_score"]
                    err    = pred - actual
                    ae     = abs(err)

                    acc[lam]["spread_ae"].append(ae)
                    acc[lam]["spread_se"].append(err ** 2)
                    acc[lam]["spread_err"].append(err)

                    ph = _phase(g["game_date"])
                    acc[lam]["phase"][ph]["ae"].append(ae)
                    acc[lam]["phase"][ph]["se"].append(err ** 2)
                    acc[lam]["phase"][ph]["err"].append(err)

                    pc["n_s"] += 1
                    pc["ae_sum"] += ae
                    pc["se_sum"] += err ** 2
                    pc["err_sum"] += err

                for g in test_wp:
                    home_r = ratings.get(g["home_team_id"])
                    away_r = ratings.get(g["away_team_id"])
                    if not home_r or not away_r:
                        continue

                    pred_margin = _predict_margin(
                        home_r, away_r, nat_avg, g["neutral_site"]
                    )
                    prob_home = scipy_stats.norm.cdf(pred_margin / sigma)
                    prob_home = max(EPS, min(1.0 - EPS, prob_home))

                    y = 1.0 if g["home_score"] > g["away_score"] else 0.0
                    acc[lam]["brier"].append((prob_home - y) ** 2)
                    acc[lam]["logloss"].append(
                        -(y * math.log(prob_home) + (1 - y) * math.log(1 - prob_home))
                    )
                    acc[lam]["correct"].append(1 if (prob_home >= 0.5) == (y >= 0.5) else 0)
                    pc["n_w"] += 1
                    pc["brier_sum"] += (prob_home - y) ** 2

                acc[lam]["per_cutoff"][cutoff] = pc

            self.stdout.write("")  # newline after all lambdas for this cutoff

        # ── Summary tables ─────────────────────────────────────────────────── #
        W = 82
        self.stdout.write("\n" + "=" * W)
        self.stdout.write(
            f"BACKTEST RESULTS — season {season_year}  (k={k:.0f}, "
            f"hca={nat_avg.hca_points or 3.20:.4f})"
        )
        self.stdout.write("=" * W)

        # Full-season spread table — sorted by MAE ascending
        rows = []
        for lam in lam_values:
            r = acc[lam]
            if not r["spread_ae"]:
                continue
            mae  = statistics.fmean(r["spread_ae"])
            rmse = math.sqrt(statistics.fmean(r["spread_se"]))
            bias = statistics.fmean(r["spread_err"])
            rows.append((lam, len(r["spread_ae"]), mae, rmse, bias))

        rows_by_mae = sorted(rows, key=lambda x: x[2])
        best_mae = rows_by_mae[0][2] if rows_by_mae else 0.0

        self.stdout.write("\nFULL-SEASON SPREAD ACCURACY  (regulation, D1vD1) — sorted by MAE")
        hdr = f"  {'λ':>7}  {'half-life':>10}  {'n':>6}  {'MAE':>8}  {'RMSE':>8}  {'bias':>8}  Δmae"
        self.stdout.write(hdr)
        self.stdout.write("-" * len(hdr))
        for lam, n, mae, rmse, bias in rows_by_mae:
            hl = f"{math.log(2)/lam:.0f}d" if lam > 0 else "∞"
            marker = " ◄" if mae == best_mae else ""
            self.stdout.write(
                f"  {lam:>7.4f}  {hl:>10}  {n:>6}  "
                f"{mae:>8.3f}  {rmse:>8.3f}  {bias:>+8.3f}  "
                f"{mae - best_mae:>+.3f}{marker}"
            )

        # Win-prob table
        self.stdout.write("\nWIN PROBABILITY ACCURACY  (all D1vD1 incl. OT)")
        hdr2 = f"  {'λ':>7}  {'n':>6}  {'Brier':>8}  {'LogLoss':>9}  {'Acc%':>6}"
        self.stdout.write(hdr2)
        self.stdout.write("-" * len(hdr2))
        for lam in lam_values:
            r = acc[lam]
            if not r["brier"]:
                continue
            brier   = statistics.fmean(r["brier"])
            logloss = statistics.fmean(r["logloss"])
            accp    = 100 * statistics.fmean(r["correct"])
            self.stdout.write(
                f"  {lam:>7.4f}  {len(r['brier']):>6}  "
                f"{brier:>8.4f}  {logloss:>9.4f}  {accp:>6.1f}"
            )

        # Phase breakdown
        self.stdout.write("\nSPREAD MAE BY SEASON PHASE  (regulation, D1vD1)")
        phase_names = [ph for ph in PHASES]
        col_w = 10
        hdr3 = f"  {'λ':>7}"
        for ph in phase_names:
            hdr3 += f"  {ph:>{col_w}}"
        hdr3 += f"  {'full':>{col_w}}"
        self.stdout.write(hdr3)
        self.stdout.write("-" * (len(hdr3) + 2))
        for lam in lam_values:
            r = acc[lam]
            row = f"  {lam:>7.4f}"
            for ph in phase_names:
                vals = r["phase"][ph]["ae"]
                row += f"  {statistics.fmean(vals):>{col_w}.3f}" if vals else f"  {'—':>{col_w}}"
            full_mae = statistics.fmean(r["spread_ae"]) if r["spread_ae"] else float("nan")
            row += f"  {full_mae:>{col_w}.3f}"
            self.stdout.write(row)

        # Phase n-counts (printed once, same for all lambdas since test sets are identical)
        self.stdout.write(
            f"\n  (n per phase — same for all λ, based on first λ)"
        )
        first_lam = lam_values[0]
        count_row = f"  {'n':>7}"
        for ph in phase_names:
            n_ph = len(acc[first_lam]["phase"][ph]["ae"])
            count_row += f"  {n_ph:>{col_w}}"
        count_row += f"  {len(acc[first_lam]['spread_ae']):>{col_w}}"
        self.stdout.write(count_row)

        # Per-cutoff MAE detail
        self.stdout.write("\nPER-CUTOFF SPREAD MAE")
        hdr4 = f"  {'cutoff':<12}  {'phase':<8}  {'n_reg':>5}"
        for lam in lam_values:
            hdr4 += f"  {'λ='+f'{lam:.4f}':>10}"
        self.stdout.write(hdr4)
        self.stdout.write("-" * (len(hdr4) + 2))
        for cutoff in cutoffs:
            ph = _phase(cutoff)
            n_reg = next(
                (acc[lam]["per_cutoff"][cutoff]["n_s"]
                 for lam in lam_values
                 if acc[lam]["per_cutoff"].get(cutoff, {}).get("n_s", 0) > 0),
                0,
            )
            row = f"  {str(cutoff):<12}  {ph:<8}  {n_reg:>5}"
            for lam in lam_values:
                pc = acc[lam]["per_cutoff"].get(cutoff, {})
                n_s = pc.get("n_s", 0)
                row += (
                    f"  {pc['ae_sum']/n_s:>10.3f}" if n_s > 0 else f"  {'—':>10}"
                )
            self.stdout.write(row)

        # Recommendation
        self.stdout.write(f"\n{'─' * W}")
        if rows_by_mae:
            best_lam, _, best_m, _, best_b = rows_by_mae[0]
            hl = f"{math.log(2)/best_lam:.0f}d" if best_lam > 0 else "∞ (flat)"
            self.stdout.write(
                f"RECOMMENDATION: λ={best_lam:.4f}  (half-life {hl})  "
                f"MAE={best_m:.3f}  bias={best_b:+.3f}"
            )
            cur_lam = 0.0040
            self.stdout.write(
                f"Production λ is {cur_lam:.4f}  (half-life "
                f"{math.log(2)/cur_lam:.0f}d).  "
                f"Change: {best_lam - cur_lam:+.4f}"
            )
        self.stdout.write("")
