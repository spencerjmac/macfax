"""
nba_forward_backtest — leakage-safe forward projection backtest.

Tests the full pipeline from compute_nba_team_outlooks.py on historical data:
  source_season N data → project → compare to actual N+1 adj_em

All pipeline inputs are from source season only. Target-season ratings are loaded
AFTER all projections are computed and used only to compute errors.

Outputs (no DB writes):
  - Per-season pair + pooled accuracy metrics (pipeline vs. persistence baseline)
  - OLS-fitted forward SLOPE  → replacement for SLOPE=0.84 in compute_nba_team_outlooks.py
  - OLS blend weights         → feeds persistence+roster hybrid decision
  - Forward RMSE              → recommended SIGMA_EM replacement
  - Per-team residuals CSV

Usage:
  python manage.py nba_forward_backtest --source-season 2024
  python manage.py nba_forward_backtest --source-season 2025
  python manage.py nba_forward_backtest --all
  python manage.py nba_forward_backtest --all --no-csv
"""

import csv
import logging
import math
import os
from dataclasses import dataclass
from typing import Optional

import numpy as np
import scipy.stats

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Avg

from nba.models import (
    NBASeason,
    NBATeam,
    NBAPlayerSeasonStats,
    NBATeamSeasonRatings,
)

logger = logging.getLogger(__name__)

# ── Pipeline constants — must match compute_nba_team_outlooks.py ──────────────
REPLACEMENT_LEVEL   = 2.0
SHRINKAGE_RETURNER  = 0.10   # all source-season players treated as returners
MINUTES_FLOOR       = 0.02
MINUTES_CEIL        = 1.20
POWER_EXPONENT      = 2.0
TOTAL_SHARES        = 5.0
PRODUCTION_SLOPE    = 0.84   # current value being tested

DEFAULT_OUTPUT_DIR = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..", "..",
        "analytics", "backtest_results",
    )
)

def _detect_available_source_years() -> list[int]:
    """
    Auto-detect every source year with BPR data whose following season has
    team ratings (replaces the old hard-coded [2024, 2025] pair list).
    """
    years_with_bpr = set(
        NBAPlayerSeasonStats.objects.filter(
            bpr__isnull=False, season_type="regular",
        ).values_list("season__year", flat=True).distinct()
    )
    years_with_ratings = set(
        NBATeamSeasonRatings.objects.values_list(
            "season__year", flat=True).distinct()
    )
    return sorted(y for y in years_with_bpr if (y + 1) in years_with_ratings)


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class TeamResult:
    team_id: int
    team_abbr: str
    source_adj_em: float
    bpr_aggregate_off: float   # Σ(share × proj_obpr)
    bpr_aggregate_def: float   # Σ(share × proj_dbpr)
    bpr_combined_signal: float # (base_off − lb_off) + (base_def − lb_def)  ← OLS input
    proj_adj_em: float         # at PRODUCTION_SLOPE
    n_players: int
    actual_adj_em: Optional[float] = None  # loaded after projection — never used as input


@dataclass
class Metrics:
    n: int
    rmse: float
    mae: float
    bias: float
    pearson_r: float
    spearman_rho: float


# ── Pure pipeline functions (no Django ORM, no side-effects) ──────────────────

def _project_bpr(bpr, obpr, dbpr, league_obpr, league_dbpr, league_bpr):
    lam = SHRINKAGE_RETURNER
    return (
        obpr * (1 - lam) + league_obpr * lam,
        dbpr * (1 - lam) + league_dbpr * lam,
        bpr  * (1 - lam) + league_bpr  * lam,
    )


def _water_fill(shares, target=TOTAL_SHARES, max_iter=25):
    shares = list(shares)
    for _ in range(max_iter):
        total = sum(shares)
        if abs(total - target) < 1e-6:
            break
        delta = (target - total) / len(shares)
        shares = [max(MINUTES_FLOOR, min(MINUTES_CEIL, s + delta)) for s in shares]
    return shares


