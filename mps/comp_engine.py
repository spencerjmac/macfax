"""
mps/comp_engine.py

Statistical similarity matching: find the closest historical NBA draft prospect
for each 2026 player based on college stats + physical measurements.

Algorithm:
  1. Build DB of all historical prospects (2010-2023) with available stats
  2. Z-score normalize all features using training-set means/stds
  3. Apply feature weights (production-heavy, physical secondary)
  4. For each 2026 prospect: compute weighted Euclidean distance to all historical players
  5. Apply 30% position-preference boost for same position group
  6. Filter to recognizable picks (≤ pick 60)
  7. Return top-N comps with name, year, pick, similarity score
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path

import numpy as np
import pandas as pd

MPS_DIR  = Path(__file__).parent
DATA_DIR = MPS_DIR / "data"
DATASET  = DATA_DIR / "mps_dataset_raw.csv"
COMBINE  = DATA_DIR / "combine_historical.json"

# ── Feature weights for similarity ────────────────────────────────────────────
# Higher weight = more important for style comparison.
# BPM/DBPM/obpm dominate (overall + defensive profile).
# trb_pg and ast_pg high — key differentiator between guard/big archetypes.
# Physical features weighted lower — many historical players missing combine data.

COMP_WEIGHTS: dict[str, float] = {
    "bpm_college": 0.13,
    "dbpm":        0.10,
    "obpm":        0.09,
    "per":         0.07,
    "ws_40":       0.06,
    "ts_pct":      0.06,
    "pts_pg":      0.07,
    "trb_pg":      0.08,
    "ast_pg":      0.08,
    "stl_pg":      0.04,
    "blk_pg":      0.05,
    "draft_age":   0.04,
    # Physical (lower weight — sparse in historical data)
    "height_in":          0.04,
    "wingspan_in":        0.05,
    "weight_lbs":         0.03,
    "standing_reach_in":  0.04,
}

# Position group normalization
_POS_MAP = {
    "G":     "G",
    "F":     "F",
    "BIG":   "BIG",
    "guard": "G",
    "wing":  "F",
    "big":   "BIG",
}


class CompEngine:
    """
    Pre-built nearest-neighbor DB for fast prospect comp lookup.
    Initialize once; call find_comp() per prospect.
    """

    def __init__(self) -> None:
        self._ready = False
        self._features: list[str] = []
        self._weights: np.ndarray = np.array([])
        self._means: dict[str, float] = {}
        self._stds:  dict[str, float] = {}
        self._X: np.ndarray = np.zeros((0, 0))
        self._db: pd.DataFrame = pd.DataFrame()
        self._build()

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        if not DATASET.exists():
            print("  [CompEngine] Dataset not found — comps disabled")
            return

        df = pd.read_csv(DATASET)

        # Join physical measurements from combine cache
        if COMBINE.exists():
            combine_data = json.loads(COMBINE.read_text()).get("data", {})
            for col in ("height_in", "wingspan_in", "weight_lbs", "standing_reach_in"):
                df[col] = np.nan
            for yr_str, players in combine_data.items():
                yr = int(yr_str)
                mask = df["draft_year"] == yr
                names = list(players.keys())
                for idx in df[mask].index:
                    pname = df.at[idx, "player_name"]
                    matches = difflib.get_close_matches(pname, names, n=1, cutoff=0.80)
                    if matches:
                        m = players[matches[0]]
                        for col in ("height_in", "wingspan_in", "weight_lbs", "standing_reach_in"):
                            if m.get(col) is not None:
                                df.at[idx, col] = float(m[col])

        # Require at minimum: BPM + pts_pg (core production signals)
        df = df[df["bpm_college"].notna() & df["pts_pg"].notna()].copy()
        df = df.reset_index(drop=True)

        # Normalize position group
        df["_pos"] = df["position_group"].map(_POS_MAP).fillna("F")

        # Determine which features are available with enough coverage
        feats: list[str] = []
        weights: list[float] = []
        for f, w in COMP_WEIGHTS.items():
            if f in df.columns and df[f].notna().sum() >= 40:
                feats.append(f)
                weights.append(w)

        # Compute normalization params from the full historical set
        means: dict[str, float] = {}
        stds:  dict[str, float] = {}
        for f in feats:
            means[f] = float(df[f].mean())
            stds[f]  = float(max(df[f].std(), 1e-8))

        # Build weighted z-score matrix (missing → 0 = neutral)
        W = np.array(weights)
        W = W / W.sum()

        X = np.zeros((len(df), len(feats)))
        for j, f in enumerate(feats):
            vals = df[f].values.astype(float)
            z = np.where(np.isnan(vals), 0.0, (vals - means[f]) / stds[f])
            X[:, j] = z * W[j]

        self._features = feats
        self._weights  = W
        self._means    = means
        self._stds     = stds
        self._X        = X
        self._db       = df
        self._ready    = True

        n_physical = sum(1 for f in feats if f in ("height_in", "wingspan_in", "weight_lbs", "standing_reach_in"))
        print(f"  [CompEngine] Ready: {len(df)} historical prospects, "
              f"{len(feats)} features ({n_physical} physical)")

    # ── Query ──────────────────────────────────────────────────────────────────

    def find_comp(
        self,
        stats: dict,
        position_group: str,
        draft_age: float,
        top_n: int = 2,
        max_pick: int = 60,
    ) -> list[dict]:
        """
        Return top_n closest historical comps for a prospect.

        Args:
            stats:          college_stats dict (same keys as training features)
            position_group: 'guard' | 'wing' | 'big'
            draft_age:      float age at draft
            top_n:          number of comps to return
            max_pick:       only consider picks within this range (default 60 = all drafted)

        Returns list of dicts:
            {name, year, pick, round, similarity}
            similarity = 0–100 (100 = identical profile)
        """
        if not self._ready:
            return []

        # Build query vector (same weighting as DB)
        q_stats = dict(stats)
        q_stats["draft_age"] = draft_age

        q = np.zeros(len(self._features))
        n_missing = 0
        for j, f in enumerate(self._features):
            val = q_stats.get(f)
            if val is None or (isinstance(val, float) and np.isnan(val)):
                n_missing += 1
                q[j] = 0.0  # neutral imputation
            else:
                q[j] = (float(val) - self._means[f]) / self._stds[f]
        q_weighted = q * self._weights

        # Euclidean distance to every historical prospect
        diff  = self._X - q_weighted
        dists = np.sqrt((diff ** 2).sum(axis=1))

        # Position preference: same group gets 30% distance reduction
        pos_norm  = _POS_MAP.get(position_group, "F")
        same_pos  = self._db["_pos"].values == pos_norm
        dists     = np.where(same_pos, dists * 0.70, dists)

        # Restrict to recognizable picks only
        r1_mask   = self._db["draft_round"].values == 1
        r2_mask   = (self._db["draft_round"].values == 2) & (self._db["draft_pick"].values <= max_pick)
        vis_mask  = r1_mask | r2_mask
        dists_vis = np.where(vis_mask, dists, np.inf)

        # Collect top_n unique comps
        results: list[dict] = []
        seen:    set[str]   = set()
        for idx in np.argsort(dists_vis):
            if len(results) >= top_n:
                break
            d = float(dists_vis[idx])
            if np.isinf(d):
                break
            row  = self._db.iloc[int(idx)]
            name = str(row["player_name"])
            if name in seen:
                continue
            seen.add(name)

            # Convert distance → similarity (0-100).
            # Distance ≈ 0 is perfect match; ≈ 2.0 is typical unrelated prospect.
            sim = max(0, min(100, int(round((1.0 - d / 2.5) * 100))))

            results.append({
                "name":       name,
                "year":       int(row["draft_year"]),
                "pick":       int(row["draft_pick"]) if pd.notna(row["draft_pick"]) else None,
                "round":      int(row["draft_round"]),
                "similarity": sim,
            })

        return results


# ── Standalone test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Building CompEngine...")
    engine = CompEngine()

    # Test: Cameron Boozer-like profile
    test_stats = {
        "bpm_college": 18.7, "dbpm": 6.0, "obpm": 12.7, "per": 28.8,
        "ws_40": 0.28, "ts_pct": 0.653, "pts_pg": 22.5, "trb_pg": 10.2,
        "ast_pg": 4.1, "stl_pg": 1.4, "blk_pg": 1.2,
        "height_in": 82.0, "wingspan_in": 87.0, "weight_lbs": 215,
    }
    comps = engine.find_comp(test_stats, "big", 18.9)
    print(f"\nTest (Cameron Boozer profile):")
    for c in comps:
        print(f"  → {c['name']} ({c['year']}, Pk#{c['pick']})  sim={c['similarity']}")

    # Test: guard profile (Darryn Peterson-like)
    test_guard = {
        "bpm_college": 14.1, "dbpm": 4.8, "obpm": 9.3, "per": 22.6,
        "ws_40": 0.22, "ts_pct": 0.545, "pts_pg": 17.8, "trb_pg": 4.2,
        "ast_pg": 4.9, "stl_pg": 2.1, "blk_pg": 0.6,
    }
    comps2 = engine.find_comp(test_guard, "guard", 19.0)
    print(f"\nTest (Darryn Peterson profile):")
    for c in comps2:
        print(f"  → {c['name']} ({c['year']}, Pk#{c['pick']})  sim={c['similarity']}")
