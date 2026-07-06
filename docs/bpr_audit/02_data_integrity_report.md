# BPR Audit — 02: Data Integrity Report

**Date:** 2026-07-02
**Commands:** `python manage.py audit_bpr_data --seasons 2021..2026` (NCAA A1–A12), `python manage.py nba_audit_bpr_data --seasons 2022..2026` (NBA B1–B4).
**Machine output:** `backend/backtest_output/bpr_audit/` (per-check CSVs, `audit_summary.json`, `nba_audit_summary.json`).

---

## Headline finding — NCAA substitution data does not exist before 2025

**2021–2024 NCAA stints are placeholders, not lineups.** Per team-game distribution of distinct players holding stints:

| Season | Team-games with exactly 5 stint-players | Team-games with 6+ (real subs) |
|---|---|---|
| 2024 | 11,319 / 11,586 (97.7%) | 0 |
| 2025 | 8,523 (~73%) | ~3,125 (27%) |
| 2026 | ~0 | ~100% |

In 2021–2024, every game's stints are 5 players per team × full halves (`clock 1200→0`), i.e. the boxscore **starters ride the entire game**. `sync_ncaa_pbp` seeds lineups from `PlayerGameStats.starter=True` and updates them only on ESPN substitution events (type 584); for stored 2019–2024 PBP those events are absent, so no stint ever closes mid-half.

**Consequences:**

1. "RAPM" for 2021–2024 is not RAPM. It is game-level plus-minus attributed to a fixed 5-man unit. One observation per half per game, identical lineups within a game → the design matrix cannot separate teammates; bench players never appear on court.
2. `baseline_obpr`/`baseline_dbpr` for those seasons — the training targets for Box BPR (`db_baseline` path) and inputs to the preseason models — inherit this degeneracy.
3. RAPM observation counts confirm it: 2024 = 11.8K observations (~1 segment/game); 2025 = 53K; 2026 = 172K (~15 segments/game) at equal total possessions.
4. Any player-level RAPM validation on pre-2025 seasons measures the wrong thing. Cross-season backtests remain interpretable as tests of the whole (box-dominated) system, not of lineup RAPM.

**Follow-up (Phase 5 candidate):** test whether ESPN's API currently serves substitution events for 2021–2024 games. The parser demonstrably works (2026). If a re-sync backfills real stints, four seasons of true RAPM history unlock at once — likely the single highest-leverage data fix available.

---

## Second production gap — 2025 has no BPR at all

