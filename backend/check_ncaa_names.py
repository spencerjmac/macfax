import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Game, TeamGameStats

# Find all unique team names from NCAA data for Michigan-related teams
print("Checking NCAA game logs for Michigan-related teams...")
print("=" * 60)

# Check home teams
home_michigan = Game.objects.filter(
    season_year=2026,
    home_team_name__icontains='michigan'
).values_list('home_team_name', flat=True).distinct()

# Check away teams  
away_michigan = Game.objects.filter(
    season_year=2026,
    away_team_name__icontains='michigan'
).values_list('away_team_name', flat=True).distinct()

all_michigan = set(list(home_michigan) + list(away_michigan))

print("Michigan-related team names in NCAA data:")
for name in sorted(all_michigan):
    home_count = Game.objects.filter(season_year=2026, home_team_name=name).count()
    away_count = Game.objects.filter(season_year=2026, away_team_name=name).count()
    total = home_count + away_count
    print(f"  '{name}': {total} games ({home_count} home, {away_count} away)")

print()

# Same for Boston
print("Checking NCAA game logs for Boston-related teams...")
print("=" * 60)

home_boston = Game.objects.filter(
    season_year=2026,
    home_team_name__icontains='boston'
).values_list('home_team_name', flat=True).distinct()

away_boston = Game.objects.filter(
    season_year=2026,
    away_team_name__icontains='boston'
).values_list('away_team_name', flat=True).distinct()

all_boston = set(list(home_boston) + list(away_boston))

print("Boston-related team names in NCAA data:")
for name in sorted(all_boston):
    home_count = Game.objects.filter(season_year=2026, home_team_name=name).count()
    away_count = Game.objects.filter(season_year=2026, away_team_name=name).count()
    total = home_count + away_count
    print(f"  '{name}': {total} games ({home_count} home, {away_count} away)")
