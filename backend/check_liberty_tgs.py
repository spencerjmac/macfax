#!/usr/bin/env python
"""Check Liberty's TeamGameStats data."""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, TeamGameStats, TeamSeasonMetrics, Season

season = Season.objects.filter(year=2026).first()
liberty = Team.objects.filter(slug='liberty').first()

print(f"Checking Liberty's data for {season.year}")
print("=" * 80)

# Check TeamGameStats
team_game_stats = TeamGameStats.objects.filter(
    team=liberty,
    game__season_year=season.year
)

print(f"\nTeamGameStats records: {team_game_stats.count()}")
if team_game_stats.exists():
    print("  Sample games:")
    for tgs in team_game_stats[:3]:
        print(f"    Game ID {tgs.game_id}: {tgs.team.name} vs opponent")
else:
    print("  NO TeamGameStats found!")

# Check TeamSeasonMetrics
try:
    metrics = TeamSeasonMetrics.objects.get(team=liberty, season=season)
    print(f"\n✓ TeamSeasonMetrics EXISTS")
    print(f"  efg_pct: {metrics.efg_pct}")
    print(f"  tov_pct: {metrics.tov_pct}")
    print(f"  orb_pct: {metrics.orb_pct}")
    print(f"  ftr: {metrics.ftr}")
    print(f"  games_played: {metrics.games_played}")
except TeamSeasonMetrics.DoesNotExist:
    print(f"\n✗ NO TeamSeasonMetrics found!")

# Check total counts
total_tgs = TeamGameStats.objects.filter(game__season_year=season.year).values('team').distinct().count()
total_metrics = TeamSeasonMetrics.objects.filter(season=season).count()
print(f"\nTotal teams with TeamGameStats: {total_tgs}")
print(f"Total teams with TeamSeasonMetrics: {total_metrics}")
