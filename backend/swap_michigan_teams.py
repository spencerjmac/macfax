"""
Script to swap Michigan and Michigan State data
The teams got mixed up during NCAA API ingestion
"""

from django.db import transaction
from core.models import Team, TeamGameStats, Game

# Get both teams
michigan = Team.objects.get(slug='michigan')
michigan_state = Team.objects.get(slug='michigan-state')

print(f"Michigan ID: {michigan.id}")
print(f"Michigan State ID: {michigan_state.id}")
print()

# Count games for each team
mich_games = TeamGameStats.objects.filter(team=michigan).count()
msu_games = TeamGameStats.objects.filter(team=michigan_state).count()

print(f"Michigan currently has {mich_games} games")
print(f"Michigan State currently has {msu_games} games")
print()

print("Starting swap...")

with transaction.atomic():
    # Get all TeamGameStats for both teams
    michigan_stats = list(TeamGameStats.objects.filter(team=michigan))
    michigan_state_stats = list(TeamGameStats.objects.filter(team=michigan_state))
    
    # Also need to swap opponent references
    michigan_opp_stats = list(TeamGameStats.objects.filter(opponent=michigan))
    michigan_state_opp_stats = list(TeamGameStats.objects.filter(opponent=michigan_state))
    
    print(f"Found {len(michigan_stats)} games for Michigan (as team)")
    print(f"Found {len(michigan_state_stats)} games for Michigan State (as team)")
    print(f"Found {len(michigan_opp_stats)} games vs Michigan (as opponent)")
    print(f"Found {len(michigan_state_opp_stats)} games vs Michigan State (as opponent)")
    print()
    
    # Also need to swap Game records where they're home/away team
    michigan_home_games = list(Game.objects.filter(home_team=michigan))
    michigan_away_games = list(Game.objects.filter(away_team=michigan))
    michigan_state_home_games = list(Game.objects.filter(home_team=michigan_state))
    michigan_state_away_games = list(Game.objects.filter(away_team=michigan_state))
    
    print(f"Michigan: {len(michigan_home_games)} home games, {len(michigan_away_games)} away games")
    print(f"Michigan State: {len(michigan_state_home_games)} home games, {len(michigan_state_away_games)} away games")
    print()
    
    # Swap TeamGameStats team field
    for stat in michigan_stats:
        stat.team = michigan_state
        stat.save()
    
    for stat in michigan_state_stats:
        stat.team = michigan
        stat.save()
    
    # Swap TeamGameStats opponent field
    for stat in michigan_opp_stats:
        stat.opponent = michigan_state
        stat.save()
    
    for stat in michigan_state_opp_stats:
        stat.opponent = michigan
        stat.save()
    
    # Swap Game home_team field
    for game in michigan_home_games:
        game.home_team = michigan_state
        game.save()
    
    for game in michigan_state_home_games:
        game.home_team = michigan
        game.save()
    
    # Swap Game away_team field
    for game in michigan_away_games:
        game.away_team = michigan_state
        game.save()
    
    for game in michigan_state_away_games:
        game.away_team = michigan
        game.save()
    
    print("✓ Swapped all TeamGameStats records")
    print("✓ Swapped all Game records")
    print()
    print("SUCCESS: Michigan and Michigan State data has been swapped!")
    print()
    print("Next steps:")
    print("1. Run: python manage.py compute_season_metrics --season 2026")
    print("2. Run: python manage.py compute_national_averages --season 2026")
    print("3. Run: python manage.py compute_adjusted_ratings --season 2026 --iterations 3")
    print("4. Run: python manage.py compute_adjusted_four_factors --season 2026 --iterations 3")
    print("5. Run: python manage.py compute_four_factor_index --season 2026")
