import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from core.models import Team, Conference

# Get all conferences
conferences = Conference.objects.all().order_by('code')
print(f"\nFound {conferences.count()} conferences in database")
print("=" * 80)

# Read the mapping from serializers
from api.serializers import RankingsSerializer

# Test sample teams from each conference
test_cases = {
    'A10': ['saint-louis', 'dayton', 'vcu'],
    'ACC': ['duke', 'north-carolina', 'virginia'],
    'AE': ['vermont', 'bryant'],
    'ASun': ['liberty', 'lipscomb'],
    'Amer': ['memphis', 'temple', 'wichita-state'],
    'B10': ['michigan', 'ohio-state', 'purdue'],
    'B12': ['kansas', 'baylor', 'texas'],
    'BE': ['connecticut', 'villanova', 'marquette'],
    'BSky': ['montana', 'weber-state'],
    'BSth': ['high-point', 'winthrop'],
    'BW': ['hawaii', 'uc-irvine', 'uc-santa-barbara'],
    'CAA': ['charleston', 'hofstra'],
    'CUSA': ['louisiana-tech', 'western-kentucky'],
    'Horz': ['wright-state', 'northern-kentucky'],
    'Ivy': ['princeton', 'yale', 'harvard'],
    'MAAC': ['iona', 'marist'],
    'MAC': ['toledo', 'akron'],
    'MEAC': ['norfolk-state', 'howard'],
    'MVC': ['illinois-chicago', 'illinois-state', 'drake'],
    'MWC': ['utah-state', 'san-diego-state'],
    'NEC': ['merrimack', 'central-connecticut'],
    'OVC': ['morehead-state', 'tennessee-state'],
    'Pat': ['colgate', 'army', 'navy'],
    'SB': ['james-madison', 'coastal-carolina'],
    'SC': ['furman', 'wofford'],
    'SEC': ['kentucky', 'florida', 'tennessee'],
    'SWAC': ['alabama-state', 'jackson-state'],
    'Slnd': ['mcneese-state', 'nicholls-state'],
    'Sum': ['south-dakota-state', 'north-dakota-state', 'oral-roberts'],
    'WAC': ['grand-canyon', 'utah-valley', 'seattle-u'],
    'WCC': ['gonzaga', 'saint-marys', 'san-francisco'],
}

# Create a mock team object for testing
class MockTeam:
    def __init__(self, slug):
        self.slug = slug

print("\nTesting conference mappings:")
print("=" * 80)

missing_mappings = []
for conf_code, team_slugs in sorted(test_cases.items()):
    print(f"\n{conf_code} ({conferences.get(code=conf_code).name}):")
    for slug in team_slugs:
        # Simulate what serializer does
        mock_team = MockTeam(slug)
        # Get conference from serializer logic
        from api.serializers import RankingsSerializer
        
        # Manually check the conf_map (simplified version)
        conf_map = {
            # BW
            'hawaii': 'BW', 'uc-irvine': 'BW', 'uc-santa-barbara': 'BW',
            # MVC
            'illinois-chicago': 'MVC', 'illinois-state': 'MVC', 'drake': 'MVC',
            # WAC
            'grand-canyon': 'WAC', 'utah-valley': 'WAC', 'seattle-u': 'WAC',
            # Sum
            'south-dakota-state': 'Sum', 'north-dakota-state': 'Sum', 'oral-roberts': 'Sum',
            # etc...
        }
        
        # Try to get team from database
        try:
            db_team = Team.objects.get(slug=slug)
            status = "✓ In DB"
        except Team.DoesNotExist:
            status = "✗ NOT IN DB"
        
        print(f"  {slug:30} {status}")

print("\n" + "=" * 80)
print("Test complete!")
