# BPR Audit — 11: Projection Wiring — Final Report

**Date:** 2026-07-05
**Scope:** production wiring + product hardening for the BPR / Projection Value split. Formula research stays closed (docs 08). The product rule enforced throughout: **BPR = player evaluation · Projection Value = team-forecast input · confidence/source/provenance = transparency layer.** Never blurred.

---

## 1. NBA Projection Value — WIRED (Priority 1)

- **Storage**: `NBAPlayerSeasonStats.projection_value` + `projection_value_version` ("pv1") + `projection_value_source` (`bpr+bpm`/`bpr_only`) + `projection_alpha` (0.25). Migration `nba/0022`.
- **Compute**: `nba/analytics/projection_value.py` (z-scored 0.25·BPR + 0.75·BPM, BBref fuzzy match, bpr_only fallback) + `manage.py nba_compute_projection_values --season YYYY`. Populated for 2022–2026 (2026: 579 players, 464 with BPM).
- **Consumption**: `compute_nba_team_outlooks` now projects team adj_em from the PV signal — `PV_SLOPE=3.58` (calibrated: 90 team-seasons over 3 forward pairs, r=0.304, RMSE=4.32), centered two-pass league baseline, `PV_SIGMA_EM=4.5`, `PV_WINS_INTERCEPT=41.0`. Same returner/acquisition shrinkage as the BPR path. Legacy BPR-path adj_em still computed + logged per team.
- **Calibration bug caught during wiring**: legacy `WINS_INTERCEPT=44.3` belonged to the uncentered legacy scale; first PV run inflated every team (+41 league total). Fixed with the centered 41.0 intercept — league mean projected wins now **40.97** ✓.
- **Before/after** (2026→27): spread 33–50W (was 29–44 with legacy-BPR pessimism tail); biggest movers = teams the legacy path over-punished (MEM 31→42W, MIL 35→44W, WAS 32→41W). OKC 50W atop.
- **Tests** (`nba/tests/test_projection_value.py`, 4/4): adj_em follows PV and is invariant to BPR at fixed PV; exact centered-slope formula; legacy path separate; off/def split sums to PV total.
- Player surfaces untouched: `projection_value` is not serialized to any player-evaluation endpoint; cards/tables still read `bpr/obpr/dbpr`.

## 2. NCAA projection transform — WIRED AS LIBRARY (Priority 2)

- `ncaa/analytics/player_value/bpr/projection_transform.py`: `ncaa_projection_player_value(bpr, box_bpr, off_poss, k=1500)` + bulk helper, version tag `nA-k1500`. Module docstring carries the N-A evidence and the within-season failure — this is explicitly **not v1.8**.
- Live rankings and `compute_ncaa_bpr` are untouched; a static test guarantees the live pipeline does not import the transform.
- **Tests** (`ncaa/tests/test_projection_transform.py`, 5/5): reliability math, fallbacks, projection≠live divergence, live-pipeline separation guard, bulk helper.
- **Where it is used**: the cross-season projection path — consumers are `backtest_bpr_suite --extra-ratings-json` arms (how it was validated) and any future NCAA year-ahead team-outlook builder. No current production NCAA surface projects Y→Y+1 team strength; when one is built it must call this transform, not raw BPR.

## 3. Frontend follow-ups — DONE (Priority 4)

- `PlayerScoutingCard` (NBA): last-updated stamp with "why ratings change" tooltip ("Ratings change when new games are played or the model version is updated").
- `PlayerOutlookTable` footnote now states the split: *"Team forecasts are driven by Projection Value — a separate forward-looking input… BPR itself remains the player evaluation rating shown on player pages."*
- Already landed in doc 07: `BPRConfidenceBadge` (source + sample-size confidence + NCAA pre-2025 "Box era" provenance), NCAA rankings Confidence column, glossary rewrite.
- Kept minimal per the UX rule — one badge, two footnotes, tooltips; no badge soup. `tsc --noEmit` clean.

## 4. Recruiting workflow — READY, AWAITING CSVs (Priority 3)

