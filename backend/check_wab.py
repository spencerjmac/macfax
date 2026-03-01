import sqlite3

conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()

# Query Michigan's WAB
query = """
SELECT t.name, tsr.wab 
FROM core_teamseasonratings tsr 
JOIN core_team t ON tsr.team_id = t.id 
WHERE t.slug = 'michigan' 
AND tsr.season_id = (SELECT id FROM core_season WHERE year = 2026)
"""

cursor.execute(query)
result = cursor.fetchone()

if result:
    print(f"Team: {result[0]}")
    print(f"WAB: {result[1]}")
else:
    print("No data found for Michigan")

# Also check if WAB field exists for any team
cursor.execute("SELECT COUNT(*) FROM core_teamseasonratings WHERE wab IS NOT NULL AND season_id = (SELECT id FROM core_season WHERE year = 2026)")
count = cursor.fetchone()[0]
print(f"\nTotal teams with WAB in 2026 season: {count}")

conn.close()
