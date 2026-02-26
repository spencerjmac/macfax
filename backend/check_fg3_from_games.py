import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import TeamGameStats
from collections import defaultdict
import statistics

team_games = TeamGameStats.objects.filter(game__season_year=2026)

# Aggregate by team
team_totals = defaultdict(lambda: {'fg3a': 0, 'fga': 0})

for game in team_games:
    team_totals[game.team_id]['fg3a'] += game.fg3a
    team_totals[game.team_id]['fga'] += game.fga

# Calculate FG3 rates
fg3_rates = []
for team_id, totals in team_totals.items():
    if totals['fga'] > 0:
        fg3_rate = (totals['fg3a'] / totals['fga']) * 100
        fg3_rates.append(fg3_rate)

print(f"Total teams with game data: {len(fg3_rates)}")
print(f"\nFG3 Rate Statistics:")
print(f"  Min:    {min(fg3_rates):.1f}%")
print(f"  Max:    {max(fg3_rates):.1f}%")
print(f"  Mean:   {statistics.mean(fg3_rates):.1f}%")
print(f"  Median: {statistics.median(fg3_rates):.1f}%")
print(f"  StdDev: {statistics.stdev(fg3_rates):.1f}%")
print(f"\nPercentiles:")
sorted_rates = sorted(fg3_rates)
print(f"  5th:    {sorted_rates[int(len(sorted_rates) * 0.05)]:.1f}%")
print(f"  10th:   {sorted_rates[int(len(sorted_rates) * 0.10)]:.1f}%")
print(f"  25th:   {sorted_rates[int(len(sorted_rates) * 0.25)]:.1f}%")
print(f"  75th:   {sorted_rates[int(len(sorted_rates) * 0.75)]:.1f}%")
print(f"  90th:   {sorted_rates[int(len(sorted_rates) * 0.90)]:.1f}%")
print(f"  95th:   {sorted_rates[int(len(sorted_rates) * 0.95)]:.1f}%")

print(f"\nRange: {min(fg3_rates):.1f}% to {max(fg3_rates):.1f}% (spread of {max(fg3_rates) - min(fg3_rates):.1f}%)")
