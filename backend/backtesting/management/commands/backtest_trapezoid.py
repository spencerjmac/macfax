"""
Backtest: evaluate Trapezoid of Excellence boundary configs against historical
tournament outcomes, 2005-2026 (skip 2020, no tournament).

Default mode runs the current trapezoid_config (backend/api/trapezoid_config.py)
across every season, reports champion capture / selectivity / margin-vs-depth
correlation, and writes a per-team CSV.

--sweep grid-searches PACE_PAD, Q_BOT_EM, Q_X_LEFT_BOT, Q_X_RIGHT_BOT for the
config that best captures real champions / deep tournament runs without
ballooning the "inside" set.

Usage:
    python manage.py backtest_trapezoid
    python manage.py backtest_trapezoid --sweep
"""

import csv
import itertools
import os

import numpy as np
from scipy import stats as scipy_stats

from django.conf import settings
from django.core.management.base import BaseCommand

from ncaa.models import Season, TeamSeasonRatings
from api.trapezoid_views import calculate_quantile, is_inside_trapezoid, trapezoid_margin
from api import trapezoid_config as cfg

SEASONS = [y for y in range(2005, 2027) if y != 2020]

# Champions the trapezoid currently misses by a small margin.
TARGET_CHAMPS = [
    (2026, "Michigan"),
    (2019, "Virginia"),
    (2009, "North Carolina"),
    (2005, "North Carolina"),
]

# The established "UConn rule" outliers - OK to keep excluding.
UCONN_OUTLIERS = [
    (2014, "Connecticut"),
    (2011, "Connecticut"),
]

DEPTH_SCORE = {
    "Champ": 6,
    "Runner-Up": 5,
    "Final Four": 4,
    "Elite Eight": 3,
    "Sweet 16": 2,
    "Round of 32": 1,
    "Round of 64": 0,
    "First Four": 0,
}

OUTPUT_DIR = os.path.join(settings.BASE_DIR, "backtest_output")


def load_season_data():
    data_by_season = {}
    for year in SEASONS:
        season = Season.objects.filter(year=year).first()
        if not season:
            continue
        rows = list(
            TeamSeasonRatings.all_objects.filter(
                season=season,
                team__is_d1=True,
                games_played__gt=0,
                is_pre_tournament=True,
            ).values("adj_tempo", "adj_em", "team__name", "tournament_finish")
        )
        data_by_season[year] = rows
    return data_by_season


def compute_boundaries(tempo_values, em_values, pace_pad, q_bot_em, q_left, q_right,
                        y_pad_min=cfg.Y_PAD_MIN, y_pad_rate=cfg.Y_PAD_RATE):
    """Mirrors compute_trapezoid_boundaries() with parametrized quantiles/padding."""
    y_bot = calculate_quantile(em_values, q_bot_em, cfg.QUANTILE_METHOD)
    y_max = float(np.max(em_values))
    y_pad = max(y_pad_min, y_pad_rate * (y_max - y_bot))
    y_top = y_max + y_pad

    elite_mask = em_values >= y_bot
    elite_tempo = tempo_values[elite_mask]
    if len(elite_tempo) < 10:
        elite_tempo = tempo_values

    x_left_top = float(np.min(elite_tempo)) - pace_pad
    x_right_top = float(np.max(elite_tempo)) + pace_pad
    x_left_bot = calculate_quantile(elite_tempo, q_left, cfg.QUANTILE_METHOD)
    x_right_bot = calculate_quantile(elite_tempo, q_right, cfg.QUANTILE_METHOD)

    if not (x_left_top < x_left_bot < x_right_bot < x_right_top):
        x_left_top = float(np.min(tempo_values)) - pace_pad
        x_right_top = float(np.max(tempo_values)) + pace_pad
        x_left_bot = calculate_quantile(tempo_values, q_left, cfg.QUANTILE_METHOD)
        x_right_bot = calculate_quantile(tempo_values, q_right, cfg.QUANTILE_METHOD)

    return {
        "x_left_top": x_left_top,
        "x_right_top": x_right_top,
        "x_left_bot": x_left_bot,
        "x_right_bot": x_right_bot,
        "y_top": y_top,
        "y_bot": y_bot,
    }


