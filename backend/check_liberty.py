#!/usr/bin/env python
"""Check Liberty's TeamSeasonRatings data."""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, TeamSeasonRatings, Season, GameLog

# Find Liberty
liberty = Team.objects.filter(slug='liberty').first()
print(f"Team: {liberty.name if liberty else 'NOT FOUND'}")
print(f"Slug: {liberty.slug if liberty else 'N/A'}")

# Check season
season = Season.objects.filter(year=2025).first()
print(f"\nCurrent Season: {season.year if season else 'NOT FOUND'}")

# Check TeamSeasonRatings
ratings = TeamSeasonRatings.objects.filter(team=liberty, season=season).first()
if ratings:
    print(f"\n✓ TeamSeasonRatings EXISTS for Liberty")
    print(f"  adj_o: {ratings.adj_o}")
    print(f"  adj_d: {ratings.adj_d}")
    print(f"  adj_efg_pct: {ratings.adj_efg_pct}")
    print(f"  adj_tov_pct: {ratings.adj_tov_pct}")
    print(f"  adj_orb_pct: {ratings.adj_orb_pct}")
    print(f"  adj_ftr: {ratings.adj_ftr}")
    print(f"  games_played: {ratings.games_played}")
else:
    print(f"\n✗ NO TeamSeasonRatings record for Liberty!")
    
    # Check if there are game logs
    game_logs = GameLog.objects.filter(team=liberty, season=season)
    print(f"\nGameLog records for Liberty: {game_logs.count()}")
    
    if game_logs.exists():
        print("  Sample games:")
        for game in game_logs[:3]:
            print(f"    {game.date}: vs {game.opponent.name}, Score: {game.points}-{game.opponent_points}")

# Check total ratings
total_ratings = TeamSeasonRatings.objects.filter(season=season).count()
print(f"\nTotal teams with ratings for 2025-26: {total_ratings}")
