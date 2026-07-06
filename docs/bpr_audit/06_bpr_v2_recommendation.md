# BPR Audit — 06: BPR v2 Recommendation Report

**Date:** 2026-07-04
**Verdict up front:** the NCAA BPR architecture is sound — it was fed placeholder lineup data for every season before 2025. With repaired 2025–2026 data the *unchanged formula* beats the team-only rating out of sample for the first time, at both game and player level. v2 is a **data + provenance release, not a formula rewrite**: adopt truthful RAPM-target gating, keep the current Bayesian blend, ship the data fixes, and raise the NBA LEBRON prior weight one notch. The single biggest remaining upside is backfilling real pre-2025 substitution data, not tuning.

---

## 1. What we fixed

| Fix | Scale |
|---|---|
| Phantom OT stint blocks deleted (parser fabricated a 300s period-3 for ~82% of games) | 259,466 rows across 2021–2026; on-court time inflation (exactly +12.5%) eliminated |
| Parser root causes in `sync_ncaa_pbp` | numeric `sequenceNumber` sort (string sort misordered plays → overlapping stints); deferred period reopen (no more phantom OT); defensive double-sub-in close; `--game-ids` targeted re-sync |
| Duplicate / zero-length stints | 105 exact dupes + ~28K zero-length rows removed; 629 overlap games re-synced |
| `went_to_ot` / `period_count` never set | backfilled from surviving stints: 354–611 OT games/season (was 0) |
| 2026 `neutral_site` flags missing | 588 games set via ESPN scoreboard matched on date+team pair |
| 2025 NCAA BPR absent from DB | recomputed + stored (3,530 rows, all validation green) |
| Stored 2025/2026 BPR built on corrupted stints | refreshed post-repair (2026: 3,812 rows, all green) |
| Walk-forward leakage (full-season box features + team ratings under a "cutoff") | `through_date.py` rebuilds + pipeline override params; old command deprecated; anti-leak tests |
| Truthful RAPM-target gating | `FIRST_VALID_RAPM_SEASON=2025`, `truthful_targets` mode end-to-end (pipeline, compute CLI, suite) |

## 2. Data now trustworthy

- NCAA 2026 stints (real substitutions; overlap residue 0.098%, A2 PASS), 2025 partially (27% of games real subs).
- All NCAA box-score, team-rating, and EM-reference data (all seasons).
- NBA data layer end-to-end (audit B1–B4 all PASS).
- Every number produced by `backtest_bpr_suite` and `nba_experiment_final_bpr` (leak-free by construction; through-date parity r = 0.993–1.000).

## 3. Data still NOT trustworthy

- **Any pre-2025 NCAA quantity presented as lineup RAPM** — permanently, unless PBP re-sync backfills substitution events (untested; parser is ready).
- `preseason_obpr/dbpr` as preseason quantities (in-season box contamination).
- ~~NBA 2025 stored `box_bpr`/`bpr` (stale)~~ — **refreshed 2026-07-05** (full chain, user-approved). Post-refresh finding: the 2025→2026 forward pair remains near-zero r (pipeline −0.00, persistence 0.19 vs its usual ~0.48) — the transition year was genuinely unpredictable for every method, not a staleness artifact. Keep the pair in pooled numbers with this caveat.
- Recruiting-prior path (48 profiles total; needs user-supplied 247/On3 CSVs → `import_recruiting`).

## 4. NCAA old vs new backtests (leak-free suite)

Cross-season, margin RMSE / win-acc; combo arm β_bpr = incremental player signal over adj_em:

| Pair | bpr | adj_em | β_bpr | Read |
|---|---|---|---|---|
| 2021→22 | 13.24 / .624 | 12.33 / .645 | 0.040 | placeholder era: BPR adds ~nothing |
| 2022→23 | 13.24 / .645 | 12.68 / .660 | 0.002 | 〃 |
| 2023→24 | 13.52 / .650 | 13.02 / .660 | 0.037 | 〃 |
| 2024→25 | 13.66 / .652 | 13.29 / .669 | 0.042 | box_bpr best (12.92) |
| **2025→26** | **13.09 / .674** | 13.62 / .661 | **0.216** | **BPR wins outright** |

