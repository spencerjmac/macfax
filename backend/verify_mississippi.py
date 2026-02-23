import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, TeamSeasonRatings, TeamSeasonMetrics

# Check counts
print(f"TeamSeasonMetrics for 2026: {TeamSeasonMetrics.objects.filter(season=2026).count()}")
print(f"TeamSeasonRatings for 2026: {TeamSeasonRatings.objects.filter(season=2026).count()}")
print()

# Get teams
miss = Team.objects.get(name='Mississippi')
miss_val = Team.objects.get(name='Mississippi Valley St.')

print("=" * 60)
print("MISSISSIPPI (Ole Miss) - SEC")
print("=" * 60)
miss_metrics = TeamSeasonMetrics.objects.filter(team=miss, season=2026).first()
if miss_metrics:
    print(f"Games: {miss_metrics.games}")
    print(f"PPG: {miss_metrics.ppg:.1f}")
    print(f"PAPG: {miss_metrics.papg:.1f}")
    print(f"eFG%: {miss_metrics.efg_pct:.1f}%")
    print(f"TOV%: {miss_metrics.tov_pct:.1f}%")
else:
    print("NO METRICS FOUND")

miss_ratings = TeamSeasonRatings.objects.filter(team=miss, season=2026).first()
if miss_ratings:
    print(f"AdjEM: {miss_ratings.adj_em:.2f}")
    print(f"Adj Offense: {miss_ratings.adj_o:.2f}")
    print(f"Adj Defense: {miss_ratings.adj_d:.2f}")
else:
    print("NO RATINGS FOUND")

print()
print("=" * 60)
print("MISSISSIPPI VALLEY ST. - SWAC")
print("=" * 60)
miss_val_metrics = TeamSeasonMetrics.objects.filter(team=miss_val, season=2026).first()
if miss_val_metrics:
    print(f"Games: {miss_val_metrics.games}")
    print(f"PPG: {miss_val_metrics.ppg:.1f}")
    print(f"PAPG: {miss_val_metrics.papg:.1f}")
    print(f"eFG%: {miss_val_metrics.efg_pct:.1f}%")
    print(f"TOV%: {miss_val_metrics.tov_pct:.1f}%")
else:
    print("NO METRICS FOUND")

miss_val_ratings = TeamSeasonRatings.objects.filter(team=miss_val, season=2026).first()
if miss_val_ratings:
    print(f"AdjEM: {miss_val_ratings.adj_em:.2f}")
    print(f"Adj Offense: {miss_val_ratings.adj_o:.2f}")
    print(f"Adj Defense: {miss_val_ratings.adj_d:.2f}")
else:
    print("NO RATINGS FOUND")
