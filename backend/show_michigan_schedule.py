"""
Show Michigan's complete schedule from game log scraper
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, Game, TeamGameStats

# Get Michigan
michigan = Team.objects.get(name='Michigan')

# Get all games (both home and away)
home_games = Game.objects.filter(home_team=michigan, season_year=2026).order_by('game_date')
away_games = Game.objects.filter(away_team=michigan, season_year=2026).order_by('game_date')

all_games = sorted(
    list(home_games) + list(away_games),
    key=lambda g: g.game_date
)

print("=" * 100)
print(f"MICHIGAN WOLVERINES - 2026 SEASON SCHEDULE ({len(all_games)} games)")
print("=" * 100)

for i, game in enumerate(all_games, 1):
    is_home = game.home_team == michigan
    opponent = game.away_team if is_home else game.home_team
    location = "vs" if is_home else "@"
    
    # Get Michigan's stats for this game
    mich_stats = TeamGameStats.objects.filter(
        game=game,
        team=michigan
    ).first()
    
    # Get opponent's stats
    opp_stats = TeamGameStats.objects.filter(
        game=game,
        team=opponent
    ).first()
    
    print(f"\n{'='*100}")
    print(f"Game #{i}: {game.game_date} - {location} {opponent.name}")
    print(f"{'='*100}")
    
    if mich_stats and opp_stats:
        mich_pts = mich_stats.pts
        opp_pts = opp_stats.pts
        result = "W" if mich_pts > opp_pts else "L"
        margin = mich_pts - opp_pts
        
        print(f"Result: {result} {mich_pts}-{opp_pts} ({margin:+d})")
        print(f"\nMichigan Stats:")
        print(f"  FG: {mich_stats.fgm}/{mich_stats.fga} ({mich_stats.fgm/mich_stats.fga*100 if mich_stats.fga > 0 else 0:.1f}%)")
        print(f"  3PT: {mich_stats.fg3m}/{mich_stats.fg3a} ({mich_stats.fg3m/mich_stats.fg3a*100 if mich_stats.fg3a > 0 else 0:.1f}%)")
        print(f"  FT: {mich_stats.ftm}/{mich_stats.fta} ({mich_stats.ftm/mich_stats.fta*100 if mich_stats.fta > 0 else 0:.1f}%)")
        print(f"  Rebounds: {mich_stats.reb} (Off: {mich_stats.oreb}, Def: {mich_stats.dreb})")
        print(f"  Assists: {mich_stats.ast}")
        print(f"  Turnovers: {mich_stats.tov}")
        print(f"  Steals: {mich_stats.stl}")
        print(f"  Blocks: {mich_stats.blk}")
        print(f"  Fouls: {mich_stats.pf}")
        
        print(f"\n{opponent.name} Stats:")
        print(f"  FG: {opp_stats.fgm}/{opp_stats.fga} ({opp_stats.fgm/opp_stats.fga*100 if opp_stats.fga > 0 else 0:.1f}%)")
        print(f"  3PT: {opp_stats.fg3m}/{opp_stats.fg3a} ({opp_stats.fg3m/opp_stats.fg3a*100 if opp_stats.fg3a > 0 else 0:.1f}%)")
        print(f"  FT: {opp_stats.ftm}/{opp_stats.fta} ({opp_stats.ftm/opp_stats.fta*100 if opp_stats.fta > 0 else 0:.1f}%)")
        print(f"  Rebounds: {opp_stats.reb} (Off: {opp_stats.oreb}, Def: {opp_stats.dreb})")
        print(f"  Assists: {opp_stats.ast}")
        print(f"  Turnovers: {opp_stats.tov}")
        print(f"  Steals: {opp_stats.stl}")
        print(f"  Blocks: {opp_stats.blk}")
        print(f"  Fouls: {opp_stats.pf}")
        
        # Raw game data
        print(f"\nRaw Game Data:")
        print(f"  Game Source ID: {game.source_game_id}")
        print(f"  Home Team: {game.home_team.name}")
        print(f"  Away Team: {game.away_team.name}")
        print(f"  Neutral Site: {game.neutral_site}")
        print(f"  Conference Game: {game.conference_game if hasattr(game, 'conference_game') else 'N/A'}")
    else:
        print("ERROR: Stats not found for this game!")

print("\n" + "=" * 100)
print("SCHEDULE COMPLETE")
print("=" * 100)
