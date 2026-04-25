import os
import sys
import time
import django
from django.test import RequestFactory

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from nba.views import NBALeaguePlayersView, NBARankingsViewSet

factory = RequestFactory()

t0 = time.time()
req = factory.get('/api/nba/rankings/')
view = NBARankingsViewSet.as_view({'get': 'list'})
resp = view(req)
print(f"Rankings status: {resp.status_code}, time: {time.time() - t0:.3f}s, size: {len(str(resp.data))} chars")

t0 = time.time()
req = factory.get('/api/nba/players/')
view = NBALeaguePlayersView.as_view()
resp = view(req)
print(f"Players status: {resp.status_code}, time: {time.time() - t0:.3f}s, size: {len(str(resp.data))} chars")
