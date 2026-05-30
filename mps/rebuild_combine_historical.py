"""
mps/rebuild_combine_historical.py

Rebuild combine_historical.json with athletic testing metrics
(lane_agility_sec, shuttle_run_sec, sprint_sec) added alongside
existing fields (height, wingspan, reach, weight, max_vertical).

API call budget: ≤25 total
  - 2010-2021: 12 years × 2 endpoints = 24 calls
  - 2022:      1 call (anthro only — holdout, no drills needed)

Run:
    backend/.venv/bin/python -m mps.rebuild_combine_historical
"""

from __future__ import annotations

import difflib
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from mps.combine_scraper import scrape_combine_athleticism, scrape_combine_measurements

DATA_DIR   = Path(__file__).parent / "data"
HIST_FILE  = DATA_DIR / "combine_historical.json"
BAK_FILE   = DATA_DIR / "combine_historical.json.bak"

TRAINING_YEARS = [2010, 2011, 2012, 2013, 2014, 2015, 2016,
                  2017, 2018, 2019, 2021]
ALL_YEARS = TRAINING_YEARS + [2020, 2022]

SLEEP_BETWEEN = 1.0   # seconds between API calls

_req_count = 0


def _season_year(draft_year: int) -> str:
    """2010 → '2010-11', 2021 → '2021-22'"""
    return f"{draft_year}-{str(draft_year + 1)[-2:]}"


def _merge_player(anthro: dict, drills: dict) -> dict:
    return {
        "height_in":          anthro.get("height_in"),
        "wingspan_in":        anthro.get("wingspan_in"),
        "standing_reach_in":  anthro.get("standing_reach_in"),
        "weight_lbs":         anthro.get("weight_lbs"),
        "max_vertical_in":    drills.get("max_vertical_in"),
        "lane_agility_sec":   drills.get("lane_agility_sec"),
        "shuttle_run_sec":    drills.get("shuttle_run_sec"),
        "sprint_sec":         drills.get("sprint_sec"),
    }


def _fuzzy_merge(
    anthro: dict[str, dict],
    drills: dict[str, dict],
) -> dict[str, dict]:
    """Merge anthro + drills by exact name first, then difflib ≥0.85."""
    merged: dict[str, dict] = {}
    drill_names = list(drills.keys())
    drill_lower = [n.lower() for n in drill_names]

    all_names = set(anthro) | set(drills)
    for name in all_names:
        a = anthro.get(name, {})
        d = drills.get(name, {})
        if not d and name in anthro:
            # Try fuzzy match in drills
            matches = difflib.get_close_matches(name.lower(), drill_lower, n=1, cutoff=0.85)
            if matches:
                idx = drill_lower.index(matches[0])
                d = drills[drill_names[idx]]
        merged[name] = _merge_player(a, d)

    return merged


def fetch_year(year: int, drills: bool = True) -> dict[str, dict]:
    global _req_count  # noqa: PLW0603
    sy = _season_year(year)
    print(f"  {year} (season={sy}):")

    # Anthro
    _req_count += 1
    print(f"    req #{_req_count}: anthro...", end=" ", flush=True)
    anthro = scrape_combine_measurements(sy)
    print(f"{len(anthro)} players")
    time.sleep(SLEEP_BETWEEN)

    if not drills:
        return _fuzzy_merge(anthro, {})

    # Drills
    _req_count += 1
    print(f"    req #{_req_count}: drills...", end=" ", flush=True)
    drill_data = scrape_combine_athleticism(sy)
    print(f"{len(drill_data)} players")
    time.sleep(SLEEP_BETWEEN)

    return _fuzzy_merge(anthro, drill_data)


