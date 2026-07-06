"""
projection_value.py — NBA Projection Value (docs/bpr_audit/09).

    projection_value = PROJECTION_ALPHA * z(BPR) + (1 - PROJECTION_ALPHA) * z(BPM)

Forward-looking TEAM-FORECAST player input. Validated out-of-sample over the
2022→23 / 2023→24 / 2024→25 forward pairs: pooled r=0.601 vs 0.596 pure BPM
and 0.583 pure BPR; alpha=0.25 is the min-regret choice (wins two pairs,
near-ties the third).

Product rule: this is NOT BPR. Player-evaluation surfaces show bpr/obpr/dbpr;
team outlooks and win projections consume projection_value. Never conflate.

BPM source: local BBref advanced exports (metrics_output/bbref_advanced_*.csv),
fuzzy name-matched. Players without a BPM match fall back to pure z(BPR)
(source="bpr_only").
"""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

PROJECTION_ALPHA = 0.25
PROJECTION_VALUE_VERSION = "pv1"
MIN_QUALIFIED_MINUTES = 500   # z-score population (matches nba_blend_test)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_METRICS_DIR = _REPO_ROOT / "metrics_output"


def _norm_name(s: str) -> str:
    s = str(s).lower().strip()
    s = s.encode("ascii", errors="ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", s)).strip()


def _bbref_path(season_year: int) -> Path | None:
    """bbref_advanced_2025.csv for 2025; 2026 lives as bbref_advanced_2025_26.csv."""
    for name in (f"bbref_advanced_{season_year}.csv",
                 f"bbref_advanced_{season_year - 1}_{str(season_year)[2:]}.csv"):
        p = _METRICS_DIR / name
        if p.exists():
            return p
    return None


def load_bpm_by_norm_name(season_year: int) -> dict[str, float]:
    path = _bbref_path(season_year)
    if path is None:
        logger.warning("No BBref advanced CSV for season %s — projection values "
                       "will be bpr_only", season_year)
        return {}
    out: dict[str, float] = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                out[_norm_name(row["player_name"])] = float(row["BPM"])
            except (KeyError, TypeError, ValueError):
                continue
    return out


def compute_projection_values(season_year: int) -> dict[int, dict]:
    """
    Returns {nba_player_id: {value, source, alpha, version, z_bpr, z_bpm}}.

    z-scores computed over qualified players (>= MIN_QUALIFIED_MINUTES) so the
    blend is scale-free and season-comparable.
    """
    from nba.models import NBAPlayerSeasonStats

    try:
        from rapidfuzz import fuzz, process as rfprocess
        have_fuzz = True
    except ImportError:
        have_fuzz = False

    rows = list(NBAPlayerSeasonStats.objects.filter(
        season__year=season_year, season_type="regular", bpr__isnull=False,
    ).values("player__player_id", "player__name", "bpr", "mpg", "gp"))
    if not rows:
        return {}

    # traded players → keep highest-minutes row per player id
    best: dict[int, dict] = {}
    for r in rows:
        pid = r["player__player_id"]
        r["minutes"] = (r["mpg"] or 0.0) * (r["gp"] or 0)
        if pid not in best or best[pid]["minutes"] < r["minutes"]:
            best[pid] = r
    rows = list(best.values())

    bpm_by_name = load_bpm_by_norm_name(season_year)
    bpm_names = list(bpm_by_name.keys())

    for r in rows:
        key = _norm_name(r["player__name"])
        bpm = bpm_by_name.get(key)
        if bpm is None and have_fuzz and bpm_names:
            m = rfprocess.extractOne(key, bpm_names, scorer=fuzz.WRatio,
                                     score_cutoff=88)
            if m:
                bpm = bpm_by_name[m[0]]
        r["bpm"] = bpm

    qual = [r for r in rows if r["minutes"] >= MIN_QUALIFIED_MINUTES]
    bpr_vals = np.array([r["bpr"] for r in qual], dtype=float)
    bpm_vals = np.array([r["bpm"] for r in qual if r["bpm"] is not None], dtype=float)
    if len(qual) < 50:
        logger.warning("Only %d qualified players for %s — z-scores unstable",
                       len(qual), season_year)
    bpr_mu, bpr_sd = float(bpr_vals.mean()), float(bpr_vals.std() or 1.0)
    bpm_mu = float(bpm_vals.mean()) if len(bpm_vals) else 0.0
    bpm_sd = float(bpm_vals.std() or 1.0) if len(bpm_vals) else 1.0

    out: dict[int, dict] = {}
    a = PROJECTION_ALPHA
    for r in rows:
        z_bpr = (float(r["bpr"]) - bpr_mu) / bpr_sd
        if r["bpm"] is not None:
            z_bpm = (float(r["bpm"]) - bpm_mu) / bpm_sd
            value = a * z_bpr + (1 - a) * z_bpm
            source = "bpr+bpm"
        else:
            z_bpm = None
            value = z_bpr
            source = "bpr_only"
        out[r["player__player_id"]] = {
            "value": round(value, 4),
            "source": source,
            "alpha": a,
            "version": PROJECTION_VALUE_VERSION,
            "z_bpr": round(z_bpr, 4),
            "z_bpm": round(z_bpm, 4) if z_bpm is not None else None,
        }
    n_bpm = sum(1 for v in out.values() if v["source"] == "bpr+bpm")
    logger.info("[projection_value] season %s: %d players (%d with BPM, %d bpr_only)",
                season_year, len(out), n_bpm, len(out) - n_bpm)
    return out
