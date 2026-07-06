# Recruiting Data Ingestion Guide

**Goal:** import 247Sports/On3-style recruiting exports so freshman/transfer priors can be calibrated empirically (experiments N-D/N-E). Priority targets: the high-minute unprofiled freshmen in `backend/backtest_output/bpr_audit/recruiting_missing_profiles.csv` (~1,900 for 2026 alone; regenerate anytime with `check_recruiting_data`).

## CSV format

Header row required; column order flexible. Print a template anytime:
```bash
python manage.py import_recruiting --print-template
```

| Column | Required? | Notes |
|---|---|---|
| `class_year` | **yes** | Season year of the player's **first college season** (2025-26 freshman → `2026`). NOT the HS graduation label if it differs. Can be overridden per-file with `--class-year`. |
| `espn_id` | strongly preferred | ESPN athlete id — links directly to our `Player` rows, no guessing. The priority CSV already includes it for every listed player; copy it into your export. |
| `player_name` | yes (fallback matcher) | Used only when `espn_id` is blank. |
| `stars` | recommended | 1–5 integer; blank = unrated. |
| `national_rank` | recommended | Overall class rank; drives the rank bonus within a star tier. |
| `composite_score` | optional | 247 composite 0–1 (e.g. `0.9985`). |
| `position_rank` | optional | |
| `source` | optional | `247sports`, `on3`, `rivals`, `espn`, `manual` (default `manual`). |
| `notes` | optional | free text. |

Example rows:
```csv
espn_id,player_name,class_year,stars,national_rank,composite_score,position_rank,source,notes
5041935,Cameron Boozer,2026,5,2,0.9993,1,247sports,
,DeShawn Harris-Smith,2024,4,38,0.9871,9,on3,no espn id — name match
```

## How matching works

1. `espn_id` present → exact join on `Player.espn_athlete_id`. Always prefer this.
2. `espn_id` blank → case-insensitive name match with prefix tolerance; accepted **only when exactly one Player matches**. Ambiguous names (e.g. two "Cameron Jackson" rows exist in our DB) are logged and **skipped**, not guessed — pull the espn_id from the priority CSV for those.
3. Re-importing the same player+class_year updates in place (upsert) — safe to re-run after fixing rows.

Missing school/team names are fine — matching never uses team; the pipeline resolves the player's team from season stats.

## Workflow

```bash
# 1. preview — no writes, prints per-row outcomes incl. skipped/ambiguous
python manage.py import_recruiting --file recruits_2026.csv --dry-run

# 2. import
python manage.py import_recruiting --file recruits_2026.csv

# 3. validate coverage + match quality + refreshed priority list
python manage.py check_recruiting_data --seasons 2021 2022 2023 2024 2025 2026

# 4. measure the payoff (before/after freshman-prior calibration)
python manage.py backtest_bpr_suite --mode player --seasons 2024 2025 --run-name recruiting_after
```

One file per class year is simplest (`recruits_2021.csv` … `recruits_2026.csv`); use `--class-year N` to stamp a file that lacks the column. Import order doesn't matter.

## What good coverage unlocks

- The `RECRUITING_PRIOR_*` path in the BPR pipeline starts firing for real (currently 48 profiles exist, all 2026 5★).
- N-D: replace the guessed tier priors (5★=+2.5 OBPR etc.) with empirical year-one values by tier/rank bucket (top-5/10/25/50/100, 4★, 3★, unranked).
- N-E: transfer translation factors get a quality anchor for incoming-class strength.

Aim: ≥60% coverage of high-minute newcomers per class (audit threshold A9). 2021–2024 classes matter as much as 2026 — they're the training history the empirical priors are estimated from.

## Known issues to not worry about

- `PlayerSeasonProjection` misses players added to the DB after its build (the 48 five-stars show as `(2027, newcomer)`); the coverage checker no longer depends on it, and the BPR recruiting path reads profiles directly. Fix tracked separately for the projections pipeline.
