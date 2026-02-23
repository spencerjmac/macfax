"""
Diagnose why Michigan has wrong game count and record
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, Game, TeamGameStats, TeamExternalId
from datetime import date

print("=" * 100)
print("MICHIGAN DATA DIAGNOSTIC")
print("=" * 100)

# Get Michigan team
try:
    michigan = Team.objects.get(name='Michigan')
    print(f"\n✓ Found Michigan in database: ID={michigan.id}, Slug={michigan.slug}")
except Team.DoesNotExist:
    print("\n✗ ERROR: Michigan not found in database!")
    sys.exit(1)

# Check external ID mappings
print("\n" + "-" * 100)
print("EXTERNAL ID MAPPINGS FOR MICHIGAN")
print("-" * 100)
external_ids = TeamExternalId.objects.filter(team=michigan)
if external_ids.exists():
    for ext_id in external_ids:
        print(f"  Source: {ext_id.source}")
        print(f"  External ID: {ext_id.external_id}")
        print(f"  External Name: {ext_id.external_name}")
        print(f"  Confidence: {ext_id.confidence}")
        print(f"  Manual Override: {ext_id.is_manual_override}")
        print()
else:
    print("  ⚠ WARNING: No external ID mappings found for Michigan!")

# Count games for 2025-26 season
print("-" * 100)
print("GAMES IN DATABASE (2025-26 SEASON)")
print("-" * 100)
home_games = Game.objects.filter(home_team=michigan, season_year=2026).order_by('game_date')
away_games = Game.objects.filter(away_team=michigan, season_year=2026).order_by('game_date')

print(f"  Home games: {home_games.count()}")
print(f"  Away games: {away_games.count()}")
print(f"  Total games: {home_games.count() + away_games.count()}")

all_games = sorted(
    list(home_games) + list(away_games),
    key=lambda g: g.game_date
)

if all_games:
    print(f"  First game: {all_games[0].game_date}")
    print(f"  Last game: {all_games[-1].game_date}")

# Check for wins and losses
print("\n" + "-" * 100)
print("RECORD BREAKDOWN")
print("-" * 100)
wins = 0
losses = 0

for game in all_games:
    mich_stats = TeamGameStats.objects.filter(game=game, team=michigan).first()
    if game.home_team == michigan:
        opp_stats = TeamGameStats.objects.filter(game=game, team=game.away_team).first()
    else:
        opp_stats = TeamGameStats.objects.filter(game=game, team=game.home_team).first()
    
    if mich_stats and opp_stats:
        if mich_stats.pts > opp_stats.pts:
            wins += 1
        else:
            losses += 1

print(f"  Wins: {wins}")
print(f"  Losses: {losses}")
print(f"  Record: {wins}-{losses}")
print(f"\n  Expected: 25-1 (26 games)")
print(f"  Actual: {wins}-{losses} ({wins + losses} games)")
print(f"  Missing: {26 - (wins + losses)} games")

# Check for games after the last recorded game
print("\n" + "-" * 100)
print("CHECKING FOR MISSING DATES")
print("-" * 100)

if all_games:
    last_date = all_games[-1].game_date
    today = date(2026, 2, 21)
    print(f"  Last game date in DB: {last_date}")
    print(f"  Today's date: {today}")
    print(f"  Days since last game: {(today - last_date).days}")
    print(f"\n  ⚠ Michigan likely has games between {last_date} and {today} that weren't imported")

# Check all teams that Michigan played
print("\n" + "-" * 100)
print("OPPONENTS IN DATABASE")
print("-" * 100)
opponents = set()
for game in all_games:
    if game.home_team == michigan:
        opponents.add(game.away_team.name)
    else:
        opponents.add(game.home_team.name)

for i, opp in enumerate(sorted(opponents), 1):
    print(f"  {i}. {opp}")

# Check for any games with Michigan in the external name
print("\n" + "-" * 100)
print("CHECKING FOR 'MICHIGAN' IN UNPROCESSED EXTERNAL NAMES")
print("-" * 100)

# Get all external IDs with "Michigan" in the name
michigan_external = TeamExternalId.objects.filter(external_name__icontains='Michigan')
print(f"  Found {michigan_external.count()} external IDs containing 'Michigan':")
for ext in michigan_external:
    print(f"    - '{ext.external_name}' -> {ext.team.name} (source: {ext.source})")

print("\n" + "=" * 100)
print("DIAGNOSTIC COMPLETE")
print("=" * 100)
