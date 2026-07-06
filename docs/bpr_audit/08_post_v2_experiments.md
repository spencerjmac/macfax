# BPR Audit — 08: Post-v2 Experiments & Accuracy Scorecard

**Date:** 2026-07-05
**Purpose:** (1) the standing answer to "how accurate are our BPRs vs everything else"; (2) the post-v2 experiment ledger (one change at a time, ship only what wins).

---

## 1. Accuracy scorecard — where MacFax BPR stands today

### NCAA — at parity with the industry reference

Head-to-head on identical out-of-sample games (2025 ratings → all 5,751 games of 2026, same rosters, same coverage; run `em_vs_us_cross`):

| Rating | RMSE | Win acc | Log loss | AUC |
|---|---|---|---|---|
| **MacFax BPR v1.7** | 13.08 | **.676** | .589 | .701 |
| **EvanMiya adj_bpr** | **13.04** | .672 | **.584** | **.708** |
| MacFax box_bpr | 13.04 | .677 | .589 | .698 |
| adj_em (team-only) | 13.62 | .661 | .637 | .693 |

**Verdict: statistical tie with EvanMiya** — the gap (0.04 RMSE, 0.004 acc) is noise at n=5,751. Both player models beat the team-only rating decisively. Player YoY stability on real data: **0.69** (EM doesn't publish an equivalent; NBA-metric context below says this is strong). NCAA BPR is a legitimate, competitive player-value metric as of v1.7 — no reason to switch.

Reliability boundary to communicate honestly: ratings driven by 2025–26 data are trustworthy; anything labeled pre-2025 RAPM is starter-unit plus-minus (permanent data limitation, §06).

### NBA — mid-pack forward, better than LEBRON on our framework, behind top box metrics

Two frameworks, reported separately (different targets/aggregations):

**(a) `nba_predictive_test` — season N metric → season N+1 team WINS** (3 pairs, 2022–26):

| Rank | Metric | avg forward r | Star YoY r |
|---|---|---|---|
| 1 | VORP | 0.593 | 0.233 |
| 2 | WS | 0.589 | — |
| 3 | BPM | 0.573 | 0.755 |
| 4 | WS48 | 0.568 | 0.602 |
| 5 | BOX_BPR (ours) | 0.534 | 0.504 |
| 6 | DBPM | 0.532 | — |
| **7** | **BPR (ours)** | **0.522** | 0.531 |
| 8 | OBPM | 0.454 | — |
| 9 | PER | 0.436 | 0.853 |

**(b) Our leak-free harness — season N metric → season N+1 adj_net** (same aggregation for all, 3 clean pairs):

| Metric | avg forward r | Team RMSE |
|---|---|---|
| **BPR (0.75 config)** | **0.36** | 3.94 |
| LEBRON (published) | 0.32 | — |
| Persistence (team-only) | 0.29 | 5.35 pooled |

**Honest verdict:** NBA BPR beats LEBRON and persistence on our framework, but **VORP/WS/BPM predict next-season team success better** (gap ≈ 0.05–0.07 r), and BPM's star stability (0.755) still exceeds ours (0.531). Also note: our final BPR trails our own BOX_BPR component on framework (a) — the RAPM layer currently costs forward accuracy at team level while adding context-adjustment at player level.

**Consequence for player values (per the mission's own rule):** if a use-case is *forward team projection from player values*, a `BPR + VORP/BPM blend` (or those metrics outright) is currently the better input. Experiment N-BLEND below tests exactly that before any switch decision. For *context-adjusted player evaluation* (role players, lineups, who-helps-whom), BPR remains the differentiated product — no public box metric answers that.

### Standing measurement commands

```bash
# NCAA vs EM + all arms (leak-free)
python manage.py backtest_bpr_suite --mode cross-season --seasons 2025 \
    --extra-ratings-json backtest_output/bpr_suite/ratings_2025_evanmiya.json
# NBA vs public metrics
python /home/spencer/Workspace/macfax/analysis/nba/nba_predictive_test.py
# NBA variant harness
python manage.py nba_experiment_final_bpr --source-seasons 2022 2023 2024 --run-name check
```

---

## 2. Experiment ledger (one at a time; ship criteria: forward prediction or calibration/stability without prediction cost)

| ID | Experiment | Status | Result | Ship? |
|---|---|---|---|---|
| N-A | Smooth reliability gates: `rel = poss/(poss+k)`, blend RAPM↔box | **DONE (split verdict)** | Cross-season 2025→26 (min-poss 50): hard-gate 13.02 → **k=1500: 12.95** (monotone, beats both endpoints; box-only 13.04). **Within-season: FAILS** — k=1500 worse than plain BPR at every 2026 cutoff (Dec 13.48 vs 13.05, Jan 12.05 vs 11.81, Feb 11.71 vs 11.49). Interpretation: heavy box-weighting is a *cross-season projection* property (box transfers between years), not a rating property (RAPM carries live in-season signal). | **NO as v1.8 rating change. YES as projection-time transform**: apply `rel(k≈1500)` blend when using season-Y ratings for season-Y+1 (margin projections, preseason team outlooks). Live ratings keep v1.7 gates. Convergent with NBA N-BLEND: evaluation metric ≠ projection input, both leagues. |
| N-B | Separate off/def prior SD scaling (override sweep vs CV-chosen 0.3) | **DONE** | Cross-season 2025→26 (truthful base 13.02): def 0.15 → 12.99; off 0.15 → 12.98; def 0.60 → **13.16 (worst)**. Tighter-everywhere helps cross-season (same box-transfers-better theme as N-A); loosening defense clearly hurts — defense-is-noisier confirmed directionally. | **NO standalone** — the pipeline's own CV optimizes within-season held-out WMSE and chose 0.3; cross-season gains are subsumed by the N-A projection transform. Keep CV tuning for live ratings. |
| N-C | Garbage-time downweighting (blowout 2nd-half stints; 6–8% of stint-secs) | **DONE** | gw=0.25: cross-season 12.99 vs 13.02 (same family-of-tiny as N-A/N-B); player YoY stability **identical** (0.6508 vs 0.6501). gw=0.0 crashes lambda-CV on zero-weight rows (floor at ≥0.05 if ever revisited). | **NO** — RAPM's opponent context already absorbs garbage time; no stability gain, margin gain subsumed by N-A projection transform. Plumbing kept for future use. |
| N-D | Empirical freshman priors by recruiting tier | **blocked: CSVs** | | |
| N-E | Transfer translation priors (conference jump/drop, role change) | blocked: CSVs (partially runnable from PSP history) | | |
| N-BLEND | BPR + BPM blend as team-projection input (`analysis/nba/nba_blend_test.py`) | **DONE incl. robustness** | Pooled: α=0 0.596, **α=0.25: 0.601**, α=0.5 0.599, α=1 0.583. Per-pair: blend wins 2022→23 (0.621 vs 0.614) and 2024→25 (0.596 vs 0.588), near-ties 2023→24 (0.586 vs 0.588). Not one-pair-dependent; α=0.25 = min-regret choice. | **SHIP** as `nba_projection_player_value` for team projections only — full spec, product split, and wiring notes in doc 09. Never labeled "BPR". |
| B-A | NBA defensive-feature ablation (d_mpir, on_court_adj_d, both) | **DONE** (`nba_experiment_box_chain`) | Full-chain player-forward r 0.2874–0.2875 for every ablation vs 0.2875 with both — **no measurable effect either way**; team metrics identical. | **NO CHANGE** — keep features for descriptive DBPR; the "are they noise?" question is closed: neither noise nor forward signal at chain level. |
| B-B | NBA LEBRON_BLEND_W sweep {0, .3, .5, .7, .9, 1.0} | **DONE** | Player-forward r 0.2860→0.2877 across the whole range (0.002 spread); team metrics flat. The final-stage LEBRON prior (0.75) absorbs the box-target blend. | **NO CHANGE** — keep 0.7, parameter is inert downstream; stop tuning it. |
| B-C | NBA archetype-specific shrinkage | **CLOSED without running** | B-A/B-B show box-model internals are washed out by the final stage; a box-side shrinkage scheme cannot move forward accuracy. | not worth compute |

**NBA wave conclusion:** forward accuracy is governed by the final-stage prior weight (0.75, shipped) and λ schedule (validated by ablation). Rating-side tuning has hit diminishing returns. The shipped gains live projection-side: `nba_projection_player_value` (doc 09).

Each entry reports on completion: margin RMSE/MAE, log loss, Brier, calibration, player YoY stability, top-player sanity, low-minute outliers, ship call. Results appended below as they land.

**NCAA wave conclusion (N-A/N-B/N-C complete):** all three formula changes produce the same signature — a small cross-season improvement from shifting weight toward box priors, no within-season improvement, no stability improvement. v1.7's live-rating formula is locally optimal for its job. The two levers that remain are **data** (recruiting priors → N-D/N-E) and the **projection transform** (N-A's k≈1500 reliability blend, applied only when season-Y ratings project season-Y+1). This mirrors the NBA N-BLEND finding exactly: evaluation metric ≠ projection input.

---

## 3. Recruiting ingestion (unblocks N-D/N-E)

Built and waiting on data:
- `import_recruiting --file <csv> [--dry-run]` — upsert with ESPN-id or fuzzy-name matching (`--print-template` for schema)
- `check_recruiting_data --seasons 2021..2026` — post-import validation: coverage by class/tier, match-quality report, missing-profile list of high-minute freshmen, duplicate detection
- Freshman-prior backtest hook: `backtest_bpr_suite --mode player` already reports newcomer prior-vs-realized bias/MAE/r per season — the before/after measure for N-D

Required CSV columns: `espn_id, player_name, class_year, stars, national_rank, composite_score, position_rank, source, notes` (header row; espn_id strongly preferred).
