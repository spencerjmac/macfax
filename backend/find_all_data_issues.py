import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Game, Team
from django.db.models import Q, Count
from datetime import datetime

# Find all teams with games that have no scores (excluding today's games)
print("="*70)
print("Checking for games without scores (excluding Feb 21)")
print("="*70)

missing_scores = Game.objects.filter(
    game_date__gte='2025-11-01',
    game_date__lt='2026-02-21',  # Exclude today
    home_score__isnull=True
).order_by('game_date')

print(f"\nFound {missing_scores.count()} games without scores before Feb 21:\n")

for game in missing_scores[:20]:  # Show first 20
    print(f"{game.game_date}: {game.home_team.name} vs {game.away_team.name} (ID: {game.id})")

# Also check: are there any duplicate game scenarios like Houston?
print("\n" + "="*70)
print("Checking for duplicate games (multiple games on same date)")
print("="*70)

teams_to_check = ['New Mexico', 'Saint Louis', 'Florida', 'Utah St.']

for team_name in teams_to_check:
    team = Team.objects.get(name=team_name)
    games = Game.objects.filter(
        Q(home_team=team) | Q(away_team=team),
        game_date__gte='2025-11-01',
        game_date__lte='2026-02-21'
    ).exclude(home_score__isnull=True).values('game_date').annotate(
        count=Count('id')
    ).filter(count__gt=1).order_by('game_date')
    
    if games.exists():
        print(f"\n{team_name} has duplicate games:")
        for dup in games:
            date = dup['game_date']
            game_list = Game.objects.filter(
                Q(home_team=team) | Q(away_team=team),
                game_date=date
            ).exclude(home_score__isnull=True)
            for g in game_list:
                if g.home_team == team:
                    print(f"  {date}: vs {g.away_team.name} ({g.home_score}-{g.away_score}) [ID: {g.id}]")
                else:
                    print(f"  {date}: @ {g.home_team.name} ({g.away_score}-{g.home_score}) [ID: {g.id}]")
