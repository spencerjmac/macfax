# BPR Audit — 09: NBA Projection Blend (`nba_projection_player_value`)

**Date:** 2026-07-05
**Ship call: YES** — as the player-value input to NBA *team projections only*. Player-facing BPR is unchanged and must never be replaced or relabeled by this value.

## Definition

```
z_BPR, z_BPM  = within-season z-scores over qualified players (>=500 min)
nba_projection_player_value = 0.25 * z_BPR + 0.75 * z_BPM
```

BPM from BBref advanced exports (`metrics_output/bbref_advanced_{year}.csv`); BPR from `NBAPlayerSeasonStats`. Rate metrics both → minutes-weighted team aggregation stays valid.

## Evidence

Test: season-N player values → season-N+1 team wins, minutes-weighted team aggregate, Pearson r (`analysis/nba/nba_blend_test.py`).

| Pair | pure BPM (α=0) | **α=0.25** | α=0.5 | pure BPR (α=1) |
|---|---|---|---|---|
| 2022→23 | 0.614 | 0.621 | **0.622** | 0.614 |
| 2023→24 | **0.588** | 0.586 | 0.575 | 0.541 |
| 2024→25 | 0.588 | 0.596 | **0.600** | 0.594 |
| **avg** | 0.596 | **0.601** | 0.599 | 0.583 |

Ship criteria check:
- Beats pure BPM and pure BPR pooled ✓ (0.601 > 0.596 > 0.583)
- Not one-pair-dependent ✓ — wins two independent pairs, near-ties the third (−0.002)
- Does not harm the projection framework ✓ — α=0.25 is never materially below BPM in any pair (α=0.5 has higher upside but loses 0.575 vs 0.588 in its bad pair; 0.25 is the robust choice)
- Product distinction ✓ — see below

## Alpha stability

Optimum sits at 0.25–0.5 in the two good pairs and at 0 in the bad pair; the pooled curve is flat between 0.25 and 0.5 (0.601 vs 0.599). **0.25 chosen for robustness** (min-regret across pairs), not peak-chasing. Re-derive when the 2026→27 pair lands.

## Product architecture (per the approved split)

| Surface | Value shown | Name |
|---|---|---|
| Player pages, rankings, scouting cards | BPR / OBPR / DBPR + confidence badge | **BPR** |
| Team outlooks / win projections / forecasts | 0.25·z(BPR) + 0.75·z(BPM) | **Projection Value** (internal: `nba_projection_player_value`) |

Why the split (user-facing copy, one sentence): *"BPR measures context-adjusted player impact; team forecasts use a blended projection value because it predicts future results better out of sample."* Never label the blend "BPR".

## Related findings that close the NBA tuning program (see 08 ledger)

- **B-B `LEBRON_BLEND_W` sweep (0→1): inert** — full-chain player-forward r range 0.0017. The final-stage LEBRON prior (0.75) absorbs whatever the box-target blend was doing. Keep 0.7; stop tuning it.
- **B-A defensive ablation (d_mpir / on_court_adj_d / both): no measurable forward effect** through the chain (0.2874–0.2875 vs 0.2875). Features kept for descriptive DBPR quality; they are neither noise nor forward signal at chain level.
- Meta-conclusion: NBA forward accuracy is governed by the final-stage prior weight (shipped 0.75) and λ schedule (validated). Box-model internals are washed out. Further NBA tuning has hit diminishing returns; the next real NBA gains are projection-side (this blend, minutes/injury modeling) — not rating-side.

## Implementation (SHIPPED 2026-07-05)

- **Fields** on `NBAPlayerSeasonStats` (migration 0022): `projection_value`, `projection_value_version` ("pv1"), `projection_value_source` (`bpr+bpm` | `bpr_only`), `projection_alpha` (0.25).
- **Compute**: `nba/analytics/projection_value.py` + `manage.py nba_compute_projection_values --season YYYY` (run after `nba_compute_final_bpr`). z-scores over ≥500-min qualified players; BBref BPM fuzzy-matched (2026: 464/579 bpr+bpm, 115 bpr_only fallback). Stored for 2022–2026.
- **Consumption**: `compute_nba_team_outlooks` — slots carry `projection_value`; per-slot `pv_effective` applies the same returner/acquisition shrinkage as the BPR path (players without stored PV fall back to z(projected_bpr)); team signal = minutes-share-weighted mean; **projected adj_em = PV_SLOPE × (team_pv − league_pv_mean)** with `PV_SLOPE=3.58`, `PV_SIGMA_EM=4.5` (calibrated: n=90 team-seasons, r=0.304, pooled RMSE 4.32). Off/def split keeps the legacy shape, rescaled to the PV total. Legacy BPR-path adj_em still computed and logged per team for comparison.
- **Wins intercept correction found during wiring**: legacy `WINS_INTERCEPT=44.3` was fit to an uncentered EM scale; the centered PV path uses `PV_WINS_INTERCEPT=41.0` (league-average team = .500). Post-fix league mean projected wins = 40.97 ✓.
- **Tests** (`nba/tests/test_projection_value.py`, 4 passing): outlook adj_em follows PV and is invariant to BPR at fixed PV; centered-slope formula exact; legacy path reported separately; off/def split sums to the PV total.
- **Before/after** (2026→27 outlooks): PV path compresses the spread honestly (33–50W vs legacy 29–44W tail-heavy); biggest movers were legacy-BPR pessimism cases (MEM 31→42, BKN 31→37 after intercept fix, MIL/WAS +6–9). OKC 50W atop.
- Player pages/cards untouched — they read `bpr/obpr/dbpr` only; `projection_value` is not serialized to any player-evaluation surface.

## Commands

```bash
backend/.venv/bin/python analysis/nba/nba_blend_test.py            # re-derive table
python manage.py nba_experiment_box_chain --source-seasons 2022 2023 2024 \
    --lebron-blend-w 0.7 --run-name check                          # chain harness
```

## Limitations

- Three pairs; 2025→26 excluded from blend derivation (transition-year anomaly documented in 06 §3). Revisit with the 2026→27 pair.
- Wins target; adj_net target gives the same ordering (08 §1).
- BPM dependency: external (BBref). If the feed dies, α falls back to 1.0 (pure BPR) gracefully.
