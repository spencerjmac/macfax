"""
Pre-flight check before running full season backfill

Verifies:
- Season 2026 exists in DB
- NCAA API is accessible
- Team mappings exist
- Current data status
"""

import sys
from pathlib import Path

# Django setup
import django
import os
sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Season, Team, Game, TeamGameStats, TeamExternalId
from core.utils.ncaa_api import NCAAAPIClient
from datetime import date


def check_season():
    """Verify Season 2026 exists"""
    print("\n[1/5] Checking Season...")
    try:
        season = Season.objects.get(year=2026)
        print(f"  ✅ Season 2026 exists: {season.display_name}")
        return True
    except Season.DoesNotExist:
        print("  ❌ Season 2026 not found")
        print("     Run: python manage.py create_season --year 2026")
        return False


def check_teams():
    """Verify teams exist"""
    print("\n[2/5] Checking Teams...")
    count = Team.objects.count()
    if count > 0:
        print(f"  ✅ {count} teams in database")
        return True
    else:
        print("  ❌ No teams found")
        return False


def check_team_mappings():
    """Verify NCAA team mappings exist"""
    print("\n[3/5] Checking Team Mappings...")
    ncaa_count = TeamExternalId.objects.filter(source='ncaa').count()
    espn_count = TeamExternalId.objects.filter(source='espn').count()
    
    print(f"  NCAA mappings: {ncaa_count}")
    print(f"  ESPN mappings: {espn_count}")
    
    if ncaa_count > 50:
        print(f"  ✅ {ncaa_count} NCAA team mappings exist")
        return True
    else:
        print("  ⚠️  Few NCAA mappings - will build during ingestion")
        return True  # Not critical


def check_ncaa_api():
    """Test NCAA API connectivity"""
    print("\n[4/5] Checking NCAA API...")
    try:
        client = NCAAAPIClient()
        # Test with a recent date
        games = client.get_scoreboard(date(2025, 11, 4))
        print(f"  ✅ NCAA API accessible ({len(games)} games found on 2025-11-04)")
        return True
    except Exception as e:
        print(f"  ❌ NCAA API error: {e}")
        return False


def check_current_data():
    """Show current data status"""
    print("\n[5/5] Current Data Status...")
    
    games_2026 = Game.objects.filter(season_year=2026).count()
    stats_2026 = TeamGameStats.objects.filter(game__season_year=2026).count()
    
    print(f"  Games (2025-26): {games_2026}")
    print(f"  Team Game Stats: {stats_2026}")
    
    if games_2026 > 0:
        first_game = Game.objects.filter(season_year=2026).order_by('game_date').first()
        last_game = Game.objects.filter(season_year=2026).order_by('-game_date').first()
        print(f"  Date Range: {first_game.game_date} to {last_game.game_date}")
    
    return True


def main():
    print("="*70)
    print(" 🏀 PRE-FLIGHT CHECK - Full Season Backfill")
    print("="*70)
    
    checks = [
        check_season(),
        check_teams(),
        check_team_mappings(),
        check_ncaa_api(),
        check_current_data(),
    ]
    
    print("\n" + "="*70)
    print(" SUMMARY")
    print("="*70)
    
    passed = sum(checks)
    total = len(checks)
    
    if passed == total:
        print(f"\n✅ All checks passed ({passed}/{total})")
        print("\n🚀 Ready to run backfill!")
        print("\nRun: python backfill_season.py")
        return True
    else:
        print(f"\n⚠️  {total - passed} check(s) failed")
        print("\nResolve issues before running backfill.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