Truthful variant (RAPM pool = [2025] only): 13.09 / .675 — identical to the 4-yr pool. Player level: YoY r 0.16–0.22 (placeholder pairs) → **0.69** (2025→26, 800+ poss); BPR→next-season on-court r 0.32 → **0.63**.

Within-season rolling 2026 on repaired data (leak-free): BPR beats or ties adj_em at **every** cutoff — Dec 1: 12.80/.723 vs 12.82/.698; Jan 15: 11.74/.674 vs 11.89/.664; Feb 15: 11.45/.681 vs 11.43/.687 — with combo β_bpr 0.15–0.31 and the combo arm best-or-tied everywhere. Truthful rolling matches or beats current (Dec 1: 12.65/.721, β_bpr 0.309).

## 4b. Pre-2025 NCAA data — formal decision (mission Step 5)

Options tested / assessed:

| Option | Verdict | Evidence |
|---|---|---|
| A. Exclude 2021–2024 from RAPM target training entirely | **ADOPT** (= truthful mode) | Cross-season 2025→26 identical (13.09 both); rolling equal-or-better (Dec 1: 12.65 vs 12.80); zero measured cost |
| B. Keep 2021–2024 for box priors + team context only | **ADOPT** (complement of A) | Box features and adj_em from those seasons are sound (audit A4/A5); EM external targets span 2010–2026 |
| C. Keep as weak/noisy RAPM target with high uncertainty | Reject | That is effectively what the 4-yr pool did; no measurable benefit over exclusion, and it launders placeholder margins as lineup impact |
| D. Internal Box-BPR targets from 2025+ RAPM only | Adopt as fallback rule (truthful mode already enforces it) | Moot in practice: production uses EM targets first |
| E. External (EM) reference targets | Already production (v1.6), keep | 98.7%+ match rates; the path that kept Box BPR healthy through the placeholder era |

Direct answers: pre-2025 **removed from RAPM training** (pool and targets); **stays in Box BPR training only through external EM targets**, never internal RAPM labels; **stays fully usable** as team/player descriptive data; sample-size cost **zero measured** (the preseason model falls back gracefully when its training window empties); honesty/prediction gain — the 2025-only pool matches or beats the contaminated pool everywhere it was tested.

**Probe result (2026-07-05): the reversal path is closed.** ESPN's PBP payloads contain zero substitution events (type 584) before ~Feb 2025 — verified on the 2024 national championship game (294 plays, 0 subs), regular-season 2024 games, and Nov 2024/Jan 2025 dates; events appear by Mar 2025 (156/game) and are standard from 2025-26 on. The alternate NCAA API shows no substitution data either. Pre-2025 seasons are **permanently placeholder** unless a commercial PBP source is acquired. Truthful mode is therefore not a preference but the only honest configuration.

## 5. NBA old vs new backtests

`nba_experiment_final_bpr` harness (in-memory variants; reproduces production to 4 decimals). Mean over clean forward pairs (2022→23, 2023→24, 2024→25; 2025-source excluded for stale box priors). Player-forward = r vs next-season baseline RAPM; team RMSE = minutes-weighted aggregate → next-season adj_net:

| Variant | Player-forward r | Team RMSE |
|---|---|---|
| pw000 (no LEBRON prior) | 0.264 | 3.945 |
| pw025 | 0.275 | 3.942 |
| **pw050 (production)** | 0.286 | 3.939 |
| **pw075** | **0.294** | 3.937 |
| pw090 | **0.298** | 3.936 |
| ls000 (no LEBRON-adjusted λ) | **0.228 (worst)** | 3.929 |
| ls140 | 0.284 | 3.940 |
| tierC (aggressive λ) | 0.240 | 3.934 |
| hl0 (no 90d recency) | 0.268 | 3.933 |

