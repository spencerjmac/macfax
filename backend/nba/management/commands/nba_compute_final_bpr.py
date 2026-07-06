"""
Management command: nba_compute_final_bpr

Computes the final displayed BPR using prior-informed RAPM
(LEBRON-style box prior + lineup data). Results written to
NBAPlayerSeasonStats.obpr / .dbpr / .bpr.

CURRENT PRODUCTION STATE (validated 2022-2026):

box_bpr training: 0.3 RAPM + 0.7 LEBRON targets (LEBRON_BLEND_W=0.7 in nba_compute_box_bpr)
  Box BPM corr: 0.794 (was 0.672 at 0.3 blend)

Lambda configuration: A_conservative + LEBRON-adjusted
  Base tiers (A_conservative):
    ≥2000 min (stars):    λ=400
    ≥1200 min (starters): λ=700
    ≥600 min (rotation):  λ=1000
    <600 min (fringe):    λ=1400
  LEBRON adjustment (scale=0.7):
    λ_adjusted = base * min(1 + 0.7 * max(0, 7.0 - LEBRON_total), 4x)
    Stars (LEBRON≥7): unchanged — free to use RAPM signal
    Role players (LEBRON≈1-3): lambda scaled 2-4x — anchored to box prior

Prior: 50% LEBRON + 50% box_obpr/box_dbpr (blended from lebron-data-{year}.csv)
Data: 3-year pooled stints for final prior-informed RAPM

Validation results (2022-2026):
  Star stability YoY r:  0.508  (was 0.268 originally — no longer flagged unstable)
  Avg predictive r:      0.523  (was 0.510)
  Pair 1 (2022-23→24):   0.547  (beats BOX_BPR at 0.519)
  Pair 2 (2023-24→25):   0.593
  Pair 3 (2024-25→26):   0.429

Known properties:
  - 2026: Wemby #1, SGA #2, Jokić #3, Jrue #4
  - 2025: Jokić #1, Giannis #2, Wemby #4
  - LEBRON-adjusted lambda anchors role players on elite teams
  - Higher LEBRON box blend (0.7) makes stars stable year-to-year

Known limitations:
  - Jrue Holiday (#4) / Queta (#6) still team-context inflated (Portland/Boston)
  - Giannis 2026 low by BPM — accurate: MPG dropped 34→29, LEBRON WAR 13→4.8
  - Star stability (0.508) still below BPM (0.755) — structural RAPM floor

Run order:
  1. nba_compute_baseline_rapm --season YYYY   (single season, no --rapm-years)
  2. nba_compute_box_bpr --season YYYY
  3. nba_compute_final_bpr --season YYYY       ← this command

Usage:
  python manage.py nba_compute_final_bpr --season 2026
  python manage.py nba_compute_final_bpr --season 2026 --lambda-val 500
  python manage.py nba_compute_final_bpr --season 2026 --dry-run
  python manage.py nba_compute_final_bpr --season 2026 --sweep
"""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path

import numpy as np
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from nba.analytics.lebron_utils import check_all_lebron_files
from nba.analytics.rapm import (
    build_design_matrix,
    build_nba_observations,
    fit_prior_informed_rapm,
    _solve_augmented,
)
from nba.models import NBAPlayerSeasonStats

logger = logging.getLogger(__name__)

SCRIPT_DIR      = Path(__file__).parent.parent.parent.parent.parent  # project root
METRICS_CSV     = SCRIPT_DIR / "metrics_output" / "nba_metrics_2025_26.csv"
OUTPUT_DIR      = SCRIPT_DIR / "metrics_output"
DEFAULT_LAMBDA  = 1000.0
DEFAULT_RAPM_WINDOW = 3
WINS_ADDED_DENOMINATOR = 56.0  # pts/win coefficient for RAPM-scale BPR → wins conversion
                                # wins_added = (bpr + 2.0) × (mpg/48) × (gp/56)
                                # Tunable: 56 ≈ player-scale, 33 = team point-margin scale (too high)
LEBRON_PRIOR_W       = 0.75  # weight given to O-LEBRON in offensive prior blend
LEBRON_PRIOR_DEF_W   = 0.75  # weight given to D-LEBRON in defensive prior blend
                              # v2 (2026-07): forward-ablation sweep (nba_experiment_final_bpr,
                              # pairs 2022→23/23→24/24→25) — player-forward r vs next-season
                              # baseline RAPM climbs monotonically 0.264→0.298 for w=0→0.9,
                              # flattening past 0.75; team-forward RMSE unchanged. 0.75 takes
                              # most of the gain while keeping independence from LEBRON.
                              # History: 0.2 hurt star stability (0.462→0.436); 0.5 shipped v1.
LEBRON_DATA_DIR      = SCRIPT_DIR / "data" / "nba"
LEBRON_LAMBDA_SCALE  = 0.7   # scales λ UP for low-LEBRON role players: lam = base * (1 + scale * max(0, 7-LEBRON))
                              # Validated: 0.3→0.5→0.7→1.0 all monotonically improved stability (0.431→0.462→0.480→0.481)
                              # 0.7 chosen: below 4x cap for most moderate players, cleaner than 1.0
