"""
mps/scale_verification.py

Scale verification: do Tankathon and CBB (Sports-Reference) report the
same numerical values for the same stats?

Compares paired CBB vs Tankathon values for 2026 prospects to determine
whether Tankathon can be used as a primary stats source when CBB is
unavailable, or whether it's fallback-only.

Run:
    backend/.venv/bin/python -m mps.scale_verification
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from mps.scorer import DRAFT_DATE_2026, PROSPECTS_2026

DATA_DIR     = Path(__file__).parent / "data"
CBB_CACHE    = DATA_DIR / "cbb_stats_cache"
SUPP_CACHE   = DATA_DIR / "supplement_cache"
TANK_CACHE   = DATA_DIR / "tankathon_2026.json"

# CBB stat name → (tankathon sub-dict, tankathon key)
STAT_MAP: dict[str, tuple[str, str]] = {
    "bpm_college": ("advanced", "bpm"),
    "obpm":        ("advanced", "obpm"),
    "dbpm":        ("advanced", "dbpm"),
    "per":         ("advanced", "per"),
    "ts_pct":      ("advanced", "ts_pct"),
    "ows":         ("advanced", "ows"),
    "dws":         ("advanced", "dws"),
    "ws_40":       ("advanced", "ws_per_40"),
    "pts_pg":      ("per_game", "pts"),
    "trb_pg":      ("per_game", "reb"),
    "ast_pg":      ("per_game", "ast"),
    "stl_pg":      ("per_game", "stl"),
    "blk_pg":      ("per_game", "blk"),
    "fg_pct":      ("per_game", "fg_pct"),
    "fg3_pct":     ("per_game", "fg3_pct"),
}

PCT_STATS = {"ts_pct", "fg_pct", "fg3_pct", "ft_pct"}


# ── Data loading ──────────────────────────────────────────────────────────────

def _cache_key(cbb_url: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", cbb_url.strip("/").split("/")[-1])


def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text()) or {}
        except Exception:
            pass
    return {}


def load_cbb_stats(cbb_url: str) -> dict:
    key  = _cache_key(cbb_url)
    cbb  = _load_json(CBB_CACHE  / f"{key}.json")
    supp = _load_json(SUPP_CACHE / f"{key}.json")
    merged = dict(cbb)
    for k, v in supp.items():
        if v is not None and merged.get(k) is None:
            merged[k] = v
    return merged


def load_tank_stats(tank_players: dict, name: str) -> dict:
    p = tank_players.get(name, {})
    flat: dict[str, float | None] = {}
    for sub in ("advanced", "per_game", "per_36", "bio", "combine"):
        for k, v in p.get(sub, {}).items():
            flat[f"{sub}.{k}"] = v
    flat["draft_age"] = p.get("bio", {}).get("draft_age")
    flat["player_name"] = p.get("player_name")
    return flat


# ── Task 1: Build paired comparison dataset ───────────────────────────────────

def task1_build_pairs(tank_players: dict) -> dict[str, list[tuple[float, float, str]]]:
    """Returns {stat: [(cbb_val, tank_val, player_name), ...]}"""
    pairs: dict[str, list[tuple[float, float, str]]] = {s: [] for s in STAT_MAP}

    print("=" * 70)
    print("  Task 1: Building Paired Comparison Dataset")
    print("=" * 70)

    matched = 0
    for p in PROSPECTS_2026:
        cbb_url = p.get("cbb_url")
        name    = p["player_name"]
        if not cbb_url:
            continue
        if p.get("withdrew"):
            continue

        cbb   = load_cbb_stats(cbb_url)
        if not cbb:
            continue
        tank  = tank_players.get(name, {})
        if not tank:
            continue

        matched += 1
        for stat, (sub, tank_key) in STAT_MAP.items():
            cbb_val  = cbb.get(stat)
            tank_val = tank.get(sub, {}).get(tank_key)
            if cbb_val is not None and tank_val is not None:
                try:
                    pairs[stat].append((float(cbb_val), float(tank_val), name))
                except (TypeError, ValueError):
                    pass

    print(f"\n  Prospects with both CBB cache and Tankathon data: {matched}")
    print(f"\n  Paired observations per stat:")
    for stat, ps in pairs.items():
        flag = "  ⚠ <15" if len(ps) < 15 else ""
        print(f"    {stat:<20}: {len(ps):>3}{flag}")

    return pairs


# ── Task 2: Historical data check ────────────────────────────────────────────

def task2_historical() -> None:
    print("\n" + "=" * 70)
    print("  Task 2: Historical Tankathon Data Availability")
    print("=" * 70)
    print("\n  tankathon_2026.json covers 2026 prospects only.")
    print("  No historical Tankathon data is available for training classes 2010-2021.")
    print("  Conclusion: comparison is 2026 prospects only (n ≈ 30-50 per stat).")


# ── Task 3: Statistical comparison ───────────────────────────────────────────

def _pearson(a: list[float], b: list[float]) -> float:
    if len(a) < 3:
        return float("nan")
    r, _ = scipy_stats.pearsonr(a, b)
    return float(r)


def _verdict(stat: str, r: float, mean_delta: float, n: int) -> str:
    if n < 15:
        return "INSUFF"
    pct_stat = stat in PCT_STATS
    bias_thresh = 0.005 if pct_stat else 0.30
    if math.isnan(r):
        return "INSUFF"
    if r >= 0.95 and abs(mean_delta) < bias_thresh:
        return "MATCH"
    if r >= 0.90:
        return "BIAS"
    return "NOISE"


def task3_compare(pairs: dict) -> pd.DataFrame:
    print("\n" + "=" * 70)
    print("  Task 3: Statistical Comparison per Stat")
    print("=" * 70)

    print(f"\n  {'Stat':<20}  {'n':>3}  {'Pearson r':>9}  {'Mean Δ':>8}  {'MAD':>6}  {'Max Δ':>6}  {'Std Δ':>6}  Verdict")
    print("  " + "-" * 80)

    rows = []
    for stat, ps in pairs.items():
        n = len(ps)
        if n == 0:
            rows.append({"stat": stat, "n": 0, "r": float("nan"), "mean_d": float("nan"),
                         "mad": float("nan"), "max_d": float("nan"), "std_d": float("nan"),
                         "verdict": "INSUFF"})
            print(f"  {stat:<20}  {n:>3}  {'—':>9}  {'—':>8}  {'—':>6}  {'—':>6}  {'—':>6}  INSUFF")
            continue

        cbb_vals  = [x[0] for x in ps]
        tank_vals = [x[1] for x in ps]
        deltas    = [c - t for c, t in zip(cbb_vals, tank_vals)]

        r        = _pearson(cbb_vals, tank_vals)
        mean_d   = float(np.mean(deltas))
        mad      = float(np.mean(np.abs(deltas)))
        max_d    = float(np.max(np.abs(deltas)))
        std_d    = float(np.std(deltas, ddof=1)) if n > 1 else 0.0
        verdict  = _verdict(stat, r, mean_d, n)

        r_s    = f"{r:+.3f}" if not math.isnan(r) else "   —"
        rows.append({"stat": stat, "n": n, "r": r, "mean_d": mean_d,
                     "mad": mad, "max_d": max_d, "std_d": std_d, "verdict": verdict})
        print(f"  {stat:<20}  {n:>3}  {r_s:>9}  {mean_d:>+8.3f}  {mad:>6.3f}  {max_d:>6.3f}  {std_d:>6.3f}  {verdict}")

    return pd.DataFrame(rows)


# ── Task 4: BPM deep dive ─────────────────────────────────────────────────────

def task4_bpm_deepdive(pairs: dict, tank_players: dict) -> None:
    print("\n" + "=" * 70)
    print("  Task 4: Top 5 BPM Discrepancy Players")
    print("=" * 70)

    bpm_pairs = pairs.get("bpm_college", [])
    if len(bpm_pairs) < 3:
        print("\n  Insufficient BPM pairs for deep dive.")
        return

    sorted_pairs = sorted(bpm_pairs, key=lambda x: abs(x[0] - x[1]), reverse=True)

    print(f"\n  {'Player':<26}  {'CBB_bpm':>8}  {'Tank_bpm':>9}  {'Δbpm':>6}  "
          f"{'CBB_per':>8}  {'Tank_per':>8}  {'Δper':>5}  "
          f"{'CBB_ts':>7}  {'Tank_ts':>8}  {'Δts':>5}")
    print("  " + "-" * 98)

    for cbb_bpm, tank_bpm, name in sorted_pairs[:5]:
        cbb_url = next((p["cbb_url"] for p in PROSPECTS_2026 if p["player_name"] == name), None)
        if not cbb_url:
            continue
        cbb   = load_cbb_stats(cbb_url)
        tank  = tank_players.get(name, {})
        adv   = tank.get("advanced", {})

        cbb_per  = cbb.get("per")
        tank_per = adv.get("per")
        cbb_ts   = cbb.get("ts_pct")
        tank_ts  = adv.get("ts_pct")

        d_per = (cbb_per - tank_per) if (cbb_per and tank_per) else float("nan")
        d_ts  = (cbb_ts  - tank_ts)  if (cbb_ts  and tank_ts)  else float("nan")

        per_s  = f"{cbb_per:>8.1f}" if cbb_per  else "     n/a"
        tper_s = f"{tank_per:>8.1f}" if tank_per else "     n/a"
        dper_s = f"{d_per:>+5.1f}"  if not math.isnan(d_per) else "  n/a"
        ts_s   = f"{cbb_ts:>7.3f}"  if cbb_ts   else "    n/a"
        tts_s  = f"{tank_ts:>8.3f}" if tank_ts  else "     n/a"
        dts_s  = f"{d_ts:>+5.3f}"  if not math.isnan(d_ts)  else "  n/a"

        print(f"  {name:<26}  {cbb_bpm:>8.1f}  {tank_bpm:>9.1f}  {cbb_bpm-tank_bpm:>+6.1f}  "
              f"{per_s}  {tper_s}  {dper_s}  {ts_s}  {tts_s}  {dts_s}")

    all_deltas = [abs(c - t) for c, t, _ in bpm_pairs]
    print(f"\n  Max |Δbpm|: {max(all_deltas):.2f}   Mean |Δbpm|: {np.mean(all_deltas):.2f}")
    if max(all_deltas) <= 1.0:
        print("  → All discrepancies ≤ 1.0 BPM. Scales effectively identical.")
    elif max(all_deltas) <= 3.0:
        print("  → Discrepancies 1-3 BPM. Small calibration gap present.")
    else:
        print("  → Discrepancies > 3 BPM. Real calibration gap — treat as different scales.")


# ── Task 5: Verdict and recommendation ───────────────────────────────────────

def task5_verdict(df: pd.DataFrame) -> None:
    print("\n" + "=" * 70)
    print("  Task 5: Verdict and Recommendation")
    print("=" * 70)

    group_a = df[df["verdict"] == "MATCH"]["stat"].tolist()
    group_b = df[df["verdict"] == "BIAS"]["stat"].tolist()
    group_c = df[df["verdict"].isin(["NOISE", "INSUFF"])]["stat"].tolist()

    # Bias correction values for group B
    bias_corr = {}
    for _, row in df[df["verdict"] == "BIAS"].iterrows():
        bias_corr[row["stat"]] = row["mean_d"]

    bpm_row = df[df["stat"] == "bpm_college"]
    bpm_verdict = bpm_row["verdict"].iloc[0] if len(bpm_row) else "INSUFF"
    if bpm_verdict == "MATCH":
        bpm_rec = "Tankathon BPM safe as primary"
    elif bpm_verdict == "BIAS":
        bias = bpm_row["mean_d"].iloc[0]
        bpm_rec = f"Tankathon BPM: bias-correct before using (add {-bias:+.3f})"
    else:
        bpm_rec = "Tankathon BPM: fallback only"

    n_match = len(group_a)
    n_total = len(df[df["n"] >= 15])
    if n_match >= n_total * 0.7:
        overall = "SAFE TO EXPAND TANKATHON USE"
    elif n_match >= n_total * 0.4:
        overall = "PARTIAL EXPANSION — stat-by-stat"
    else:
        overall = "DO NOT EXPAND — scales differ"

    w = 68
    def row(left, right=""):
        content = f"  {left:<40}{right}" if right else f"  {left}"
        pad = w - 2 - len(content)
        return "│" + content + " " * max(pad, 0) + "│"

    print("\n" + "┌" + "─" * w + "┐")
    print(row("SCALE VERIFICATION RESULTS"))
    print(row(""))
    print(row("GROUP A — Safe as primary (same scale):"))
    print(row(f"  {', '.join(group_a) if group_a else 'none'}"))
    print(row(""))
    print(row("GROUP B — Use with bias correction:"))
    for stat in group_b:
        corr = bias_corr.get(stat, 0.0)
        std  = df[df["stat"] == stat]["std_d"].iloc[0]
        print(row(f"  {stat}: correction = {-corr:+.4f}  (std={std:.3f})"))
    if not group_b:
        print(row("  none"))
    print(row(""))
    print(row("GROUP C — CBB primary only:"))
    print(row(f"  {', '.join(group_c) if group_c else 'none'}"))
    print(row(""))
    print(row(f"BPM verdict: {bpm_verdict}"))
    print(row(f"Recommendation:"))
    print(row(f"  {bpm_rec}"))
    print(row(""))
    print(row(f"Overall: {overall}"))
    print("└" + "─" * w + "┘")


# ── Task 6: Draft age reliability ────────────────────────────────────────────

# Players with confirmed accurate birth dates (non-placeholder, verified)
CONFIRMED_DOBS = {
    "Cameron Boozer":   "2007-07-18",
    "AJ Dybantsa":      "2007-01-29",
    "Aday Mara":        "2005-04-07",
    "Keaton Wagler":    "2007-02-03",
    "Darryn Peterson":  "2007-01-17",
    "Koa Peat":         "2007-01-20",
    "Nate Ament":       "2006-12-10",
    "Darius Acuff Jr.": "2006-11-16",
    "Caleb Wilson":     "2006-07-18",
    "Allen Graves":     "2006-07-28",
}


def task6_draft_age(tank_players: dict) -> None:
    print("\n" + "=" * 70)
    print("  Task 6: Tankathon Draft Age Reliability")
    print("=" * 70)

    from datetime import date as date_cls
    print(f"\n  {'Player (confirmed DOB)':<28}  {'Model_age':>10}  {'Tank_age':>9}  {'Δ':>6}  Status")
    print("  " + "-" * 65)

    max_delta = 0.0
    all_deltas = []
    for name, dob_str in sorted(CONFIRMED_DOBS.items()):
        dob = date_cls.fromisoformat(dob_str)
        model_age = (DRAFT_DATE_2026 - dob).days / 365.25
        tank_p = tank_players.get(name, {})
        tank_age = tank_p.get("bio", {}).get("draft_age")
        if tank_age is None:
            print(f"  {name:<28}  {model_age:>10.2f}  {'—':>9}  {'—':>6}  no tank data")
            continue
        delta = model_age - tank_age
        all_deltas.append(abs(delta))
        max_delta = max(max_delta, abs(delta))
        flag = "  ⚠ FLAGGED" if abs(delta) > 0.15 else ""
        print(f"  {name:<28}  {model_age:>10.2f}  {tank_age:>9.2f}  {delta:>+6.2f}{flag}")

    if all_deltas:
        print(f"\n  Max |Δ| across confirmed players: {max_delta:.3f} years ({max_delta*365:.0f} days)")
        if max_delta <= 0.10:
            print("  → RELIABLE: Tankathon draft_age matches confirmed DOBs within 37 days.")
            print("  → Safe for birth date validation (flag |Δ| > 0.3 as suspected error).")
        elif max_delta <= 0.15:
            print("  → MOSTLY RELIABLE: max deviation ≤ 55 days. Usable for validation.")
        else:
            print("  → CAUTION: deviation > 55 days on confirmed DOB. Investigate before trusting.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Scale Verification: Tankathon vs CBB (Sports-Reference)")
    print()

    tank_raw     = json.loads(TANK_CACHE.read_text())
    tank_players = {p["player_name"]: p for p in tank_raw.get("players", {}).values()}
    print(f"  Tankathon players loaded: {len(tank_players)}")

    pairs = task1_build_pairs(tank_players)
    task2_historical()
    comp_df = task3_compare(pairs)
    task4_bpm_deepdive(pairs, tank_players)
    task5_verdict(comp_df)
    task6_draft_age(tank_players)


if __name__ == "__main__":
    main()
