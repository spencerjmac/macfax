import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, TeamSeasonMetrics, Game, TeamGameStats

# Check total teams
total_teams = Team.objects.count()
teams_with_metrics = TeamSeasonMetrics.objects.filter(season__year=2026).count()

print(f"Total D1 Teams: {total_teams}")
print(f"Teams with 2026 metrics: {teams_with_metrics}")
print(f"Missing: {total_teams - teams_with_metrics}")
print()

# Find teams without metrics
teams_without_metrics = Team.objects.exclude(
    season_metrics__season__year=2026
)

print("Teams WITHOUT 2026 metrics:")
print("=" * 60)
for team in teams_without_metrics:
    games = Game.objects.filter(season_year=2026).filter(
        home_team=team
    ).count() + Game.objects.filter(season_year=2026).filter(
        away_team=team
    ).count()
    print(f"  {team.name:30} - {games} games")

print()

# Check Michigan and Michigan State specifically
print("MICHIGAN vs MICHIGAN STATE:")
print("=" * 60)
for name in ['Michigan', 'Michigan State']:
    try:
        team = Team.objects.get(name=name)
        games = Game.objects.filter(season_year=2026).filter(
            home_team=team
        ).count() + Game.objects.filter(season_year=2026).filter(
            away_team=team
        ).count()
        
        game_stats = TeamGameStats.objects.filter(
            team=team,
            game__season_year=2026
        ).count()
        
        print(f"{name}:")
        print(f"  Games (as home/away): {games}")
        print(f"  Game stats records: {game_stats}")
        
        # Check external IDs
        external_ids = team.external_ids.all()
        print(f"  External IDs: {external_ids.count()}")
        for ext_id in external_ids[:5]:
            print(f"    - {ext_id.source}: {ext_id.external_name}")
        print()
    except Team.DoesNotExist:
        print(f"{name}: NOT FOUND IN DATABASE")
        print()
