"""
Compare our game counts with what's expected for specific teams
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import models
from core.models import Team, Game, TeamGameStats

teams_check = {
    'Florida': '20-6',
    'Houston': '23-3',
    'Utah St.': '23-3',
    'Saint Louis': '25-2'
}

for team_name, expected_record in teams_check.items():
    print("=" * 100)
    print(f"{team_name} - Expected: {expected_record}")
    print("=" * 100)
    
    try:
        team = Team.objects.get(name=team_name)
    except Team.DoesNotExist:
        print(f"Team not found!\n")
        continue
    
    # Get all games
    all_games = list(Game.objects.filter(
        models.Q(home_team=team) | models.Q(away_team=team),
        season_year=2026
    ).exclude(
        models.Q(home_score__isnull=True) | models.Q(away_score__isnull=True)
    ).order_by('game_date'))
    
    print(f"Total games with scores: {len(all_games)}\n")
    
    wins = 0
    losses = 0
    
    print("ALL GAMES:")
    for i, game in enumerate(all_games, 1):
        if game.home_team == team:
            opp = game.away_team.name
            loc = "vs"
            team_score = game.home_score
            opp_score = game.away_score
        else:
            opp = game.home_team.name
            loc = "@"
            team_score = game.away_score
            opp_score = game.home_score
        
        result = "W" if team_score > opp_score else "L"
        if result == "W":
            wins += 1
        else:
            losses += 1
        
        print(f"  {i:2}. {game.game_date} {loc} {opp:<30} {team_score}-{opp_score} {result}")
    
    print(f"\nActual record in DB: {wins}-{losses}")
    print(f"Expected record: {expected_record}")
    
    exp_wins, exp_losses = expected_record.split('-')
    if str(wins) != exp_wins or str(losses) != exp_losses:
        print(f"❌ MISMATCH!")
        exp_total = int(exp_wins) + int(exp_losses)
        actual_total = wins + losses
        if exp_total > actual_total:
            print(f"   Missing {exp_total - actual_total} game(s)")
        elif exp_total < actual_total:
            print(f"   Have {actual_total - exp_total} extra game(s)")
    else:
        print("✓ Match!")
    
    print()
