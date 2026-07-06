"""
nba_blend_test — Experiment N-BLEND: does blending MacFax BPR with a public
box metric (BPM) improve forward team prediction over either alone?

blend_alpha = alpha * z(BPR) + (1 - alpha) * z(BPM)   per player-season
(z-scores within season over qualified players — puts the two scales on
common footing; both are rate metrics so minutes-weighted team aggregation
is apples-to-apples)

Forward test mirrors nba_predictive_test: team aggregate (season N) → wins
(season N+1), Pearson r, pairs 2022→23 / 2023→24 / 2024→25.

Usage:
    backend/.venv/bin/python analysis/nba/nba_blend_test.py
"""

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPT_DIR / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()

from nba_predictive_test import (  # noqa: E402
    scrape_bbref_advanced, load_bpr_from_db, load_wins_srs,
    merge_bpr_onto_players,
)

ALPHAS = [0.0, 0.25, 0.5, 0.75, 1.0]
PAIRS = [(2022, 2023), (2023, 2024), (2024, 2025)]
MIN_MINUTES = 500


def team_forward_r(players: pd.DataFrame, col: str, wins_next: dict) -> float:
    # dedupe traded players: keep highest-minutes row
    players = (players.sort_values("minutes", ascending=False)
               .drop_duplicates("player_name"))
    agg = {}
    for team, grp in players.groupby("team"):
        valid = grp[["minutes", col]].dropna()
        valid = valid[valid["minutes"] >= MIN_MINUTES]
        if len(valid) and valid["minutes"].sum() > 0:
            agg[team] = (valid[col] * valid["minutes"]).sum() / valid["minutes"].sum()
    pairs = [(v, wins_next[t]["wins"]) for t, v in agg.items() if t in wins_next]
    if len(pairs) < 10:
        return float("nan")
    a, b = zip(*pairs)
    return float(np.corrcoef(a, b)[0, 1])


def main():
    results = {a: [] for a in ALPHAS}
    for src, tgt in PAIRS:
        bbref = scrape_bbref_advanced(src)
        bpr = load_bpr_from_db(src)
        merged = merge_bpr_onto_players(bbref, bpr)
        merged["minutes"] = pd.to_numeric(merged["minutes"], errors="coerce")
        merged["BPM"] = pd.to_numeric(merged["BPM"], errors="coerce")

        qual = merged[merged["minutes"] >= MIN_MINUTES]
        for col in ("BPR", "BPM"):
            mu, sd = qual[col].mean(), qual[col].std()
            merged[f"z_{col}"] = (merged[col] - mu) / sd

        wins_next = load_wins_srs(tgt)
        for a in ALPHAS:
            merged["blend"] = a * merged["z_BPR"] + (1 - a) * merged["z_BPM"]
            r = team_forward_r(merged, "blend", wins_next)
            results[a].append(r)
            print(f"  {src}->{tgt}  alpha={a:.2f}  r={r:.4f}")

    print("\nalpha  avg_r  (alpha=1 pure BPR, alpha=0 pure BPM)")
    for a in ALPHAS:
        vals = [v for v in results[a] if v == v]
        print(f"{a:5.2f}  {sum(vals)/len(vals):.4f}")


if __name__ == "__main__":
    main()
