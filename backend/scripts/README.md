# Backend Utility Scripts

This folder contains utility scripts for data management, pipeline execution, and system maintenance.

## Scripts

### Data Pipeline

**`complete_pipeline.py`**
- Runs the complete data pipeline (ingest → metrics → ratings)
- Used for full season backfill and updates
- Executes: ingest_gamelogs, compute_team_metrics, compute_adjusted_ratings

**`backfill_season.py`**
- Backfills game data in weekly chunks
- More reliable for large date ranges
- Provides progress updates

### Data Export

**`export_rankings_to_json.py`**
- Exports team rankings to JSON format
- Used for external integrations or backups

### System Setup

**`create_external_ids.py`**
- Creates NCAA external ID mappings for teams
- Run once during initial setup

**`preflight_check.py`**
- Validates system configuration before operations
- Checks database, dependencies, and data integrity

**`validate_pipeline.py`**
- Validates data pipeline execution
- Shows record counts and sample data
- Use after running pipeline to verify results

### Maintenance

**`update_logos_fixed.py`**
- Updates team logo URLs from external sources
- Run periodically to refresh logo assets

## Usage

All scripts should be run from the `backend/` directory:

```powershell
cd backend
python scripts/complete_pipeline.py
python scripts/validate_pipeline.py
```

## Django Management Commands

For data operations, prefer using Django management commands:

```powershell
# Ingest game data
python manage.py ingest_gamelogs --start-date 2026-02-21 --end-date 2026-02-26

# Compute team metrics
python manage.py compute_team_metrics --season 2025-26

# Compute adjusted ratings (USE THIS ONE, NOT compute_game_adjusted_ratings)
python manage.py compute_adjusted_ratings --season 2025-26

# Compute national averages
python manage.py compute_national_averages --season 2025-26

# Compute four factor index
python manage.py compute_four_factor_index --season 2025-26
```

## Important Notes

- **Always use `compute_adjusted_ratings`** (iterative method) - gives correct results
- **Never use `compute_game_adjusted_ratings`** (ridge regression) - has scaling issues
- Scripts use `update_or_create()` - safe to re-run, won't create duplicates
- For incremental updates, just ingest new date range and re-run metrics/ratings
