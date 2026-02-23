import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from core.models import Team, TeamSeasonRatings
from api.serializers import RankingsSerializer

print("\n" + "=" * 80)
print("Testing Conference Mapping in Serializer")
print("=" * 80)

# Get a sample of teams to test
test_teams = [
    'hawaii',           # Should be BW
    'illinois-chicago', # Should be MVC
    'utah-valley',      # Should be WAC
]

print("\nUser-reported teams that were showing as 'Ind':")
print("=" * 80)

for slug in test_teams:
    try:
        team = Team.objects.get(slug=slug)
        
        # Get a team season rating for this team (if exists)
        try:
            rating = TeamSeasonRatings.objects.filter(team=team, season__year=2026).first()
            
            if rating:
                # Simulate serializer
                serializer = RankingsSerializer(rating)
                conf = serializer.data.get('conference', 'Unknown')
                
                print(f"\n{team.name} (slug: {slug}):")
                print(f"  Conference: {conf}")
                print(f"  ✓ Fixed!" if conf != 'Ind' else "  ✗ Still showing as Independent")
            else:
                print(f"\n{team.name} (slug: {slug}):")
                print(f"  No 2026 season data available")
                
        except Exception as e:
            print(f"\n{team.name} (slug: {slug}):")
            print(f"  Error getting rating: {e}")
            
    except Team.DoesNotExist:
        print(f"\n✗ Team not found: {slug}")

print("\n" + "=" * 80)
print("Testing other conferences to ensure no regression:")
print("=" * 80)

# Test a few teams from different conferences
other_tests = {
    'michigan': 'B10',
    'duke': 'ACC',
    'kansas': 'B12',
    'kentucky': 'SEC',
    'gonzaga': 'WCC',
    'grand-canyon': 'WAC',
}

for slug, expected_conf in other_tests.items():
    try:
        team = Team.objects.get(slug=slug)
        rating = TeamSeasonRatings.objects.filter(team=team, season__year=2026).first()
        
        if rating:
            serializer = RankingsSerializer(rating)
            conf = serializer.data.get('conference', 'Unknown')
            status = "✓" if conf == expected_conf else "✗"
            print(f"{status} {team.name:25} → {conf:5} (expected: {expected_conf})")
        else:
            print(f"- {team.name:25} → No 2026 data")
            
    except Team.DoesNotExist:
        print(f"✗ {slug:25} → Team not found in database")

print("\n" + "=" * 80)
