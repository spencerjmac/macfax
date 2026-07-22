# Macfax conventions — written baseline (stub)

Status: documentation only. The open decision at the bottom is deliberately
NOT resolved here (Phase 7 item 12 — the operator deferred it); this stub
exists so the eventual decision has a written starting point.

## The minutes-share pool (both products)

- The allocation currency is a **5.0-share pool** per team ("5 lineup slots").
- Conversion in code and display: **share × 20 = MPG-equivalent**
  (MINUTES_CEIL 1.80 ⇒ 36 MPG; NCAA `mpg_p2 = minutes_share_p2 × 40` uses the
  40-minute-game framing — same pool, factor differs by sport framing).
- All calibrated slopes (NCAA SLOPE_OFF/DEF, NBA SLOPE / PV_SLOPE) were fit on
  aggregates computed **in this share currency**, so the pool is internally
  consistent: changing the convention requires re-deriving those slopes.

## The known mismatch (the deferred decision)

- The pool descends from the NCAA implementation: 5.0 shares ≈ 200
  team-minutes at 40-minute games.
- **NBA games are 48 minutes → 240 team-minutes.** The NBA pipeline inherited
  the 5.0-pool/×20 convention anyway; the pool therefore under-represents real
  NBA minutes by 240/200 = 1.2× (and the `mpg/36` demand term is a third
  framing again).
- This has already bitten once: the Phase 2 `formatMinutesShare` display bug
  came from an author reasonably assuming shares were a 0–1 fraction of real
  team minutes (the model help_text said so, wrongly — fixed in Phase 4).

## When the decision is made, it must cover

1. One sport-aware share→minutes conversion, used by allocator, models,
   serializers, and display alike (single source of truth, not per-file math).
2. Re-derivation of every slope calibrated on the old currency (NCAA
   SLOPE_OFF/DEF; NBA SLOPE, PV_SLOPE — house two-stage gate applies).
3. Migration/display plan for stored `minutes_share` values.

Until then: **do not "fix" individual conversion sites in isolation** — local
corrections against a globally consistent-but-odd currency introduce real
bugs into a system that is currently only cosmetically odd.
