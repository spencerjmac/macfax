# Data Pipeline Reference

All data comes from the **NCAA Stats API**. There are no CSV files or external static data sources. The Django management commands below form the complete pipeline.

---

## `update_ncaa_all` — Full Pipeline (use this)

Runs the complete pipeline in sequence. Idempotent — safe to re-run.

```bash
python manage.py update_ncaa_all --season 2026
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--season` | required | Season end-year (e.g. `2026` for 2025-26) |
| `--skip-ingest` | false | Skip game ingestion, only recompute metrics |
| `--iterations` | 25 | Iterations for adjusted ratings convergence |
| `--sor-trials` | 10000 | Monte Carlo trials for Strength of Record |
| `--ingest-workers` | 1 | Parallel workers for game ingestion |

**Pipeline steps:**
```
[0]  ensure_ncaa_teams          — create missing D1 team rows
[1]  ingest_gamelogs            — fetch games + box scores from NCAA API
[2]  compute_team_metrics       — aggregate raw four-factor stats
[3]  compute_national_averages  — league-wide averages
[4]  compute_adjusted_ratings   — iterative AdjO/AdjD/AdjEM
[5]  compute_adjusted_four_factors
[6]  compute_four_factor_index  — 0-100 composite score
[7]  fetch_net_rankings         — NCAA NET rankings
[8]  compute_sor                — Strength of Record (Monte Carlo)
[9]  compute_game_value         — game importance scores
[10] compute_sos                — Strength of Schedule
```

---

## Individual Commands

### Setup (run once)

**`seed_conferences`** — Populate conference table from built-in list.
```bash
python manage.py seed_conferences
```

**`ensure_ncaa_teams`** — Create Team rows for every canonical name in `ncaa_team_name_mappings.yml`. Idempotent.
```bash
python manage.py ensure_ncaa_teams
python manage.py ensure_ncaa_teams --dry-run
```

**`import_logos`** — Scan `backend/static/logos/` and set `Team.logo_url` in the DB. Run after `collectstatic`.
```bash
python manage.py import_logos
python manage.py import_logos --dry-run
python manage.py import_logos --clear-missing   # null out URLs for teams with no logo file
```

**`sync_team_d1_status`** — Set `Team.is_d1` based on the YAML mappings. Useful if non-D1 teams were accidentally created with `is_d1=True`.
```bash
python manage.py sync_team_d1_status
python manage.py sync_team_d1_status --dry-run
```

---

### Data Ingestion

**`ingest_gamelogs`** — Fetch game results and box scores from the NCAA API.
```bash
# Full season (default: Nov 1 to yesterday)
python manage.py ingest_gamelogs --season 2026

# Specific date range
python manage.py ingest_gamelogs --season 2026 --start 2026-01-01 --end 2026-01-31

# Force re-fetch existing games
python manage.py ingest_gamelogs --season 2026 --refresh

# Parallel workers (faster, no Redis needed)
python manage.py ingest_gamelogs --season 2026 --workers 4
```

**`backfill_missing_game_stats`** — Re-fetch box scores only for games that have no `TeamGameStats` (e.g. after 428/502 errors from NCAA API).
```bash
python manage.py backfill_missing_game_stats --season 2026
python manage.py backfill_missing_game_stats --season 2026 --limit 50
python manage.py backfill_missing_game_stats --season 2026 --dry-run
```

---

### Metrics Computation

All metric commands take `--season <year>`.

**`compute_team_metrics`** — Aggregate raw four-factor stats from `TeamGameStats`. Produces `TeamSeasonMetrics`.
```bash
python manage.py compute_team_metrics --season 2026
```

**`compute_national_averages`** — Compute league-wide averages. Required before adjusted ratings.
```bash
python manage.py compute_national_averages --season 2026
```

**`compute_adjusted_ratings`** — Iterative opponent-adjustment to produce AdjO, AdjD, AdjEM, AdjTempo.
```bash
python manage.py compute_adjusted_ratings --season 2026
python manage.py compute_adjusted_ratings --season 2026 --iterations 25
```

> Use this command. Do **not** use `compute_game_adjusted_ratings` — it has a known bug producing inflated values (~2×).

**`compute_adjusted_four_factors`** — Opponent-adjusted four factors using the same iterative method.
```bash
python manage.py compute_adjusted_four_factors --season 2026
```

**`compute_four_factor_index`** — Compute the 0-100 Four Factor Index composite score.
```bash
python manage.py compute_four_factor_index --season 2026
```

**`fetch_net_rankings`** — Fetch NCAA NET rankings from NCAA.com.
```bash
python manage.py fetch_net_rankings --season 2026
```

**`compute_sor`** — Strength of Record via Monte Carlo simulation.
```bash
python manage.py compute_sor --season 2026
python manage.py compute_sor --season 2026 --trials 10000
```

**`compute_game_value`** — Score each game by its importance (quad system).
```bash
python manage.py compute_game_value --season 2026
```

**`compute_sos`** — Strength of Schedule.
```bash
python manage.py compute_sos --season 2026
```

---

### Matchup Engine Support

These commands calibrate the matchup win-probability engine. Run after a full season of data is ingested.

**`compute_hca`** — Estimate Home Court Advantage from game margins.
```bash
python manage.py compute_hca --season 2026
```

**`compute_sigma`** — Compute prediction error standard deviation for win probability calibration.
```bash
python manage.py compute_sigma --season 2026
```

**`train_four_factor_regression`** — Train regression coefficients used by the matchup engine.
```bash
python manage.py train_four_factor_regression --season 2026
```

**`compute_wab`** — Wins Above Bubble.
```bash
python manage.py compute_wab --season 2026
```

---

### Utility

**`clear_cache`** — Clear Django view cache. Run after data updates if caching is enabled.
```bash
python manage.py clear_cache
```

---

## Team Name Mapping

The NCAA API uses short team names (e.g. `"Michigan St."`, `"NIU"`) that must be mapped to canonical DB names.

**`backend/mappings/ncaa_team_name_mappings.yml`** — Comprehensive mapping of all 365 D1 teams:
```yaml
ncaa:
  "Michigan St.": "Michigan St."   # NCAA name → canonical DB name
  "NIU": "Northern Illinois"
  ...
```

When a game is ingested, the mapper looks up the NCAA team name in this file to find the canonical name, then queries `Team.objects.filter(name=canonical_name)`.

If the canonical name is not in the Team table, run `ensure_ncaa_teams` which creates a row for every canonical name in the YAML.

**`backend/mappings/team_alias_overrides.yml`** — Fallback overrides for non-NCAA sources. Only used when the primary YAML lookup fails.

---

## First-Time Setup Order

```
1. python manage.py migrate
2. python manage.py seed_conferences
3. python manage.py ensure_ncaa_teams
4. python manage.py createsuperuser
5. python manage.py update_ncaa_all --season 2026
6. python manage.py import_logos
7. python manage.py collectstatic --noinput
```
