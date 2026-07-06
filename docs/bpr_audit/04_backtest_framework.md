# BPR Audit — 04: Leak-Free Backtest Framework & Baselines

**Date:** 2026-07-02
**Command:** `python manage.py backtest_bpr_suite --mode {cross-season, rolling, player}`
**Outputs:** `backend/backtest_output/bpr_suite/ncaa/<run-name>/` — `manifest.json` (args, model version, git SHA), `summary.csv` (metrics per arm × season × cutoff × split), `games.csv` (per-game predictions), `calibration.csv`, `player_validation.csv`. No DB writes anywhere; all pipeline runs use `persist=False`.

---

## 1. Methodology

### Why a new framework
The prior within-season tool (`backtest_bpr_walkforward`) leaked: `run_bpr_season(cutoff_date)` date-bounds only the RAPM stint dataset, while box features and team ratings loaded full-season values (weakness report 3.1/3.2). It is now marked DEPRECATED in its docstring. `backtest_bpr_game_prediction` is descriptive-only (full-season ratings on the same season's games).

### Leak-free within-season evaluation (rolling mode)
Per season × cutoff:
1. `through_date.build_team_adj_em_through_date` — iterative opponent-adjusted team EM from games ≤ cutoff (lightweight mirror of `compute_adjusted_ratings`; omits elevation/recency/importance).
2. `through_date.build_pss_features_through_date` — every box + on-court feature the pipeline consumes, rebuilt from per-game `PlayerGameStats`/`PlayerGameStint` rows ≤ cutoff (`on_court_adj_em` replicates the Phase E formula with the through-date team map).
3. `run_bpr_season(cutoff_date, persist=False, player_season_stats_override=…, opp_quality_map_override=…, team_adj_em_map_override=…)` — date-bounded RAPM **and** date-bounded priors.
4. Rosters (mpg) from date-bounded game logs — not season `PlayerSeasonStats`.
5. Per-arm OLS (`margin ~ β0 + β1·strength_diff + β2·home`) fit on games ≤ cutoff; predict games in `(cutoff, next-cutoff]` (`--horizon window`) or to season end (`--horizon full`).

**Acceptance evidence** (`manage.py validate_bpr_through_date --season 2026`):
- Through-date team adj_em at season-end cutoff vs stored `TeamSeasonRatings`: **r = 0.993** (bar 0.97).
- Box-rate features vs stored `PlayerSeasonStats`: **r = 1.000** exact, all 17 features.
- `on_court_adj_em`: **r = 0.973** (bar 0.90 — simplified team engine + phantom-stint differences, documented).
- Mid-season anti-leak: 4,406/4,406 players with post-cutoff games differ from season-end values.
- Static guards (`ncaa/tests/test_bpr_through_date.py`): every ORM filter in `through_date.py` carries a game-date bound; module cannot import `PlayerSeasonStats`/`TeamSeasonRatings`. Run with `pytest ncaa/tests/test_bpr_through_date.py -o addopts=""`.

### Cross-season mode
Season-Y stored ratings → season-Y+1 games, Y+1 rosters. OLS calibration fit **on season-Y games only** (every input predates the evaluated season). Reuses the already-clean `backtest_bpr_margin` design with added log loss, calibration buckets, and splits.

### Arms
`bpr` (final prior-informed), `box_bpr`, `baseline` (RAPM-only — the pure lineup-signal lower bound), `adj_em` (team-only; through-date version in rolling mode), `home_only`, plus `--extra-ratings-json {player_id: bpr}` — the hook for Phase 5+ experiments: any model variant dumps a ratings JSON and becomes a compared arm with zero framework changes.

### Metrics & splits
Per arm × season × cutoff: n, margin MAE/RMSE, win accuracy, Brier, log loss, AUC, mean roster coverage, 10-bucket probability calibration. Splits: home/away vs neutral, conference vs non-conference, high-major/mid-major/cross-tier (power-5 set from `TeamSeasonStats.conference`). Note: 2026 neutral split is empty until the missing `neutral_site` flags (bug 1.5) are backfilled.

---

## 2. Baseline results — NCAA v1.6 (the numbers experiments must beat)

### Cross-season (`baseline_v16_cross`): Y ratings → Y+1 margins, RMSE / win-acc

| Pair | bpr | box_bpr | baseline (RAPM) | adj_em | home_only |
|---|---|---|---|---|---|
| 2021→2022 | 13.24 / .624 | 13.24 / .608 | 12.70 / .644 | **12.33 / .645** | 13.74 / .586 |
| 2022→2023 | 13.24 / .645 | 13.30 / .642 | 12.72 / .668 | **12.68 / .660** | 13.84 / .638 |
| 2023→2024 | 13.52 / .650 | 13.53 / .650 | 13.09 / .660 | **13.02 / .660** | 14.32 / .639 |
| 2024→2025 | 13.66 / .652 | **12.92 / .673** | 13.32 / .660 | 13.29 / .669 | 14.63 / .643 |

(2025→2026 skipped automatically: no stored 2025 BPR. Player-arm coverage ≈ 0.40 — roster turnover means 60% of Y+1 minutes have no Y rating; adj_em coverage ≈ 0.99.)

**Reading:**
- Final `bpr` **loses to its own `baseline` RAPM arm in all four pairs** and to team-only `adj_em` everywhere. The box-prior machinery, as tuned, *hurts* year-ahead prediction.
- 2024→2025 flips: `box_bpr` becomes the best arm overall (12.92, beating adj_em). Caveat everything pre-2025 with the placeholder-stint finding — "baseline RAPM" in those years is starters-unit plus-minus.

### Rolling within-season (`baseline_v16_rolling`, 2026, horizon=window): RMSE / win-acc

| Cutoff → window | bpr | box_bpr | baseline | adj_em | home_only |
|---|---|---|---|---|---|
| Dec 1 → Jan 15 | 13.21 / **.711** | 13.64 / .694 | 14.51 / .680 | **12.90** / .693 | 15.88 / .642 |
| Jan 15 → Feb 15 | 11.89 / .667 | 12.57 / .646 | 12.28 / .661 | 11.90 / .663 | 14.45 / .573 |
| Feb 15 → end | 11.78 / .674 | 12.36 / .645 | 11.95 / .665 | **11.62 / .682** | 13.22 / .619 |

Additional Dec-1 detail: `bpr` Brier .195 / log loss .585 vs `adj_em` .199 / .595 — BPR has the best win-probability calibration of any arm in the early window despite the worse margin RMSE.

**Reading:** with real 2026 substitution data and no leakage, within-season `bpr` is **at parity with team-only adj_em**: better win accuracy and calibration early (Dec 1 — when priors matter most and adj_em has ~7 games/team), near-tied mid-season, slightly behind late. Clearly ahead of `box_bpr` and `baseline` alone at every cutoff — the Bayesian blend genuinely adds value over its components within-season. It does not yet beat a good team rating on margin RMSE.

### Player-level (`baseline_v16_player`)

| Check | Result |
|---|---|
| YoY BPR r (returning players, by poss bucket) | 0.06–0.22 across 2021→24 pairs — very low; consistent with placeholder-RAPM noise. 800+ poss bucket: 0.16–0.22. |
| BPR(Y) → Y+1 on-court adj net r | 0.32–0.38 — real forward signal at player level. |
| Preseason prior "calibration" | **Invalid as preseason evidence.** `preseason_obpr/dbpr` are written in-season with current-season box features (weakness 3.3); 2026 shows r=0.92–0.94 for all groups incl. newcomers — that's contamination, not skill. True preseason calibration requires storing predictions from a preseason snapshot. |

### NBA forward (`nba_forward_backtest --all`, now auto-detecting 4 pairs)

| | RMSE | MAE | r | ρ |
|---|---|---|---|---|
| Pipeline (pooled, 120 team-seasons) | **5.36** | 4.37 | 0.168 | 0.159 |
| Persistence baseline | 5.89 | 4.67 | 0.161 | 0.160 |

Pooled OLS forward slope 0.182 (production uses SLOPE=0.48 from the 2024→2025 pair alone). The 2025→2026 pair is broken by stale stored 2025 BPR (pipeline r = −0.04) and drags the pool — re-derive after a 2025 recompute. Player YoY stability (2025→2026): r = 0.515 overall. Same-season LEBRON in source ratings is legitimate here (all inputs predate target season); it stays illegitimate for within-season NBA claims.

---

## 2b. Rebuilt baselines after data repairs (2026-07-04, runs `v2data_*`)

Stint repairs applied (phantom OT deletion, dupe/zero-length cleanup, parser fixes, overlap re-sync, OT/neutral backfill, on-court aggregate recompute) and stored 2025+2026 BPR refreshed on the repaired data. Cross-season rerun, now including the restored 2025→2026 pair and the `adj_em_plus_bpr` combo arm (margin ~ β0 + β_em·adj_em_diff + β_bpr·bpr_diff + β_home):

| Pair | bpr | adj_em | combo (β_bpr) | Winner |
|---|---|---|---|---|
| 2021→2022 | 13.24 / .624 | 12.33 / .645 | 12.26 (β_bpr **0.040**) | adj_em |
| 2022→2023 | 13.24 / .645 | 12.68 / .660 | 12.67 (β_bpr **0.002**) | adj_em |
| 2023→2024 | 13.52 / .650 | 13.02 / .660 | 12.95 (β_bpr **0.037**) | adj_em |
| 2024→2025 | 13.66 / .652 | 13.29 / .669 | 13.19 (β_bpr **0.042**) | box_bpr (12.92) |
| **2025→2026** | **13.09 / .674** | 13.62 / .661 | 13.15 (β_bpr **0.216**) | **bpr** |

**The decisive read:** in every placeholder-era pair, player BPR adds ~zero over the team rating (β_bpr ≤ 0.04). In the first pair built on real substitution data, BPR **beats adj_em outright** and carries β_bpr = 0.216 of incremental signal. The architecture works; the historical inputs were the problem.

**Truthful arm** (`exp_truthful_cross`, 2025 ratings recomputed with `truthful_targets=True`, RAPM pool = [2025] only): RMSE 13.09 / acc .675 — **identical to the current 4-yr-pool blend**. Dropping placeholder seasons from the pool costs nothing.

**Player-level after repairs** (`v2data_player`):

| Pair | YoY r (200-400 / 400-800 / 800+ poss) | BPR→next on-court r |
|---|---|---|
| 2021→22 | .12 / .11 / .17 | .32 |
| 2022→23 | .22 / .06 / .16 | .38 |
| 2023→24 | .19 / .19 / .22 | .38 |
| 2024→25 | .51 / .32 / .47 | .45 |
| **2025→26** | **.64 / .67 / .69** | **.63** |

NCAA YoY stability on real data (0.69) exceeds the NBA pipeline's (0.52). The preseason-calibration rows remain excluded as evidence (in-season contamination, weakness 3.3).

**Rolling 2026 on repaired data** (`v2data_rolling` / `exp_truthful_rolling`) — RMSE / win-acc:

| Cutoff → window | bpr | adj_em | truthful bpr | combo (β_bpr) |
|---|---|---|---|---|
| Dec 1 → Jan 15 | **12.80 / .723** | 12.82 / .698 | **12.65 / .721** | 12.68 (0.291) / truthful 12.65 (0.309) |
| Jan 15 → Feb 15 | **11.74 / .674** | 11.89 / .664 | 11.77 / .675 | 11.80 (0.188) |
| Feb 15 → end | 11.45 / .681 | 11.43 / .687 | 11.47 / .677 | **11.40** (0.148) |

Post-repair, within-season BPR beats or ties adj_em at every cutoff (pre-repair it trailed at Dec 1 and Feb 15), the combo arm is best-or-tied everywhere with β_bpr 0.15–0.31, and truthful mode matches or beats the 4-yr pool. Together with the cross-season table above, this is the complete ship case for v2 (see 06).

## 3. Limitations

1. **Pre-2025 NCAA results measure a placeholder-lineup system** (integrity report headline). Cross-season baselines are still the honest measure of *what production shipped*, but improvements to lineup-RAPM machinery can only show up in 2025+/2026 evaluations until PBP is re-synced.
2. Rolling mode currently has one fully-real season (2026). One season × 3 cutoffs = weak statistical power; treat deltas < ~0.15 RMSE as noise.
3. The through-date team engine omits elevation/recency/importance weighting (r=0.993 parity accepted); the `adj_em` arm in rolling mode is therefore mildly weaker than production `compute_adjusted_ratings` would be.
4. 2026 neutral-site flags are missing → HCA is misapplied for those games in every arm equally; neutral split unavailable.
5. `em_calibrated` Box BPR training inside rolling runs uses prior-season EM (clean), but prior-season DB baselines inherit placeholder degeneracy.
6. NBA date-sliced margin backtest deferred — no NBA through-date dataset builder exists. Design sketch: mirror `build_rapm_dataset_through_date` over `NBAPlayerGameStint` + a through-date `NBATeamSeasonRatings` equivalent; lag LEBRON to the prior season for any mid-season arm.

## 4. How to run

```bash
# audits (read-only)
python manage.py audit_bpr_data --seasons 2021 2022 2023 2024 2025 2026
python manage.py nba_audit_bpr_data --seasons 2022 2023 2024 2025 2026

# through-date acceptance
python manage.py validate_bpr_through_date --season 2026
pytest ncaa/tests/test_bpr_through_date.py -o addopts=""

# baselines
python manage.py backtest_bpr_suite --mode cross-season --seasons 2021 2022 2023 2024
python manage.py backtest_bpr_suite --mode rolling --seasons 2026 --cutoffs 12-01 01-15 02-15
python manage.py backtest_bpr_suite --mode player --seasons 2021 2022 2023
python manage.py nba_forward_backtest --all

# experiment arm (Phase 5+): dump {player_id: bpr} json, then
python manage.py backtest_bpr_suite --mode rolling --seasons 2026 \
    --extra-ratings-json my_variant.json --run-name exp_my_variant
```

## 5. What Phase 5 should attack first (evidence-ranked)

1. **PBP re-sync test for 2021–2024** — if ESPN serves substitution events, everything upstream improves at once (data fix beats formula work).
2. **Recompute 2025 NCAA BPR** (and NBA 2025 stored ratings) — unblocks two backtest pairs.
3. **Prior machinery vs baseline RAPM, cross-season** — final bpr losing to its own baseline arm in all pairs is the clearest formula-level regression signal; sweep prior weights/sd_scale against the suite.
4. Garbage-time downweighting (6–8% of stint-seconds), smooth possession-reliability blending vs 200-poss cliffs, neutral-flag backfill.
