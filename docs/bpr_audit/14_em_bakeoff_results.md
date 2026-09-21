# 14 — Macfax BPR vs EvanMiya: Bake-Off Results (2026-09-21)

`backtest_em_bakeoff.py` existed, was leak-free, and had never been run and
recorded. This is that run.

## Setup

- Command: `python manage.py backtest_em_bakeoff --seasons 2022 2023 2024 2025 --verbose`
- Frame: cross-season only (year-Y ratings predict year-(Y+1) games). EM has
  no partial-season slicing, so this is the only leakage-free frame available.
- Matched universe: only players appearing in both Macfax and EM for a given
  season (fuzzy name+team match, threshold 0.55) — both predictors see the
  identical player set, same mpg weights, same coverage denominator.
- 3 folds: 2022→2023, 2023→2024, 2024→2025. Match rate 95.2–95.8% (avg 95.5%).
- 6,525 test games total, min_coverage=40%.

## Results

| Predictor         | n     | RMSE   | MAE    | WinAcc | AUC    | Brier  |
|-------------------|-------|--------|--------|--------|--------|--------|
| bpr (Macfax)      | 6,525 | 13.470 | 10.660 | 0.652  | 0.6550 | 0.2209 |
| em (EvanMiya)     | 6,525 | 12.416 | 9.784  | 0.678  | 0.7023 | 0.2027 |
| box_bpr (Macfax)  | 6,525 | 12.907 | 10.168 | 0.661  | 0.6609 | 0.2118 |
| adj_em            | 6,525 | 12.763 | 10.083 | 0.668  | 0.6910 | 0.2087 |
| home_only         | 6,525 | 13.991 | 10.947 | 0.647  | 0.5071 | 0.2289 |

## Verdict

**EvanMiya wins.** Not close, and not split — EM beats Macfax BPR on every
single metric: RMSE (+1.054 worse for Macfax), MAE, WinAcc, AUC, and Brier.

The script's own printed annotation says `WinAcc Δ: -0.025 (DISAGREES with
RMSE verdict)` — that annotation is wrong, not the result. Checked the code
(`backtest_em_bakeoff.py:373-374`): the WinAcc agreement check compares
`(delta_wa < 0) == (delta_rmse < 0)` with no correction for WinAcc being
higher-is-better against RMSE being lower-is-better, so it flags disagreement
whenever both metrics actually agree that EM is better. The AUC check two
lines down (`:375-376`) has the correct sign correction. Small standalone bug
in the script, doesn't change the substance of the result — all 5 raw metrics
independently favor EM.

## Secondary finding — worth its own look

`box_bpr` (Macfax's box-score-only component, no RAPM) beats full `bpr`
(Macfax) on every metric in this test: RMSE 12.907 vs 13.470, MAE 10.168 vs
10.660, WinAcc .661 vs .652, AUC .6609 vs .6550. The plain team-level `adj_em`
(no player aggregation at all) also beats full player-level `bpr`. Whatever
the RAPM/prior blend is adding to `box_bpr` to produce the full `bpr` is
currently making the game-prediction signal *worse*, not better, in this
leak-free frame. This is independent of the EM comparison and arguably the
more actionable finding — worth a dedicated diagnostic on what the RAPM
blend step is doing to predictive power.

## Sanity gate

`⚠ Macfax β2=+4.18 outside [2,4]` — mild, not a correctness alarm, but flagged
by the script's own gate and worth knowing about if β2 stability matters
downstream.

## Bottom line

The EM bake-off question that's been open the longest now has an answer:
EvanMiya currently predicts games better than Macfax BPR, on a leak-free,
matched-universe, held-out test. The `box_bpr`-beats-`bpr` finding suggests
part of the gap may be self-inflicted (the RAPM blend), not just "EM's data
is better" — that's the next thread to pull before concluding BPR needs a
bigger rebuild.
