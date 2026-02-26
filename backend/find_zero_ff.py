#!/usr/bin/env python
"""Find all teams with zero four factor stats."""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import TeamSeasonRatings, Season

season = Season.objects.filter(year=2026).first()

# Find teams with zero four factors
print("Teams with all four factor stats = 0.0:")
print("-" * 60)

zero_ff_teams = TeamSeasonRatings.objects.filter(
    season=season,
    adj_efg_pct=0.0,
    adj_tov_pct=0.0,
    adj_orb_pct=0.0,
    adj_ftr=0.0
)

for rating in zero_ff_teams.order_by('team__name'):
    print(f"{rating.team.name:30} | Games: {rating.games_played:2} | adj_o: {rating.adj_o:7.2f} | adj_d: {rating.adj_d:7.2f}")

print(f"\nTotal teams with zero four factors: {zero_ff_teams.count()}")
print(f"Total teams in season: {TeamSeasonRatings.objects.filter(season=season).count()}")