def vectorized_inside_and_margin(tempo, em, trap):
    """Vectorized version of is_inside_trapezoid()/trapezoid_margin() for sweeps."""
    x_left_top = trap["x_left_top"]
    x_right_top = trap["x_right_top"]
    x_left_bot = trap["x_left_bot"]
    x_right_bot = trap["x_right_bot"]
    y_top = trap["y_top"]
    y_bot = trap["y_bot"]

    left_slope = (y_bot - y_top) / (x_left_bot - x_left_top) if x_left_bot != x_left_top else 0.0
    right_slope = (y_top - y_bot) / (x_right_top - x_right_bot) if x_right_top != x_right_bot else 0.0

    y_min_left = y_top + left_slope * (tempo - x_left_top)
    y_min_right = y_bot + right_slope * (tempo - x_right_bot)

    y_min = np.where(tempo <= x_left_bot, y_min_left,
                      np.where(tempo < x_right_bot, y_bot, y_min_right))

    margin = em - y_min
    in_x_range = (tempo >= x_left_top) & (tempo <= x_right_top)
    inside = in_x_range & (em <= y_top) & (margin >= 0)
    margin = np.where(in_x_range, margin, np.nan)
    return inside, margin


def evaluate_config(data_by_season, pace_pad, q_bot_em, q_left, q_right):
    """
    Run one config across all seasons. Returns:
      - rows: list of dicts (season, team, tournament_finish, adj_tempo, adj_em, inside, margin)
      - summary: dict of aggregate metrics
    """
    rows = []
    inside_counts = []
    for year, data in data_by_season.items():
        tempo = np.array([d["adj_tempo"] for d in data])
        em = np.array([d["adj_em"] for d in data])
        trap = compute_boundaries(tempo, em, pace_pad, q_bot_em, q_left, q_right)
        inside, margin = vectorized_inside_and_margin(tempo, em, trap)
        inside_counts.append(int(inside.sum()))
        for d, ins, mar in zip(data, inside, margin):
            rows.append({
                "season": year,
                "team": d["team__name"],
                "tournament_finish": d["tournament_finish"] or "",
                "adj_tempo": d["adj_tempo"],
                "adj_em": d["adj_em"],
                "inside": bool(ins),
                "margin": None if np.isnan(mar) else float(mar),
            })

    lookup = {(r["season"], r["team"]): r for r in rows}

    champ_capture = sum(1 for (y, name) in TARGET_CHAMPS if lookup[(y, name)]["inside"])
    uconn_excluded = all(not lookup[(y, name)]["inside"] for (y, name) in UCONN_OUTLIERS)

    bucket_capture = {}
    for bucket in ("Champ", "Runner-Up", "Final Four", "Elite Eight"):
        bucket_rows = [r for r in rows if r["tournament_finish"] == bucket]
        if bucket_rows:
            bucket_capture[bucket] = sum(1 for r in bucket_rows if r["inside"]) / len(bucket_rows)
        else:
            bucket_capture[bucket] = None

    margins = np.array([r["margin"] for r in rows if r["margin"] is not None])
    depths = np.array([
        DEPTH_SCORE.get(r["tournament_finish"], 0)
        for r in rows if r["margin"] is not None
    ])
    if len(margins) > 1 and np.std(margins) > 0 and np.std(depths) > 0:
        depth_corr = float(scipy_stats.spearmanr(margins, depths).correlation)
    else:
        depth_corr = float("nan")

    summary = {
        "champ_capture_excl_uconn": champ_capture,
        "uconn_excluded": uconn_excluded,
        "avg_inside_per_season": float(np.mean(inside_counts)),
        "bucket_capture": bucket_capture,
        "depth_corr": depth_corr,
    }
    return rows, summary


