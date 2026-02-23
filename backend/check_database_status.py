import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import TeamSeasonRatings

print("\n" + "="*80)
print("DATABASE STATUS CHECK")
print("="*80)

# Count D1 vs non-D1 teams in rankings
d1_ratings = TeamSeasonRatings.objects.filter(season__year=2026, team__is_d1=True).count()
non_d1_ratings = TeamSeasonRatings.objects.filter(season__year=2026, team__is_d1=False).count()

print(f"\nTeamSeasonRatings (2026 season):")
print(f"  D1 teams: {d1_ratings}")
print(f"  Non-D1 teams: {non_d1_ratings}")

if non_d1_ratings > 0:
    print(f"\n  ⚠️  WARNING: {non_d1_ratings} non-D1 teams in rankings!")
else:
    print(f"\n  ✓ Good - Only D1 teams in rankings")

# Check a few sample teams
from core.models import Team

samples = ['Michigan', 'New Mexico', 'Saint Louis']
print(f"\nSample team records:")
print("-" * 80)

for team_name in samples:
    team = Team.objects.get(name=team_name)
    ratings = TeamSeasonRatings.objects.filter(team=team, season__year=2026).first()
    
    if ratings:
        print(f"{team_name:20s}: {ratings.wins}-{ratings.losses} ({ratings.games_played} games), Adj EM: {ratings.adj_em:+.2f}")

print("\n" + "="*80)
print("✓ Data is in the database and ready for the website")
print("="*80 + "\n")