def _allocate_minutes(players):
    demands = [
        max(0.0, (p["proj_bpr"] or 0.0) + REPLACEMENT_LEVEL) + (p["mpg"] or 15.0) / 36.0
        for p in players
    ]
    powered = [d ** POWER_EXPONENT for d in demands]
    total = sum(powered) or 1.0
    raw = [v / total * TOTAL_SHARES for v in powered]
    clamped = [max(MINUTES_FLOOR, min(MINUTES_CEIL, s)) for s in raw]
    normalized = _water_fill(clamped)
    for p, share in zip(players, normalized):
        p["minutes_share"] = share
    return players


def _compute_metrics(preds, actuals):
    n = len(preds)
    errors = [p - a for p, a in zip(preds, actuals)]
    rmse = math.sqrt(sum(e ** 2 for e in errors) / n)
    mae  = sum(abs(e) for e in errors) / n
    bias = sum(errors) / n
    r, _   = scipy.stats.pearsonr(preds, actuals)
    rho, _ = scipy.stats.spearmanr(preds, actuals)
    return Metrics(n=n, rmse=rmse, mae=mae, bias=bias, pearson_r=float(r), spearman_rho=float(rho))


def _ols(X_rows, y):
    """OLS via numpy least squares. Returns (coefficients, R²)."""
    X = np.array(X_rows, dtype=float)
    y = np.array(y, dtype=float)
    coeffs, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    y_hat = X @ coeffs
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return coeffs, r2