class Command(BaseCommand):
    help = "Backtest the Trapezoid of Excellence boundary against historical tournament outcomes"

    def add_arguments(self, parser):
        parser.add_argument(
            "--sweep", action="store_true",
            help="Grid-search PACE_PAD / Q_BOT_EM / Q_X_LEFT_BOT / Q_X_RIGHT_BOT",
        )

    def handle(self, *args, **options):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        self.stdout.write("Loading season data (2005-2026, skip 2020)...")
        data_by_season = load_season_data()

        if options["sweep"]:
            self._run_sweep(data_by_season)
        else:
            self._run_default(data_by_season)

    # ------------------------------------------------------------------ #

    def _run_default(self, data_by_season):
        rows, summary = evaluate_config(
            data_by_season, cfg.PACE_PAD, cfg.Q_BOT_EM, cfg.Q_X_LEFT_BOT, cfg.Q_X_RIGHT_BOT,
        )

        out_path = os.path.join(OUTPUT_DIR, "trapezoid_backtest.csv")
        with open(out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "season", "team", "tournament_finish", "adj_tempo", "adj_em", "inside", "margin",
            ])
            writer.writeheader()
            writer.writerows(rows)
        self.stdout.write(f"Wrote {len(rows)} rows to {out_path}")

        lookup = {(r["season"], r["team"]): r for r in rows}

        self.stdout.write(
            f"\nCurrent config: PACE_PAD={cfg.PACE_PAD}, Q_BOT_EM={cfg.Q_BOT_EM}, "
            f"Q_X_LEFT_BOT={cfg.Q_X_LEFT_BOT}, Q_X_RIGHT_BOT={cfg.Q_X_RIGHT_BOT}\n"
        )

        self.stdout.write("Champion check:")
        self.stdout.write(f"{'Year':<6}{'Team':<18}{'Tempo':<8}{'EM':<8}{'Inside':<8}{'Margin'}")
        for year, name in TARGET_CHAMPS + UCONN_OUTLIERS:
            r = lookup[(year, name)]
            self.stdout.write(
                f"{year:<6}{name:<18}{r['adj_tempo']:<8.2f}{r['adj_em']:<8.2f}"
                f"{str(r['inside']):<8}{r['margin']:+.2f}"
            )

        self.stdout.write(f"\nChampions captured (excl. UConn rule): {summary['champ_capture_excl_uconn']}/4")
        self.stdout.write(f"UConn 2011 & 2014 still excluded: {summary['uconn_excluded']}")

        self.stdout.write("\nCapture rate by tournament finish:")
        for bucket, rate in summary["bucket_capture"].items():
            rate_str = f"{rate:.1%}" if rate is not None else "N/A"
            self.stdout.write(f"  {bucket:<12}: {rate_str}")

        self.stdout.write(f"\nAvg 'inside' teams per season: {summary['avg_inside_per_season']:.2f}")
        self.stdout.write(f"Spearman corr(margin, tournament depth): {summary['depth_corr']:.3f}")

    # ------------------------------------------------------------------ #

    def _run_sweep(self, data_by_season):
        pace_pad_grid = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5]
        q_bot_em_grid = [0.94, 0.945, 0.95, 0.955, 0.96, 0.965, 0.97]
        q_left_grid = [0.10, 0.15, 0.20, 0.25, 0.30]
        q_right_grid = [0.70, 0.75, 0.80, 0.85, 0.90]

        # Baseline = current production config
        _, baseline_summary = evaluate_config(
            data_by_season, cfg.PACE_PAD, cfg.Q_BOT_EM, cfg.Q_X_LEFT_BOT, cfg.Q_X_RIGHT_BOT,
        )
        baseline_avg_inside = baseline_summary["avg_inside_per_season"]

        self.stdout.write(
            f"Baseline (current config): champs={baseline_summary['champ_capture_excl_uconn']}/4, "
            f"uconn_excluded={baseline_summary['uconn_excluded']}, "
            f"avg_inside={baseline_avg_inside:.2f}, depth_corr={baseline_summary['depth_corr']:.3f}\n"
        )

        combos = list(itertools.product(pace_pad_grid, q_bot_em_grid, q_left_grid, q_right_grid))
        self.stdout.write(f"Evaluating {len(combos)} configs...")

        results = []
        for pace_pad, q_bot_em, q_left, q_right in combos:
            if not (q_left < q_right):
                continue
            _, summary = evaluate_config(data_by_season, pace_pad, q_bot_em, q_left, q_right)
            results.append({
                "pace_pad": pace_pad,
                "q_bot_em": q_bot_em,
                "q_x_left_bot": q_left,
                "q_x_right_bot": q_right,
                "champ_capture_excl_uconn": summary["champ_capture_excl_uconn"],
                "uconn_excluded": summary["uconn_excluded"],
                "avg_inside_per_season": summary["avg_inside_per_season"],
                "inside_growth": summary["avg_inside_per_season"] - baseline_avg_inside,
                "depth_corr": summary["depth_corr"],
            })

        out_path = os.path.join(OUTPUT_DIR, "trapezoid_sweep.csv")
        with open(out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
            writer.writeheader()
            writer.writerows(results)
        self.stdout.write(f"Wrote {len(results)} configs to {out_path}\n")

        # Rank: champ capture desc -> uconn_excluded desc -> inside_growth asc -> depth_corr desc
        results.sort(key=lambda r: (
            -r["champ_capture_excl_uconn"],
            0 if r["uconn_excluded"] else 1,
            r["inside_growth"],
            -r["depth_corr"],
        ))

        self.stdout.write("Top 10 configs:")
        header = (
            f"{'PACE_PAD':<10}{'Q_BOT_EM':<10}{'Q_LEFT':<8}{'Q_RIGHT':<8}"
            f"{'Champs':<8}{'UConnExcl':<11}{'AvgInside':<11}{'Growth':<9}{'DepthCorr'}"
        )
        self.stdout.write(header)
        for r in results[:10]:
            self.stdout.write(
                f"{r['pace_pad']:<10}{r['q_bot_em']:<10}{r['q_x_left_bot']:<8}{r['q_x_right_bot']:<8}"
                f"{r['champ_capture_excl_uconn']:<8}{str(r['uconn_excluded']):<11}"
                f"{r['avg_inside_per_season']:<11.2f}{r['inside_growth']:<+9.2f}{r['depth_corr']:.3f}"
            )
