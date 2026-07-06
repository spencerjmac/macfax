# BPR Audit — 01: Architecture Map

**Date:** 2026-07-02
**Scope:** Mission Phase 1 deliverable. Full pipeline map for NCAA and NBA BPR, data models, backtest inventory with honesty classifications, and known-issues ledger.
**Model versions:** NCAA `BPR_MODEL_VERSION = "1.6"` (`backend/ncaa/analytics/player_value/bpr/constants.py`), NBA (unversioned; validated 2022–2026 per `nba_compute_final_bpr.py` docstring).

---

## 1. NCAA pipeline

### Data flow

```
ESPN PBP API
  └─ sync_ncaa_pbp ──────────────► PlayerGameStint  (per-stint team/opp box events)
ESPN box scores
  └─ (stats sync) ───────────────► PlayerGameStats  (per-game player box)
                                    PlayerSeasonStats (season aggregates + on_court_*)
compute_adjusted_ratings ─────────► TeamSeasonRatings (adj_o / adj_d / adj_em; box-only, BPR-independent)
recruiting scrape (247/Rivals/ESPN/On3)
  └─ ──────────────────────────────► PlayerRecruitingProfile
compute_player_projections ───────► PlayerSeasonProjection (returner/transfer/newcomer, n_prior_seasons)

compute_ncaa_bpr --season YYYY   (orchestrator: pipeline.run_bpr_season)
  Phase 1  datasets.build_rapm_dataset([Y-3..Y])          4-yr rolling window (default)
  Phase 2  fit_baseline_rapm                              game-split 5-fold CV λ ∈ [1..5000]
  Phase 2b fit_baseline_rapm(λ=500)                       wider Box-BPR training targets
  Phase 2c write baseline_obpr/baseline_dbpr              clean teacher targets for future seasons
  Phase 3  load PlayerSeasonStats box features            ⚠ full-season even under cutoff_date
  Phase 4  Box BPR ridge                                  target priority: em_calibrated →
                                                          multi_year_rapm → db_baseline → OOF
  Phase 4.5 prior SDs from R²                             σ = √(1−R²)·σ_rapm, clip [0.5, 8.0]
  Phase 5  preseason Ridge models + prior maps            0.20 history blend, recruiting tiers,
           + CV sd_scale (joint + separate)               candidates [0.1..3.0]
           fit_prior_informed_rapm                        per-player λᵢ = λ_base / (SDᵢ·scale)²
  Phase 6  write obpr/dbpr/bpr to PlayerSeasonStats       200-poss hard gates, provenance
                                                          (rapm/box_bpr/mixed/partial),
                                                          clamps OBPR ±15 / DBPR ±12
  Phase 7  BPRModelArtifact                               coefficients + assumptions
  Phase 8  validation.run_validation                      13 sanity/predictive checks
```

### Key mechanics

- **Stint → observation:** lineup segments from stint intersection per period; narrowest stint scaled proportionally to segment duration; ~77.5% of playing time resolves to clean 5v5 (`datasets.py` docstring — reconciled by audit check A3). Kubatko possessions `FGA + 0.44·FTA + TOV − ORB`. `MIN_SEGMENT_POSS = 0.5`.
- **FGA coverage gate:** prior seasons with <50% of stints having `team_fga > 0` are excluded from the pooled window (ESPN PBP 2015–2020 stores team_fga=0 → possession estimates ~6× low). Target year always included, with warning.
- **Multi-year keying (v1.3.1):** design-matrix columns keyed `(player_id, season_year)`; earlier seasons contribute estimation power only; only target-season coefficients written.
- **RAPM solve:** sparse augmented least squares (`lsqr`), design `[intercept | hca | OBPR-block | DBPR-block]`, 2 rows per segment, y = pts/poss·100, weights = possessions. DBPR sign-flipped at output (positive = good).
- **Box BPR:** 15 off / 14 def features (v1.3 pruned `reb100`, `stl_blk100`; v1.6 added `blk_to_fga_ratio`). Ridge α grids off [0.01–50], def [0.1–200]. Training target priority in `pipeline.py:262-334`:
  1. `em_calibrated` — Evan Miya adj_obpr/adj_dbpr from **prior seasons only** (fuzzy name+team match, accept ≥0.58)
  2. `multi_year_rapm` — non-target-season coefficients from the current pooled fit
  3. `db_baseline` — stored baseline_obpr/dbpr from prior seasons (FGA-gated)
  4. `out_of_fold` — same-season, 5-fold player split