LEBRON_LAMBDA_CAP    = 7.0   # LEBRON total above which no extra λ applied (true stars)


# Minutes-stratified lambda tiers: (≥2000, ≥1200, ≥600, <600)
LAMBDA_TIERS: dict[str, tuple[float, float, float, float]] = {
    "A_conservative": (400.0,  700.0, 1000.0, 1400.0),
    "B_moderate":     (200.0,  400.0,  700.0, 1200.0),
    "C_aggressive":   (100.0,  200.0,  400.0,  800.0),
    "D_very_agg":     ( 50.0,  100.0,  200.0,  500.0),
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _stratified_lambda(minutes: float, tiers: tuple[float, float, float, float]) -> float:
    lam_hi, lam_mid, lam_lo, lam_fringe = tiers
    if minutes >= 2000:   return lam_hi
    elif minutes >= 1200: return lam_mid
    elif minutes >= 600:  return lam_lo
    else:                 return lam_fringe


def _build_lambda_array(
    player_season_keys: list[tuple[int, int]],
    minutes_by_nba_id: dict[int, float],
    tiers: tuple[float, float, float, float],
    lebron_map: dict[int, tuple[float, float]] | None = None,
    lebron_scale: float = 0.0,
    lebron_cap: float = 7.0,
) -> np.ndarray:
    """
    Per-player lambda array, shape (2*N,) — off then def, same λ per player.

    lebron_map: {nba_id: (o_lebron, d_lebron)} — when provided and lebron_scale > 0,
      scales λ UP for low-LEBRON players (role players on good teams) to anchor them
      near their box prior.  Stars (high LEBRON) keep the base λ for RAPM freedom.

    LEBRON-adjusted lambda formula:
      lam = base * (1 + lebron_scale * max(0, lebron_cap - total_lebron))
      capped at 4x base.
    """
    n = len(player_season_keys)
    arr = np.zeros(2 * n)
    for i, (pid, _yr) in enumerate(player_season_keys):
        base = _stratified_lambda(minutes_by_nba_id.get(pid, 0.0), tiers)
        if lebron_map and lebron_scale > 0 and pid in lebron_map:
            o_leb, d_leb = lebron_map[pid]
            total_leb = o_leb + d_leb
            excess = max(0.0, lebron_cap - total_leb)
            multiplier = min(1.0 + lebron_scale * excess, 4.0)
            lam = base * multiplier
        else:
            lam = base
        arr[i] = lam
        arr[n + i] = lam
    return arr


def _norm_name(s: str) -> str:
    s = str(s).lower().strip()
    s = s.encode("ascii", errors="ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", s)).strip()


def _load_lebron_priors(season_year: int, nba_ids: list[int]) -> dict[int, tuple[float, float]]:
    """
    Load O-LEBRON / D-LEBRON from lebron-data-{year}.csv, keyed by NBA.com player_id.
    The CSV _id column IS the NBA.com player_id — no fuzzy matching needed.
    Returns {nba_id: (o_lebron, d_lebron)}.  Falls back to {} if CSV missing.
    Available for seasons 2016-2026.
    """
    try:
        import pandas as pd
    except ImportError:
        return {}

    csv_path = SCRIPT_DIR / "data" / "nba" / f"lebron-data-{season_year}.csv"
    if not csv_path.exists():
        return {}

    df = pd.read_csv(csv_path)
    df = df.rename(columns={"_id": "nba_id", "O-LEBRON": "O_LEBRON", "D-LEBRON": "D_LEBRON"})
    df = df.dropna(subset=["O_LEBRON", "D_LEBRON", "nba_id"])
    df["nba_id"] = df["nba_id"].astype(int)
    # If same player on multiple rows (rare), keep highest-MPG row
    df = df.sort_values("MPG", ascending=False).drop_duplicates("nba_id", keep="first")

    id_set = set(nba_ids)
    result: dict[int, tuple[float, float]] = {}
    for _, row in df.iterrows():
        nba_id = int(row["nba_id"])
        if nba_id in id_set:
            result[nba_id] = (float(row["O_LEBRON"]), float(row["D_LEBRON"]))
    return result


def _load_bpm_map() -> dict[str, float]:
    """Load player_name → BPM from metrics CSV."""
    bpm: dict[str, float] = {}
    if not METRICS_CSV.exists():
        return bpm
    import pandas as pd  # type: ignore
    df = pd.read_csv(METRICS_CSV)
    for _, row in df.iterrows():
        if str(row.get("BPM", "")).strip() not in ("", "nan"):
            try:
                bpm[_norm_name(str(row["player_name"]))] = float(row["BPM"])
            except (ValueError, TypeError):
                pass
    return bpm


def _extract_results(
    beta: np.ndarray,
    player_season_keys: list[tuple[int, int]],
    n_ps: int,
    season_year: int,
) -> tuple[dict[int, float], dict[int, float]]:
    """Extract obpr/dbpr dicts for target season from beta vector."""
    obpr_block = beta[2: 2 + n_ps]
    dbpr_block = beta[2 + n_ps: 2 + 2 * n_ps]
    obpr = {pid: float(obpr_block[i]) for i, (pid, yr) in enumerate(player_season_keys) if yr == season_year}
    dbpr = {pid: float(-dbpr_block[i]) for i, (pid, yr) in enumerate(player_season_keys) if yr == season_year}
    return obpr, dbpr


