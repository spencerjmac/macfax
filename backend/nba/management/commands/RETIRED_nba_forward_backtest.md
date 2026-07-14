# RETIRED: nba_forward_backtest (Phase 4 Stage 1, 2026-07-13)

`nba_forward_backtest.py` was deleted. It was a closed island — a management
command with zero importers/callers (verified by grep across the repo).

## Why retired — stale on three axes
1. **Missing `season_type="regular"` target filter.** Its target-season
   `actual_adj_em` dict joined against all `NBATeamSeasonRatings` rows for the
   season, so playoff rows silently overwrote the regular-season rating for the
   16 playoff teams — the exact corruption class that poisoned Phase 2 Stage 1's
   candidate slopes before it was caught at the gate.
2. **Hardcoded `MINUTES_CEIL = 1.20`** — the NCAA-inherited ceiling that Phase 2
   replaced with 1.80 (NBA star scale). The backtest measured an allocator that
   no longer exists.
3. **Hardcoded `PRODUCTION_SLOPE = 0.84`** — never updated to the Phase 2
   committed `SLOPE = 0.453` / `PV_SLOPE = 5.591`.

## Replaced by
`derive_nba_slope` (Phase 2 Stage 2) — pooled multi-pair OLS with a fresh-BPR
lineage gate, explicit `season_type="regular"` target filtering + one-row-per-
team assertion, and allocator constants imported live from
`compute_nba_team_outlooks` so it can never drift on the ceiling again.
