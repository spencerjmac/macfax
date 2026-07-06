# BPR Audit — 13: Recruiting & Transfer Priors — Results (Partial: CSVs not yet provided)

**Date:** 2026-07-06 · **Branch:** `recruiting-priors`
**Status:** freshman-prior experiments (recruiting-tier curves) remain **blocked — no recruiting CSVs have been provided** (repo, Downloads, Desktop searched). Everything runnable without them was run: the PSP classification question is resolved, and the transfer-prior experiments are complete with a clear result.

## 1. CSV source / coverage summary

No external CSVs exist yet. Current profile inventory: **48 rows, all class-2026 five-stars** (source: prior manual import; 100% espn_id-matched — no fuzzy rows). Before-state coverage (PSS-derived newcomer definition):

| Class | Newcomers | Profiled | High-minute (≥12 mpg) unprofiled |
|---|---|---|---|
| 2021 | 2,242 | 0 | 962 |
| 2022 | 2,535 | 0 | 1,148 |
| 2023 | 2,828 | 0 | 1,274 |
| 2024 | 2,809 | 0 | 1,309 |
| 2025 | 3,220 | 0 | 1,511 |
| 2026 | 3,659 | 48 (1.3%, all 5★) | 1,867 |

Priority ingest list regenerated: `backend/backtest_output/bpr_audit/recruiting_missing_profiles.csv` — **5,962 players across six classes, espn_ids pre-filled**. Import path unchanged (`import_recruiting --dry-run` → import → `check_recruiting_data`); source terms note: CSVs must be manually exported/provided — no scraping.

## 2. Match-quality / duplicates / unmatched

For the existing 48: 48/48 espn_id exact matches, 0 fuzzy, 0 duplicates (2 same-name collisions in the Player table — Cameron Boozer, Caleb Wilson — resolve correctly via espn_id; this is why espn_id is mandatory-in-practice for the big import). Reports for future imports come from `check_recruiting_data` (orphan-profile audit, per-class coverage by star tier, duplicate detection) and `import_recruiting`'s per-row skip/ambiguity log.

## 3. PSP classification — RESOLVED AS SEMANTICS, NOT A BUG

Doc 11 §5 flagged the 48 five-stars as "misclassified `(2027, newcomer)`". Re-reading `projection/pipeline.py::classify_recruitment_type`: **`recruitment_type` is from-season-relative** — a row with `from_season=2026, projected_season_year=2027, type=newcomer` means *"was a newcomer during 2026"*, and the BPR pipeline consumes it through exactly that lens (`from_season__year=season_year`). Boozer check under correct semantics: `from_season=2026 → ('newcomer', projected 2027)` ✓; all 48 profiled players classify `newcomer` ✓. **No code fix needed.** The doc-11 remediation stands only in that `check_recruiting_data` now derives newcomers from PSS directly (robust to either lens and to late-added players).

## 4. Freshman prior experiments — BLOCKED

Cannot be run honestly: 48 five-stars is one tier of one class — no 4★/3★/rank spread, no historical classes to fit tier curves or position/role/major splits. Runs the moment CSVs for classes 2021–2026 land (the evaluation harness — `backtest_bpr_suite --mode player` newcomer rows + prior-vs-realized tables — is ready).

## 5. Transfer prior experiments — COMPLETE

Cohorts: `from_season ∈ {2025, 2026}` transfers with ≥8 mpg both years (n=1,737); returners as control (n=2,048). Preseason-honest features only (prior-year box_bpr, prior-year usage, **prior-year** dest-vs-origin adj_em delta); outcome = realized v1.7 BPR.

**Translation regressions:**

```
transfers:  bpr_Y = +0.54 + 0.737·box_prev + 0.029·Δadj_em + 0.038·usg_prev   r=0.571, resid_sd=2.34
returners:  bpr_Y = +1.36 + 0.664·box_prev + 0.074·Δadj_em + 0.005·usg_prev   r=0.585, resid_sd=2.45
```

**Bucket table (realized − prior box):**

| Move (prior-year Δadj_em) | n | prior box mean | realized mean | delta |
|---|---|---|---|---|
| Up (>+5, mid→high-major) | 776 | +0.86 | +2.32 | **+1.46** |
| Lateral | 541 | +0.70 | +1.75 | +1.06 |
| Down (<−5, high→mid) | 420 | +0.62 | +1.36 | +0.74 |
| Returners (control) | 2,040 | +0.49 | +1.76 | +1.27 |

**Findings:**
1. **No conference-jump penalty.** Conditioned on prior production, moving up carries a slightly *positive* coefficient — selection effect (good programs pick well). Any prior scheme that discounts up-transfers would be wrong on this data.
2. **Transfers translate as reliably as returners** (carry 0.737 vs 0.664; residual SD 2.34 vs 2.45). The "transfers are extra noisy" assumption baked into the fallback SDs is not supported.
3. **Empirical preseason uncertainty ≈ 2.4 BPR** for both groups — the existing constants (returner 2.5/2.0, transfer 3.0/2.5) bracket it, transfer side conservatively wide.
4. Usage carries small positive signal for transfers only (+0.038/pt) — high-usage transfers slightly outperform.

Splits not run (documented gaps): by position (data available, low expected value), early-vs-full-season (needs through-date outcome frame — extension of the suite, queue with freshman work).

## 6. Recommended config changes

**One small, evidence-backed change:** `PRESEASON_FALLBACK_SD_TRANSFER_OFF/DEF: 3.0/2.5 → 2.5/2.0` (equal to returner fallbacks) — empirical residuals are equal, and the trained transfer sub-model already learns `competition_delta` (which this data validates as mildly positive, not negative). **Not applied** — effect is confined to the fallback path (fires only when the Ridge sub-model lacks training pairs) and is unmeasurable in game-level metrics; grooming-tier change for the next formula-touching release rather than a solo ship.

**No changes to live v1.7, the projection transform, or the preseason model structure.** The translation table above is the durable asset: it is the empirical answer to "how do transfers translate" and directly validates the current model's design choices (competition_delta as a learned feature, no hard-coded penalty).

## 7. Ship / no-ship

- Transfer-prior formula changes: **NO-SHIP** (current design already consistent with the evidence; only the SD-grooming note above).
- Freshman priors: **PENDING DATA** — the decision cannot be made without the CSVs.

## 8. Reproduce

```bash
python manage.py check_recruiting_data --seasons 2021 2022 2023 2024 2025 2026
# Boozer semantics check:
#   PlayerSeasonProjection.objects.filter(player_id=9105, from_season__year=2026)
#   → ('newcomer', projected 2027) ✓
# Transfer regression: shell snippet in this doc's session (PSP from_season
# cohorts × PSS prior/realized × prior-year TeamSeasonRatings deltas)
```

## 9. Files changed

None in production code. Branch `recruiting-priors` carries only this doc (+ the doc-11 semantics correction).

## 10. Remaining data gaps

1. **Recruiting CSVs, classes 2021–2026** — the sole blocker for freshman-tier priors; priority list of 5,962 (espn_ids included) is waiting. Historical classes matter most: they are the training data.
2. Position/role split of transfer translation (cheap once freshman work runs).
3. Early-season vs full-season calibration frame (through-date outcome extension).
4. True preseason snapshots (doc 07 open item) — needed before next year's prior-calibration check can be honest.
