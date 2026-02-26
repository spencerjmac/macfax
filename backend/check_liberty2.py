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

# Check all seasons
all_seasons = Season.objects.all().order_by('-year')
print(f"\nAvailable seasons:")
for s in all_seasons:
    print(f"  {s.year}")

# Use current season (2026 for 2025-26)
season = Season.objects.filter(year=2026).first()
if not season:
    season = Season.objects.latest('year')
    
print(f"\nUsing Season: {season.year}")

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
    print(f"  adj_opp_efg_pct: {ratings.adj_opp_efg_pct}")
    print(f"  games_played: {ratings.games_played}")
else:
    print(f"\n✗ NO TeamSeasonRatings record for Liberty in {season.year}!")
    
    # Check if there are game logs
    game_logs = GameLog.objects.filter(team=liberty, season=season)
    print(f"\nGameLog records for Liberty in {season.year}: {game_logs.count()}")
    
    if game_logs.exists():
        print("  Sample games:")
        for game in game_logs[:5]:
            print(f"    {game.date}: vs {game.opponent.name if game.opponent else 'Unknown'}")

# Check total ratings
total_ratings = TeamSeasonRatings.objects.filter(season=season).count()
print(f"\nTotal teams with ratings for {season.year}: {total_ratings}")

# Check if ratings calculation script exists
print(f"\n--- Checking for a few other teams ---")
for team_slug in ['michigan', 'duke', 'kansas']:
    team = Team.objects.filter(slug=team_slug).first()
    if team:
        r = TeamSeasonRatings.objects.filter(team=team, season=season).first()
        print(f"{team.name}: {'✓ Has ratings' if r else '✗ No ratings'}")
