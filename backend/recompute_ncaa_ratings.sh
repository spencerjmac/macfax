#!/bin/bash

# Navigate to the backend directory
cd "$(dirname "$0")"

# Activate the virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Define the range of seasons
START_YEAR=2005
END_YEAR=2026

echo "Starting recomputation of NCAA Adjusted Ratings from $START_YEAR to $END_YEAR..."
echo "Using Adaptive Freeze Iteration (default = 0)."

for year in $(seq $START_YEAR $END_YEAR); do
    echo "================================================="
    echo "Processing Season: $year"
    echo "================================================="
    
    # 1. Compute Full Season Ratings
    echo "--> Running full season ratings for $year..."
    python manage.py compute_adjusted_ratings --season $year
    
    # 2. Compute Pre-Tournament Ratings
    echo "--> Running pre-tournament ratings for $year..."
    python manage.py compute_adjusted_ratings --season $year --pre-tournament

    echo "Completed $year."
    echo ""
done

echo "================================================="
echo "Finished recomputing all NCAA Adjusted Ratings!"
echo "================================================="
