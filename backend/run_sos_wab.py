import sys
sys.path.append('.')
import django
django.setup()
from django.core.management import call_command
from ncaa.models import Season

seasons = Season.objects.filter(year__gte=2005).exclude(year=2020).order_by('year')
for s in seasons:
    print(f"Running SOS and WAB for {s.year}...")
    try:
        call_command("compute_sos", season=s.year, pre_tournament=True)
    except Exception as e:
        print(f"Failed SOS {s.year}: {e}")
    try:
        call_command("compute_wab", season=s.year, pre_tournament=True)
    except Exception as e:
        print(f"Failed WAB {s.year}: {e}")
print("Done!")