def coverage_report(data: dict[int, dict[str, dict]]) -> dict[str, int]:
    metrics = ["max_vertical_in", "lane_agility_sec", "shuttle_run_sec", "sprint_sec"]
    training_players = 0
    counts = {m: 0 for m in metrics}

    # Count over training years only (2020 excluded)
    train_years = [y for y in TRAINING_YEARS if y != 2020]
    for year in train_years:
        for player, vals in data.get(year, {}).items():
            training_players += 1
            for m in metrics:
                if vals.get(m) is not None:
                    counts[m] += 1

    threshold = int(training_players * 0.30)

    print(f"\n  Coverage report (training set: {training_players} players w/ combine data)")
    print(f"  Threshold (30%): {threshold} players")
    print(f"\n  {'Metric':<22}  {'n_covered':>10}  {'pct':>6}  Status")
    print("  " + "-" * 52)

    proceed = {}
    for m in metrics:
        n = counts[m]
        pct = n / training_players * 100 if training_players else 0
        ok = n >= threshold
        proceed[m] = ok
        status = "✓ proceed" if ok else "✗ exclude (too sparse)"
        print(f"  {m:<22}  {n:>10}  {pct:>5.1f}%  {status}")

    return proceed


def validate_2019(data: dict[int, dict[str, dict]]) -> None:
    print("\n  Validation — 2019 class (Zion Williamson, Ja Morant):")
    year_data = data.get(2019, {})
    for name in ["Zion Williamson", "Ja Morant"]:
        p = year_data.get(name)
        if p:
            print(f"    {name}:")
            for k, v in p.items():
                if v is not None:
                    print(f"      {k}: {v}")
        else:
            print(f"    {name}: NOT FOUND in 2019 combine data")


def main() -> None:
    global _req_count
    print("Rebuild combine_historical.json")
    print(f"Budget: ≤25 API calls  |  Years: {ALL_YEARS}")
    print()

    # Backup
    if HIST_FILE.exists():
        shutil.copy2(HIST_FILE, BAK_FILE)
        print(f"  Backup: {BAK_FILE}")

    # Load existing data as fallback
    existing: dict[int, dict[str, dict]] = {}
    if BAK_FILE.exists():
        try:
            raw = json.loads(BAK_FILE.read_text())
            raw_data = raw.get("data", raw)
            existing = {int(y): v for y, v in raw_data.items()}
        except Exception:
            pass

    data: dict[int, dict[str, dict]] = {}

    # 2010-2021 with drills
    for year in TRAINING_YEARS:
        if _req_count >= 24:
            print(f"  Budget limit reached — skipping {year}")
            data[year] = existing.get(year, {})
            continue
        data[year] = fetch_year(year, drills=True)

    # 2020 (not in training but keep in file)
    if _req_count < 24:
        data[2020] = fetch_year(2020, drills=True)
    else:
        data[2020] = existing.get(2020, {})
        print(f"  2020: using cached ({len(data[2020])} players)")

    # 2022 — anthro only
    if _req_count < 25:
        print(f"  2022 (anthro only):")
        _req_count += 1
        print(f"    req #{_req_count}: anthro...", end=" ", flush=True)
        a = scrape_combine_measurements("2022-23")
        print(f"{len(a)} players")
        data[2022] = {name: _merge_player(vals, {}) for name, vals in a.items()}
    else:
        data[2022] = existing.get(2022, {})
        print(f"  2022: using cached ({len(data[2022])} players)")

    # Per-year summary
    print(f"\n  Per-year coverage:")
    print(f"  {'Year':>4}  {'Players':>8}  {'Vertical':>9}  {'Agility':>8}  "
          f"{'Shuttle':>8}  {'Sprint':>7}")
    print("  " + "-" * 56)
    for year in sorted(data.keys()):
        players = data[year]
        n = len(players)
        nv = sum(1 for p in players.values() if p.get("max_vertical_in") is not None)
        na = sum(1 for p in players.values() if p.get("lane_agility_sec") is not None)
        ns = sum(1 for p in players.values() if p.get("shuttle_run_sec") is not None)
        nsp = sum(1 for p in players.values() if p.get("sprint_sec") is not None)
        print(f"  {year:>4}  {n:>8}  {nv:>9}  {na:>8}  {ns:>8}  {nsp:>7}")

    proceed = coverage_report(data)
    validate_2019(data)

    # Save
    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "seasons": sorted(str(y) for y in data.keys()),
        "data": {str(y): v for y, v in sorted(data.items())},
    }
    HIST_FILE.write_text(json.dumps(output, indent=2))
    print(f"\n  Saved: {HIST_FILE}")
    print(f"  Total API calls: {_req_count}")

    print(f"\n  Metrics proceeding to LOYO test: "
          f"{[m for m, ok in proceed.items() if ok]}")


if __name__ == "__main__":
    main()
