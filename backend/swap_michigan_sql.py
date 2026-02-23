"""
Script to swap Michigan and Michigan State data using raw SQL
"""

from django.db import connection
from core.models import Team

# Get both teams
michigan = Team.objects.get(slug='michigan')
michigan_state = Team.objects.get(slug='michigan-state')

mich_id = michigan.id
msu_id = michigan_state.id

print(f"Michigan ID: {mich_id}")
print(f"Michigan State ID: {msu_id}")
print()

# Use a temporary ID that doesn't exist (999999)
temp_id = 999999

with connection.cursor() as cursor:
    # Disable foreign key constraints temporarily
    cursor.execute("PRAGMA foreign_keys=OFF")
    
    print("Swapping TeamGameStats team field...")
    # Step 1: Michigan -> Temp
    cursor.execute("UPDATE core_teamgamestats SET team_id = %s WHERE team_id = %s", [temp_id, mich_id])
    print(f"  Moved Michigan ({mich_id}) to temp ({temp_id}): {cursor.rowcount} rows")
    
    # Step 2: Michigan State -> Michigan
    cursor.execute("UPDATE core_teamgamestats SET team_id = %s WHERE team_id = %s", [mich_id, msu_id])
    print(f"  Moved Michigan State ({msu_id}) to Michigan ({mich_id}): {cursor.rowcount} rows")
    
    # Step 3: Temp -> Michigan State
    cursor.execute("UPDATE core_teamgamestats SET team_id = %s WHERE team_id = %s", [msu_id, temp_id])
    print(f"  Moved temp ({temp_id}) to Michigan State ({msu_id}): {cursor.rowcount} rows")
    print()
    
    print("Swapping TeamGameStats opponent field...")
    # Step 1: Michigan -> Temp
    cursor.execute("UPDATE core_teamgamestats SET opponent_id = %s WHERE opponent_id = %s", [temp_id, mich_id])
    print(f"  Moved Michigan ({mich_id}) to temp ({temp_id}): {cursor.rowcount} rows")
    
    # Step 2: Michigan State -> Michigan
    cursor.execute("UPDATE core_teamgamestats SET opponent_id = %s WHERE opponent_id = %s", [mich_id, msu_id])
    print(f"  Moved Michigan State ({msu_id}) to Michigan ({mich_id}): {cursor.rowcount} rows")
    
    # Step 3: Temp -> Michigan State
    cursor.execute("UPDATE core_teamgamestats SET opponent_id = %s WHERE opponent_id = %s", [msu_id, temp_id])
    print(f"  Moved temp ({temp_id}) to Michigan State ({msu_id}): {cursor.rowcount} rows")
    print()
    
    print("Swapping Game home_team field...")
    # Step 1: Michigan -> Temp
    cursor.execute("UPDATE core_game SET home_team_id = %s WHERE home_team_id = %s", [temp_id, mich_id])
    print(f"  Moved Michigan ({mich_id}) to temp ({temp_id}): {cursor.rowcount} rows")
    
    # Step 2: Michigan State -> Michigan
    cursor.execute("UPDATE core_game SET home_team_id = %s WHERE home_team_id = %s", [mich_id, msu_id])
    print(f"  Moved Michigan State ({msu_id}) to Michigan ({mich_id}): {cursor.rowcount} rows")
    
    # Step 3: Temp -> Michigan State
    cursor.execute("UPDATE core_game SET home_team_id = %s WHERE home_team_id = %s", [msu_id, temp_id])
    print(f"  Moved temp ({temp_id}) to Michigan State ({msu_id}): {cursor.rowcount} rows")
    print()
    
    print("Swapping Game away_team field...")
    # Step 1: Michigan -> Temp
    cursor.execute("UPDATE core_game SET away_team_id = %s WHERE away_team_id = %s", [temp_id, mich_id])
    print(f"  Moved Michigan ({mich_id}) to temp ({temp_id}): {cursor.rowcount} rows")
    
    # Step 2: Michigan State -> Michigan
    cursor.execute("UPDATE core_game SET away_team_id = %s WHERE away_team_id = %s", [mich_id, msu_id])
    print(f"  Moved Michigan State ({msu_id}) to Michigan ({mich_id}): {cursor.rowcount} rows")
    
    # Step 3: Temp -> Michigan State
    cursor.execute("UPDATE core_game SET away_team_id = %s WHERE away_team_id = %s", [msu_id, temp_id])
    print(f"  Moved temp ({temp_id}) to Michigan State ({msu_id}): {cursor.rowcount} rows")
    print()
    
    # Re-enable foreign key constraints
    cursor.execute("PRAGMA foreign_keys=ON")
    print("✓ Foreign key constraints re-enabled")

print("=" * 80)
print("SUCCESS: Michigan and Michigan State data has been swapped!")
print("=" * 80)
print()
print("Now recomputing all aggregated metrics...")