- **Priors (Phase 5):** preseason Ridge sub-models (returner: 14 features incl. Y−1 baseline/box/on-court; transfer: same minus on-court, plus competition_delta) trained on 4 prior years → per-player mean + per-group residual SD. Fallbacks: box + 0.20·prior-season-baseline blend → recruiting tier (5★ +2.5/+1.0 with rank/team bonuses) → flat (0, SD 4.0/3.0).
- **Final write policy:** OBPR from RAPM needs `off_poss ≥ 200`, DBPR needs `def_poss ≥ 200`; else box fallback (needs `off_poss ≥ 50`); else null. `bpr_source ∈ {rapm, box_bpr, mixed, partial}`.

### Documented deviations from the EvanMiya article (constants.py §1–9)

1. Multi-year RAPM is player-season-keyed pooling, not one 4-yr sample; single-season remains production default.
2. Lineup segments (~77.5% clean 5v5) instead of true possession-level design.
3. Box BPR trains on baseline RAPM (not final BPR) — breaks recursive contamination.
4. Preseason priors: box mean + fixed σ, recruiting tiers for freshmen (no transfer data in the flat path; Ridge sub-models add it).
5. Prior SD tuned by CV — joint AND separate off/def, lower held-out WMSE wins.
6. HCA estimated freely as a coefficient (3.0 constant is a sanity bound only).
7. Intercept absorbs league average (no pre-centering).
8. Version history v1.2 → v1.6 (see constants.py docstring).
9. Opp quality = mean opponent adj_em added to both feature sets.

---

## 2. NBA pipeline

### Data flow

```
NBA.com stats API
  └─ nba_sync_play_by_play ────────► NBAPlayerGameStint  (garbage time NOT flagged;
                                       bad games excluded via game.pbp_quality_flag)
  └─ nba_sync_player_advanced ─────► o_mpir / d_mpir  (= E_OFF/DEF_RATING − league avg)
data/nba/lebron-data-{2016..2026}.csv  (BBall Index LEBRON; exact nba_id match)

Run order:
  1. nba_compute_baseline_rapm --season YYYY     single-season, 5-fold CV λ
       → baseline_obpr / baseline_dbpr / off_poss / def_poss
  2. nba_compute_box_bpr --season YYYY
       targets = 0.3·baseline_RAPM + 0.7·LEBRON   (LEBRON_BLEND_W = 0.7)
       Ridge pinned α: off 5.0, def 10.0          (CV unstable 5–200 year-to-year)
       features: 25 off / 13 def + 6 archetype one-hots
       career stabilization (career_stats.py):
         Tier 1 rates  — full career-poss-weighted blend
         Tier 2 per100 — 0.5× role-discounted career weight
         window 2016+; traded players deduped (max poss / gp-weighted rates)
       MPIR-only players predicted, never trained (mixed-scale guard)
       → box_obpr / box_dbpr / box_bpr
  3. nba_compute_final_bpr --season YYYY
       prior  = 0.5·LEBRON + 0.5·box   (both sides, LEBRON_PRIOR_W = 0.5)
       stints = 3-yr pool, player-season-keyed
       λ      = minutes tier (≥2000:400, ≥1200:700, ≥600:1000, <600:1400)
                × min(1 + 0.7·max(0, 7.0 − LEBRON_total), 4)   ← role players shrunk to prior
       optional within-season recency half-life (default 90d); cross-season decay inert at λ≥1000
       → obpr / dbpr / bpr / wins_added = (bpr+2)·(mpg/48)·(gp/56)

compute_nba_team_outlooks
       player BPR → projected roster slots → team adj_em → wins
       SLOPE=0.48 (single 2024→2025 pair), WINS_PER_EM=2.46, WINS_INTERCEPT=44.3, SIGMA_EM=5.5
       RAPM inflation cap: |bpr − box_bpr| gap capped at 1.6σ (positive gaps only)
```

NBA team ratings (`nba_compute_ratings` → `NBATeamSeasonRatings.adj_net`) are box-only and BPR-independent — no double-counting into outlooks' error calibration.

---

## 3. Data-model map

| Model | Populated by | Consumed by |
|---|---|---|
| `PlayerGameStint` (ncaa) | `sync_ncaa_pbp` | RAPM datasets, on-court features |
| `PlayerGameStats` (ncaa) | box-score sync | season aggregates, rosters, through-date rebuilds |
| `PlayerSeasonStats` (ncaa) | stats sync + `compute_ncaa_bpr` (bpr fields) | Box BPR features, API/frontend |
| `PlayerSeasonProjection` | `compute_player_projections` | preseason model (recruitment_type, n_prior_seasons) |
| `PlayerRecruitingProfile` | recruiting scrape | freshman priors |
| `TeamSeasonRatings` | `compute_adjusted_ratings` (box-only) | opp_quality, on_court_adj_em, matchup engine |
| `BPRModelArtifact` | `compute_ncaa_bpr` Phase 7 | provenance/debug |
| `NBAPlayerGameStint` | `nba_sync_play_by_play` | NBA RAPM |
| `NBAPlayerSeasonStats` | syncs + 3 BPR commands | box features, outlooks, API |
| `NBATeamSeasonRatings` | `nba_compute_ratings` | opp_quality (NBA), outlook calibration |
| `NBAProjectedRosterSlot` | `compute_nba_team_outlooks` | frontend outlook pages |