def _compute_metrics(
    obpr: dict[int, float],
    dbpr: dict[int, float],
    bpm_map: dict[str, float],
    usg_map: dict[int, float],
    name_map: dict[int, str],
    box_bpr_map: dict[int, float],
) -> dict:
    """Compute BPM corr, Jokić z, Q4 divergence, SD, top5."""
    import scipy.stats  # type: ignore

    bpr_vals, bpm_vals, usg_vals, pids = [], [], [], []
    for pid, o in obpr.items():
        d = dbpr.get(pid, 0.0)
        name = name_map.get(pid, "")
        bpm = bpm_map.get(_norm_name(name))
        if bpm is None:
            continue
        bpr_vals.append(o + d)
        bpm_vals.append(bpm)
        usg_vals.append(usg_map.get(pid, 0.0))
        pids.append(pid)

    if len(bpr_vals) < 10:
        return {"bpm_r": float("nan"), "jokic_z": float("nan"),
                "q4_div": float("nan"), "sd": float("nan"), "top5": []}

    bpr_arr = np.array(bpr_vals)
    bpm_arr = np.array(bpm_vals)
    usg_arr = np.array(usg_vals)

    r_bpm, _ = scipy.stats.pearsonr(bpr_arr, bpm_arr)
    sd = float(bpr_arr.std())

    # Jokić z-score
    jokic_z = float("nan")
    if sd > 0:
        for i, pid in enumerate(pids):
            if "joki" in _norm_name(name_map.get(pid, "")):
                jokic_z = float((bpr_arr[i] - bpr_arr.mean()) / sd)
                break

    # Q4 divergence
    q4_div = float("nan")
    q4_mask = usg_arr > 0.28
    if q4_mask.sum() >= 3 and sd > 0 and bpm_arr.std() > 0:
        z_bpr = (bpr_arr - bpr_arr.mean()) / sd
        z_bpm = (bpm_arr - bpm_arr.mean()) / bpm_arr.std()
        q4_div = float((z_bpr[q4_mask] - z_bpm[q4_mask]).mean())

    # Top 5
    top5_idx = np.argsort(bpr_arr)[::-1][:5]
    top5 = [name_map.get(pids[i], f"id={pids[i]}") for i in top5_idx]

    return {
        "bpm_r":   round(float(r_bpm), 3),
        "jokic_z": round(jokic_z, 3) if not np.isnan(jokic_z) else float("nan"),
        "q4_div":  round(q4_div, 3) if not np.isnan(q4_div) else float("nan"),
        "sd":      round(sd, 3),
        "top5":    top5,
        "bpr_map": dict(zip(pids, bpr_arr.tolist())),   # for stability/team checks
    }


