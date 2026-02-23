import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, Game
from django.db.models import Q

def show_schedule(team_name):
    """Show complete schedule for a team"""
    try:
        team = Team.objects.get(name=team_name)
    except Team.DoesNotExist:
        print(f"Team '{team_name}' not found")
        return
    
    games = Game.objects.filter(
        Q(home_team=team) | Q(away_team=team),
        game_date__gte='2025-11-01',
        game_date__lte='2026-02-21'
    ).order_by('game_date')
    
    wins = 0
    losses = 0
    
    print(f"\n{'='*70}")
    print(f"{team_name} Schedule ({games.count()} games)")
    print(f"{'='*70}\n")
    
    for game in games:
        has_score = game.home_score is not None and game.away_score is not None
        
        if game.home_team == team:
            opponent = game.away_team.name
            location = "vs"
            if has_score:
                result = "W" if game.home_score > game.away_score else "L"
                score = f"{game.home_score}-{game.away_score}"
                if result == "W":
                    wins += 1
                else:
                    losses += 1
            else:
                result = "?"
                score = "No score"
        else:
            opponent = game.home_team.name
            location = "@"
            if has_score:
                result = "W" if game.away_score > game.home_score else "L"
                score = f"{game.away_score}-{game.home_score}"
                if result == "W":
                    wins += 1
                else:
                    losses += 1
            else:
                result = "?"
                score = "No score"
        
        print(f"{game.game_date} {result:1s} {location:2s} {opponent:25s} {score:12s} (Game ID: {game.id})")
    
    print(f"\n{'='*70}")
    print(f"Record in DB: {wins}-{losses}")
    print(f"{'='*70}\n")

# Check the teams mentioned
teams_to_check = ['Saint Louis', 'St. John\'s', 'New Mexico']

for team_name in teams_to_check:
    show_schedule(team_name)
