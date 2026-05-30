"""
mps/join_consensus_ranks.py

Phase 2: Join scraped NBADraft.net pre-draft consensus ranks to training CSV.
Uses fuzzy name matching within each draft year. Applies T4 tier-flat
transformation. Writes mps/data/mps_dataset_with_consensus.csv.

Run:
    backend/.venv/bin/python -m mps.join_consensus_ranks
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

import pandas as pd

DATA_DIR     = Path(__file__).parent / "data"
CACHE_PATH   = DATA_DIR / "historical_consensus.json"
DATASET_PATH = DATA_DIR / "mps_dataset_raw.csv"
OUTPUT_PATH  = DATA_DIR / "mps_dataset_with_consensus.csv"

TRAINING_YEARS = {2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2021}


# ── Name normalization ────────────────────────────────────────────────────────

def _normalize(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[.''\-,]", " ", name)
    name = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _last_name(name: str) -> str:
    parts = _normalize(name).split()
    return parts[-1] if parts else ""


# ── T4 transform (identical to scorer.py) ────────────────────────────────────

def _t4_tier_score(rank: int | None) -> float:
    if rank is None:
        return 0.050
    if rank <= 5:  return 0.900
    if rank <= 14: return 0.700
    if rank <= 30: return 0.500
    if rank <= 60: return 0.250
    return 0.050  # 61+


# ── Matching ──────────────────────────────────────────────────────────────────

def _match_player(
    csv_name: str,
    board: list[dict],
) -> tuple[int | None, float, str]:
    """
    Match csv_name against board. Returns (rank, confidence, method).
    rank=None if no match found.
    """
    norm_csv   = _normalize(csv_name)
    last_csv   = _last_name(csv_name)
    board_norms = [_normalize(p["player_name"]) for p in board]
    board_lasts = [_last_name(p["player_name"]) for p in board]

    # Priority 1: exact normalized match
    for i, norm_b in enumerate(board_norms):
        if norm_csv == norm_b:
            return board[i]["rank"], 1.0, "exact"

    # Priority 2: difflib close match on full normalized name
    matches = difflib.get_close_matches(norm_csv, board_norms, n=1, cutoff=0.80)
    if matches:
        idx = board_norms.index(matches[0])
        score = difflib.SequenceMatcher(None, norm_csv, matches[0]).ratio()
        return board[idx]["rank"], score, "fuzzy"

    # Priority 3: last-name-only if unique in board AND first initial matches
    first_initial_csv = norm_csv[0] if norm_csv else ""
    last_matches = [
        i for i, (l, nb) in enumerate(zip(board_lasts, board_norms))
        if l == last_csv and len(last_csv) >= 5 and nb[0] == first_initial_csv
    ]
    if len(last_matches) == 1:
        i = last_matches[0]
        return board[i]["rank"], 0.75, "last_name"

    return None, 0.0, "unmatched"


# ── Main join ─────────────────────────────────────────────────────────────────

def main() -> None:
    print("Phase 2: Join Consensus Ranks to Training CSV")
    print()

    with CACHE_PATH.open() as f:
        cache = json.load(f)

    boards: dict[int, list[dict]] = {}
    for year_str, players in cache["sources"]["nbadraft_net"].items():
        boards[int(year_str)] = players

    df = pd.read_csv(DATASET_PATH)
    df = df[df["draft_year"].isin(TRAINING_YEARS) & df["vorp_yr2_5_avg"].notna()].copy()
    print(f"  Training rows: {len(df)}")

    # Per-year matching
    results: list[dict] = []
    all_low_conf: list[dict] = []

    print(f"\n  {'Year':>4}  {'Board n':>7}  {'Matched':>8}  {'Low-conf':>9}  {'Unmatched':>10}  {'Coverage':>9}")
    print("  " + "-" * 62)

    for year in sorted(df["draft_year"].unique()):
        year_df   = df[df["draft_year"] == year]
        board     = boards.get(year, [])
        board_n   = len(board)

        matched = unmatched = low_conf = 0
        for _, row in year_df.iterrows():
            csv_name = str(row["player_name"])
            rank, conf, method = _match_player(csv_name, board)

            if rank is not None:
                matched += 1
                if conf < 0.90:
                    low_conf += 1
                    all_low_conf.append({
                        "year": year, "csv_name": csv_name,
                        "board_name": next(
                            (b["player_name"] for b in board if b["rank"] == rank), "?"
                        ),
                        "conf": round(conf, 3), "method": method, "rank": rank,
                    })
            else:
                unmatched += 1

            results.append({
                "player_name":             row["player_name"],
                "draft_year":              year,
                "consensus_rank_nbadraft": rank,
                "consensus_tier_score":    _t4_tier_score(rank),
                "consensus_source": (
                    "nbadraft_net" if rank is not None else
                    ("no_board" if board_n == 0 else "unmatched")
                ),
                "_conf":   conf,
                "_method": method,
            })

        cov = f"{matched/(matched+unmatched):.0%}" if (matched+unmatched) > 0 else "—"
        print(f"  {year:>4}  {board_n:>7}  {matched:>8}  {low_conf:>9}  {unmatched:>10}  {cov:>9}")

    # Coverage gate
    res_df = pd.DataFrame(results)
    has_board_years = {y for y in sorted(df["draft_year"].unique()) if boards.get(y)}
    rows_with_board = df[df["draft_year"].isin(has_board_years)]
    matched_rows = res_df[res_df["consensus_rank_nbadraft"].notna()]

    overall_match = len(matched_rows) / len(df)
    board_year_match = len(matched_rows) / len(rows_with_board) if len(rows_with_board) else 0

    print(f"\n  Overall coverage:    {len(matched_rows)}/{len(df)} = {overall_match:.1%}")
    print(f"  Board-year coverage: {len(matched_rows)}/{len(rows_with_board)} = {board_year_match:.1%}")
    print(f"  Missing years (no board): {sorted(y for y in TRAINING_YEARS if not boards.get(y))}")

    # Low-confidence matches
    print(f"\n  Low-confidence matches (conf < 0.90): {len(all_low_conf)}")
    if all_low_conf:
        print(f"  {'Year':>4}  {'CSV name':<30}  {'Board name':<30}  {'Conf':>5}  {'Method':<10}  {'Rank':>5}")
        print("  " + "-" * 90)
        for m in sorted(all_low_conf, key=lambda x: x["conf"]):
            print(f"  {m['year']:>4}  {m['csv_name']:<30}  {m['board_name']:<30}  "
                  f"{m['conf']:>5.3f}  {m['method']:<10}  {m['rank']:>5}")

    # Tier distribution
    tier_counts = {
        "0.900 (top 5)":   (res_df["consensus_tier_score"] == 0.900).sum(),
        "0.700 (lottery)": (res_df["consensus_tier_score"] == 0.700).sum(),
        "0.500 (late 1st)":(res_df["consensus_tier_score"] == 0.500).sum(),
        "0.250 (2nd rd)":  (res_df["consensus_tier_score"] == 0.250).sum(),
        "0.050 (fringe/unranked)": (res_df["consensus_tier_score"] == 0.050).sum(),
    }
    print(f"\n  T4 tier distribution:")
    for tier, count in tier_counts.items():
        print(f"    {tier}: {count}")

    # Threshold: 70% overall OR 80% board-year coverage (3 years have no archive = structural gap)
    if overall_match < 0.70 and board_year_match < 0.80:
        print(f"\n  STOP: coverage {overall_match:.1%} overall / {board_year_match:.1%} board-year — both below threshold.")
        print(f"  Do not write output CSV. Investigate scraping before proceeding.")
        return
    if overall_match < 0.70:
        missing_yrs = sorted(y for y in TRAINING_YEARS if not boards.get(y))
        print(f"\n  NOTE: Overall {overall_match:.1%} < 70% threshold, but board-year coverage is {board_year_match:.1%}")
        print(f"  Missing years have no Wayback archive ({missing_yrs}) — structural gap, not matching failure.")
        print(f"  Proceeding — consensus feature will be neutral (0.050) for those years' folds.")

    # Merge consensus columns onto original training df
    lookup = res_df.set_index(["player_name", "draft_year"])
    df = df.copy()
    df["consensus_rank_nbadraft"] = df.apply(
        lambda r: lookup.loc[(r["player_name"], r["draft_year"]), "consensus_rank_nbadraft"]
        if (r["player_name"], r["draft_year"]) in lookup.index else None,
        axis=1,
    )
    df["consensus_tier_score"] = df.apply(
        lambda r: lookup.loc[(r["player_name"], r["draft_year"]), "consensus_tier_score"]
        if (r["player_name"], r["draft_year"]) in lookup.index else 0.050,
        axis=1,
    )
    df["consensus_source"] = df.apply(
        lambda r: lookup.loc[(r["player_name"], r["draft_year"]), "consensus_source"]
        if (r["player_name"], r["draft_year"]) in lookup.index else "unmatched",
        axis=1,
    )

    df.to_csv(OUTPUT_PATH, index=False)
    print(f"\n  Written: {OUTPUT_PATH}")
    print(f"  Columns added: consensus_rank_nbadraft, consensus_tier_score, consensus_source")


if __name__ == "__main__":
    main()
