import sys
sys.path.append('.')
import django
django.setup()
from django.test import Client
c = Client()
r = c.get('/api/viz/crystal-ball?season=2024')
data = r.json()
print([i['key'] for i in data['teams'][0]['checklist']['items']])