Workflow: `import_recruiting --dry-run` (per-row skip/ambiguity logging) → `import_recruiting` → `check_recruiting_data` (coverage by class/tier, orphan-profile match audit, duplicate detection, priority-ingest CSV regeneration) → `backtest_bpr_suite --mode player` (before/after freshman-prior calibration). Full guide: `docs/bpr_audit/recruiting_ingest_guide.md`; priority list with pre-filled espn_ids: `backend/backtest_output/bpr_audit/recruiting_missing_profiles.csv`. **N-D/N-E experiments stay blocked until real CSVs are imported** — no guessed priors will be shipped.

## 5. PSP / projections classification bug — DEFERRED WITH GUARDRAILS (Priority 5)

- **Summary**: `compute_player_projections` builds its player universe from the prior-season roster snapshot and never back-fills players added later — the 48 five-star 2026 freshmen have no (2026) projection rows and sit misclassified as `(2027, newcomer)` despite 2026 stats. Reruns report "0 created".
- **Affected**: `ncaa/analytics/player_value/projection/pipeline.py` (universe construction), `PlayerSeasonProjection` consumers relying on `recruitment_type`.
- **Why it matters**: preseason-model metadata and any PSP-based newcomer/transfer split under-count late-added players.
- **Why it does NOT block this release**: the BPR recruiting-prior path reads `PlayerRecruitingProfile` directly; `check_recruiting_data` was made PSP-independent (newcomer = has stats this season, none earlier); Projection Value is NBA-side.
- **Must be fixed before**: any experiment or product feature that consumes `recruitment_type` for late-added players (N-E transfer priors at scale).
- **Fix validation**: after patching universe construction, rerun `compute_player_projections --season 2025` and assert Cameron Boozer (player 9105) holds `(2026, newcomer)` + `(2027, returner)`.

## 6. Independence audit — PREPARED, NOT RUN (Priority 6)

`docs/bpr_audit/10_nba_bpr_independence_audit.md`: measurements, the fully-native variant to run, a native-λ alternative design, and the ≥90%-of-gap decision rule. Kept out of this wiring release by design.

## 7. QA run (Priority 7)

| Check | Result |
|---|---|
| New tests (projection transform, PV wiring, anti-leak) | **11/11 pass** |
| Full nba+ncaa test files touched | 32/34 — the 2 failures (`test_matchup.py` series-engine) **pre-date this work** (fail with all changes stashed); out of scope |
| `compute_ncaa_bpr --season 2026 --validate-only` | all_passed + strict ✓ |
| NCAA 2026 live ratings | 7,549 rows @ version **1.7** (v1.7 confirmed live) |
| NBA PV coverage | 661 rows for 2026; 2022–2026 populated |
| Outlook generation | 30 teams; league mean wins 40.97 ✓; PV drives `projected_*` fields, legacy logged |
| Frontend | `tsc --noEmit` clean |
| Docs 07/09 reflect shipped state | updated this session |

## 8. Files changed

New: `nba/analytics/projection_value.py`, `nba/management/commands/nba_compute_projection_values.py`, `nba/migrations/0022_*`, `nba/tests/test_projection_value.py`, `ncaa/analytics/player_value/bpr/projection_transform.py`, `ncaa/tests/test_projection_transform.py`, `docs/bpr_audit/{10,11}_*.md`.
Modified: `nba/models.py` (4 PV fields), `nba/management/commands/compute_nba_team_outlooks.py` (PV path, constants, comparison logging), `web/src/components/{PlayerScoutingCard.tsx, outlook/PlayerOutlookTable.tsx}`, `docs/bpr_audit/09_*.md`.

## 9. Remaining manual tasks (user)

1. **Recruiting CSVs** — the only blocker for N-D/N-E (guide + priority list ready).
2. Decide when to run the doc-10 independence audit.
3. Optional: commit this work (nothing has been committed; working tree carries the full audit + wiring).
4. Seasonal ops addition: run `nba_compute_projection_values --season YYYY` after each `nba_compute_final_bpr` (add to `recompute_all.sh` if desired).
5. PSP universe fix (§5) before large-scale transfer-prior work.
