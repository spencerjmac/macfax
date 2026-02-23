"""
Complete the Season Backfill & Update All Metrics
Finishes Jan 18 - Feb 19, 2026 and recalculates everything
"""

import subprocess
import sys
from datetime import date

PYTHON_EXE = "C:/Users/spenc/OneDrive/Workspace/CBB Analytical Dashboard/backend/venv/Scripts/python.exe"

def run_command(desc, cmd):
    """Run a command and show results"""
    print(f"\n{'='*70}")
    print(f" {desc}")
    print(f"{'='*70}")
    print(f"Command: {' '.join(cmd[1:])}\n")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        print(result.stdout)
        
        if result.returncode != 0:
            print(f"❌ Error:\n{result.stderr}")
            return False
        
        print(f"✅ {desc} complete!")
        return True
    except subprocess.TimeoutExpired:
        print(f"⚠️  Timeout - command took > 15 minutes")
        return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False


def main():
    print("="*70)
    print(" 🏀 COMPLETE SEASON BACKFILL & METRICS UPDATE")
    print("="*70)
    print(f"Current Date: {date.today()}")
    print(f"\nThis will:")
    print("  1. Backfill missing games (Jan 18 - Feb 19, 2026)")
    print("  2. Recalculate season metrics for all teams")
    print("  3. Recalculate adjusted ratings")
    print("  4. Test the API")
    
    input("\nPress Enter to continue, or Ctrl+C to cancel...")
    
    results = []
    
    # Step 1: Backfill missing dates
    results.append((
        "Backfill Jan 18 - Feb 19",
        run_command(
            "Step 1: Backfill Missing Games",
            [
                PYTHON_EXE, "manage.py", "ingest_gamelogs",
                "--season", "2026",
                "--start", "2026-01-18",
                "--end", "2026-02-19",
                "--source", "ncaa"
            ]
        )
    ))
    
    # Step 2: Recalculate season metrics
    results.append((
        "Recalculate Season Metrics",
        run_command(
            "Step 2: Recalculate Season Metrics",
            [
                PYTHON_EXE, "manage.py", "calculate_season_metrics",
                "--season", "2026"
            ]
        )
    ))
    
    # Step 3: Recalculate adjusted ratings
    results.append((
        "Recalculate Adjusted Ratings",
        run_command(
            "Step 3: Recalculate Adjusted Ratings",
            [
                PYTHON_EXE, "manage.py", "calculate_adjusted_ratings",
                "--season", "2026"
            ]
        )
    ))
    
    # Step 4: Test API
    results.append((
        "Test API",
        run_command(
            "Step 4: Test Game Log API",
            [PYTHON_EXE, "test_simple.py"]
        )
    ))
    
    # Summary
    print("\n" + "="*70)
    print(" 📊 COMPLETION SUMMARY")
    print("="*70)
    
    passed = 0
    for step, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {step}")
        if success:
            passed += 1
    
    print(f"\n{passed}/{len(results)} steps completed successfully")
    
    if passed == len(results):
        print("\n" + "="*70)
        print(" 🎉 PIPELINE COMPLETE!")
        print("="*70)
        print("\n✅ Game log pipeline is fully operational!")
        print("\nFinal Step:")
        print("  → Integrate GameLog component into team profile page")
        print("  → File: frontend/src/app/teams/[slug]/page.tsx")
        print(f"\nRun status check: python check_status.py\n")
    else:
        print(f"\n⚠️  {len(results) - passed} step(s) failed")
    
    return passed == len(results)


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Cancelled by user")
        sys.exit(1)
