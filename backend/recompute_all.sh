#!/bin/bash

echo "Starting bulk recomputation of NCAA Adjusted Ratings (2005-2026)..."

# Loop through all historical seasons
for year in {2005..2026}; do
    echo "--------------------------------------------------------"
    echo "Recomputing FULL SEASON Adjusted Ratings for $year..."
    echo "--------------------------------------------------------"
    uv run python manage.py compute_adjusted_ratings --season $year
    
    echo "--------------------------------------------------------"
    echo "Recomputing PRE-TOURNAMENT Adjusted Ratings for $year..."
    echo "--------------------------------------------------------"
    uv run python manage.py compute_adjusted_ratings --season $year --pre-tournament
done

echo "========================================================"
echo "All seasons successfully recomputed with the new elevation logic!"
echo "========================================================"

echo "========================================================"
echo "NBA BPR chain (current season)"
echo "========================================================"
NBA_SEASON=${NBA_SEASON:-2026}
uv run python manage.py nba_compute_baseline_rapm --season $NBA_SEASON
uv run python manage.py nba_compute_box_bpr --season $NBA_SEASON
uv run python manage.py nba_compute_final_bpr --season $NBA_SEASON
# Projection Value (docs/bpr_audit/09) — team-forecast input, NOT BPR.
# Must run after final BPR; consumed by compute_nba_team_outlooks.
uv run python manage.py nba_compute_projection_values --season $NBA_SEASON
uv run python manage.py compute_nba_team_outlooks --source-season $NBA_SEASON