Reads: LEBRON-adjusted λ is the most valuable single component (−0.058 without it); A_conservative tiers and the 90-day half-life earn their keep. The LEBRON prior weight climbs monotonically through 0.9 but flattens (+0.008 for 0.5→0.75, +0.004 for 0.75→0.9). Team-level differences are noise-scale — these knobs matter for player quality, not team aggregates. **Recommendation: 0.75** — takes most of the measured gain while keeping the rating meaningfully independent of LEBRON; 0.9 is a measured alternative if independence is not valued. `LEBRON_BLEND_W` (box-target blend) not sweepable in this harness (needs box_bpr chain recompute) — deferred, tracked.

Pooled team forward reference (4 pairs, `nba_forward_backtest`): pipeline RMSE 5.36 vs persistence 5.89.

## 6. Experiment table

| # | Experiment | Result | Ship? |
|---|---|---|---|
| N1 | Truthful targets (pool=[2025], no pre-2025 internal targets) | identical accuracy, cleaner provenance | **YES** |
| N2 | adj_em_plus_bpr combo arm | β_bpr 0.216 on real data (≤.04 placeholder) | evidence, not a config |
| B1 | LEBRON prior w 0 → 0.9 | monotonic ↑ player-forward (0.264→0.298), flattening past 0.75; team unchanged | **raise to 0.75** |
| B2 | LEBRON-adjusted λ off | −0.058 player-forward | keep ON |
| B3 | Aggressive λ tiers | −0.046 | keep A_conservative |
| B4 | Recency half-life off | −0.018 | keep 90d |
| — | Smooth reliability gates, prior-SD retune, garbage-time downweight, recency (NCAA), freshman/transfer empirical priors | **not yet run** — next experiment wave, now measurable against honest baselines | pending |

## 7. Recommended config (v2)

**NCAA (`BPR_MODEL_VERSION` → 1.7):**
- `truthful_targets=True` as the production default (`compute_ncaa_bpr --truthful-targets`): RAPM pool = valid seasons only (2025+), no pre-2025 internal RAPM targets/history/preseason training. EM external targets unchanged.
- Everything else unchanged — the blend, gates, SD tuning, EM calibration all validated on real data.
- Data-side requirements shipped with it: fixed parser, repaired stints, OT/neutral flags, refreshed 2025+2026 ratings.

**NBA:**
- `LEBRON_PRIOR_W 0.5 → 0.75` (both sides). Gradient measured through 0.9 (flattens; 0.75 keeps independence).
- Keep λ tiers, LEBRON-λ scale 0.7, 90d half-life.
- Refresh the NBA 2025 chain (baseline → box → final) **after user approval** (overwrites stored values), then re-derive outlook SLOPE with the restored pair.

## 8. Model versioning

- NCAA: bump `BPR_MODEL_VERSION` to "1.7" on the truthful-default flip; old outputs remain comparable via `bpr_model_version` on every row + suite run manifests (git SHA + config recorded).
- NBA: tag config in `wins_added`/outlook manifests; keep `nba_experiment_final_bpr` runs as the variant archive.

## 9. Files changed (this mission)

New: `ncaa/.../bpr/through_date.py`, `ncaa/.../bpr/backtest_lib.py`, `ncaa/management/commands/{audit_bpr_data, backtest_bpr_suite, validate_bpr_through_date, fix_ncaa_stint_data, backfill_neutral_flags, dump_bpr_ratings}.py`, `nba/management/commands/{nba_audit_bpr_data, nba_experiment_final_bpr}.py`, `ncaa/tests/test_bpr_through_date.py`, `docs/bpr_audit/01–06`.
Modified: `ncaa/.../bpr/{pipeline.py, constants.py, preseason_model.py}` (override params, truthful gating — defaults preserve old behavior), `ncaa/management/commands/{sync_ncaa_pbp.py (parser fixes + --game-ids), compute_ncaa_bpr.py (--truthful-targets), backtest_bpr_walkforward.py (deprecation)}`, `nba/management/commands/nba_forward_backtest.py` (auto pairs, player stability).

