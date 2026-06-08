import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from nba.models import NBATeam, NBAGame
from ncaa.models.teams import Team
from ncaa.models.games import Game
from django.db import transaction

print("Starting mock elevation script...")

# NBA
nba_elevations = {'Denver Nuggets': 5280, 'Utah Jazz': 4226, 'Phoenix Suns': 1086}
NBATeam.objects.all().update(elevation=0)
for name, elev in nba_elevations.items():
    NBATeam.objects.filter(name=name).update(elevation=elev)

# Quick way to update NBA Games
for team in NBATeam.objects.all():
    NBAGame.objects.filter(home_team=team).update(elevation=team.elevation)

# NCAA
ncaa_elevations = {
    'Wyoming': 7220, 'Air Force': 7258, 'Colorado': 5300, 'Colorado State': 5000,
    'Utah': 4600, 'BYU': 4600, 'Utah State': 4700, 'New Mexico': 5100, 
    'Nevada': 4500, 'Denver': 5280, 'Northern Arizona': 6800, 'Montana State': 4800
}
Team.objects.all().update(elevation=0)
for name, elev in ncaa_elevations.items():
    Team.objects.filter(name=name).update(elevation=elev)

# Fast update for NCAA games
for team in Team.objects.all():
    Game.objects.filter(home_team=team, neutral_site=False).update(elevation=team.elevation)

Game.objects.filter(neutral_site=True).update(elevation=0)

print('Mock Elevation data populated successfully.')
