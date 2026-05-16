"""
nba_lambda_fix.py — Emergency lambda asymmetry fix for BPR leaderboard.

Problem: role players (λ=700) ride noisy stints to top-3; stars (λ=200) can't
escape compressed priors. Siakam #3, Jokić not top-20, SGA #16.

Tests 4 asymmetric lambda configs simultaneously. Writes best to DB if it
passes: stars ≥7 in top-20 AND top-30 overlap ≥20.

Run:
    backend/.venv/bin/python nba_lambda_fix.py
"""

from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.stats
from django.utils import timezone

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from nba.analytics.rapm import _solve_augmented, build_design_matrix, build_nba_observations
from nba.models import NBAPlayer, NBAPlayerSeasonStats

# ── Constants ──────────────────────────────────────────────────────────────────

SEASON_YEAR  = 2026
RAPM_WINDOW  = 3
METRICS_CSV  = SCRIPT_DIR / "metrics_output" / "nba_metrics_2025_26.csv"

# ≥2000 min, ≥1200 min, ≥600 min, <600 min
CUSTOM_CONFIGS: dict[str, tuple[float, float, float, float]] = {
    "C1_asym_moderate":     (100.0,  300.0, 1200.0, 2000.0),
    "C2_asym_aggressive":   ( 50.0,  200.0, 1500.0, 2500.0),
    "C3_asym_conservative": (150.0,  350.0, 1000.0, 1800.0),
    "C4_star_focused":      ( 75.0,  400.0, 1500.0, 2000.0),
}

# Normalized names — fuzzy match will catch variants (Jokić/Jokic etc.)
TARGET_STARS_SUBSTRINGS = [
    "nikola joki",   # Jokić / Jokic
    "shai gilgeous",
    "giannis antet",
    "lebron james",
    "victor wembanyama",
    "luka don",      # Dončić / Doncic
    "kevin durant",
    "stephen curry",
    "anthony edwards",
]

