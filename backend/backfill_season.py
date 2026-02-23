"""
Full Season Backfill Script
Nov 2025 - Feb 2026 (current: Feb 18, 2026)

This script runs the game log ingestion in WEEKLY chunks to ensure 
reliability and provide progress updates.
"""

import subprocess
import sys
from datetime import date, datetime

# Define WEEKLY ranges for the 2025-26 season
SEASON_YEAR = 2026
WEEKS = [
    # November 2025
    ("Week 1 (Nov 1-7)", "2025-11-01", "2025-11-07"),
    ("Week 2 (Nov 8-14)", "2025-11-08", "2025-11-14"),
    ("Week 3 (Nov 15-21)", "2025-11-15", "2025-11-21"),
    ("Week 4 (Nov 22-30)", "2025-11-22", "2025-11-30"),
    # December 2025
    ("Week 5 (Dec 1-7)", "2025-12-01", "2025-12-07"),
    ("Week 6 (Dec 8-14)", "2025-12-08", "2025-12-14"),
    ("Week 7 (Dec 15-21)", "2025-12-15", "2025-12-21"),
    ("Week 8 (Dec 22-31)", "2025-12-22", "2025-12-31"),
    # January 2026
    ("Week 9 (Jan 1-7)", "2026-01-01", "2026-01-07"),
    ("Week 10 (Jan 8-14)", "2026-01-08", "2026-01-14"),
    ("Week 11 (Jan 15-21)", "2026-01-15", "2026-01-21"),
    ("Week 12 (Jan 22-31)", "2026-01-22", "2026-01-31"),
    # February 2026
    ("Week 13 (Feb 1-7)", "2026-02-01", "2026-02-07"),
    ("Week 14 (Feb 8-14)", "2026-02-08", "2026-02-14"),
    ("Week 15 (Feb 15-18)", "2026-02-15", "2026-02-18"),
]

PYTHON_EXE = "C:/Users/spenc/OneDrive/Workspace/CBB Analytical Dashboard/backend/venv/Scripts/python.exe"


def print_header(text):
    print("\n" + "="*70)
    print(f" {text}")
    print("="*70)


def run_ingestion(week_name, start_date, end_date, refresh=False):
    """Run the ingestion command for a date range"""
    print_header(f"Ingesting {week_name}")
    print(f"Date Range: {start_date} to {end_date}")
    
    cmd = [
        PYTHON_EXE,
        "manage.py",
        "ingest_gamelogs",
        "--season", str(SEASON_YEAR),
        "--start", start_date,
        "--end", end_date,
        "--source", "ncaa",  # Use NCAA API
    ]
    
    if refresh:
        cmd.append("--refresh")
    
    print(f"\nCommand: {' '.join(cmd[1:])}\n")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout per week
        )
        
        print(result.stdout)
        
        if result.returncode != 0:
            print(f"❌ Error during {week_name}:")
            print(result.stderr)
            return False
        
        print(f"✅ {week_name} complete!")
        return True
        
    except subprocess.TimeoutExpired:
        print(f"⚠️  Timeout during {week_name} - may need to retry")
        return False
    except Exception as e:
        print(f"❌ Exception during {week_name}: {e}")
        return False


def main():
    print_header("🏀 FULL SEASON BACKFILL (WEEKLY)")
    print(f"Season: {SEASON_YEAR}")
    print(f"Current Date: {date.today()}")
    print(f"Data Source: NCAA API (ncaa-api.henrygd.me)")
    print(f"\nThis will ingest game logs for all D1 games from Nov 2025 to Feb 18, 2026")
    print(f"Processing in {len(WEEKS)} weekly chunks for reliability")
    
    # Show plan
    print_header("Ingestion Plan")
    for i, (week, start, end) in enumerate(WEEKS, 1):
        print(f"{i:2d}. {week}: {start} to {end}")
    
    input("\nPress Enter to start, or Ctrl+C to cancel...")
    
    results = []
    start_time = datetime.now()
    
    # Run each week
    for week_name, start_date, end_date in WEEKS:
        success = run_ingestion(week_name, start_date, end_date)
        results.append((week_name, success))
        
        if not success:
            print(f"\n⚠️  Failed on {week_name}. Continue? (y/n): ", end='')
            response = input()
            if response.lower() != 'y':
                print("Aborting backfill.")
                break
    
    # Final summary
    end_time = datetime.now()
    duration = end_time - start_time
    
    print_header("📊 BACKFILL SUMMARY")
    print(f"Duration: {duration}")
    print(f"\nResults:")
    
    passed = 0
    for week_name, success in results:
        status = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"  {status} - {week_name}")
        if success:
            passed += 1
    
    print(f"\n{passed}/{len(results)} weeks completed successfully")
    
    if passed == len(results):
        print_header("🎉 FULL SEASON BACKFILL COMPLETE!")
        print("\nNext steps:")
        print("1. Verify game counts: python manage.py check_games")
        print("2. Calculate adjusted ratings: python manage.py calculate_adjusted_ratings --season 2026")
        print("3. Calculate kill shots: python manage.py calculate_kill_shots --season 2026")
        print("4. Test API: python test_gamelog_api.py")
    else:
        print(f"\n⚠️  {len(results) - passed} week(s) failed. Check errors above.")
    
    return passed == len(results)


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Backfill cancelled by user")
        sys.exit(1)
