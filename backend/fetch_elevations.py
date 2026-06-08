import os
import sys
import time
import requests
import json
from collections import Counter

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from nba.models import NBATeam, NBAGame
from ncaa.models.teams import Team
from ncaa.models.games import Game

# Cache for Geocoding to avoid hitting API repeatedly for same locations
GEO_CACHE = {}

def get_elevation_for_location(query: str):
    """Gets elevation in feet for a given text query (City, State or Arena)"""
    if query in GEO_CACHE:
        return GEO_CACHE[query]
        
    try:
        # 1. Geocoding
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={requests.utils.quote(query)}&count=1&language=en&format=json"
        geo_res = requests.get(geo_url, timeout=10)
        geo_data = geo_res.json()
        
        if not geo_data.get('results'):
            # Fallback: maybe strip some words
            return None
            
        lat = geo_data['results'][0]['latitude']
        lon = geo_data['results'][0]['longitude']
        
        # 2. Elevation
        elev_url = f"https://api.open-meteo.com/v1/elevation?latitude={lat}&longitude={lon}"
        elev_res = requests.get(elev_url, timeout=10)
        elev_data = elev_res.json()
        
        if not elev_data.get('elevation'):
            return None
            
        elevation_meters = elev_data['elevation'][0]
        elevation_feet = int(elevation_meters * 3.28084)
        
        GEO_CACHE[query] = elevation_feet
        time.sleep(0.5) # rate limit prevention
        return elevation_feet
        
    except Exception as e:
        print(f"Error fetching {query}: {e}")
        return None


def populate_nba():
    print("--- Populating NBA Elevations ---")
    teams = NBATeam.objects.all()
    
    for team in teams:
        if team.elevation is not None:
            continue
        query = f"{team.city} NBA"
        elev = get_elevation_for_location(query)
        if elev is None:
            query = team.city
            elev = get_elevation_for_location(query)
            
        if elev is not None:
            team.elevation = elev
            team.save(update_fields=['elevation'])
            print(f"NBA: {team.name} -> {elev} ft")
            
    # Games
    games = NBAGame.objects.all()
    count = 0
    for g in games:
        # Home game uses home team elevation
        if g.home_team.elevation is not None:
            g.elevation = g.home_team.elevation
            g.save(update_fields=['elevation'])
            count += 1
    print(f"Updated {count} NBA Games")


def populate_ncaa():
    print("--- Populating NCAA Elevations ---")
    teams = Team.objects.filter(is_d1=True)
    
    for team in teams:
        if team.elevation is not None:
            continue
        # Find home city from games (just grab the first valid one to be fast)
        home_game = Game.objects.filter(
            home_team=team, 
            neutral_site=False, 
            venue_city__isnull=False, 
            venue_state__isnull=False
        ).exclude(venue_city='').exclude(venue_state='').first()
        
        if not home_game:
            continue
            
        most_common_city = f"{home_game.venue_city}, {home_game.venue_state}"
        print(f"Processing {team.name} ({most_common_city})...")
        elev = get_elevation_for_location(most_common_city)
        if elev is not None:
            team.elevation = elev
            team.save(update_fields=['elevation'])
            print(f"NCAA: {team.name} ({most_common_city}) -> {elev} ft")
            
    # Games
    # For performance, use bulk updates or at least transaction
    from django.db import transaction
    
    with transaction.atomic():
        games = Game.objects.all()
        count = 0
        for g in games:
            if not g.neutral_site and g.home_team.elevation is not None:
                g.elevation = g.home_team.elevation
                g.save(update_fields=['elevation'])
                count += 1
            elif g.neutral_site and g.venue_city and g.venue_state:
                query = f"{g.venue_city}, {g.venue_state}"
                elev = get_elevation_for_location(query)
                if elev is not None:
                    g.elevation = elev
                    g.save(update_fields=['elevation'])
                    count += 1
                    
    print(f"Updated {count} NCAA Games")

if __name__ == "__main__":
    populate_nba()
    populate_ncaa()
    print("Done!")
