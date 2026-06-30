# LEBRON Data Update Guide

## What Is This

LEBRON (Luck-adjusted player Estimate using a Box score prior Of Regularized on/off) is a public
player metric from BBall Index (Jacob Goldstein). MacFax uses O-LEBRON and D-LEBRON as a 50%
prior in the NBA BPR pipeline — blended with box_bpr to anchor role-player estimates.

## File Location

```
data/nba/lebron-data-{year}.csv
```

Example: `data/nba/lebron-data-2026.csv`

## Expected Columns

| Column | Description |
|--------|-------------|
| `_id` | NBA.com player ID (maps directly — no fuzzy matching needed) |
| `Player` | Player name |
| `Seasons` | Season year |
| `Team` | NBA team abbreviation |
| `Pos` | Position |
| `MPG` | Minutes per game (used to deduplicate traded players) |
| `LEBRON` | Total LEBRON rating |
| `O-LEBRON` | Offensive LEBRON — used as offensive prior |
| `D-LEBRON` | Defensive LEBRON — used as defensive prior |
| `WAR` | Wins above replacement |
| `OffRole` | Offensive role label |
| `DefRole` | Defensive role label |

## Where to Get It

Download from BBall Index. The `_id` column must be the NBA.com player ID integer.

## How to Check Freshness

```bash
cd backend
python manage.py check_lebron_data --season-year 2026
```

Exit codes: `0` = OK, `1` = stale (warning), `2` = missing (error).

## Recommended Update Cadence

| Period | Cadence |
|--------|---------|
| Active season (Oct–Jun) | Weekly — data updates as games are played |
| Preseason / before season start | Once before running BPR for the new season |
| Offseason (Jul–Sep) | On demand — final season values are stable |

## What Happens If You Don't Update

- **Missing CSV**: `nba_compute_final_bpr` will abort with a `CommandError`. BPR cannot run.
- **Stale CSV (> 14 days during active season)**: Pipeline runs with a logged `WARNING` and
  a printed `⚠` banner. Results will be based on outdated LEBRON priors — role-player estimates
  and lambda adjustments may drift from current performance.

## Seasons Available

Files exist for 2016–2026. Historical files rarely need updating.

## Pipeline Integration

LEBRON data is used in two ways in `nba_compute_final_bpr`:

1. **Prior blend** — O-LEBRON and D-LEBRON blended 50/50 with box_bpr priors before RAPM solve
2. **Lambda adjustment** — LEBRON total used to scale regularization strength per player
   (low-LEBRON role players anchored harder; high-LEBRON stars left free)

Both are controlled by `--lebron-prior-weight` and `--lebron-lambda-scale` flags.