NOISE_PLAYERS_SUBSTRINGS = [
    "ajay mitchell",
    "davion mitchell",
    "pascal siakam",
    "julian champagnie",
    "nique clifford",
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def norm_name(s: str) -> str:
    s = str(s).lower().strip()
    s = s.encode("ascii", errors="ignore").decode()
    s = re.sub(r"[^a-z ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


# ── Data loading ───────────────────────────────────────────────────────────────

def load_priors(season_year: int) -> tuple[dict, dict, dict]:
    """prior_obpr, prior_dbpr, minutes_by_nba_id — keyed by NBA.com player_id."""
    box_stats = list(
        NBAPlayerSeasonStats.objects.filter(
            season__year=season_year,
            season_type="regular",
            box_obpr__isnull=False,
        ).select_related("player").only(
            "player__player_id", "box_obpr", "box_dbpr", "mpg", "gp",
        )
    )
    prior_obpr, prior_dbpr, minutes = {}, {}, {}
    for row in box_stats:
        nba_id = row.player.player_id
        if nba_id:
            prior_obpr[nba_id] = row.box_obpr or 0.0
            prior_dbpr[nba_id] = row.box_dbpr or 0.0
            minutes[nba_id]    = (row.mpg or 0.0) * (row.gp or 0)
    print(f"  Priors loaded: {len(prior_obpr)} players")
    return prior_obpr, prior_dbpr, minutes


def load_stints(season_year: int, rapm_window: int) -> tuple[list, dict, int]:
    rapm_years = list(range(season_year - rapm_window + 1, season_year + 1))
    print(f"  Loading stints for {rapm_years}...")
    observations = build_nba_observations(season_year=season_year, rapm_years=rapm_years)
    all_ps: set[tuple[int, int]] = set()
    for obs in observations:
        yr = obs["season_year"]
        for pid in obs["home_player_ids"] + obs["away_player_ids"]:
            all_ps.add((pid, yr))
    player_season_index = {ps: i for i, ps in enumerate(sorted(all_ps))}
    n_ps = len(player_season_index)
    print(f"  {len(observations)} observations, {n_ps} player-season columns")
    return observations, player_season_index, n_ps


def build_name_map(nba_ids: list[int]) -> dict[int, str]:
    """nba_id (NBA.com int) → normalized name."""
    return {
        p.player_id: norm_name(p.name)
        for p in NBAPlayer.objects.filter(player_id__in=nba_ids).only("player_id", "name")
        if p.player_id
    }


def load_bpm_data() -> tuple[dict[str, float], dict[str, float]]:
    """Load BPM and minutes from metrics CSV. Returns {norm_name: bpm}, {norm_name: minutes}."""
    df = pd.read_csv(METRICS_CSV)
    multi = df["team"].str.match(r"^\d+TM$", na=False)
    df = df[~multi].sort_values("minutes", ascending=False).drop_duplicates("player_name", keep="first")
    bpm_map, min_map = {}, {}
    for _, row in df.iterrows():
        name = norm_name(str(row.get("player_name", "")))
        if not name:
            continue
        bpm = row.get("BPM")
        mins = row.get("minutes")
        if pd.notna(bpm):
            try:
                bpm_map[name] = float(bpm)
            except (ValueError, TypeError):
                pass
        if pd.notna(mins):
            try:
                min_map[name] = float(mins)
            except (ValueError, TypeError):
                pass
    print(f"  BPM data: {len(bpm_map)} players")
    return bpm_map, min_map


# ── Lambda helpers ─────────────────────────────────────────────────────────────

def stratified_lambda(minutes: float, tiers: tuple) -> float:
    if minutes >= 2000:   return tiers[0]
    elif minutes >= 1200: return tiers[1]
    elif minutes >= 600:  return tiers[2]
    else:                 return tiers[3]


def build_lambda_array(
    player_season_keys: list,
    minutes_by_nba_id: dict,
    tiers: tuple,
    n_ps: int,
) -> np.ndarray:
    arr = np.zeros(2 * n_ps)
    for i, (pid, _yr) in enumerate(player_season_keys):
        lam = stratified_lambda(minutes_by_nba_id.get(pid, 0.0), tiers)
        arr[i] = lam
        arr[n_ps + i] = lam
    return arr


# ── Metrics ────────────────────────────────────────────────────────────────────

def compute_config_metrics(
    obpr: dict[int, float],
    dbpr: dict[int, float],
    bpm_map: dict[str, float],
    min_map: dict[str, float],
    name_map: dict[int, str],
) -> dict:
    # Build bpr_by_name
    bpr_by_name: dict[str, float] = {}
    nba_id_by_name: dict[str, int] = {}
    for nba_id, o in obpr.items():
        name = name_map.get(nba_id)
        if name:
            bpr_by_name[name] = o + dbpr.get(nba_id, 0.0)
            nba_id_by_name[name] = nba_id

    # Rank all by BPR
    bpr_ranked = sorted(bpr_by_name, key=bpr_by_name.get, reverse=True)
    bpr_rank   = {n: i + 1 for i, n in enumerate(bpr_ranked)}
    bpm_ranked = sorted(bpm_map, key=bpm_map.get, reverse=True)
    bpm_rank   = {n: i + 1 for i, n in enumerate(bpm_ranked)}

    top20_names = set(bpr_ranked[:20])

    # Stars in top 20
    stars_in_top20 = sum(
        1 for sub in TARGET_STARS_SUBSTRINGS
        if any(sub in n for n in top20_names)
    )

    # Noise player ranks
    noise_ranks: dict[str, int] = {}
    for sub in NOISE_PLAYERS_SUBSTRINGS:
        match = next((n for n in bpr_rank if sub in n), None)
        noise_ranks[sub] = bpr_rank.get(match, 999) if match else 999

    # Individual star details
    star_details: dict[str, dict] = {}
    for sub in TARGET_STARS_SUBSTRINGS:
        match = next((n for n in bpr_by_name if sub in n), None)
        if match:
            bpm_match = next((n for n in bpm_map if sub in n), None)
            star_details[sub] = {
                "bpr": round(bpr_by_name[match], 2),
                "bpr_rank": bpr_rank[match],
                "bpm": round(bpm_map.get(bpm_match, float("nan")), 2) if bpm_match else float("nan"),
                "bpm_rank": bpm_rank.get(bpm_match, 999) if bpm_match else 999,
                "name": match,
            }

    # ≥1200 min — Pearson r and top-30 overlap
    common_1200 = [n for n in bpr_by_name if n in bpm_map and min_map.get(n, 0) >= 1200]
    if len(common_1200) >= 10:
        bpr_v = [bpr_by_name[n] for n in common_1200]
        bpm_v = [bpm_map[n]     for n in common_1200]
        pearson_r = float(scipy.stats.pearsonr(bpr_v, bpm_v)[0])
        top30_bpr_set = set(sorted(common_1200, key=bpr_by_name.get, reverse=True)[:30])
        top30_bpm_set = set(sorted(common_1200, key=bpm_map.get,     reverse=True)[:30])
        top30_overlap = len(top30_bpr_set & top30_bpm_set)
    else:
        pearson_r, top30_overlap = float("nan"), 0

    sd = float(np.std(list(bpr_by_name.values())))

    return {
        "stars_in_top20": stars_in_top20,
        "noise_ranks":    noise_ranks,
        "star_details":   star_details,
        "pearson_r_1200": round(pearson_r, 3),
        "top30_overlap":  top30_overlap,
        "sd":             round(sd, 3),
        "bpr_rank":       bpr_rank,
        "bpm_rank":       bpm_rank,
        "bpr_ranked":     bpr_ranked,
        "bpr_by_name":    bpr_by_name,
        "nba_id_by_name": nba_id_by_name,
    }


# ── Output ─────────────────────────────────────────────────────────────────────

def print_config_leaderboard(cfg_name: str, m: dict, bpm_map: dict) -> None:
    print(f"\n{'='*70}")
    print(f"[{cfg_name}] tiers — top 20 by BPR")
    print(f"{'='*70}")
    print(f"  {'Player':<30} {'BPR':>6} {'BPM':>6} {'BPRrk':>6} {'BPMrk':>6}")
    print(f"  {'-'*55}")
    for rank, name in enumerate(m["bpr_ranked"][:20], 1):
        bpr = m["bpr_by_name"][name]
        bpm_name = next((n for n in bpm_map if any(sub in name for sub in name.split()[:1])), None)
        # Better: exact lookup
        bpm = bpm_map.get(name, float("nan"))
        bpm_rk = m["bpm_rank"].get(name, 999)
        is_star = any(sub in name for sub in TARGET_STARS_SUBSTRINGS)
        is_noise = any(sub in name for sub in NOISE_PLAYERS_SUBSTRINGS)
        flag = " ★" if is_star else (" ⚠" if is_noise else "")
        print(f"  {name:<30} {bpr:>6.2f} {bpm:>6.2f} {rank:>6} {bpm_rk:>6}{flag}")


def print_comparison_table(results: dict) -> None:
    print(f"\n{'='*90}")
    print("LAMBDA SWEEP COMPARISON TABLE")
    print(f"{'='*90}")
    print(f"  {'Config':<22} {'Stars/9':>7} {'Overlap':>8} {'PearsonR':>9} {'Siakam':>7} {'Jokic':>6} {'SGA':>5} {'SD':>6}")
    print(f"  {'-'*75}")
    for name, res in results.items():
        siakam_rk = next((res["noise_ranks"].get(s, 999) for s in NOISE_PLAYERS_SUBSTRINGS if "siakam" in s), 999)
        jokic     = res["star_details"].get("nikola joki", {})
        sga       = res["star_details"].get("shai gilgeous", {})
        print(
            f"  {name:<22} {res['stars_in_top20']:>7} {res['top30_overlap']:>8} "
            f"{res['pearson_r_1200']:>9.3f} {siakam_rk:>7} "
            f"{jokic.get('bpr_rank', 999):>6} {sga.get('bpr_rank', 999):>5} {res['sd']:>6.3f}"
        )
    print(f"  {'='*75}")
    print(f"  {'CURRENT':<22} {'7/9':>7} {'7/30':>8} {'0.350':>9} {'3':>7} {'NR':>6} {'16':>5} {'~4.6':>6}")
    print(f"  {'TARGETS':<22} {'≥7':>7} {'≥20':>8} {'>0.60':>9} {'>30':>7} {'≤5':>6} {'≤8':>5} {'<6.0':>6}")
    print(f"{'='*90}")


def select_best(results: dict) -> str:
    def score(name):
        r = results[name]
        p1 = r["stars_in_top20"] >= 7
        p2 = r["top30_overlap"]  >= 20
        p3 = r["pearson_r_1200"] >= 0.60
        siakam_rk = next((r["noise_ranks"].get(s, 999) for s in NOISE_PLAYERS_SUBSTRINGS if "siakam" in s), 999)
        p4 = siakam_rk > 30
        return (int(p1), int(p2), int(p3), int(p4), r["pearson_r_1200"])
    return max(results, key=score)


def write_to_db(obpr: dict, dbpr: dict, season_year: int) -> int:
    from django.utils import timezone
    now = timezone.now()
    stats_qs = NBAPlayerSeasonStats.objects.filter(
        season__year=season_year, season_type="regular"
    ).select_related("player")
    updated = 0
    for stat_row in stats_qs:
        nba_id = stat_row.player.player_id
        if nba_id not in obpr:
            continue
        o = obpr[nba_id]
        d = dbpr[nba_id]
        stat_row.obpr  = round(o, 4)
        stat_row.dbpr  = round(d, 4)
        stat_row.bpr   = round(o + d, 4)
        stat_row.updated_at = now
        stat_row.save(update_fields=["obpr", "dbpr", "bpr", "updated_at"])
        updated += 1
    return updated


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print("NBA BPR Lambda Asymmetry Fix")
    print("=" * 70)

    # ── 1. Load data ───────────────────────────────────────────────────────────
    print("\n[LOADING]")
    prior_obpr, prior_dbpr, minutes_by_nba_id = load_priors(SEASON_YEAR)
    observations, player_season_index, n_ps = load_stints(SEASON_YEAR, RAPM_WINDOW)
    bpm_map, min_map = load_bpm_data()
    name_map = build_name_map(list(prior_obpr.keys()))

    # ── 2. Build design matrix once ────────────────────────────────────────────
    print("\n[BUILDING DESIGN MATRIX]")
    player_season_keys = sorted(player_season_index, key=player_season_index.get)
    n_features = 2 + 2 * n_ps
    prior_means = np.zeros(n_features)
    for i, (pid, _yr) in enumerate(player_season_keys):
        prior_means[2 + i]         =  prior_obpr.get(pid, 0.0)
        prior_means[2 + n_ps + i]  = -prior_dbpr.get(pid, 0.0)

    X, y, weights = build_design_matrix(observations, player_season_index, n_ps)
    player_col_slice = (2, 2 + 2 * n_ps)
    print(f"  Matrix: {X.shape[0]} × {X.shape[1]}")

    # ── 3. Test all configs ────────────────────────────────────────────────────
    print("\n[TESTING CONFIGS]")
    results: dict[str, dict] = {}
    for cfg_name, tiers in CUSTOM_CONFIGS.items():
        print(f"  {cfg_name}  tiers={tiers}...")
        lam_arr = build_lambda_array(player_season_keys, minutes_by_nba_id, tiers, n_ps)
        beta = _solve_augmented(
            X, y, weights,
            lambda_val=tiers[0],
            prior_means=prior_means,
            player_col_slice=player_col_slice,
            per_player_lambda=lam_arr,
        )
        obpr = {pid: float(beta[2 + i])       for i, (pid, yr) in enumerate(player_season_keys) if yr == SEASON_YEAR}
        dbpr = {pid: float(-beta[2 + n_ps + i]) for i, (pid, yr) in enumerate(player_season_keys) if yr == SEASON_YEAR}
        metrics = compute_config_metrics(obpr, dbpr, bpm_map, min_map, name_map)
        results[cfg_name] = {**metrics, "obpr": obpr, "dbpr": dbpr, "tiers": tiers}
        print_config_leaderboard(cfg_name, metrics, bpm_map)

    # ── 4. Comparison table ────────────────────────────────────────────────────
    print_comparison_table(results)

    # ── 5. Select best ─────────────────────────────────────────────────────────
    best_name = select_best(results)
    best = results[best_name]
    print(f"\nSelected config: {best_name}  tiers={best['tiers']}")

    # ── 6. Print star details for best ────────────────────────────────────────
    print(f"\n[STAR DETAILS — {best_name}]")
    print(f"  {'Substring':<25} {'BPR':>6} {'BPRrk':>6} {'BPM':>6} {'BPMrk':>6}")
    print(f"  {'-'*52}")
    for sub, det in sorted(best["star_details"].items(), key=lambda x: x[1]["bpr_rank"]):
        print(f"  {sub:<25} {det['bpr']:>6.2f} {det['bpr_rank']:>6} {det['bpm']:>6.2f} {det['bpm_rank']:>6}")

    print(f"\n[NOISE PLAYER RANKS — {best_name}]")
    for sub, rk in sorted(best["noise_ranks"].items(), key=lambda x: x[1]):
        print(f"  {sub:<28} rank={rk}")

    # ── 7. Write to DB if passes criteria ─────────────────────────────────────
    passes_p1 = best["stars_in_top20"] >= 7
    passes_p2 = best["top30_overlap"]  >= 20

    print(f"\n{'='*70}")
    print("LEADERBOARD FIX RESULTS")
    print(f"{'='*70}")
    print(f"  Best config:              {best_name}  tiers={best['tiers']}")
    print(f"  Stars in top 20:          {best['stars_in_top20']}/9  (was ~3/9, target ≥7)  {'✓' if passes_p1 else '✗'}")
    print(f"  Top-30 overlap (≥1200m):  {best['top30_overlap']}/30  (was 7/30, target ≥20)  {'✓' if passes_p2 else '✗'}")
    print(f"  Pearson r (≥1200m):       {best['pearson_r_1200']:.3f}  (was 0.350, target >0.60)")
    print(f"  SD of BPR:                {best['sd']:.3f}  (target 3.0-6.0)")

    siakam_rk = next((best["noise_ranks"].get(s, 999) for s in NOISE_PLAYERS_SUBSTRINGS if "siakam" in s), 999)
    jokic_d = best["star_details"].get("nikola joki", {})
    sga_d   = best["star_details"].get("shai gilgeous", {})
    wemb_d  = best["star_details"].get("victor wembanyama", {})
    print(f"  Siakam rank:              #{siakam_rk}  (was #3)")
    print(f"  Jokić rank:               #{jokic_d.get('bpr_rank','NR')}  BPR={jokic_d.get('bpr','?')}  (was not top-20)")
    print(f"  SGA rank:                 #{sga_d.get('bpr_rank','NR')}    BPR={sga_d.get('bpr','?')}  (was #16)")
    print(f"  Wembanyama rank:          #{wemb_d.get('bpr_rank','NR')}  BPR={wemb_d.get('bpr','?')}")

    if passes_p1 and passes_p2:
        print(f"\n  Both primary checks passed — WRITING TO DB")
        n = write_to_db(best["obpr"], best["dbpr"], SEASON_YEAR)
        print(f"  Written to DB: YES ({n} players updated)")
    else:
        print(f"\n  NOT WRITTEN TO DB — {int(passes_p1)+int(passes_p2)}/2 primary checks passed.")
        print("  Adjust configs and re-run, or lower thresholds if results look acceptable.")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
