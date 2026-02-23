import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, Game
from django.db.models import Q, Count

print("="*70)
print("Checking for potential fuzzy matching errors")
print("="*70)

# Find teams with unusual game counts (much higher or lower than 25-27 games)
from core.models import TeamSeasonRatings

ratings = TeamSeasonRatings.objects.filter(season__year=2026).order_by('games_played')

print("\nTeams with unusual game counts:")
print("-"*70)

unusual_counts = []
for r in ratings:
    if r.games_played < 20 or r.games_played > 30:
        unusual_counts.append(r)
        print(f"{r.team.name:30s}: {r.games_played} games")

print(f"\nTotal teams with unusual counts: {len(unusual_counts)}")

# Check for teams that might be fuzzy matched incorrectly
# Look for similar team names that might be confused
print("\n" + "="*70)
print("Checking for potential name confusion")
print("="*70)

# Common confusions
similar_names = [
    ('Saint Louis', 'Saint Leo'),
    ('Saint Joseph\'s', 'St. Joseph\'s'),
    ('Miami (FL)', 'Miami (OH)'),
    ('Texas', 'Texas Tech', 'Texas A&M', 'Texas St.'),
    ('USC', 'South Carolina'),
]

from core.models import TeamExternalId

print("\nChecking TeamExternalId entries for fuzzy matches...")
print("-"*70)

# Get all external IDs and check for low confidence or suspicious names
external_ids = TeamExternalId.objects.all().select_related('team')

suspicious = []
for ext_id in external_ids:
    # Check if external name significantly differs from team name
    ext_name = ext_id.external_name.lower()
    team_name = ext_id.team.name.lower()
    
    # Simple check: if names are very different, flag it
    if ext_name not in team_name and team_name not in ext_name:
        if len(ext_name) > 3 and len(team_name) > 3:  # Avoid short abbreviations
            suspicious.append(ext_id)

print(f"Found {len(suspicious)} potentially suspicious mappings")
if len(suspicious) > 0:
    print("\nShowing first 30 suspicious mappings:")
    for ext_id in suspicious[:30]:
        print(f"  '{ext_id.external_name}' -> '{ext_id.team.name}'")
