import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Game, Team, TeamGameStats
from datetime import date
from django.db.models import Q

print("=" * 80)
print("CHECKING GAMES FEB 21-26, 2026")
print("=" * 80)

# Check Michigan specifically
michigan = Team.objects.get(slug='michigan')
duke = Team.objects.get(slug='duke')

print("\n1. MICHIGAN GAMES (Feb 21-26):")
print("-" * 80)
mich_games = Game.objects.filter(
    Q(home_team=michigan) | Q(away_team=michigan),
    season_year=2026,
    game_date__gte=date(2026, 2, 21),
    game_date__lte=date(2026, 2, 26)
).order_by('game_date')

for game in mich_games:
    opponent = game.away_team if game.home_team == michigan else game.home_team
    location = "vs" if game.home_team == michigan else "@"
    
    # Get stats
    mich_stats = TeamGameStats.objects.filter(game=game, team=michigan).first()
    opp_stats = TeamGameStats.objects.filter(game=game, team=opponent).first()
    
    score = ""
    if mich_stats and opp_stats:
        score = f"{mich_stats.pts}-{opp_stats.pts}"
        result = "W" if mich_stats.pts > opp_stats.pts else "L"
        score = f"({result} {score})"
    
    has_stats = "✓" if mich_stats else "✗"
    
    print(f"  {game.game_date} {location} {opponent.name:30s} {game.status:12s} Stats:{has_stats} {score}")

print("\n2. DUKE GAMES (Feb 21-26):")
print("-" * 80)
duke_games = Game.objects.filter(
    Q(home_team=duke) | Q(away_team=duke),
    season_year=2026,
    game_date__gte=date(2026, 2, 21),
    game_date__lte=date(2026, 2, 26)
).order_by('game_date')

for game in duke_games:
    opponent = game.away_team if game.home_team == duke else game.home_team
    location = "vs" if game.home_team == duke else "@"
    
    # Get stats
    duke_stats = TeamGameStats.objects.filter(game=game, team=duke).first()
    opp_stats = TeamGameStats.objects.filter(game=game, team=opponent).first()
    
    score = ""
    if duke_stats and opp_stats:
        score = f"{duke_stats.pts}-{opp_stats.pts}"
        result = "W" if duke_stats.pts > opp_stats.pts else "L"
        score = f"({result} {score})"
    
    has_stats = "✓" if duke_stats else "✗"
    
    print(f"  {game.game_date} {location} {opponent.name:30s} {game.status:12s} Stats:{has_stats} {score}")

# Check for Michigan vs Duke game specifically
print("\n3. CHECKING FOR MICHIGAN VS DUKE ON FEB 21:")
print("-" * 80)
mich_duke_game = Game.objects.filter(
    Q(home_team=michigan, away_team=duke) | Q(home_team=duke, away_team=michigan),
    season_year=2026,
    game_date=date(2026, 2, 21)
).first()

if mich_duke_game:
    print(f"✓ FOUND: {mich_duke_game.game_date} - {mich_duke_game.away_team.name} @ {mich_duke_game.home_team.name}")
    print(f"  Status: {mich_duke_game.status}")
    print(f"  Source Game ID: {mich_duke_game.source_game_id}")
    
    mich_stats = TeamGameStats.objects.filter(game=mich_duke_game, team=michigan).first()
    duke_stats = TeamGameStats.objects.filter(game=mich_duke_game, team=duke).first()
    
    if mich_stats and duke_stats:
        print(f"  Score: {mich_duke_game.away_team.name} {mich_stats.pts if mich_duke_game.away_team == michigan else duke_stats.pts} - {mich_duke_game.home_team.name} {duke_stats.pts if mich_duke_game.home_team == duke else mich_stats.pts}")
    else:
        print(f"  ✗ NO BOX SCORE DATA")
else:
    print("✗ MICHIGAN VS DUKE GAME NOT FOUND IN DATABASE")

# Summary of all games Feb 21-26
print("\n4. ALL GAMES FEB 21-26 SUMMARY:")
print("-" * 80)
all_games = Game.objects.filter(
    season_year=2026,
    game_date__gte=date(2026, 2, 21),
    game_date__lte=date(2026, 2, 26)
).order_by('game_date')

print(f"Total games: {all_games.count()}")

by_date = {}
for game in all_games:
    date_str = str(game.game_date)
    if date_str not in by_date:
        by_date[date_str] = {'total': 0, 'with_stats': 0, 'final': 0}
    by_date[date_str]['total'] += 1
    if game.status == 'final':
        by_date[date_str]['final'] += 1
    if TeamGameStats.objects.filter(game=game).exists():
        by_date[date_str]['with_stats'] += 1

for date_str in sorted(by_date.keys()):
    stats = by_date[date_str]
    print(f"  {date_str}: {stats['total']:3d} games ({stats['final']:3d} final, {stats['with_stats']:3d} with stats)")

print("\n" + "=" * 80)
