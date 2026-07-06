# BPR Audit — 05: Next Steps Plan (audit lock)

**Date:** 2026-07-02
Audit Phases 1–4 are complete. This document locks what the audit established and gates what happens next.

---

## Safe to trust now

- **The leak-free tooling itself**: `backtest_bpr_suite` (all three modes), `through_date.py` rebuilds (validated r=0.993–1.000 at season-end parity), audit commands, static anti-leak tests.
- **Cross-season baselines** as measures of *what production shipped* (numbers in 04 §2).
- **Rolling 2026 within-season baselines** — the only leak-free within-season numbers ever produced for this system.
- **NBA data layer** (B1–B4 all PASS) and `nba_forward_backtest` methodology, now over 4 auto-detected pairs.
- **NCAA 2026 stint data** (real substitutions; caveats: 495 overlap-defect games, no neutral flags).
- The `em_calibrated` Box BPR training path (strict prior-year EM, 98.7%+ match).

## NOT safe to trust

- **Any pre-2025 NCAA "RAPM" quantity as lineup-isolated player impact** — baseline_obpr/dbpr, RAPM-sourced obpr/dbpr, YoY RAPM stability numbers. They are fixed-starter-unit plus-minus.
- **All legacy walk-forward results** (leak; command now deprecated).
- `backtest_bpr_game_prediction` accuracy targets as forward evidence (descriptive).
- **`preseason_obpr/dbpr` as preseason quantities** — written in-season with current-season box features (2026 "calibration" r=0.94 across all groups = contamination).
- **Stored 2025 ratings, both leagues**: NCAA 2025 has zero BPR; NBA 2025 stored BPR is stale vs current pipeline (forward pair r=−0.04).
- Recruiting-tier prior constants (dead code — 48 profiles exist, all class 2026).
- 2026 neutral-site splits and any `went_to_ot`-dependent quantity.

## Season classification (NCAA)

| Seasons | RAPM target validity | Allowed uses |
|---|---|---|
| ≤2024 | **INVALID** — placeholder starter stints | Team-level context (adj_em), box-score priors/features, descriptive stats, EM-target training. NOT RAPM targets, NOT lineup claims. |
| 2025 | Partial (27% of games have real subs) | Lineup RAPM with caveats after recompute; second-tier evidence. |
| 2026+ | Valid | Full lineup-informed RAPM; primary experiment season. |

## Must fix before model tuning

1. 2025 NCAA BPR recompute + store (fills empty fields — nothing overwritten).
2. Phantom OT stints stripped (or excluded at read time) + `went_to_ot`/`period_count` backfill.
3. 2026 duplicate/overlapping stints cleaned (delete + re-sync or dedupe the 495-game list).
4. 2026 `neutral_site` backfill.
5. Truthful-baseline config: pre-2025 seasons flagged `invalid_for_rapm_target`; Box BPR training must not consume their baseline RAPM as if lineup-isolated (EM targets remain allowed).

Deferred (external dependency): recruiting-profile ingestion 2021+ (only 48 rows exist); ESPN PBP re-sync test for 2021–2024 substitution events — highest-leverage data experiment, needs network access to ESPN API.

## Experiments allowed next (in order)

1. Truthful blend vs current blend (Box BPR target source ablation — pre-2025 RAPM excluded).
2. Smooth possession-reliability blending vs hard 200-poss gates.
3. Prior SD retuning (separate off/def) against the leak-free suite.
4. Garbage-time downweighting.
5. Recency weighting.
6. Defensive BPR audit (shrinkage/reliability).
7. Team aggregation: does player BPR improve over adj_em; where does it break (ratings vs minutes vs double-count).
8. NBA: LEBRON_BLEND_W / LEBRON_PRIOR_W sweeps, lambda schedules, d_mpir ablation — all against `nba_forward_backtest` + team/persistence baselines.

Rule standing over all of it: one change at a time, judged on out-of-sample prediction and calibration, `--extra-ratings-json` arm for every variant, and if NCAA BPR cannot beat adj_em due to data limits, we say so and fix data first.
