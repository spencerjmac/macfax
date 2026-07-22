# Macfax Player Market Value — Methodology

<!-- ═══════════════════════════════════════════════════════════════════
     PENDING OPERATOR SIGN-OFF — this banner is removed only by the
     operator. Until removed, nothing renders publicly from this chain
     (API serves; frontend does not link). methodology_version stays
     "1.0-pending-signoff" until the banner goes.
     ═══════════════════════════════════════════════════════════════════ -->

Every number below regenerates from `python manage.py derive_market_value`
(derivation) and `python manage.py compute_market_values` (production rows) —
this page documents the chain, its constants, and its honest limits.

## What this number is — and is not

Macfax Player Market Value is a **transparent estimate of on-court production
value**: what a player's actual performance this season was worth, in dollars,
against the economics of the revenue-sharing era. It is **not** a report of
what any player is paid. Public per-player payment data does not exist —
third-party "valuations" are model estimates, and cleared-deal databases
capture a non-representative fraction of the market. We publish our own chain
instead, with every link inspectable.

## The chain

**BPR → marginal team EM → marginal wins → dollars**

1. **Player impact (BPR).** A player's offensive and defensive Bayesian
   Performance Rating for the most recent complete season (actuals, not
   projections), weighted by their share of team minutes.

2. **Marginal team EM.** How much the player's production raises team
   efficiency margin above a *replacement-level* alternative:
   `mEM = 0.73·share·(obpr − repl_obpr) + 0.66·share·(dbpr − repl_dbpr)`
   - Slopes 0.73/0.66: the committed BPR→rating translation slopes
     (BT-4 OLS, N=1779 team-seasons — same constants the projection engine
     uses; reused, never re-fit here).
   - Replacement level: minutes-weighted mean obpr/dbpr of every player
     outside their team's top-8 actual-minutes rotation, derived fresh from
     the valuation season (2026: obpr −0.681, dbpr +0.312, N=897).
   - `share` = mpg/40 (the pipeline's 5.0-share pool convention).

3. **Marginal wins.** `mWins = mEM × 1.007` — one point of efficiency margin
   is worth ≈ one win per 30-game season on a *league-average schedule*.
   Derived from a logistic fit on 28,259 D1-vs-D1 game results (2022–2026):
   `P(win) = σ(0.134·ΔEM + 0.544·home)`. We use the schedule-neutral
   convention deliberately: raw wins-vs-EM regression (slope 0.400) is
   contaminated by schedule strength — a +10 EM mid-major wins ~3 more games
   per 30 than a +10 EM power team (power-conference residual −2.45 wins/30,
   mid-major +0.68). Macfax is a comparative product; value should not depend
   on who your conference makes you play.

4. **Dollars.** `$Value = mWins × $/win`, where
   `$/win = MBB rev-share pool ÷ median power-conference roster's total
   marginal wins`.
   - Pool: 2026-27 school cap ≈ **$21.3M** × men's basketball allocation of
     **17–23%** → **$3.6M–$4.9M**. The range is bracketed by public
     disclosures: Texas Tech projected ~17–18% of its full rev-share pool to
     men's basketball; Missouri's men's program is credited with ~23% of
     department revenue / payments to its NIL entity. Corroborating: power
     schools with FBS football were expected to direct ~75% to football,
     leaving roughly $4M for men's basketball — inside this range. The share
     varies school-to-school, so every dollar figure is a **range**, not a
     point.
   - Median power roster Σ positive mWins: 18.8 → **$/win ≈ $193k–$261k**.

**Anchor A prices the rev-share pool only; actual roster spend at top
programs includes third-party NIL above the pool, which is why implied
total values can exceed any single school's rev-share allocation.** Public
reporting confirms power-conference schools spend well beyond the ~$4M
rev-share slice via collectives and third-party deals — our closure table
exceeding the pool is consistency with that reality, not a contradiction.

## Calibration reference points (2026 actuals)

| Quantity | Value |
|---|---|
| #1 player nationally (Cameron Boozer, Duke) | +7.35 mWins → $1.42M–$1.92M |
| Median power-conference starter | +2.79 mWins → $538k–$728k |
| Median top-8 rotation player | +0.83 mWins → $160k–$217k |
| Median deep bench (rank > 10) | −0.14 mWins → ~$0 |

External closure check (house doctrine — the model must agree with the world
it didn't train on): implied full-roster values — Duke $6.4–8.7M, Florida
$6.2–8.4M, Gonzaga $6.0–8.1M, Kansas $4.9–6.6M, Vermont $1.1–1.5M — sit
inside publicly reported top-roster spend ($5–10M+) without any tuning toward
it. The anchor range is the only degree of freedom, and it is sourced, not
fit. See the Anchor-A paragraph above for why top-roster totals may exceed
any single school's rev-share pool.

## Honest limitations

- **Replacement-level sensitivity.** Value-above-replacement doubles as a
  definition choice; moving the replacement line moves every number. Ours is
  derived (not asserted) from outside-the-rotation players, and the derivation
  prints it alongside the projection-side constant for comparison
  (they differ on offense: −0.68 actuals vs +0.26 projections — projections
  shrink toward the mean; actuals do not).
- **Schedule convention.** We value wins on a neutral schedule. The
  schedule-blind alternative was rejected on quantified grounds: power-
  conference teams under-perform their EM by ~2.45 wins/30 and mid-majors
  over-perform by ~0.68 purely from schedule strength — pricing by raw wins
  would pay players for their conference affiliation. A bubble-team's real
  marginal win may be worth more than a 30-win team's; we deliberately do
  not model leverage/tournament value in v1.
- **Share-allocation uncertainty.** The MBB slice of the rev-share pool is
  the widest error bar in the chain, which is why it is carried end-to-end
  as a range.
- **Mid-year transfers are slightly undervalued.** A split-season player is
  valued from their highest-minutes team's stat line only, so part of their
  season's production is not priced. Conservative by construction.
- **Production value ≠ market price.** Scarcity premiums, positional runs,
  eligibility, and negotiation all move real prices. This chain prices
  production, on purpose.
- **No third-party comparison layer.** A comparison column against external
  valuations was considered and **declined**: no defensible public multiplier
  connects model-estimated NIL figures to actual payments. Revisit only with
  a sourced basis.

## Provenance one-liners

| Constant | Value | Source |
|---|---|---|
| SLOPE_OFF / SLOPE_DEF | 0.73 / 0.66 | BT-4 OLS, committed (team_projection/constants.py) |
| Replacement obpr/dbpr (actuals) | −0.681 / +0.312 | derive_market_value, rank>8 by mpg, minutes-weighted, N=897, 2026 |
| Wins/EM (schedule-neutral) | 1.007 | logistic on 28,259 D1vD1 games 2022–26, k=0.1343 |
| Rev-share cap | $21.3M | public reporting, 2026-27 |
| MBB share | 17–23% | Texas Tech (~17–18%) and Missouri (~23%) public disclosures |
| $/marginal-win | $192.9k–$261.0k | pool ÷ median power roster mWins (18.77) |
