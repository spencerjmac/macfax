import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import TeamSeasonStats, Season
import statistics

season = Season.objects.get(year=2026)
all_stats = TeamSeasonStats.objects.filter(season=season)

fg3_rates = [s.fg3_rate for s in all_stats if s.fg3_rate is not None]

print(f"Total D1 teams with FG3 rate data: {len(fg3_rates)}")
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
