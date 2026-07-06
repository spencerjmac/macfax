# BPR Audit — 03: Weakness Report

**Date:** 2026-07-02
Each item: evidence → severity (`blocks-trust` / `degrades-accuracy` / `cosmetic`) → the experiment or fix it motivates. Severity is about the *claim* the item undermines, not the code style.

---

## 1. Definite bugs

| # | Bug | Evidence | Severity | Motivates |
|---|---|---|---|---|
| 1.1 | **NCAA stints 2021–2024 are starter placeholders** — no substitution events parsed; 5 fixed players × full halves | Audit headline; 97.7% of 2024 team-games have exactly 5 stint-players | blocks-trust (for any lineup-RAPM claim pre-2025) | Re-sync experiment: test if ESPN serves sub events for old seasons; if yes, backfill 4 seasons of real RAPM |
| 1.2 | **Phantom OT stints** `(period≥3, 300→0)` created for ~82% of games at end-of-game handling | A1 median ratio exactly 1.125; 47K phantom stints in 2024 | degrades-accuracy (inflates `on_court_secs_pg` ~12.5%; mostly gated out of RAPM) | `sync_ncaa_pbp` end-game fix + backfill; short-term: strip `(period≥3, clock 300→0)` stints in aggregation |
| 1.3 | **Duplicate/overlapping stints** in 2022/24/25/26; 2026: 74 exact dupes, 495 games with overlaps (0.15% of seconds) | A2 FAIL; `a2_overlaps_*.csv` | degrades-accuracy (corrupted lineups in overlap windows) | Delete+re-sync affected games (same fix as NBA 2026 incident); exclude from stint-sensitive evals meanwhile |
| 1.4 | **`went_to_ot` / `period_count` never populated** | A8: 0 OT games in 6 seasons | degrades-accuracy (OT pace/possession scaling silently wrong) | Ingestion fix; recompute pace-dependent stats |
| 1.5 | **2026 `neutral_site` flags all missing** | A8: 0 neutral of 6,297 (prior seasons: 519–761) | degrades-accuracy (HCA misapplied to every 2026 neutral game — RAPM design matrix, adj ratings, margin fits) | Backfill flags from schedule source; until then 2026 home/neutral splits unavailable |
| 1.6 | **2025 NCAA BPR entirely absent from DB** | A11: 0 rows with bpr for 2025 | blocks-trust (any consumer of 2025 ratings) | Recompute 2025 (persist decision = user's); backtests recompute in-memory |

## 2. Data issues (not bugs, but material)

| # | Issue | Evidence | Severity | Motivates |
|---|---|---|---|---|
| 2.1 | **Recruiting profiles: 48 rows total, all class 2026** → freshman recruiting-prior path never fires (0–1.3% coverage vs ~3K newcomers/yr) | A9 | degrades-accuracy (freshmen fall to box/flat priors; all `RECRUITING_PRIOR_*` tuning is dead code) | Ingest recruiting data 2021+; then calibrate empirical tier priors (mission Phase 5 item 7) |
| 2.2 | Garbage time unflagged: 6.1–8.4% of stint-seconds in 25+ blowout second halves, full RAPM weight | A12 | degrades-accuracy (plausibly) | Experiment: exclude/downweight garbage segments, measure forward delta |
| 2.3 | Stint possession undercount ~3.5% vs box; 6–8% of game-teams off by >10% | A4 | cosmetic-to-minor | Monitor; RAPM weights tolerate unbiased noise |
| 2.4 | 2021 stint coverage only 76.9% of games | A1 | minor | Drop 2021 from stint-based training windows |
| 2.5 | EM 2026 reference only 200 players (partial leaderboard) | A10 | minor | Refresh EM 2026 snapshot before using it as a 2026 sanity reference |

## 3. Leakage

| # | Item | Evidence | Verdict |
|---|---|---|---|
| 3.1 | **Within-season walk-forward leaks.** `run_bpr_season(cutoff_date)` date-bounds only the RAPM dataset. Phase 3 loads full-season `PlayerSeasonStats` (incl. `on_court_adj_em`, `on_court_tov_edge`, `on_court_reb_edge`) regardless of cutoff; `_build_opponent_quality_map`/`_build_team_adj_em_map` read full-season `TeamSeasonRatings` | `pipeline.py:231-251, 768-810, 813-830` | **CONFIRMED LEAK.** Every existing within-season number for the `bpr`/`box_bpr` arms is contaminated. Fixed by Step 4a overrides. |
| 3.2 | Walk-forward command additionally builds rosters from full-season `PlayerSeasonStats.mpg` and its `adj_em` comparison arm from end-of-season `TeamSeasonRatings` | `backtest_bpr_walkforward.py:216-228` | **CONFIRMED LEAK** — its adj_em baseline is unfairly strong, its BPR arm unfairly informed. Command superseded by `backtest_bpr_suite --mode rolling`; deprecation note added to its docstring. |
| 3.3 | Preseason prior path consumes current-season `box_bpr_preds` (features from full-season PSS) | `pipeline.py:454-491` feature `box_off_Y` | Leaks only *via 3.1* in date-sliced runs; clean at season end (box prior is current-season by design). Covered by the same override fix. |
| 3.4 | NCAA `em_calibrated` Box BPR training | `pipeline.py:853` — `yr < season_year` strict | **CLEAN** — prior-season EM only. |
| 3.5 | `backtest_bpr_game_prediction`: full-season BPR predicting the same season's games | command docstring | **Descriptive only.** Its 72%-accuracy targets must never be quoted as forward performance. |
| 3.6 | NBA final BPR uses **same-season full-season LEBRON** as prior (`lebron-data-{season_year}.csv`) and Box BPR trains on 0.3·same-season RAPM + 0.7·same-season LEBRON | `nba_compute_final_bpr.py:159-177`, `nba_compute_box_bpr.py:45,66` | Fine for season-end retrodiction; **invalid for any within-season or forward claim**. Forward backtests must lag LEBRON (Step 4c rule). |
| 3.7 | NCAA preseason Ridge models train on years < season_year with Y−1 features | `preseason_model.py:325-334` | **CLEAN.** |
| 3.8 | Cross-season backtests (`backtest_bpr_margin`, `nba_forward_backtest`) | code review | **CLEAN** — Y frozen before Y+1. |

## 4. Modeling issues

| # | Issue | Evidence | Motivates |
|---|---|---|---|
| 4.1 | Pre-2025 "RAPM" degeneracy (item 1.1) also contaminates *training chains*: Box BPR `db_baseline` targets and preseason-model targets for those years are 5-man-unit margins, not player isolation | pipeline target priority; preseason training window = 4 prior years | Re-rank Box BPR target priority experiments; possibly restrict `db_baseline`/preseason training to 2025+ (or EM targets, which are external and unaffected) |
| 4.2 | Hard 200-possession gates create rating cliffs (rapm↔box discontinuity at the threshold) | `_write_bpr_results`, A11 bucket table | Smooth reliability blend `poss/(poss+k)` experiment (mission Phase 5 item 3) |
| 4.3 | Garbage time at full weight (item 2.2) | A12 | Downweight experiment |
| 4.4 | NBA team-context inflation (Jrue/Queta) — RAPM absorbs team-level signal; mitigated only in outlooks (1.6σ cap), display BPR untouched | `nba_compute_final_bpr` docstring; outlook cap logs | Team-effect term in NBA RAPM design, or display-side cap experiment |
| 4.5 | `game_prediction.py` team strength: `min(mpg/40,1)` weights and `× min(total_w, 5)` renormalization overweight short benches and are sensitive to roster coverage | `game_prediction.py:18-71` | Through-date roster construction in suite (done in Step 4b); minutes-projection experiment later |
| 4.6 | NBA cross-season decay inert at λ≥1000; within-season 90d half-life untested against forward metrics | `nba/analytics/rapm.py` docstring | Recency experiments (mission Phase 5 item 5) with the new leak-free harness |

## 5. Calibration issues

| # | Issue | Evidence | Motivates |
|---|---|---|---|
| 5.1 | OBPR ±15 / DBPR ±12 clamps are hard caps at write time — silently truncate legitimate elite seasons if scale drifts | `constants.py:284-286`, `_write_bpr_results` | Flag-not-clamp experiment; monitor clamp-fire counts per season |
| 5.2 | Freshman tier priors (5★ = +2.5 OBPR etc.) are guesses AND dead code (item 2.1) | constants + A9 | Empirical recalibration after recruiting ingest |
| 5.3 | `PRIOR_HISTORY_BLEND = 0.20` and preseason-model residual SDs tuned on contaminated pre-2025 baselines | 4.1 | Re-tune on 2025+/EM-target variants |
| 5.4 | NBA outlook `SLOPE = 0.48` derived from a single season pair (2024→2025); 2025→2026 pair excluded for stale stored BPR | `compute_nba_team_outlooks.py`, memory note | Re-derive when a third pair exists (spring 2027) or after 2025 recompute |

## 6. Verified fine — do not touch

- `em_calibrated` Box BPR path (strict prior-year EM, 98.7%+ match rates).
- Cross-season `backtest_bpr_margin` and `nba_forward_backtest` methodology.
- RAPM lambda CV (game-split folds), prior SD tuning CV (held-out WMSE objective, joint + separate).
- Teacher-student chain: Box BPR trains on baseline (not final) RAPM — the v1.2 recursive-contamination fix is intact.
- Team ratings (`adj_em`, `adj_net`) independence from BPR — no double-counting into forecasts.
- NBA data layer (stints, traded players, LEBRON matching, d_mpir coverage).
- Multi-year player-season keying (v1.3.1) and through-date dataset builder (A6 exact match).

---

## Priority reading of the evidence

The mission asks *why isn't BPR predictive enough*. The audit answer, in order:

1. **The NCAA model has been learning from starters-only pseudo-lineups for every season before 2025.** Whatever the formula does, its RAPM signal pre-2025 is a team-margin share, and its box model was partly trained to imitate that. This is the dominant explanation candidate and it is a *data* problem, not a formula problem.
2. **No trustworthy within-season forward measurement existed** — the walk-forward leaked box features and team ratings, so tuning decisions made against it (sd_scale sweeps, gate choices) rest on contaminated numbers. The Step 4 framework replaces it.
3. Real but second-order: garbage time, phantom stints, hard gates, dead recruiting priors, missing 2026 neutral flags.
