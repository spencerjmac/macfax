import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, Game, TeamGameStats

# Get teams
michigan = Team.objects.get(name='Michigan')
michigan_state = Team.objects.get(name='Michigan State')
boston_college = Team.objects.get(name='Boston College')
boston_u = Team.objects.get(name='Boston University')

print("GAME COUNTS:")
print("=" * 60)

for team in [michigan, michigan_state, boston_college, boston_u]:
    games_home = Game.objects.filter(season_year=2026, home_team=team).count()
    games_away = Game.objects.filter(season_year=2026, away_team=team).count()
    game_stats = TeamGameStats.objects.filter(team=team, game__season_year=2026).count()
    
    print(f"\n{team.name}:")
    print(f"  Home games: {games_home}")
    print(f"  Away games: {games_away}")
    print(f"  Total: {games_home + games_away}")
    print(f"  Game stats: {game_stats}")

# Show some Michigan State games to see if they look like Michigan games
print("\n\nSample Michigan State games (first 15):")
print("=" * 60)
msu_games = TeamGameStats.objects.filter(
    team=michigan_state,
    game__season_year=2026
).select_related('game', 'opponent').order_by('game__game_date')[:15]

for tgs in msu_games:
    game = tgs.game
    if game.home_team == michigan_state:
        vs_text = f"vs {tgs.opponent.name}"
        score_text = f"{game.home_score}-{game.away_score}"
    else:
        vs_text = f"@ {tgs.opponent.name}"
        score_text = f"{game.away_score}-{game.home_score}"
    print(f"  {game.game_date.strftime('%Y-%m-%d')} {vs_text:35} {score_text}")

# Show some Boston U games to see if they look like Boston College games  
print("\n\nSample Boston University games (first 15):")
print("=" * 60)
bu_games = TeamGameStats.objects.filter(
    team=boston_u,
    game__season_year=2026
).select_related('game', 'opponent').order_by('game__game_date')[:15]

for tgs in bu_games:
    game = tgs.game
    if game.home_team == boston_u:
        vs_text = f"vs {tgs.opponent.name}"
        score_text = f"{game.home_score}-{game.away_score}"
    else:
        vs_text = f"@ {tgs.opponent.name}"
        score_text = f"{game.away_score}-{game.home_score}"
    print(f"  {game.game_date.strftime('%Y-%m-%d')} {vs_text:35} {score_text}")