## 10. Commands to rerun

```bash
# audits & acceptance
python manage.py audit_bpr_data --seasons 2021 2022 2023 2024 2025 2026
python manage.py nba_audit_bpr_data --seasons 2022 2023 2024 2025 2026
python manage.py validate_bpr_through_date --season 2026
pytest ncaa/tests/test_bpr_through_date.py -o addopts=""

# data repairs (idempotent)
python manage.py fix_ncaa_stint_data --seasons 2021 2022 2023 2024 2025 2026 --dry-run
python manage.py backfill_neutral_flags --season 2026 --dry-run

# production compute (v2)
python manage.py compute_ncaa_bpr --season 2026 --truthful-targets

# backtests
python manage.py backtest_bpr_suite --mode cross-season --seasons 2021 2022 2023 2024 2025
python manage.py backtest_bpr_suite --mode rolling --seasons 2026 --cutoffs 12-01 01-15 02-15
python manage.py backtest_bpr_suite --mode player --seasons 2021 2022 2023 2024 2025
python manage.py nba_forward_backtest --all
python manage.py nba_experiment_final_bpr --source-seasons 2022 2023 2024 --lebron-prior-w 0.75 --run-name check
```

## 11. Ship / no-ship

**SHIP (NCAA v2 = data fixes + truthful default):** no known leakage; data bugs fixed or explicitly excluded; 2025+ RAPM path validated; player ratings stabilized 3× (YoY 0.22→0.69) *and* game prediction improved (first arm to beat adj_em); team aggregation improves (β_bpr 0.216); old/new comparable via versioning. All eight ship criteria pass.

**SHIP (NBA prior_w=0.75) conditionally:** improves player-forward without hurting team RMSE; LEBRON dependency now justified by forward ablation (pw000 loses everywhere); defensive-feature ablation (d_mpir, on_court_adj_d) still pending — run before flipping the constant, or ship 0.75 as config-flag first.

**NO-SHIP items:** NBA 2025 chain refresh (needs approval — overwrites), recruiting priors (blocked on data), NCAA formula experiments (gates/SDs/garbage-time — now measurable, next wave).

## 12. What next after v2

1. ~~ESPN PBP re-sync for 2021–2024~~ — **CLOSED by probe (§4b)**: ESPN never served substitution events before ~Feb 2025; no free backfill exists. Replacement upside: each new season adds a real-RAPM year — by 2027-28 the valid window is 3+ seasons deep and multi-year pooling becomes meaningful again. A commercial PBP source (Synergy/Genius) is the only way to buy history.
2. NCAA experiment wave against the honest baselines: smooth reliability gates, off/def prior SD, garbage-time downweighting, within-season recency.
3. NBA: defensive-feature ablation (d_mpir / on_court_adj_d), LEBRON_BLEND_W chain sweep, rookie/sophomore priors, archetype shrinkage.
4. Recruiting CSVs → empirical freshman/transfer priors.
5. Frontend (mission Phase 8): surface `bpr_source` + possession-based confidence in player cards; add "why did this rating change" note tied to `bpr_model_version`.
6. True preseason snapshots: store preseason predictions at a preseason date so next year's calibration check is honest.

## 13. Shipped (2026-07-05, user-approved)

- NCAA `BPR_MODEL_VERSION` → **1.7**; `compute_ncaa_bpr` now defaults to truthful targets (`--no-truthful-targets` is the legacy escape hatch); stored 2025 + 2026 recomputed under v1.7.
- NBA `LEBRON_PRIOR_W` / `LEBRON_PRIOR_DEF_W` → **0.75**; full 2025 chain refreshed (baseline → box → final) and 2026 final recomputed at the new weight.
- Recruiting CSVs remain the one open external dependency.