Frontend surfaces (web/): `NCAAPlayerRankingsTable`, `NBAPlayerRankingsTable`, `PlayerScoutingCard` (BPR/OBPR/DBPR + tiers), outlook pages, glossary (`web/src/lib/glossaryContent.ts`). `bpr_source` is serialized but **not** surfaced as a confidence indicator in the UI (Phase 8 item).

---

## 4. Backtest inventory — honesty classification

| Command | What it measures | Classification |
|---|---|---|
| `backtest_bpr_margin` (ncaa) | Y ratings → Y+1 margins, OLS calib, RMSE/MAE/Brier/AUC | **Leak-free** (Y frozen before Y+1) |
| `backtest_bpr_walkforward` (ncaa) | within-season date-split (~70/30) | **Leaky as forward test.** `run_bpr_season(cutoff_date)` date-bounds only the RAPM dataset; Phase 3 loads full-season `PlayerSeasonStats` (incl. `on_court_adj_em`) at `pipeline.py:231-251` and full-season `TeamSeasonRatings` at `pipeline.py:779, 823`. Command also builds rosters from full-season mpg (`backtest_bpr_walkforward.py:216-221`) and the adj_em arm from end-of-season ratings (`:223-228`). bpr / box_bpr / adj_em arms all contaminated. |
| `backtest_bpr_game_prediction` (ncaa) | full-season BPR → same season's games | **Descriptive only** — never cite as predictive |
| `backtest_bpr_continuity` (ncaa) | ΔRMSE by roster-continuity bucket | Leak-free (built on margin pattern) |
| `backtest_bpr_predictive` (ncaa) | YoY stability r; EM alignment r | Leak-free / reference alignment (not a prediction target) |
| `backtest_bpr_shrinkage_sweep` (ncaa) | sd_scale sweep vs margins | Diagnostic; train-fold selection, held-out verdict |
| `backtest_bpr_vs_evan_miya` (ncaa) | ours vs EM adj_bpr, bias/scale/discrepancies | Reference comparison only |
| `nba_backtest_bpr` | same-season wins fit + N→N+1 Spearman | Mixed: fit part descriptive, predictive part clean |
| `nba_forward_backtest` | season N inputs → N+1 team EM/wins | **Leak-free by design**, but only 2 pairs and 2025→2026 excluded (stale stored BPR) |
| `nba_retrodiction_2025_26` (analysis/) | same-season explanatory RMSE vs BPM etc. | Descriptive only |
| `nba_predictive_test`, `nba_bpr_calibration` (analysis/) | YoY metric comparisons; post-hoc team calibration | Clean (cross-season), ad-hoc |

**Consequence:** the only trustworthy forward evidence today is cross-season (margin, predictive, forward_backtest). There is **no valid within-season forward measurement** — that is the Phase 4 gap this audit fills.

---

## 5. Known-issues ledger (starting state)

| Issue | Evidence | Status |
|---|---|---|
| Within-season walkforward leaks (PSS features, team ratings, rosters) | pipeline.py:231-251, 779, 823; walkforward.py:216-228 | Confirmed; framework fix in Phase 4 |
| NBA star stability YoY r = 0.508 vs BPM 0.755 | nba_compute_final_bpr docstring | Structural RAPM floor; accepted trade-off, revisit in experiments |
| NBA retrodiction RMSE 5.636 vs BPM 3.559 | analysis/nba_predictive_test.py RETRO_RMSE | Descriptive gap; motivates target/blend experiments |
| NBA 2026 stint duplication (update_conflicts re-sync bug) | nba/analytics/rapm.py docstring | Fixed by delete+re-sync; recurrence check = audit B1 |
| Team-context inflation (Jrue Holiday #4, Queta #6 in 2026) | nba_compute_final_bpr docstring; outlook RAPM cap fires | Partially mitigated by 1.6σ inflation cap in outlooks only — display BPR still inflated |
| Garbage time not flagged (both leagues) | no Game flag; NBA excludes only pbp_quality_flag games | Quantified by audit A12; experiment candidate |
| NCAA 2015–2020 PBP team_fga=0 | datasets.py FGA gate | Handled by 50% gate; verified by audit A5 |
| NBA outlook SLOPE=0.48 from a single season pair | compute_nba_team_outlooks; memory note | Provisional until 2026→2027 actuals |
| `bpr_source` not surfaced in UI as confidence signal | serializers expose it; components don't render warnings | Phase 8 item |
| EM fuzzy match accept threshold 0.58 | pipeline.py:933 | Match-quality audit = A10 |