# ── Management command ────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "Leakage-safe forward projection backtest for the NBA team outlook pipeline."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-season", type=int, dest="source_year", metavar="YEAR",
            help="Source season ending year (2024 = 2023-24 source → 2024-25 target).",
        )
        parser.add_argument(
            "--all", action="store_true",
            help="Run all available season pairs and pool results.",
        )
        parser.add_argument(
            "--min-mpg", type=float, default=5.0, metavar="MPG",
            help="Minimum MPG to qualify a player (default 5.0 — matches production pipeline).",
        )
        parser.add_argument(
            "--min-gp", type=int, default=10, metavar="GP",
            help="Minimum games played to qualify a player (default 10).",
        )
        parser.add_argument(
            "--output-dir", type=str, default=DEFAULT_OUTPUT_DIR, metavar="PATH",
            help="Directory for per-team residuals CSVs.",
        )
        parser.add_argument(
            "--no-csv", action="store_true",
            help="Print results to stdout only; do not write CSV files.",
        )

    def handle(self, *args, **options):
        source_year = options.get("source_year")
        run_all     = options["all"]
        min_mpg     = options["min_mpg"]
        min_gp      = options["min_gp"]
        output_dir  = options["output_dir"]
        no_csv      = options["no_csv"]

        if not source_year and not run_all:
            raise CommandError("Specify --source-season YEAR or --all.")

        if run_all:
            source_years = [
                yr for yr in _detect_available_source_years()
                if self._pair_available(yr)
            ]
            if not source_years:
                raise CommandError("No complete season pairs found in DB.")
        else:
            source_years = [source_year]

        self.stdout.write(f"\n{'='*62}")
        self.stdout.write("NBA Forward Projection Backtest")
        self.stdout.write(f"Testing PRODUCTION_SLOPE={PRODUCTION_SLOPE}")
        self.stdout.write(f"Season pairs: {[f'{y}->{y+1}' for y in source_years]}")
        self.stdout.write(
            "NOTE: source-season BPR embeds the source season's own LEBRON prior — "
            "legitimate for this forward test (all inputs predate the target season). "
            "Never reuse these ratings for within-season claims (weakness report 3.6)."
        )
        self.stdout.write(f"{'='*62}")

        all_results = []

        for src_yr in source_years:
            tgt_yr = src_yr + 1
            results = self._run_pair(src_yr, tgt_yr, min_mpg, min_gp)
            if not results:
                self.stderr.write(f"  No evaluable teams for {src_yr}→{tgt_yr} — skip")
                continue
            self._print_pair(src_yr, tgt_yr, results)
            self._print_player_stability(src_yr, tgt_yr)
            if not no_csv:
                self._write_csv(results, src_yr, tgt_yr, output_dir)
            all_results.extend(results)

        if len(source_years) > 1 and len(all_results) >= 10:
            self.stdout.write(f"\n{'='*62}")
            self.stdout.write(f"=== POOLED ({len(all_results)} team-seasons) ===")
            self.stdout.write(f"{'='*62}")
            self._print_summary(all_results, pooled=True)

    # ── Season pair runner ─────────────────────────────────────────────────────

    def _run_pair(self, source_year, target_year, min_mpg, min_gp):
        self.stdout.write(f"\n--- {source_year}→{target_year} ---")

        try:
            source_season = NBASeason.objects.get(year=source_year)
            target_season = NBASeason.objects.get(year=target_year)
        except NBASeason.DoesNotExist as exc:
            self.stderr.write(f"  Season not found: {exc}")
            return []

        # ── Source: league-average ratings (adj_o, adj_d) ─────────────────────
        src_ratings = list(NBATeamSeasonRatings.objects.filter(season=source_season))
        if not src_ratings:
            self.stderr.write(f"  No NBATeamSeasonRatings for {source_year}")
            return []

        agg = NBATeamSeasonRatings.objects.filter(season=source_season).aggregate(
            avg_off=Avg("adj_off"), avg_def=Avg("adj_def")
        )
        nba_avg_adj_o = agg["avg_off"] or 115.0
        nba_avg_adj_d = agg["avg_def"] or 115.0

        source_adj_em_by_team = {
            r.team_id: float(r.adj_off - r.adj_def)
            for r in src_ratings
            if r.adj_off is not None and r.adj_def is not None
        }

        # ── Source: BPR league averages (shrinkage targets) ───────────────────
        bpr_qs = NBAPlayerSeasonStats.objects.filter(
            season=source_season, season_type="regular", mpg__gte=min_mpg,
        )
        league_obpr = bpr_qs.filter(obpr__isnull=False).aggregate(v=Avg("obpr"))["v"] or 0.0
        league_dbpr = bpr_qs.filter(dbpr__isnull=False).aggregate(v=Avg("dbpr"))["v"] or 0.0
        league_bpr  = bpr_qs.filter(bpr__isnull=False).aggregate(v=Avg("bpr"))["v"] or 0.0

        # ── Source: per-player data, grouped by team ───────────────────────────
        player_qs = NBAPlayerSeasonStats.objects.filter(
            season=source_season,
            season_type="regular",
            mpg__gte=min_mpg,
            gp__gte=min_gp,
            bpr__isnull=False,
        ).only("team_id", "mpg", "gp", "obpr", "dbpr", "bpr", "box_obpr", "box_dbpr")

        team_players: dict[int, list[dict]] = {}
        for row in player_qs:
            if row.team_id is None or row.team_id not in source_adj_em_by_team:
                continue
            team_players.setdefault(row.team_id, []).append({
                "mpg":     row.mpg  or 15.0,
                "obpr":    row.obpr or 0.0,
                "dbpr":    row.dbpr or 0.0,
                "bpr":     row.bpr  or 0.0,
                "box_obpr": float(row.box_obpr) if row.box_obpr is not None else None,
                "box_dbpr": float(row.box_dbpr) if row.box_dbpr is not None else None,
            })

        # ── RAPM-gap σ for inflation cap (mirrors compute command) ────────────
        import statistics as _stats
        gap_qs = NBAPlayerSeasonStats.objects.filter(
            season=source_season, season_type="regular",
            gp__gte=20, mpg__gte=12,
            bpr__isnull=False, box_obpr__isnull=False, box_dbpr__isnull=False,
        ).only("bpr", "box_obpr", "box_dbpr")
        gaps = [float(r.bpr) - (float(r.box_obpr) + float(r.box_dbpr)) for r in gap_qs]
        rapm_gap_sigma = _stats.stdev(gaps) if len(gaps) >= 20 else 3.5
        cap_threshold = 1.6 * rapm_gap_sigma
        self.stdout.write(f"  RAPM-gap σ={rapm_gap_sigma:.2f}  cap={cap_threshold:.2f}  ({len(gaps)} qualifying players)")

        # ── Pass 1: project BPR + allocate minutes ────────────────────────────
        team_data: dict[int, list[dict]] = {}
        for team_id, players in team_players.items():
            for p in players:
                p["proj_obpr"], p["proj_dbpr"], p["proj_bpr"] = _project_bpr(
                    p["bpr"], p["obpr"], p["dbpr"], league_obpr, league_dbpr, league_bpr
                )
                # RAPM-inflation cap (asymmetric: only positive gaps)
                box_obpr = p["box_obpr"]
                box_dbpr = p["box_dbpr"]
                if box_obpr is not None and box_dbpr is not None:
                    box_bpr = box_obpr + box_dbpr
                    rapm_gap = p["proj_bpr"] - box_bpr
                    if rapm_gap > cap_threshold:
                        excess = rapm_gap - cap_threshold
                        p["proj_bpr"] -= excess
                        if abs(rapm_gap) > 0:
                            p["proj_obpr"] -= excess * (p["proj_obpr"] - box_obpr) / rapm_gap
                            p["proj_dbpr"] -= excess * (p["proj_dbpr"] - box_dbpr) / rapm_gap
            _allocate_minutes(players)
            team_data[team_id] = players

        # ── Compute league baselines (two-pass — matches production) ──────────
        all_base_off = [
            sum(p["minutes_share"] * p["proj_obpr"] for p in players)
            for players in team_data.values()
        ]
        all_base_def = [
            sum(p["minutes_share"] * p["proj_dbpr"] for p in players)
            for players in team_data.values()
        ]
        league_base_off = sum(all_base_off) / len(all_base_off) if all_base_off else 0.0
        league_base_def = sum(all_base_def) / len(all_base_def) if all_base_def else 0.0

        # ── Pass 2: project team ratings ──────────────────────────────────────
        team_abbrs = {t.pk: t.abbreviation for t in NBATeam.objects.only("id", "abbreviation")}

        projections: list[TeamResult] = []
        for team_id, players in team_data.items():
            base_off = sum(p["minutes_share"] * p["proj_obpr"] for p in players)
            base_def = sum(p["minutes_share"] * p["proj_dbpr"] for p in players)

            excess_off = base_off - league_base_off
            excess_def = base_def - league_base_def

            proj_adj_o  = nba_avg_adj_o + PRODUCTION_SLOPE * excess_off
            proj_adj_d  = nba_avg_adj_d - PRODUCTION_SLOPE * excess_def
            proj_adj_em = proj_adj_o - proj_adj_d

            projections.append(TeamResult(
                team_id=team_id,
                team_abbr=team_abbrs.get(team_id, "???"),
                source_adj_em=source_adj_em_by_team[team_id],
                bpr_aggregate_off=base_off,
                bpr_aggregate_def=base_def,
                bpr_combined_signal=excess_off + excess_def,
                proj_adj_em=proj_adj_em,
                n_players=len(players),
            ))

        # ── Load holdout: target-season adj_em ───────────────────────────────
        # Loaded AFTER all projections are computed — leakage guard.
        target_adj_em = {
            r.team_id: float(r.adj_off - r.adj_def)
            for r in NBATeamSeasonRatings.objects.filter(season=target_season)
            if r.adj_off is not None and r.adj_def is not None
        }

        matched = []
        for proj in projections:
            if proj.team_id in target_adj_em:
                proj.actual_adj_em = target_adj_em[proj.team_id]
                matched.append(proj)

        self.stdout.write(
            f"  {len(matched)} teams | "
            f"avg n_players={sum(p.n_players for p in matched)/max(len(matched),1):.1f} | "
            f"lg_base off={league_base_off:.2f} def={league_base_def:.2f}"
        )
        return matched

    # ── Player-level YoY stability ─────────────────────────────────────────────

    MINUTE_BUCKETS = [(0, 1200), (1200, 2000), (2000, 10 ** 9)]

    def _print_player_stability(self, src_yr: int, tgt_yr: int) -> None:
        """
        BPR(Y) vs BPR(Y+1) Pearson/Spearman for returning players, overall and
        by total-minutes bucket. Player-level validation companion to the
        team-level forward metrics.
        """
        rows = {}
        for yr in (src_yr, tgt_yr):
            for r in NBAPlayerSeasonStats.objects.filter(
                season__year=yr, season_type="regular",
                bpr__isnull=False, mpg__gte=12.0, gp__gte=20,
            ).values("player_id", "bpr", "mpg", "gp"):
                rows.setdefault(yr, {})[r["player_id"]] = {
                    "bpr": float(r["bpr"]),
                    "minutes": (r["mpg"] or 0.0) * (r["gp"] or 0),
                }
        cur, nxt = rows.get(src_yr, {}), rows.get(tgt_yr, {})
        common = sorted(set(cur) & set(nxt))
        if len(common) < 30:
            self.stdout.write("  Player stability: insufficient overlap — skipped")
            return

        self.stdout.write(f"\n  Player YoY stability (BPR {src_yr} → {tgt_yr}):")
        a = [cur[p]["bpr"] for p in common]
        b = [nxt[p]["bpr"] for p in common]
        r, _ = scipy.stats.pearsonr(a, b)
        rho, _ = scipy.stats.spearmanr(a, b)
        self.stdout.write(f"    all (n={len(common)}):  r={r:.3f}  rho={rho:.3f}")
        for lo, hi in self.MINUTE_BUCKETS:
            sel = [p for p in common if lo <= cur[p]["minutes"] < hi]
            if len(sel) < 20:
                continue
            a = [cur[p]["bpr"] for p in sel]
            b = [nxt[p]["bpr"] for p in sel]
            r, _ = scipy.stats.pearsonr(a, b)
            label = f"{lo}-{hi if hi < 10**9 else '+'} min"
            self.stdout.write(f"    {label:14s} (n={len(sel)}):  r={r:.3f}")

    # ── Printing ───────────────────────────────────────────────────────────────

    def _print_pair(self, source_year, target_year, results):
        self.stdout.write(f"\n  Season {source_year}→{target_year}  (n={len(results)})")
        self._print_summary(results, pooled=False)

    def _print_summary(self, results, pooled=False):
        preds_pipe    = [r.proj_adj_em    for r in results]
        preds_persist = [r.source_adj_em  for r in results]
        actuals       = [r.actual_adj_em  for r in results]

        m_pipe    = _compute_metrics(preds_pipe, actuals)
        m_persist = _compute_metrics(preds_persist, actuals)

        self.stdout.write(
            f"  {'Model':<12} {'RMSE':>6} {'MAE':>6} {'Bias':>6} {'r':>6} {'ρ':>6}"
        )
        self.stdout.write("  " + "─" * 50)
        self._fmt_metrics("Pipeline", m_pipe)
        self._fmt_metrics("Persist", m_persist)

        # OLS fits
        signals = [r.bpr_combined_signal for r in results]
        src_em  = [r.source_adj_em       for r in results]

        (c0, c1), r2_simple = _ols([[1, s] for s in signals], actuals)
        (b0, b1, b2), r2_blend = _ols([[1, s, se] for s, se in zip(signals, src_em)], actuals)

        self.stdout.write("")
        self.stdout.write(
            f"  OLS simple:  adj_em = {c0:+.2f} + {c1:.3f}·bpr_signal  "
            f"(R²={r2_simple:.3f})"
        )
        self.stdout.write(
            f"  OLS blend:   adj_em = {b0:+.2f} + {b1:.3f}·bpr_signal + {b2:.3f}·prior_adj_em  "
            f"(R²={r2_blend:.3f})"
        )

        if pooled:
            self.stdout.write("")
            self.stdout.write(f"  ╔══ CALIBRATION RECOMMENDATIONS ══════════════════════╗")
            self.stdout.write(f"  ║  SLOPE  (was {PRODUCTION_SLOPE:.2f})  → {c1:.3f}  (OLS forward)")
            self.stdout.write(f"  ║  SIGMA_EM (was 4.0)  → {m_pipe.rmse:.2f}  (pipeline forward RMSE)")
            blend_note = (
                "→ add persistence term" if b2 > b1 * 2 else "→ BPR signal dominant"
            )
            self.stdout.write(
                f"  ║  Blend: bpr={b1:.3f}  prior={b2:.3f}  {blend_note}"
            )
            self.stdout.write(f"  ╚══════════════════════════════════════════════════════╝")

        # Worst residuals
        self._print_residuals(results)

    def _fmt_metrics(self, label, m: Metrics):
        self.stdout.write(
            f"  {label:<12} {m.rmse:>6.2f} {m.mae:>6.2f} {m.bias:>+6.2f} "
            f"{m.pearson_r:>6.3f} {m.spearman_rho:>6.3f}"
        )

    def _print_residuals(self, results):
        preds  = [r.proj_adj_em   for r in results]
        actual = [r.actual_adj_em for r in results]
        errors = [abs(p - a) for p, a in zip(preds, actual)]
        rmse   = math.sqrt(sum(e ** 2 for e in errors) / len(errors))
        threshold = 2 * rmse

        ranked = sorted(results, key=lambda r: abs(r.proj_adj_em - r.actual_adj_em), reverse=True)
        self.stdout.write(f"\n  Worst residuals  (2×RMSE={threshold:.1f} flag threshold):")
        self.stdout.write(
            f"  {'Tm':<5} {'Proj':>6} {'Actual':>7} {'Err':>6} {'Persist':>8} {'PersErr':>8}"
        )
        for r in ranked[:8]:
            pipe_err    = r.proj_adj_em - r.actual_adj_em
            persist_err = r.source_adj_em - r.actual_adj_em
            flag = " *" if abs(pipe_err) > threshold else ""
            self.stdout.write(
                f"  {r.team_abbr:<5} {r.proj_adj_em:>+6.1f} {r.actual_adj_em:>+7.1f} "
                f"{pipe_err:>+6.1f} {r.source_adj_em:>+8.1f} {persist_err:>+8.1f}{flag}"
            )

    # ── CSV output ─────────────────────────────────────────────────────────────

    def _write_csv(self, results, source_year, target_year, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(
            output_dir, f"nba_forward_{source_year}_{target_year}.csv"
        )
        errors = [abs(r.proj_adj_em - r.actual_adj_em) for r in results]
        rmse = math.sqrt(sum(e ** 2 for e in errors) / len(errors))
        threshold = 2 * rmse

        rows = sorted(results, key=lambda r: abs(r.proj_adj_em - r.actual_adj_em), reverse=True)

        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=[
                "team_abbr",
                "source_adj_em",
                "bpr_aggregate_off",
                "bpr_aggregate_def",
                "bpr_combined_signal",
                "proj_adj_em",
                "actual_adj_em",
                "pipeline_error",
                "persistence_error",
                "n_players",
                "outlier",
            ])
            writer.writeheader()
            for r in rows:
                pipe_err    = r.proj_adj_em - r.actual_adj_em
                persist_err = r.source_adj_em - r.actual_adj_em
                writer.writerow({
                    "team_abbr":            r.team_abbr,
                    "source_adj_em":        round(r.source_adj_em, 2),
                    "bpr_aggregate_off":    round(r.bpr_aggregate_off, 3),
                    "bpr_aggregate_def":    round(r.bpr_aggregate_def, 3),
                    "bpr_combined_signal":  round(r.bpr_combined_signal, 3),
                    "proj_adj_em":          round(r.proj_adj_em, 2),
                    "actual_adj_em":        round(r.actual_adj_em, 2),
                    "pipeline_error":       round(pipe_err, 2),
                    "persistence_error":    round(persist_err, 2),
                    "n_players":            r.n_players,
                    "outlier":              "*" if abs(pipe_err) > threshold else "",
                })
        self.stdout.write(f"  CSV → {path}")

    # ── Availability check ─────────────────────────────────────────────────────

    def _pair_available(self, source_year):
        target_year = source_year + 1
        return (
            NBASeason.objects.filter(year=source_year).exists()
            and NBASeason.objects.filter(year=target_year).exists()
            and NBAPlayerSeasonStats.objects.filter(
                season__year=source_year, bpr__isnull=False, season_type="regular"
            ).exists()
            and NBATeamSeasonRatings.objects.filter(season__year=target_year).exists()
        )