class Command(BaseCommand):
    help = "Compute final BPR (prior-informed RAPM) with minutes-stratified λ"

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument(
            "--lambda-val", type=float, default=DEFAULT_LAMBDA,
            help=f"Ridge regularization λ for single run (default {DEFAULT_LAMBDA})",
        )
        parser.add_argument(
            "--rapm-window", type=int, default=DEFAULT_RAPM_WINDOW,
            help=f"Seasons of stints to pool (default {DEFAULT_RAPM_WINDOW})",
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--sweep",
            action="store_true",
            help="Run all 4 lambda-tier configs, print comparison table, write best if checks pass",
        )
        parser.add_argument(
            "--within-season-half-life", type=float, default=90.0,
            help="Days half-life for within-season recency decay. Default 90 (best retrodiction R²=0.739 vs baseline 0.715). Pass 0 to disable.",
        )
        parser.add_argument(
            "--cross-season-decay", type=float, default=1.0,
            # Note: empirically inert at λ≥1000 (regularization dominates). Exposed for experiments only.
            help="Per-year multiplier for cross-season decay (default 1.0 = off; tested 0.25–1.0, all identical).",
        )
        parser.add_argument(
            "--lebron-prior-weight", type=float, default=LEBRON_PRIOR_W,
            help=f"Blend weight for LEBRON in prior (0=pure box_bpr, 1=pure LEBRON, default {LEBRON_PRIOR_W}). "
                 "Uses lebron-data-{{year}}.csv. LEBRON stabilizes stars, reduces role-player inflation.",
        )
        parser.add_argument(
            "--lebron-lambda-scale", type=float, default=LEBRON_LAMBDA_SCALE,
            help=f"Scales λ UP for low-LEBRON role players: lam = base * (1 + scale * max(0, cap - LEBRON)). "
                 f"Default {LEBRON_LAMBDA_SCALE}. 0 = disabled. Higher = stronger anchoring for non-stars.",
        )
        parser.add_argument(
            "--lebron-prior-def-weight", type=float, default=LEBRON_PRIOR_DEF_W,
            help=f"LEBRON blend weight for DEFENSIVE prior only (default {LEBRON_PRIOR_DEF_W}). "
                 "Lower than offensive weight because D-LEBRON is noisier (can mislabel elite defenders).",
        )

    def handle(self, *args, **options):
        season_year: int = options["season"]
        lambda_val: float = options["lambda_val"]
        rapm_window: int = options["rapm_window"]
        dry_run: bool = options["dry_run"]
        sweep: bool = options.get("sweep", False)
        _whl = options.get("within_season_half_life")
        within_season_half_life: float | None = None if (_whl is not None and _whl <= 0) else _whl
        cross_season_decay: float = options["cross_season_decay"]
        lebron_prior_w: float = options.get("lebron_prior_weight", LEBRON_PRIOR_W)
        lebron_prior_def_w: float = options.get("lebron_prior_def_weight", LEBRON_PRIOR_DEF_W)
        lebron_lambda_scale: float = options.get("lebron_lambda_scale", LEBRON_LAMBDA_SCALE)

        # ── LEBRON freshness gate ─────────────────────────────────────────────
        for _result in check_all_lebron_files(str(LEBRON_DATA_DIR), season_year):
            _label = f"lebron-data-{_result['year']}.csv"
            if _result["status"] == "error":
                raise CommandError(
                    f"LEBRON data missing: {_result['path']}\n"
                    f"NBA BPR cannot run without current-season LEBRON prior.\n"
                    f"Download from BBall Index and place at: {_result['path']}"
                )
            elif _result["status"] == "warning":
                logger.warning(
                    "LEBRON data may be stale: %s  (%.0f days old, season_active=%s)",
                    _label,
                    _result["age_days"],
                    _result["season_active"],
                )
                self.stdout.write(
                    self.style.WARNING(f"  ⚠  {_label}: {_result['message']}")
                )
            else:
                logger.info("LEBRON data OK: %s (%.1f days old)", _label, _result["age_days"])

        if sweep:
            self._run_sweep(season_year, rapm_window, within_season_half_life, cross_season_decay, lebron_prior_w)
            return

        self.stdout.write(f"\n[FINAL BPR] Season {season_year}  λ={lambda_val}  window={rapm_window}yr")
        if dry_run:
            self.stdout.write("[DRY RUN] No writes")

        # ── 1. Load box_bpr priors ─────────────────────────────────────────────
        prior_obpr, prior_dbpr, minutes_by_nba_id = self._load_priors(season_year)

        # ── 1b. Load LEBRON map and blend into priors ─────────────────────────
        # LEBRON map is also used for LEBRON-adjusted lambda (see 1c)
        lebron_map_raw = _load_lebron_priors(season_year, list(prior_obpr.keys()))
        if lebron_prior_w > 0 and lebron_map_raw:
            prior_obpr, prior_dbpr = self._blend_lebron_priors(
                season_year, prior_obpr, prior_dbpr, lebron_prior_w,
                def_weight=lebron_prior_def_w, lebron_map=lebron_map_raw
            )
        elif lebron_prior_w > 0:
            prior_obpr, prior_dbpr = self._blend_lebron_priors(
                season_year, prior_obpr, prior_dbpr, lebron_prior_w,
                def_weight=lebron_prior_def_w
            )

        # ── 1c. Build LEBRON-adjusted lambda array ────────────────────────────
        # A_conservative (400/700/1000/1400) selected by sweep: best BPM correlation (0.480)
        # LEBRON-adjusted: scales λ UP for low-LEBRON role players, keeps base for stars.
        # This prevents context-inflation for role players on good teams (e.g. Jrue on POR).
        if lambda_val == DEFAULT_LAMBDA:
            # Build player_season_keys in the order needed by _build_lambda_array
            # (called again after loading stints, but we need it before stints for the msg)
            self.stdout.write("Using A_conservative stratified λ (400/700/1000/1400 by minutes tier)", )
            if lebron_lambda_scale > 0 and lebron_map_raw:
                self.stdout.write(
                    f"  LEBRON-adjusted λ: scale={lebron_lambda_scale} "
                    f"(role players anchored, stars free)"
                )
            lambda_by_nba_id = None  # rebuilt using player_season_keys after stints load
            _use_a_conservative = True
        else:
            lambda_by_nba_id = None
            _use_a_conservative = False
            self.stdout.write(f"Using uniform λ={lambda_val}")

        # ── 2. Load stints ─────────────────────────────────────────────────────
        observations, player_season_index, n_ps = self._load_stints(season_year, rapm_window)

        # ── 2b. Build LEBRON-adjusted lambda array ─────────────────────────────
        if _use_a_conservative:
            player_season_keys = sorted(player_season_index, key=player_season_index.get)
            lam_arr = _build_lambda_array(
                player_season_keys,
                minutes_by_nba_id,
                LAMBDA_TIERS["A_conservative"],
                lebron_map=lebron_map_raw if lebron_lambda_scale > 0 else None,
                lebron_scale=lebron_lambda_scale,
                lebron_cap=LEBRON_LAMBDA_CAP,
            )
            lambda_by_nba_id = {
                pid: float(lam_arr[i])
                for i, (pid, _yr) in enumerate(player_season_keys)
            }

        # ── 3. Fit ─────────────────────────────────────────────────────────────
        self.stdout.write("Fitting prior-informed RAPM...")
        result = fit_prior_informed_rapm(
            observations=observations,
            player_season_index=player_season_index,
            n_player_seasons=n_ps,
            prior_obpr=prior_obpr,
            prior_dbpr=prior_dbpr,
            lambda_val=lambda_val,
            lambda_by_nba_id=lambda_by_nba_id,
            target_season_year=season_year,
            cross_season_decay=cross_season_decay,
            within_season_half_life=within_season_half_life,
        )

        final_obpr = {pid: v for (pid, yr), v in result["obpr"].items() if yr == season_year}
        final_dbpr = {pid: v for (pid, yr), v in result["dbpr"].items() if yr == season_year}
        self.stdout.write(f"  {len(final_obpr)} players with final BPR for {season_year}")

        if dry_run:
            self._print_leaderboard(final_obpr, final_dbpr, season_year)
            return

        self._write_to_db(final_obpr, final_dbpr, season_year)
        self._print_leaderboard(final_obpr, final_dbpr, season_year)

    # ── Sweep ──────────────────────────────────────────────────────────────────

    def _run_sweep(
        self, season_year: int, rapm_window: int,
        within_season_half_life: float | None = None,
        cross_season_decay: float = 1.0,
        lebron_prior_w: float = LEBRON_PRIOR_W,
    ) -> None:
        self.stdout.write(f"\n[SWEEP] Season {season_year} — testing {len(LAMBDA_TIERS)} lambda configs")

        # Load shared data once
        prior_obpr, prior_dbpr, minutes_by_nba_id = self._load_priors(season_year)
        if lebron_prior_w > 0:
            prior_obpr, prior_dbpr = self._blend_lebron_priors(
                season_year, prior_obpr, prior_dbpr, lebron_prior_w
            )
        observations, player_season_index, n_ps = self._load_stints(season_year, rapm_window)

        bpm_map  = _load_bpm_map()
        usg_map  = self._load_usg_map(season_year)
        name_map = self._load_name_map(list(prior_obpr.keys()))
        box_bpr_map = self._load_box_bpr_map(season_year)
        old_bpr_map = self._load_current_bpr_map(season_year)

        self.stdout.write(f"  BPM map: {len(bpm_map)} players")
        self.stdout.write(f"  USG map: {len(usg_map)} players")

        # Build design matrix ONCE — reused across all configs
        self.stdout.write("Building design matrix (done once)...")
        player_season_keys = sorted(player_season_index, key=player_season_index.get)
        n_features = 2 + 2 * n_ps
        prior_means = np.zeros(n_features)
        for i, (pid, _yr) in enumerate(player_season_keys):
            prior_means[2 + i]          =  prior_obpr.get(pid, 0.0)
            prior_means[2 + n_ps + i]   = -prior_dbpr.get(pid, 0.0)

        X, y, weights = build_design_matrix(
            observations, player_season_index, n_ps,
            target_season_year=season_year,
            cross_season_decay=cross_season_decay,
            within_season_half_life=within_season_half_life,
        )
        player_col_slice = (2, 2 + 2 * n_ps)
        self.stdout.write(f"  Matrix: {X.shape[0]} × {X.shape[1]}")

        # Sweep configs
        results: dict[str, dict] = {}
        for config_name, tiers in LAMBDA_TIERS.items():
            self.stdout.write(f"\n  [{config_name}] tiers={tiers}...")
            lam_arr = _build_lambda_array(player_season_keys, minutes_by_nba_id, tiers)
            beta = _solve_augmented(
                X, y, weights,
                lambda_val=tiers[0],         # scalar fallback (not used when per_player_lambda set)
                prior_means=prior_means,
                player_col_slice=player_col_slice,
                per_player_lambda=lam_arr,
            )
            obpr, dbpr = _extract_results(beta, player_season_keys, n_ps, season_year)
            metrics = _compute_metrics(obpr, dbpr, bpm_map, usg_map, name_map, box_bpr_map)
            results[config_name] = {**metrics, "obpr": obpr, "dbpr": dbpr, "tiers": tiers}

        # Print comparison table
        self.stdout.write("\n" + "=" * 75)
        self.stdout.write("LAMBDA SWEEP COMPARISON TABLE")
        self.stdout.write("=" * 75)
        self.stdout.write(
            f"{'Config':<16} {'BPM_r':>6} {'Jokić_z':>8} {'Q4_div':>8} {'SD':>6}  {'Top1'}"
        )
        self.stdout.write("-" * 75)
        for name, res in results.items():
            top1 = res["top5"][0].split()[-1] if res["top5"] else "?"
            self.stdout.write(
                f"  {name:<14} {res['bpm_r']:>6.3f} {res['jokic_z']:>8.3f} "
                f"{res['q4_div']:>8.3f} {res['sd']:>6.3f}  {top1}"
            )
        self.stdout.write("=" * 75)

        # Select best config
        best_name = self._select_best_config(results)
        best = results[best_name]
        self.stdout.write(f"\nSelected config: {best_name}  tiers={best['tiers']}")

        # Stability checks on best config
        self._stability_checks(
            best["obpr"], best["dbpr"], best["bpr_map"],
            box_bpr_map, minutes_by_nba_id, usg_map, name_map, season_year
        )

        # Team bias check
        self._team_bias_check(best["obpr"], best["dbpr"], bpm_map, name_map, season_year)

        # Conditional DB write
        bpm_r   = best["bpm_r"]
        jokic_z = best["jokic_z"]
        q4_div  = best["q4_div"]
        n_pass  = sum([bpm_r > 0.70, jokic_z > 2.5, q4_div > -0.30])

        self.stdout.write("\n" + "=" * 55)
        self.stdout.write("LAMBDA TUNING RESULTS")
        self.stdout.write("=" * 55)
        self.stdout.write(f"Best config: {best_name}")
        self._print_check("BPM correlation",   bpm_r,   0.70, "above")
        self._print_check("Jokić z-score",     jokic_z, 2.50, "above")
        self._print_check("Q4 divergence",     q4_div, -0.30, "above")
        self._print_check("SD of BPR",         best["sd"], 5.0, "below", low=3.0)
        self.stdout.write("=" * 55)

        if n_pass >= 3:
            self.stdout.write(self.style.SUCCESS(f"\n{n_pass}/3 primary checks passed — WRITING TO DB"))
            self._write_to_db(best["obpr"], best["dbpr"], season_year)
            self._print_leaderboard(best["obpr"], best["dbpr"], season_year)
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"\nNOT WRITTEN TO DB — {n_pass}/3 primary checks failed. "
                    "Review CSV and decide whether to adjust λ further or accept current state."
                )
            )
            self._save_comparison_csv(
                best["obpr"], best["dbpr"], old_bpr_map, box_bpr_map,
                bpm_map, usg_map, name_map, season_year
            )

    def _select_best_config(self, results: dict) -> str:
        def score(name):
            r = results[name]
            n_pass = sum([r["bpm_r"] > 0.70, r["jokic_z"] > 2.5, r["q4_div"] > -0.30])
            # Prefer passing checks first, then lower SD (stability)
            return (n_pass, -r["sd"])
        return max(results, key=score)

    def _stability_checks(
        self, obpr, dbpr, bpr_map, box_bpr_map, minutes_by_nba_id, usg_map, name_map, season_year
    ) -> None:
        self.stdout.write("\n[STABILITY CHECK A] Fringe player stability (10 lowest minutes):")
        fringe = sorted(
            [(pid, minutes_by_nba_id.get(pid, 0)) for pid in obpr],
            key=lambda x: x[1]
        )[:10]
        for pid, mins in fringe:
            bpr_new = (obpr.get(pid, 0) + dbpr.get(pid, 0))
            box_b   = box_bpr_map.get(pid, float("nan"))
            diff    = abs(bpr_new - box_b) if not (box_b != box_b) else float("nan")
            flag    = " ← UNSTABLE" if diff > 1.0 else ""
            self.stdout.write(
                f"  {name_map.get(pid, pid):<28} min={mins:.0f}  "
                f"bpr={bpr_new:+.2f}  box={box_b:+.2f}  |diff|={diff:.2f}{flag}"
            )

        self.stdout.write("\n[STABILITY CHECK B] Top 20 — flag <800 min players:")
        ranked = sorted(obpr.items(), key=lambda x: x[1] + dbpr.get(x[0], 0), reverse=True)[:20]
        for rank, (pid, o) in enumerate(ranked, 1):
            d   = dbpr.get(pid, 0)
            mins = minutes_by_nba_id.get(pid, 0)
            flag = " ← LOW MINUTES" if mins < 800 else ""
            self.stdout.write(
                f"  {rank:>2}. {name_map.get(pid, pid):<28} bpr={o+d:+.2f}  min={mins:.0f}{flag}"
            )

    def _team_bias_check(self, obpr, dbpr, bpm_map, name_map, season_year) -> None:
        from collections import defaultdict
        from nba.models import NBAPlayerSeasonStats
        self.stdout.write("\n[STABILITY CHECK C] Team bias:")
        target_teams = {"IND", "MIA", "TOR", "LAL", "NYK"}
        team_bpr: dict[str, list[tuple[float, float]]] = defaultdict(list)
        team_bpm: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for row in NBAPlayerSeasonStats.objects.filter(
            season__year=season_year, season_type="regular"
        ).select_related("player", "team").only(
            "player__player_id", "player__name", "team__abbreviation", "mpg", "gp"
        ):
            abbr = row.team.abbreviation if row.team else ""
            if abbr not in target_teams:
                continue
            nba_id = row.player.player_id
            mins = (row.mpg or 0) * (row.gp or 0)
            bpr_val = obpr.get(nba_id, 0) + dbpr.get(nba_id, 0)
            bpm_val = bpm_map.get(_norm_name(row.player.name))
            team_bpr[abbr].append((bpr_val, mins))
            if bpm_val is not None:
                team_bpm[abbr].append((bpm_val, mins))
        for abbr in sorted(target_teams):
            if not team_bpr.get(abbr):
                continue
            def wgt_mean(pairs):
                total_w = sum(w for _, w in pairs)
                return sum(v * w for v, w in pairs) / total_w if total_w > 0 else 0.0
            m_bpr = wgt_mean(team_bpr[abbr])
            m_bpm = wgt_mean(team_bpm.get(abbr, [(0.0, 1.0)]))
            self.stdout.write(
                f"  {abbr}: mean_BPR={m_bpr:+.2f}  mean_BPM={m_bpm:+.2f}  diff={m_bpr-m_bpm:+.2f}"
            )

    # ── Shared helpers ─────────────────────────────────────────────────────────

    def _load_priors(self, season_year: int) -> tuple[dict, dict, dict]:
        box_stats = list(
            NBAPlayerSeasonStats.objects.filter(
                season__year=season_year,
                season_type="regular",
                box_obpr__isnull=False,
            ).select_related("player").only(
                "player__player_id", "box_obpr", "box_dbpr", "mpg", "gp",
            )
        )
        if not box_stats:
            raise CommandError(f"No box_obpr found for {season_year}. Run nba_compute_box_bpr first.")
        prior_obpr: dict[int, float] = {}
        prior_dbpr: dict[int, float] = {}
        minutes_by_nba_id: dict[int, float] = {}
        for row in box_stats:
            nba_id = row.player.player_id
            if nba_id:
                prior_obpr[nba_id] = row.box_obpr or 0.0
                prior_dbpr[nba_id] = row.box_dbpr or 0.0
                minutes_by_nba_id[nba_id] = (row.mpg or 0.0) * (row.gp or 0)
        self.stdout.write(
            f"Box priors loaded: {len(prior_obpr)} players  "
            f"(stars ≥2000 min: {sum(1 for m in minutes_by_nba_id.values() if m >= 2000)})"
        )
        return prior_obpr, prior_dbpr, minutes_by_nba_id

    def _blend_lebron_priors(
        self,
        season_year: int,
        prior_obpr: dict[int, float],
        prior_dbpr: dict[int, float],
        weight: float,
        def_weight: float = LEBRON_PRIOR_DEF_W,
        lebron_map: dict[int, tuple[float, float]] | None = None,
    ) -> tuple[dict[int, float], dict[int, float]]:
        """
        Blend LEBRON into box_bpr priors with separate weights for offense and defense.

          prior_obpr[pid] = weight     * O_LEBRON + (1-weight)     * box_obpr
          prior_dbpr[pid] = def_weight * D_LEBRON + (1-def_weight) * box_dbpr

        Defensive weight is lower than offensive (def_weight=0.2 default) because:
        - D-LEBRON is noisier and can mislabel elite defenders
        - Example: Giannis D-LEBRON=-0.363 in 2026, but his box DBPR is positive
        - Box DREB%, BLK%, STL% are more reliable defensive signals than LEBRON

        LEBRON keyed by NBA.com player_id (_id column in CSV) — exact match, no fuzzy.
        """
        if lebron_map is None:
            lebron_map = _load_lebron_priors(season_year, list(prior_obpr.keys()))
        if not lebron_map:
            self.stdout.write(f"  LEBRON prior: no data for {season_year}, using box priors only")
            return prior_obpr, prior_dbpr

        n_blended = 0
        new_obpr = dict(prior_obpr)
        new_dbpr = dict(prior_dbpr)
        for pid, (o_leb, d_leb) in lebron_map.items():
            if pid in prior_obpr:
                new_obpr[pid] = weight     * o_leb + (1 - weight)     * prior_obpr[pid]
                new_dbpr[pid] = def_weight * d_leb + (1 - def_weight) * prior_dbpr[pid]
                n_blended += 1

        self.stdout.write(
            f"  LEBRON prior blend (off={weight:.0%}/def={def_weight:.0%} LEBRON): "
            f"{n_blended} players blended, {len(prior_obpr) - n_blended} box only"
        )
        return new_obpr, new_dbpr

    def _load_stints(self, season_year: int, rapm_window: int) -> tuple[list, dict, int]:
        rapm_years = list(range(season_year - rapm_window + 1, season_year + 1))
        self.stdout.write(f"Loading stints for {rapm_years}...")
        observations = build_nba_observations(season_year=season_year, rapm_years=rapm_years)
        if not observations:
            raise CommandError("No stint observations found.")
        all_ps: set[tuple[int, int]] = set()
        for obs in observations:
            yr = obs["season_year"]
            for pid in obs["home_player_ids"] + obs["away_player_ids"]:
                all_ps.add((pid, yr))
        player_season_index = {ps: i for i, ps in enumerate(sorted(all_ps))}
        n_ps = len(player_season_index)
        self.stdout.write(
            f"  {len(observations)} lineup observations  "
            f"{n_ps} player-season columns  "
            f"({len({ps[0] for ps in all_ps})} unique players)"
        )
        return observations, player_season_index, n_ps

    def _load_usg_map(self, season_year: int) -> dict[int, float]:
        return {
            row["player__player_id"]: (row["usg_pct"] or 0.0)
            for row in NBAPlayerSeasonStats.objects.filter(
                season__year=season_year, season_type="regular"
            ).values("player__player_id", "usg_pct")
            if row["player__player_id"]
        }

    def _load_name_map(self, nba_ids: list[int]) -> dict[int, str]:
        from nba.models import NBAPlayer
        return {
            p.player_id: p.name
            for p in NBAPlayer.objects.filter(player_id__in=nba_ids).only("player_id", "name")
        }

    def _load_box_bpr_map(self, season_year: int) -> dict[int, float]:
        return {
            row["player__player_id"]: (row["box_bpr"] or 0.0)
            for row in NBAPlayerSeasonStats.objects.filter(
                season__year=season_year, season_type="regular", box_bpr__isnull=False
            ).values("player__player_id", "box_bpr")
            if row["player__player_id"]
        }

    def _load_current_bpr_map(self, season_year: int) -> dict[int, float]:
        return {
            row["player__player_id"]: (row["bpr"] or 0.0)
            for row in NBAPlayerSeasonStats.objects.filter(
                season__year=season_year, season_type="regular", bpr__isnull=False
            ).values("player__player_id", "bpr")
            if row["player__player_id"]
        }

    def _write_to_db(
        self, final_obpr: dict[int, float], final_dbpr: dict[int, float], season_year: int
    ) -> None:
        stats_qs = NBAPlayerSeasonStats.objects.filter(
            season__year=season_year, season_type="regular"
        ).select_related("player")
        now = timezone.now()
        updated = skipped = 0
        for row in stats_qs:
            nba_id = row.player.player_id
            if nba_id not in final_obpr:
                skipped += 1
                continue
            o = final_obpr[nba_id]
            d = final_dbpr.get(nba_id, 0.0)
            total_bpr = o + d
            row.obpr = round(o, 3)
            row.dbpr = round(d, 3)
            row.bpr  = round(total_bpr, 3)
            row.bpr_last_updated = now
            # wins_added = (bpr + 2.0) × (mpg / 48) × (gp / WINS_ADDED_DENOMINATOR)
            # replacement level = BPR -2.0 (freely available player), denominator tunable
            mpg = row.mpg or 0.0
            gp  = row.gp  or 0
            if mpg > 0 and gp > 0:
                row.wins_added = round(
                    (total_bpr + 2.0) * (mpg / 48.0) * (gp / WINS_ADDED_DENOMINATOR), 2
                )
            else:
                row.wins_added = None
            row.save(update_fields=["obpr", "dbpr", "bpr", "bpr_last_updated", "wins_added"])
            updated += 1
        self.stdout.write(self.style.SUCCESS(
            f"[OK] Final BPR written: {updated} updated, {skipped} skipped"
        ))

    def _save_comparison_csv(
        self, obpr, dbpr, old_bpr_map, box_bpr_map,
        bpm_map, usg_map, name_map, season_year
    ) -> None:
        path = OUTPUT_DIR / "final_bpr_lambda_best.csv"
        rows = []
        for pid, o in obpr.items():
            d = dbpr.get(pid, 0.0)
            bpr_new = o + d
            name = name_map.get(pid, f"id={pid}")
            bpm  = bpm_map.get(_norm_name(name))
            z_bpr = z_bpm = div = None
            rows.append({
                "player_name": name,
                "player_id":   pid,
                "bpr_new":     round(bpr_new, 3),
                "bpr_old":     round(old_bpr_map.get(pid, float("nan")), 3),
                "box_bpr":     round(box_bpr_map.get(pid, float("nan")), 3),
                "bpm":         bpm,
            })
        import pandas as pd  # type: ignore
        df = pd.DataFrame(rows).sort_values("bpr_new", ascending=False)
        df.to_csv(path, index=False)
        self.stdout.write(f"[SAVED] {path}")

    def _print_check(self, label: str, val: float, target: float, direction: str,
                     low: float | None = None) -> None:
        if direction == "above":
            ok = val > target
            sym = ">"
        else:
            ok = val < target
            sym = "<"
        if low is not None:
            ok = low < val < target
            sym = f"{low}-{target}"
        status = self.style.SUCCESS("PASS") if ok else self.style.WARNING("FAIL")
        self.stdout.write(f"  {label:<25} {val:.3f}  [{status}] (target {sym}{target})")

    def _print_leaderboard(self, final_obpr, final_dbpr, season_year) -> None:
        from nba.models import NBAPlayer
        name_map = {
            p.player_id: p.name
            for p in NBAPlayer.objects.filter(player_id__in=final_obpr.keys()).only("player_id", "name")
        }
        ranked = sorted(
            [(pid, final_obpr[pid], final_dbpr.get(pid, 0.0)) for pid in final_obpr],
            key=lambda x: x[1] + x[2], reverse=True,
        )
        self.stdout.write(f"\nTop 20 by final BPR — Season {season_year}:")
        self.stdout.write(f"  {'Player':<30} {'OBPR':>6} {'DBPR':>6} {'BPR':>7}")
        self.stdout.write("  " + "-" * 55)
        for pid, o, d in ranked[:20]:
            name = name_map.get(pid, f"id={pid}")
            self.stdout.write(f"  {name:<30} {o:>+6.2f} {d:>+6.2f} {o+d:>+7.2f}")
