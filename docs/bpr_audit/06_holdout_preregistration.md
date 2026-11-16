# BPR Audit — 06: Holdout Test Pre-registration (T.1)

**Date:** 2026-11-15
**Status:** committed before any holdout result was computed. Nothing in
this definition changes after the results are seen.

The 2006–2015 NBA seasons were never looked at by any decision in Phases 2–4.
This test checks whether the Phase 3/4 recipe holds up on them.

## Definition

Seasons: chain start 2006; sources 2007-2014 scored on Y+1. All box fits and
career windows use 2006-2015 only (career floor 2006). Fewer than 3 training
seasons -> alpha by 5-fold CV over players (as in development). --rapm-window 1.

(1) Recipe: nba_fit_box_pooled box (box_only, window 3, target lambda 300,
    alpha-max 1000, opp_quality); chain w_box 0.5, rho 1.0, x8, age-mult 1.
(2) Old native: per-season nba_compute_box_bpr --lebron-blend-w 0 box;
    chain w_box 0.5, rho 0.8, x8, age-mult 0.
(3) Recipe at x1 (as (1), --lambda-mult 1).
(4) (1)'s box used directly as ratings.

PASS: (1) beats (2) and (3) pooled by > 2 game-clustered SEs each.
Informational: whether (1)'s pooled gain falls in 24.75-40.05.

Report pooled and per-season gains, (1)-(2) and (1)-(3) with SEs, PASS/FAIL.

Nov 15: birth dates backfilled for 2006-2015 before the run; no setting changed.
