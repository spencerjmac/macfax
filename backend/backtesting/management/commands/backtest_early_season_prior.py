"""
Backtest: BPR prior injection vs flat prior — early-season accuracy comparison.

For each season, computes ratings using only games within the first N calendar
days (default 30), then scores those same games under two variants:
  - Prior OFF: flat league-average Bayesian prior (current production behavior)
  - Prior ON:  team-specific BPR projection anchors the prior, fading to flat
               after `prior_decay_games` valid games per team

Decision signal: days 1–10 Brier. If Prior ON < Prior OFF there, adopt.

All computation is in-memory — NO database writes.

Usage:
    python manage.py backtest_early_season_prior
    python manage.py backtest_early_season_prior --seasons 2020 2022 2023 2024 2025 2026
    python manage.py backtest_early_season_prior --seasons 2026 --window-days 45
"""

import math
import statistics
from collections import defaultdict
from datetime import timedelta

from scipy import stats as scipy_stats

from django.core.management.base import BaseCommand

from api.matchup_engine import forecast_game
from ncaa.models import Game, NationalAverages, Team, TeamGameStats, TeamSeasonProjection

# ── Solver constants (match production defaults) ───────────────────────────
CONVERGENCE = 0.001
MAX_ITERATIONS = 150
SHRINKAGE_CEILING = 300
SHRINKAGE_FLOOR = 150
SHRINKAGE_DECAY = 6.25

# Importance weighting constants (always ON, matching production)
IMP_C = 40.0
IMP_FLOOR = 0.35
CLOSE_M = 12.0
BOOST_MAX = 1.40

EPS = 1e-9


# ── Inline ratings solver (no DB writes) ──────────────────────────────────

def _solve_ratings(by_team, stats_lookup, team_ids, nat_avg,
                   proj_ratings, use_prior, prior_decay_games, shrinkage_k):
    """
    Iterative opponent-adjusted ratings solver — no DB writes, in-memory only.

    Returns {team_id: {'aor': float, 'adr': float, 'pace': float}}.
    Importance weighting is always enabled (matches production).
    Recency weighting is disabled (short windows don't benefit from decay).
    """
    ratings = {
        tid: {"aor": nat_avg.avg_ortg, "adr": nat_avg.avg_ortg, "pace": nat_avg.avg_pace}
        for tid in team_ids
    }
    frozen_imp: dict = {}
    imp_scale: dict = {}

    # Adaptive freeze iteration based on training data depth
    all_row_count = sum(len(v) for v in by_team.values())
    avg_gp = all_row_count / max(1, len(team_ids))
    freeze_iter = max(4, min(20, int(avg_gp / 2.0)))

    for iteration in range(1, MAX_ITERATIONS + 1):
        cur_imp: dict = {}
        new_r: dict = {}
        max_change = 0.0

        for tid in team_ids:
            sw_aor = sw_adr = sw_pace = sw = 0.0
            n_valid = 0

            for row in by_team.get(tid, []):
                poss_g = (
                    (row["fga"] or 0)
                    - (row["oreb"] or 0)
                    + (row["tov"] or 0)
                    + 0.44 * (row["fta"] or 0)
                )
                if poss_g <= 0:
                    continue
                opp_id = row["opponent_id"]
                if opp_id not in ratings:
                    continue
                opp_st = stats_lookup.get((row["game_id"], opp_id))
                if not opp_st:
                    continue

                n_valid += 1
                opp_aor = ratings[opp_id]["aor"]
                opp_adr = ratings[opp_id]["adr"]
                opp_pace = ratings[opp_id]["pace"]

                minutes = row["minutes"] or 40
                raw_oe = 100 * row["pts"] / poss_g
                raw_de = 100 * opp_st["pts"] / poss_g
                raw_pace = 40 * poss_g / minutes

                ha = row["home_away"]
                if ha == "H":
                    off_sf, def_sf = 0.9862, 1.0140
                elif ha == "A":
                    off_sf, def_sf = 1.0140, 0.9862
                else:
                    off_sf, def_sf = 1.0, 1.0

                aor_g = raw_oe * (nat_avg.avg_ortg / opp_adr) * off_sf if opp_adr > 0 else raw_oe
                adr_g = raw_de * (nat_avg.avg_ortg / opp_aor) * def_sf if opp_aor > 0 else raw_de
                blend = (opp_pace + nat_avg.avg_pace) / 2
                pace_g = raw_pace * (nat_avg.avg_pace / blend) if blend > 0 else raw_pace

                imp_key = (tid, row["game_id"])
                if iteration <= freeze_iter:
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

                wt = poss_g * w_imp * imp_scale.get(tid, 1.0)
                sw_aor += wt * aor_g
                sw_adr += wt * adr_g
                sw_pace += wt * pace_g
                sw += wt

            # BPR prior blend
            if use_prior and tid in proj_ratings:
                alpha = max(0.0, 1.0 - n_valid / prior_decay_games)
                proj = proj_ratings[tid]
                prior_off = alpha * proj["adj_o"] + (1 - alpha) * nat_avg.avg_ortg
                prior_def = alpha * proj["adj_d"] + (1 - alpha) * nat_avg.avg_ortg
            else:
                prior_off = nat_avg.avg_ortg
                prior_def = nat_avg.avg_ortg

            if sw > 0:
                aor_s = (sw_aor + shrinkage_k * prior_off) / (sw + shrinkage_k)
                adr_s = (sw_adr + shrinkage_k * prior_def) / (sw + shrinkage_k)
                pace_s = (sw_pace + shrinkage_k * nat_avg.avg_pace) / (sw + shrinkage_k)
            else:
                aor_s = prior_off
                adr_s = prior_def
                pace_s = nat_avg.avg_pace

            old_aem = ratings[tid]["aor"] - ratings[tid]["adr"]
            new_aem = aor_s - adr_s
            max_change = max(max_change, abs(new_aem - old_aem))
            new_r[tid] = {"aor": aor_s, "adr": adr_s, "pace": pace_s}

        if iteration == freeze_iter:
            frozen_imp = dict(cur_imp)
            sb: defaultdict = defaultdict(float)
            si: defaultdict = defaultdict(float)
            for rows in by_team.values():
                for row in rows:
                    poss = (
                        (row["fga"] or 0)
                        - (row["oreb"] or 0)
                        + (row["tov"] or 0)
                        + 0.44 * (row["fta"] or 0)
                    )
                    if poss <= 0:
                        continue
                    tid = row["team_id"]
                    wi = frozen_imp.get((tid, row["game_id"]), 1.0)
                    sb[tid] += poss
                    si[tid] += poss * wi
            imp_scale = {
                t: max(0.85, min(1.30, (sb[t] / si[t]) if si[t] > 0 else 1.0))
                for t in sb
            }

        ratings = new_r
        if max_change < CONVERGENCE:
            break

    return ratings


