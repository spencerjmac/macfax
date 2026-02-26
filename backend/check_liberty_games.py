#!/usr/bin/env python
"""Check Liberty's game log data."""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, GameLog, Season

season = Season.objects.filter(year=2026).first()
liberty = Team.objects.filter(slug='liberty').first()

game_logs = GameLog.objects.filter(team=liberty, season=season).order_by('date')

print(f"Liberty Game Logs for {season.year}")
print("=" * 100)
print(f"Total games: {game_logs.count()}\n")

if game_logs.exists():
    # Check first few games for data quality
    print("Sample game data (first 3 games):")
    print("-" * 100)
    
    for game in game_logs[:3]:
        print(f"\nDate: {game.date}")
        print(f"Opponent: {game.opponent.name if game.opponent else 'Unknown'}")
        print(f"Score: {game.points}-{game.opponent_points}")
        print(f"FGM-FGA: {game.fgm}-{game.fga}")
        print(f"3PM-3PA: {game.fg3m}-{game.fg3a}")
        print(f"FTM-FTA: {game.ftm}-{game.fta}")
        print(f"ORB: {game.orb}, DRB: {game.drb}, TRB: {game.trb}")
        print(f"TOV: {game.tov}")
        print(f"Opp FGM-FGA: {game.opp_fgm}-{game.opp_fga}")
        print(f"Opp ORB-DRB: {game.opp_orb}-{game.opp_drb}")
        print(f"Opp TOV: {game.opp_tov}")
        
    # Check if any critical stats are all zeros
    print("\n\nChecking for missing data across all games:")
    print("-" * 100)
    
    all_games_data = {
        'fgm_zero': game_logs.filter(fgm=0).count(),
        'fga_zero': game_logs.filter(fga=0).count(),
        'fg3a_zero': game_logs.filter(fg3a=0).count(),
        'fta_zero': game_logs.filter(fta=0).count(),
        'orb_zero': game_logs.filter(orb=0).count(),
        'tov_zero': game_logs.filter(tov=0).count(),
        'opp_fga_zero': game_logs.filter(opp_fga=0).count(),
        'opp_orb_zero': game_logs.filter(opp_orb=0).count(),
        'opp_tov_zero': game_logs.filter(opp_tov=0).count(),
    }
    
    for stat, zero_count in all_games_data.items():
        if zero_count > 0:
            print(f"  {stat}: {zero_count}/{game_logs.count()} games with zero")
        else:
            print(f"  {stat}: ✓ All games have data")
else:
    print("NO GAME LOGS FOUND!")
