"""
Show Michigan's complete schedule with results and compute all metrics
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, Game, TeamGameStats, TeamSeasonMetrics
from datetime import date

# Get Michigan team
michigan = Team.objects.get(name='Michigan')

# Get all games
home_games = Game.objects.filter(home_team=michigan, season_year=2026).order_by('game_date')
away_games = Game.objects.filter(away_team=michigan, season_year=2026).order_by('game_date')

all_games = sorted(
    list(home_games) + list(away_games),
    key=lambda g: (g.game_date, g.id)
)

print("=" * 120)
print("MICHIGAN 2025-26 COMPLETE SCHEDULE")
print("=" * 120)
print()

wins = 0
losses = 0

for i, game in enumerate(all_games, 1):
    # Skip future games (no stats yet)
    mich_stats = TeamGameStats.objects.filter(game=game, team=michigan).first()
    
    if game.home_team == michigan:
        opp = game.away_team
        location = "vs"
        opp_stats = TeamGameStats.objects.filter(game=game, team=opp).first()
    else:
        opp = game.home_team
        location = "@"
        opp_stats = TeamGameStats.objects.filter(game=game, team=opp).first()
    
    # Check if game has been played
    if mich_stats and opp_stats:
        mich_score = mich_stats.pts
        opp_score = opp_stats.pts
        
        if mich_score > opp_score:
            result = "W"
            wins += 1
        else:
            result = "L"
            losses += 1
        
        score_display = f"{mich_score}-{opp_score}"
        print(f"{i:2}. {str(game.game_date):<12} {location} {opp.name:<30} {score_display:<10} {result}")
    else:
        print(f"{i:2}. {str(game.game_date):<12} {location} {opp.name:<30} {'(Not played)':<10}")

print()
print("=" * 120)
print(f"RECORD: {wins}-{losses} ({wins + losses} games played)")
print("=" * 120)
print()

# Get computed metrics
try:
    metrics = TeamSeasonMetrics.objects.get(team=michigan, season__year=2026)
    
    print("COMPUTED TEAM METRICS")
    print("=" * 120)
    print()
    print("BASIC STATS:")
    print(f"  Games Played: {metrics.games}")
    print(f"  PPG: {metrics.ppg:.1f}")
    print(f"  Opp PPG: {metrics.papg:.1f}")
    print(f"  Pace: {metrics.pace:.1f}")
    print()
    
    print("EFFICIENCY RATINGS:")
    print(f"  Offensive Rating (Adj O): {metrics.ortg:.1f}")
    print(f"  Defensive Rating (Adj D): {metrics.drtg:.1f}")
    print(f"  Net Rating (EM): {metrics.net_rtg:.1f}")
    print()
    
    print("FOUR FACTORS - OFFENSE:")
    print(f"  eFG%: {metrics.efg_pct:.1%}")
    print(f"  TOV%: {metrics.tov_pct:.1%}")
    print(f"  ORB%: {metrics.orb_pct:.1%}")
    print(f"  FTR: {metrics.ftr:.3f}")
    print()
    
    print("FOUR FACTORS - DEFENSE:")
    print(f"  Opp eFG%: {metrics.opp_efg_pct:.1%}")
    print(f"  Opp TOV%: {metrics.opp_tov_pct:.1%}")
    print(f"  DRB%: {metrics.drb_pct:.1%}")
    print(f"  Opp FTR: {metrics.opp_ftr:.3f}")
    print()
    
    print("FOUR FACTOR MARGINS:")
    print(f"  eFG Margin: {metrics.efg_margin:+.1%}")
    print(f"  TOV Edge: {metrics.tov_edge:+.1%}")
    print(f"  REB Edge: {metrics.reb_edge:+.1%}")
    print(f"  FTR Margin: {metrics.ftr_margin:+.3f}")
    print()
    
    print("KILL SHOTS:")
    print(f"  Kill Shots For: {metrics.kill_shots_for}")
    print(f"  Kill Shots Against: {metrics.kill_shots_against}")
    print(f"  Kill Shots Per Game: {metrics.kill_shots_pg:.2f}")
    print(f"  Kill Shots Allowed Per Game: {metrics.kill_shots_conceded_pg:.2f}")
    print(f"  Kill Shot Margin Per Game: {metrics.kill_shot_margin_pg:+.2f}")
    print()
    
    print("=" * 120)
    
except TeamSeasonMetrics.DoesNotExist:
    print("No computed metrics found for Michigan 2025-26")