`PlayerSeasonStats` season 2025: **0 rows with `bpr` non-null** (A11). All other seasons 2015–2024 and 2026 have ~2.8–3.8K rated players. The 2025 season was either never computed with the current pipeline version or wiped by a partial re-run. This matches the NBA-side memory note that stored 2025 output is stale/incoherent with the current pipeline. Any backtest pair involving stored 2025 NCAA ratings is currently impossible — 2025 must be recomputed (non-destructively for experiments; production write is the user's call).

---

## Check-by-check results (NCAA)

### A1 — Stint minute coverage: WARN (systematic +12.5%)
Median stint-time ratio is **exactly 1.125 (=45/40 min) in every season**. Cause found: phantom overtime stints — 47,424 stints of exactly `(period=3, clock 300→0)` in 2024 alone, present in ~82% of games (real OT rate ≈ 5%). End-of-game handling in `sync_ncaa_pbp` opens a 300-second period-3 stint block for every player still on court. Sampled games show these carry ~zero points (score reconciles with periods 1–2 alone), so RAPM's `MIN_SEGMENT_POSS` gate drops most of them, but:
- `on_court_secs_pg` (a Box BPR context feature) is inflated ~12.5% across the board;
- ratio 1.25 games (228 in 2024) have two phantom periods.
2021 additionally has only 76.9% of final games covered by stints at all.
**Severity:** definite parser bug, moderate impact (uniform inflation, mostly gated out of RAPM).

### A2 — Duplicate/overlapping stints: FAIL 2022, 2024, 2025, 2026
Exact duplicates (same player/game/period/clock with different `stint_index`): 20 (2022), 10 (2024), 12 (2025), 74 (2026). Overlapping intervals: 2026 worst at 0.15% of stint-seconds across **495 games (~8%)**; some overlaps are near-total (e.g. `1200-40` vs `992-0` — a player on court twice simultaneously). During overlapping windows the 5v5 resolver either fails (segment dropped) or resolves the wrong five.
**Severity:** same bug class as the NBA 2026 `update_conflicts` incident. Small in aggregate; concentrated per-game. Fix path is the same: delete + single re-sync for affected games (list in `a2_overlaps_*.csv`). Not a Phase 4 blocker at 0.15%, but the affected-game list should be excluded from stint-sensitive experiments.

### A3 — Lineup-size sweep: PASS
Clean-5v5 share of covered seconds: 88.0% (2021) → 97.96% (2025), 93.95% (2026). Better than the 77.5% docstring claim — but note for 2021–2024 this is vacuously clean (fixed 5-man placeholders are always 5v5).

### A4 — Possession sanity: PASS
Median stint-Kubatko vs box-score possession ratio 0.957–0.969 across seasons; 6–8% of game-teams flagged beyond ±10%. The ~3.5% systematic undercount comes from imperfect stint box-event attribution; unbiased enough for RAPM weights.

### A5 — FGA coverage: PASS 2021–2026
73–80% of stints have `team_fga > 0`; all audited seasons clear the 50% `datasets.py` gate. (2015–2020 exclusion not directly re-tested here; the gate logic itself was verified in code.)

### A6 — Through-date builder consistency: PASS (Phase 4 gate cleared)
`build_rapm_dataset([Y])` vs `build_rapm_dataset_through_date(Y, season-end)`: identical observation counts, total possessions, and player columns for all six seasons.

### A7 — Mid-season transfers: PASS
0–1 multi-team players per season in NCAA game logs; zero misattributed stints. (Effectively no mid-season transfers in college — expected.)

### A8 — OT / neutral flags: two metadata defects
- `went_to_ot` is **never set** (0 OT games across six seasons; real rate ~5%). `period_count` is NULL on sampled games too. Downstream: `TeamGameStats` pace/possession scaling that keys off `went_to_ot` (40 vs 45 min) is silently wrong for OT games.
- **2026 has zero `neutral_site=True` games** (2021–2025: 519–761/season). Neutral handling in RAPM HCA, adjusted ratings site factors, and margin backtests is broken for 2026 — every 2026 neutral game is treated as home/away.
**Severity:** definite ingestion defects; cheap to fix; matter for the backtest arms.

### A9 — Freshman recruiting coverage: effectively 0%
`PlayerRecruitingProfile` contains **48 rows total, all class 2026** — vs ~3,000–3,600 newcomers per season. Coverage 0.0% for 2022–2025 and 1.3% for 2026. **The recruiting-tier prior path (`RECRUITING_PRIOR_*` constants, rank bonuses, per-tier SDs) essentially never fires in production.** Freshman priors in practice are box-BPR-only or flat (0, wide SD). All tuning of those constants is untested dead code until profiles are ingested.

### A10 — Evan Miya match audit: PASS
Match rates 98.7–99.9% for 2021–2025 (fuzzy accept ≥ 0.58); worst accepted scores ~0.58 dumped to `a10_em_worst_matches_*.csv` for eyeballing (spot-check shows same-player name variants, not wrong players). 2026 EM data currently holds only 200 records (partial leaderboard). The `em_calibrated` Box BPR training path is healthy.

### A11 — BPR by possession bucket: healthy for 2026
2026: sources behave as designed (box_bpr below 200 poss, rapm above; extreme |BPR|>8 rate 0.8% in the 200–400 bucket). 2021–2024 buckets exist but sit on placeholder-RAPM values. 2025: no BPR (see above).

### A12 — Garbage time: 6.1–8.4% of stint-seconds
Share of stint time in 2nd half of 25+ point blowouts rises from 6.1% (2021) to 8.4% (2026). No flag exists anywhere; all of it enters RAPM at full weight. Quantified experiment candidate for Phase 5.

---

## Check-by-check results (NBA)

| Check | Result |
|---|---|
| B1 stint duplication | **PASS all 2022–2026** — 0 exact dupes, 0 overlap. The 2026 fix held; no recurrence. |
| B2 traded players | PASS — 71–105 multi-team players/season, all with per-team season rows. |
| B3 LEBRON id match | PASS — 98.5–99.7% of qualified players matched, 2022–2026. (Note: older CSVs use `nba_id` header, 2026 uses `_id`; production loader handles both.) |
| B4 d_mpir / pbp_quality | PASS — d_mpir coverage 94.8–100%; 0.5–2.5% of games PBP-flagged and excluded. |

NBA data layer is clean. NBA weaknesses are modeling-side (see report 03), not data-side.

---

## Trust verdicts → what the Phase 4 backtest may use

| Season | NCAA stint quality | Verdict |
|---|---|---|
| 2021–2024 | Placeholder 5-man lineups | Usable for **box-driven** cross-season arms and as Box BPR training history; **meaningless for lineup-RAPM claims**. Label all results accordingly. |
| 2025 | Mixed (27% real subs); **no stored BPR** | Recompute (persist=False) before use; RAPM interpretable with caveats. |
| 2026 | Real substitution data; 8% of games have overlap defects; neutral flags missing | Primary season for rolling within-season backtest. Exclude the 495 overlap games from stint-sensitive checks; treat HCA/neutral splits as unavailable until flags are backfilled. |
| NBA 2022–2026 | Clean | All usable. |

**Gates for Step 4:** A6 PASS (through-date builder exact) — cleared. A2 FAIL is documented and quantified (≤0.15%); proceed with the exclusion list rather than blocking, since the defect is bounded and listed per game.

---

## Remediation log (2026-07-02, post-audit fixes)

### Applied fixes — before/after

| Fix | Command | Before | After |
|---|---|---|---|
| 2025 NCAA BPR missing | `compute_ncaa_bpr --season 2025` (production config, filled nulls) | 0 rows with bpr | **3,530 rows**; all 13 validation checks pass; HCA 3.84; top-25 sane (Tugler 11.2, Knueppel 10.9, Flagg 9.9) |
| Phantom OT stints (bug 1.2) | `fix_ncaa_stint_data` — deletes zero-point full-span period≥3 blocks | 23.7K–57.8K phantom stints/season (2021–2026); A1 median stint-time ratio 1.125 | **259,466 phantom stints deleted** across 6 seasons; A1 median ratio now **1.000** every season; real OT periods kept (425–697/season) |
| Exact duplicate stints (bug 1.3a) | same command | 20/10/11/64 dupes (2022/24/25/26) | **0 exact dupes** all seasons (A2 re-run) |
| `went_to_ot`/`period_count` never set (bug 1.4) | same command — backfilled from surviving stint periods | 0 OT games recorded, all seasons | 354–611 OT games/season (~6–10%, plausible); `ot_flag_period_mismatch=0` |
| 2026 neutral flags missing (bug 1.5) | new `backfill_neutral_flags --season 2026` (ESPN scoreboard by date, matched on date+team pair via TeamExternalId) | 0 neutral games | **588 neutral games set** (5,788/6,297 games matched to ESPN events) |
| Parser root causes (bugs 1.2/1.3) | `sync_ncaa_pbp` fixed: (a) numeric `sequenceNumber` sort (was string sort — "1000"<"999" misordered plays → overlapping stints); (b) deferred period reopen (END_PERIOD no longer fabricates a post-regulation stint block); (c) defensive close-before-reopen on double sub-in | single-game re-sync recreated 9 phantoms + overlaps | re-sync of test game: **0 phantoms**; overlap reduced; residual overlap traced to a *different* defect (one Player receiving stints from two ESPN athlete identities) |
| Overlapping stints 2025/2026 (bug 1.3b) | targeted `sync_ncaa_pbp --game-ids ... --force` re-sync of 139 (2025) + 490 (2026) flagged games with the fixed parser | 0.06% / 0.15% of stint-seconds | re-sync in progress — final A2 numbers to be appended |
| On-court aggregates stale after stint repair | `compute_ncaa_player_impact` re-run 2021–2026 | `on_court_secs_pg` +12.5% inflated | recompute in progress |

### Truthful-baseline plumbing (Step 2 of the v2 path)

- `FIRST_VALID_RAPM_SEASON = 2025` + `is_valid_rapm_target_season()` added to `constants.py`.
- `run_bpr_season(truthful_targets=True)` / `compute_ncaa_bpr --truthful-targets` / `backtest_bpr_suite --truthful-targets`: restricts the RAPM pool to valid seasons and excludes pre-2025 baselines from Box-BPR `db_baseline` targets, the 0.20 prior-history blend, and preseason-model training. External EM targets unaffected. Default off — production behavior unchanged.
- Note from artifacts: production 2024–2026 Box BPR already trains on **em_calibrated** external targets, so the placeholder contamination enters mainly through the 4-yr RAPM pool, prior-history blend, and preseason models — exactly what truthful mode gates.

### Still blocked / open

- **Recruiting priors (issue 2.1):** no recruiting source data exists anywhere in the repo (only 48 profiles, class 2026). `import_recruiting --file <csv>` is ready; needs user-supplied 247/On3 exports for classes 2021–2026. All `RECRUITING_PRIOR_*` calibration stays dead code until then.
- **Duplicate ESPN athlete identities:** at least one case of a single `Player` accruing stints under two ESPN ids (residual overlap after parser fix). Needs an identity audit pass; affected games go on the exclusion list meanwhile.
- **Pre-2025 substitution backfill:** untested whether ESPN currently serves substitution events for 2021–2024 (the parser provably works on them now). Single-game probe is the next data experiment.
