# 15 — Correction to Doc 14: the bake-off pool was contaminated by pre-2025 placeholder lineups

Doc 14 concluded "EvanMiya wins clean sweep" and flagged a secondary finding
that Macfax `box_bpr` and even team-level `adj_em` beat full `bpr`, suggesting
the RAPM blend was self-inflicted damage. That framing was wrong, or at least
badly incomplete. Root cause below, and a corrected read.

## What was actually tested

Doc 14 ran `--seasons 2022 2023 2024 2025` (3 folds: 2022→23, 2023→24,
2024→25). Every fold uses a **2022, 2023, or 2024 season as the predictor**
side. Checked `bpr_source` distribution by season:

| Season | rapm | box_bpr | mixed/partial |
|--------|------|---------|----------------|
| 2022   | 2,912 (93%) | 230 | — |
| 2023   | 2,943 (93%) | 208 | — |
| 2024   | 3,059 (94%) | 201 | — |
| 2025   | 3,102 (88%) | 415 | 15 |

`docs/bpr_audit/03_weakness_report.md` (item 1.1) and `06_bpr_v2_recommendation.md`
already documented that **NCAA lineup data for every season before 2025 is a
starters-only placeholder** — ESPN never served substitution events before
~Feb 2025, so "RAPM" for 2021-2024 is actually a fixed 5-man-unit team-margin
share, not real individual lineup impact. `06_bpr_v2_recommendation.md` line 31:
*"Any pre-2025 NCAA quantity presented as lineup RAPM — permanently[invalid],
unless PBP re-sync backfills substitution events."* Line 156: that backfill
was probed and closed — no free fix exists.

The `--truthful-targets` fix documented in 06 changes what feeds **training**
(box_bpr no longer learns from bad pre-2025 RAPM targets) — it does not, and
cannot, retroactively fix the pre-2025 `bpr` field itself, which is still
~93% RAPM-sourced from degenerate placeholder lineups. So doc 14's bake-off
tested Macfax BPR using **only structurally-broken predictor seasons**, in
every one of its 3 folds. `box_bpr` (trained toward EM targets, never touches
the bad in-season RAPM) and `adj_em` (team-level, no player lineup RAPM at
all) were never exposed to this contamination — so of course they came out
ahead. That comparison was never fair to `bpr`.

## Clean re-run: 2025→2026 only

2025 is the first season with real substitution-event lineup data. Ran the
one fold that doesn't touch placeholder data as a predictor:

`python manage.py backtest_em_bakeoff --seasons 2025 2026 --verbose`

| Predictor         | n     | RMSE   | MAE    | WinAcc | AUC    | Brier  |
|-------------------|-------|--------|--------|--------|--------|--------|
| bpr (Macfax)      | 3,016 | 12.684 | 10.014 | 0.667  | 0.7001 | 0.2090 |
| em (EvanMiya)     | 3,016 | 12.549 | 9.938  | 0.668  | 0.7107 | 0.2064 |
| box_bpr (Macfax)  | 3,016 | 12.607 | 9.987  | 0.666  | 0.6982 | 0.2083 |
| adj_em            | 3,016 | 13.517 | 10.711 | 0.656  | 0.6774 | 0.2178 |
| home_only         | 3,016 | 14.564 | 11.397 | 0.620  | 0.5088 | 0.2375 |

EM match rate 99.3% (vs 95.5% avg in the contaminated pool) — 2025 EM
coverage is also better than 2022-2024's.

## Corrected picture

- **Δ(bpr − em) RMSE shrinks from +1.054 to +0.135** — an 87% reduction.
  WinAcc is a virtual tie (0.667 vs 0.668, Δ=-0.001). EM still edges ahead on
  every metric, but this is now a close race, not a rout.
- **`bpr` now essentially matches `box_bpr`** (12.684 vs 12.607 — 0.077 RMSE
  apart, a wash) instead of trailing it by 0.563. The "RAPM blend is
  self-inflicted damage" read from doc 14 does not hold up on clean data.
- **`bpr` now clearly beats `adj_em`** (12.684 vs 13.517) — reversed from the
  contaminated pool, where adj_em beat bpr. This is the direction you'd
  actually expect (player-level rating beating a plain team aggregate). The
  script's own sanity-gate note flags this as "surprising" — that's because
  it was tuned against the broken pattern being normal; here it's correct.

## Bottom line

The real, fair verdict — tested on the one season where Macfax's lineup data
isn't structurally placeholder — is **EM slightly ahead, BPR close behind,
both clearly beating the box-only and team-only baselines**. That's a much
more encouraging result than doc 14 reported, and the "RAPM blend is hurting
prediction" thread from doc 14 is not supported once the pre-2025 placeholder
contamination is controlled for — retract that conclusion.

Practical implication: **any future BPR backtest needs a season floor of
2025** (or wait for 2026 to deepen the pool) to mean anything. Pooling in
pre-2025 seasons as predictor years — as doc 14 did, and as
`backtest_em_bakeoff`'s own multi-season examples in its docstring invite —
silently reintroduces the placeholder-lineup contamination every time. Worth
either hard-gating the command to `--seasons >= 2025` or adding a loud warning
when older seasons are requested as predictors.
