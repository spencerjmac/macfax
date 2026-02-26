import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import TeamSeasonRatings, Season
import statistics

season = Season.objects.get(year=2026)
all_ratings = TeamSeasonRatings.objects.filter(season=season)

tempos = [r.adj_tempo for r in all_ratings if r.adj_tempo]

print(f"Total D1 teams with tempo data: {len(tempos)}")
print(f"\nTempo Statistics:")
print(f"  Min:    {min(tempos):.1f}")
print(f"  Max:    {max(tempos):.1f}")
print(f"  Mean:   {statistics.mean(tempos):.1f}")
print(f"  Median: {statistics.median(tempos):.1f}")
print(f"  StdDev: {statistics.stdev(tempos):.1f}")
print(f"\nPercentiles:")
sorted_tempos = sorted(tempos)
print(f"  5th:    {sorted_tempos[int(len(sorted_tempos) * 0.05)]:.1f}")
print(f"  10th:   {sorted_tempos[int(len(sorted_tempos) * 0.10)]:.1f}")
print(f"  25th:   {sorted_tempos[int(len(sorted_tempos) * 0.25)]:.1f}")
print(f"  75th:   {sorted_tempos[int(len(sorted_tempos) * 0.75)]:.1f}")
print(f"  90th:   {sorted_tempos[int(len(sorted_tempos) * 0.90)]:.1f}")
print(f"  95th:   {sorted_tempos[int(len(sorted_tempos) * 0.95)]:.1f}")

print(f"\nRange: {min(tempos):.1f} to {max(tempos):.1f} (spread of {max(tempos) - min(tempos):.1f})")
