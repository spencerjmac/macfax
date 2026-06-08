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
