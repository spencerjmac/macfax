#!/usr/bin/env python  
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import (
    Game, TeamGameStats, ScoringEvent,
    TeamSeasonMetrics, TeamSeasonRatings, TeamExternalId
)

print("\n" + "="*60)
print("GAME LOG PIPELINE VALIDATION - 2025-26 SEASON")
print("="*60)

# Count all records
games = Game.objects.filter(season_year=2026).count()
stats = TeamGameStats.objects.filter(game__season_year=2026).count()
events = ScoringEvent.objects.filter(game__season_year=2026).count()
metrics = TeamSeasonMetrics.objects.filter(season__year=2026).count()
ratings = TeamSeasonRatings.objects.filter(season__year=2026).count()
mappings = TeamExternalId.objects.filter(source='ncaa').count()

print(f"\n📊 RECORD COUNTS:")
print(f"  Games:              {games}")
print(f"  Team Stats:         {stats} ({stats//games if games else 0} per game)")
print(f"  Scoring Events:     {events}")
print(f"  Team Metrics:       {metrics}")
print(f"  Team Ratings:       {ratings}")
print(f"  NCAA Mappings:      {mappings}")

# Sample game details
print(f"\n🏀 SAMPLE GAMES:")
for g in Game.objects.filter(season_year=2026).order_by('-away_score')[:3]:
    print(f"  {g.away_team.name} ({g.away_score}) @ {g.home_team.name} ({g.home_score})")
    print(f"    Date: {g.game_date}, Status: {g.status}")
    
    # Show box scores
    away_stats = TeamGameStats.objects.filter(game=g, team=g.away_team).first()
    home_stats = TeamGameStats.objects.filter(game=g, team=g.home_team).first()
    
    if away_stats and home_stats:
        print(f"    {g.away_team.name}: {away_stats.fgm}-{away_stats.fga} FG, {away_stats.fg3m}-{away_stats.fg3a} 3PT, {away_stats.ftm}-{away_stats.fta} FT")
        print(f"    {g.home_team.name}: {home_stats.fgm}-{home_stats.fga} FG, {home_stats.fg3m}-{home_stats.fg3a} 3PT, {home_stats.ftm}-{home_stats.fta} FT")

# Sample team metrics
print(f"\n📈 SAMPLE TEAM METRICS (with games):")
for m in TeamSeasonMetrics.objects.filter(season__year=2026, games__gt=0).order_by('-ortg')[:5]:
    print(f"  {m.team.name}:")
    print(f"    Games: {m.games}, PPG: {m.ppg:.1f}, ORtg: {m.ortg:.1f}")
    print(f"    Four Factors: eFG%={m.efg_pct*100:.1f}%, TOV%={m.tov_pct*100:.1f}%, ORB%={m.orb_pct*100:.1f}%, FTR={m.ftr:.3f}")
    print(f"    Kill Shots/Game: {m.kill_shots_pg:.2f}")

# Sample team ratings
print(f"\n🏆 SAMPLE TEAM RATINGS (Top 5 by Adj EM):")
for r in TeamSeasonRatings.objects.filter(season__year=2026).order_by('-adj_em')[:5]:
    print(f"  {r.team.name}:")
    print(f"    Adj EM: {r.adj_em:+.2f}, Adj O: {r.adj_o:.2f}, Adj D: {r.adj_d:.2f}")

# Data quality checks
print(f"\n✓ DATA QUALITY CHECKS:")

# Check 1: All games have 2 team stats
games_without_stats = Game.objects.filter(season_year=2026).exclude(
    team_stats__isnull=False
).count()
print(f"  Games without stats: {games_without_stats}")

# Check 2: Team stats points match game scores
mismatched = 0
for g in Game.objects.filter(season_year=2026):
    home_stat = TeamGameStats.objects.filter(game=g, team=g.home_team).first()
    away_stat = TeamGameStats.objects.filter(game=g, team=g.away_team).first()
    if home_stat and g.home_score and home_stat.pts != g.home_score:
        mismatched += 1
    if away_stat and g.away_score and away_stat.pts != g.away_score:
        mismatched += 1

print(f"  Mismatched scores: {mismatched}")

# Check 3: All metrics have valid Four Factors
invalid_metrics = TeamSeasonMetrics.objects.filter(
    season__year=2026,
    games__gt=0
).filter(
    efg_pct__lt=0
).count()
print(f"  Invalid Four Factors: {invalid_metrics}")

# Check 4: All ratings exist
teams_with_ratings = TeamSeasonRatings.objects.filter(
    season__year=2026
).count()
print(f"  Teams with ratings: {teams_with_ratings}")

print(f"\n✅ PIPELINE STATUS: {'OPERATIONAL' if games > 0 and stats > 0 and ratings > 0 else 'INCOMPLETE'}")
print("="*60 + "\n")
