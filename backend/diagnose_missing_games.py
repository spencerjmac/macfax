import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, Game, TeamGameStats
from django.db.models import Q

print("\n" + "="*80)
print("CHECKING FOR MISSING GAMES")
print("="*80)

# New Mexico should be 20-6 (showing 19-6)
# Saint Louis should be 25-2 (showing 24-2)

teams_to_check = [
    ('New Mexico', 20, 6),
    ('Saint Louis', 25, 2)
]

for team_name, expected_wins, expected_losses in teams_to_check:
    team = Team.objects.get(name=team_name)
    
    # Get all game stats for this team
    all_games = TeamGameStats.objects.filter(
        team=team,
        game__season_year=2026,
        game__status='final'
    ).select_related('game', 'opponent').order_by('game__game_date')
    
    wins = 0
    losses = 0
    
    for game_stat in all_games:
        # Get opponent's stats
        opp_stats = TeamGameStats.objects.filter(
            game=game_stat.game,
            team=game_stat.opponent
        ).first()
        
        if opp_stats:
            if game_stat.pts > opp_stats.pts:
                wins += 1
            else:
                losses += 1
    
    total_games = all_games.count()
    expected_games = expected_wins + expected_losses
    
    print(f"\n{team_name}:")
    print(f"  Current: {wins}-{losses} ({total_games} games)")
    print(f"  Expected: {expected_wins}-{expected_losses} ({expected_games} games)")
    print(f"  Missing: {expected_games - total_games} game(s)")
    
    if total_games < expected_games:
        print(f"\n  This team is missing {expected_games - total_games} game(s) from the database")
        print(f"  The NCAA API may not have returned all games, or the game was skipped")

print("\n" + "="*80)
print("\nNOTE: If games are missing, you may need to:")
print("1. Check the NCAA.com schedule page for these teams")
print("2. Manually verify which games are in the database")
print("3. Re-import specific date ranges if needed")
print("="*80 + "\n")