def _auc(ys, probs):
    """ROC AUC from binary labels and predicted probabilities."""
    try:
        from sklearn.metrics import roc_auc_score
        return roc_auc_score(ys, probs)
    except Exception:
        pass
    # Fallback: manual trapezoidal
    pairs = sorted(zip(probs, ys), reverse=True)
    tp = fp = 0
    prev_tp = prev_fp = 0
    auc = 0.0
    for _, y in pairs:
        if y:
            tp += 1
        else:
            fp += 1
    if tp == 0 or fp == 0:
        return float("nan")
    tp = fp = 0
    for _, y in pairs:
        if y:
            tp += 1
        else:
            fp += 1
            auc += tp
    return auc / (tp * fp) if tp * fp > 0 else float("nan")


# ── Management command ─────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "Backtest BPR prior injection vs flat prior on early-season games (days 1–30)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--seasons", type=int, nargs="+",
            default=[2020, 2022, 2023, 2024, 2025, 2026],
            help="Seasons to evaluate (default: 2020 2022 2023 2024 2025 2026)",
        )
        parser.add_argument(
            "--window-days", type=int, default=30,
            help="Calendar days from first game to include (default: 30)",
        )
        parser.add_argument(
            "--prior-decay-games", type=int, default=30,
            help="Games over which BPR prior fades to league average (default: 30)",
        )
        parser.add_argument(
            "--k", type=float, default=None,
            help="Fixed shrinkage k (default: dynamic, same as production)",
        )

    def handle(self, *args, **options):
        seasons = options["seasons"]
        window_days = options["window_days"]
        prior_decay_games = options["prior_decay_games"]
        k_override = options["k"]

        WINDOWS = [("Days 1–10", 1, 10), ("Days 11–20", 11, 20), ("Days 21–30", 21, 30), ("Overall", 1, 9999)]

        # Pooled accumulators: acc[label][window_label] = {'brier':[], 'correct':[], 'y':[], 'prob':[]}
        def _empty():
            return {w: {"brier": [], "correct": [], "y": [], "prob": []} for _, *_ in WINDOWS}

        pooled = {label: {w[0]: {"brier": [], "correct": [], "y": [], "prob": []} for w in WINDOWS}
                  for label in ["ON", "OFF"]}

        self.stdout.write(
            f"\nbacktest_early_season_prior  |  seasons={seasons}  "
            f"window={window_days}d  decay={prior_decay_games} games"
        )

        for season_year in seasons:
            self.stdout.write(f"\n{'─'*60} {season_year} {'─'*20}")

            try:
                nat_avg = NationalAverages.objects.get(season__year=season_year)
            except NationalAverages.DoesNotExist:
                self.stdout.write(f"  WARNING: No NationalAverages for {season_year} — skipping")
                continue

            sigma = nat_avg.prediction_sigma or 11.08
            hca = nat_avg.hca_points or 3.20

            # Load projections
            proj_ratings = {}
            for r in TeamSeasonProjection.objects.filter(
                projected_season_year=season_year,
                projected_adj_o__isnull=False,
                projected_adj_d__isnull=False,
            ).values("team_id", "projected_adj_o", "projected_adj_d"):
                proj_ratings[r["team_id"]] = {
                    "adj_o": r["projected_adj_o"],
                    "adj_d": r["projected_adj_d"],
                }

            if not proj_ratings:
                self.stdout.write(
                    f"  WARNING: No projections for {season_year} — "
                    f"both variants will run as prior OFF"
                )

            # Find season start and cutoff
            first_game = (
                Game.objects.filter(season_year=season_year, status="final")
                .order_by("game_date")
                .values("game_date")
                .first()
            )
            if not first_game:
                self.stdout.write(f"  WARNING: No games for {season_year} — skipping")
                continue

            season_start = first_game["game_date"]
            cutoff_date = season_start + timedelta(days=window_days)

            self.stdout.write(
                f"  Season start: {season_start}  |  cutoff: {cutoff_date}  "
                f"({window_days}d window)  |  {len(proj_ratings)} teams with projections"
            )

            # Bulk-load TeamGameStats for training window
            all_tgs = list(
                TeamGameStats.objects.filter(
                    game__season_year=season_year,
                    game__status="final",
                    game__game_date__lt=cutoff_date,
                    team__is_d1=True,
                    opponent__is_d1=True,
                ).values(
                    "team_id", "opponent_id", "game_id",
                    "fga", "oreb", "tov", "fta", "pts",
                    "home_away", "minutes",
                )
            )

            by_team: defaultdict = defaultdict(list)
            for r in all_tgs:
                by_team[r["team_id"]].append(r)

            stats_lookup = {(r["game_id"], r["team_id"]): r for r in all_tgs}

            n_d1_teams = Team.objects.filter(is_d1=True).count()
            team_ids = list(Team.objects.filter(is_d1=True).values_list("id", flat=True))

            # Dynamic shrinkage k (same formula as production)
            if k_override is not None:
                k = k_override
            else:
                avg_gp = len(all_tgs) / max(1, n_d1_teams)
                k = min(SHRINKAGE_CEILING, max(SHRINKAGE_FLOOR,
                        SHRINKAGE_CEILING - avg_gp * SHRINKAGE_DECAY))

            self.stdout.write(
                f"  {len(all_tgs)} team-game rows  k={k:.1f}  "
                f"σ={sigma:.3f}  hca={hca:.4f}"
            )

            # Run solver twice: prior ON and prior OFF
            ratings_on = _solve_ratings(
                by_team, stats_lookup, team_ids, nat_avg,
                proj_ratings, use_prior=True,
                prior_decay_games=prior_decay_games, shrinkage_k=k,
            )
            ratings_off = _solve_ratings(
                by_team, stats_lookup, team_ids, nat_avg,
                proj_ratings={}, use_prior=False,
                prior_decay_games=prior_decay_games, shrinkage_k=k,
            )

            # Load games to score
            games = list(
                Game.objects.filter(
                    season_year=season_year,
                    status="final",
                    game_date__lt=cutoff_date,
                    home_team__is_d1=True,
                    away_team__is_d1=True,
                    home_score__isnull=False,
                    away_score__isnull=False,
                ).values(
                    "game_date", "home_team_id", "away_team_id",
                    "home_score", "away_score", "neutral_site",
                )
            )

            n_scored_on = n_scored_off = 0
            for g in games:
                days_in = (g["game_date"] - season_start).days + 1

                y = 1.0 if g["home_score"] > g["away_score"] else 0.0
                site = "neutral" if g["neutral_site"] else "home"

                for label, ratings in [("ON", ratings_on), ("OFF", ratings_off)]:
                    home_r = ratings.get(g["home_team_id"])
                    away_r = ratings.get(g["away_team_id"])
                    if not home_r or not away_r:
                        continue

                    try:
                        result = forecast_game(
                            adj_o_a=home_r["aor"],
                            adj_d_a=home_r["adr"],
                            adj_em_a=home_r["aor"] - home_r["adr"],
                            tempo_a=home_r["pace"],
                            adj_o_b=away_r["aor"],
                            adj_d_b=away_r["adr"],
                            adj_em_b=away_r["aor"] - away_r["adr"],
                            tempo_b=away_r["pace"],
                            nat_avg_ortg=nat_avg.avg_ortg,
                            hca_points=hca,
                            sigma=sigma,
                            site=site,
                        )
                    except Exception:
                        continue

                    prob = max(EPS, min(1.0 - EPS, result["prob_a"]))
                    brier = (prob - y) ** 2
                    correct = 1 if (prob >= 0.5) == (y >= 0.5) else 0

                    for wname, wlo, whi in WINDOWS:
                        if wlo <= days_in <= whi:
                            pooled[label][wname]["brier"].append(brier)
                            pooled[label][wname]["correct"].append(correct)
                            pooled[label][wname]["y"].append(y)
                            pooled[label][wname]["prob"].append(prob)

                    if label == "ON":
                        n_scored_on += 1
                    else:
                        n_scored_off += 1

            self.stdout.write(
                f"  Scored: {n_scored_on // len(games) if games else 0} avg games/variant  "
                f"({len(games)} games total)"
            )

        # ── Summary output ─────────────────────────────────────────────────── #
        W = 85
        self.stdout.write(f"\n{'='*W}")
        self.stdout.write(
            f"POOLED RESULTS — {len(seasons)} seasons  "
            f"(window={window_days}d, decay={prior_decay_games} games)"
        )
        self.stdout.write(f"{'='*W}")
        self.stdout.write(
            f"\n  {'Window':<14}  {'Variant':<10}  {'N':>6}  "
            f"{'SU Acc%':>8}  {'Brier':>8}  {'AUC':>8}"
        )
        self.stdout.write("  " + "─" * (W - 2))

        brier_d1_10 = {}
        su_d1_10 = {}

        for wname, wlo, whi in WINDOWS:
            for label in ["ON", "OFF"]:
                d = pooled[label][wname]
                n = len(d["brier"])
                if n == 0:
                    self.stdout.write(
                        f"  {wname:<14}  {f'Prior {label}':<10}  {'—':>6}"
                    )
                    continue
                brier = statistics.fmean(d["brier"])
                su = 100 * statistics.fmean(d["correct"])
                auc = _auc(d["y"], d["prob"])
                auc_str = f"{auc:.4f}" if not math.isnan(auc) else "  —  "
                self.stdout.write(
                    f"  {wname:<14}  {f'Prior {label}':<10}  {n:>6}  "
                    f"{su:>7.1f}%  {brier:>8.4f}  {auc_str:>8}"
                )
                if wname == "Days 1–10":
                    brier_d1_10[label] = brier
                    su_d1_10[label] = su
            self.stdout.write("")

        # ── Delta table ────────────────────────────────────────────────────── #
        self.stdout.write(f"\n  {'Window':<14}  {'ΔBrier (ON−OFF)':>18}  {'ΔSU% (ON−OFF)':>16}  {'Signal'}")
        self.stdout.write("  " + "─" * 60)
        for wname, wlo, whi in WINDOWS:
            on_b = pooled["ON"][wname]["brier"]
            off_b = pooled["OFF"][wname]["brier"]
            on_s = pooled["ON"][wname]["correct"]
            off_s = pooled["OFF"][wname]["correct"]
            if not on_b or not off_b:
                continue
            db = statistics.fmean(on_b) - statistics.fmean(off_b)
            ds = 100 * (statistics.fmean(on_s) - statistics.fmean(off_s))
            sig = "✓ Prior ON better" if db < -0.0001 else ("= tie" if abs(db) <= 0.0001 else "✗ Prior OFF better")
            self.stdout.write(
                f"  {wname:<14}  {db:>+18.4f}  {ds:>+15.1f}%  {sig}"
            )

        # ── Verdict ────────────────────────────────────────────────────────── #
        self.stdout.write(f"\n{'─'*W}")
        if "ON" in brier_d1_10 and "OFF" in brier_d1_10:
            b_on = brier_d1_10["ON"]
            b_off = brier_d1_10["OFF"]
            s_on = su_d1_10["ON"]
            s_off = su_d1_10["OFF"]
            brier_verdict = "wins" if b_on < b_off - 0.0001 else ("ties" if abs(b_on - b_off) <= 0.0001 else "loses")
            su_verdict = "wins" if s_on > s_off + 0.05 else ("ties" if abs(s_on - s_off) <= 0.05 else "loses")
            self.stdout.write(
                f"VERDICT (days 1–10):  "
                f"Prior ON {brier_verdict} on Brier ({b_on:.4f} vs {b_off:.4f})  |  "
                f"Prior ON {su_verdict} on SU Acc ({s_on:.1f}% vs {s_off:.1f}%)"
            )
            if brier_verdict == "wins":
                self.stdout.write("ADOPT: Prior ON improves days 1–10 Brier. Run pipeline with --use-bpr-prior.")
            else:
                self.stdout.write("SKIP: Prior ON does not improve days 1–10 Brier. Keep flat prior.")
        else:
            self.stdout.write("VERDICT: Insufficient data.")
        self.stdout.write("")
