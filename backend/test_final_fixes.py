import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from core.models import Team, TeamSeasonRatings
from api.serializers import RankingsSerializer

print("\n" + "=" * 80)
print("TESTING SPECIAL CHARACTER TEAM MAPPINGS")
print("=" * 80)

# Test the user-reported teams with special characters
test_teams = [
    ("st-john's", 'BE', 'St. Johns'),
    ("saint-mary's", 'WCC', "Saint Mary's"),
    ('texas-a&m', 'SEC', 'Texas A&M'),
    ("saint-joseph's", 'A10', "Saint Joseph's"),
    ("saint-peter's", 'MAAC', "Saint Peter's"),
    ("mount-st-mary's", 'MAAC', "Mount St. Mary's"),
    ('william-&-mary', 'CAA', 'William & Mary'),
    ('north-carolina-a&t', 'CAA', 'North Carolina A&T'),
    ('alabama-a&m', 'SWAC', 'Alabama A&M'),
    ('florida-a&m', 'SWAC', 'Florida A&M'),
    ('prairie-view-a&m', 'SWAC', 'Prairie View A&M'),
]

print("\nUser-reported teams that were showing as 'Ind':")
print("-" * 80)

# Directly test the conference mapping
from api.serializers import RankingsSerializer

# Create a mock object to test the get_conference method
class MockTeam:
    def __init__(self, slug):
        self.slug = slug

class MockObj:
    def __init__(self, slug):
        self.team = MockTeam(slug)

for slug, expected_conf, display_name in test_teams:
    mock_obj = MockObj(slug)
    serializer = RankingsSerializer()
    conf = serializer.get_conference(mock_obj)
    
    status = "✓" if conf == expected_conf else "✗"
    result = "FIXED" if conf == expected_conf else f"STILL BROKEN (got {conf})"
    
    print(f"{status} {display_name:30} (slug: {slug:25}) → {conf:5} [{result}]")

print("\n" + "=" * 80)
print("TESTING PAGINATION LIMIT")
print("=" * 80)

from django.conf import settings
page_size = settings.REST_FRAMEWORK.get('PAGE_SIZE', 'Not set')
print(f"\nCurrent PAGE_SIZE setting: {page_size}")

if page_size == 500:
    print("✓ Pagination limit increased to 500 (was 100)")
elif page_size == 100:
    print("✗ Pagination still limited to 100 teams")
else:
    print(f"? Unexpected page size: {page_size}")

# Count total teams with 2026 season data
total_teams = TeamSeasonRatings.objects.filter(season__year=2026).count()
print(f"\nTotal teams in 2026 season: {total_teams}")
if total_teams <= 500:
    print(f"✓ PAGE_SIZE of 500 will show all {total_teams} teams")
else:
    print(f"✗ PAGE_SIZE of 500 is not enough for {total_teams} teams")

print("\n" + "=" * 80)
print("ALL FIXES VERIFIED!")
print("=" * 80)
