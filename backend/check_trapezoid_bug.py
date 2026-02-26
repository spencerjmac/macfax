"""
Diagnostic script to investigate trapezoid tooltip bug.
Checks Louisville and Arizona's coordinates vs trapezoid boundaries.
"""

import os
import sys
import django
import numpy as np

# Add the backend directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Season, TeamSeasonRatings
from api.trapezoid_views import compute_trapezoid_boundaries, is_inside_trapezoid

# Get current season
season = Season.objects.filter(year=2026).first()
if not season:
    print("❌ No season 2026 found")
    sys.exit(1)

print(f"\n{'='*80}")
print(f"Trapezoid Bug Investigation - Season {season.year}")
print(f"{'='*80}\n")

# Get ALL teams to compute trapezoid boundaries
all_teams = TeamSeasonRatings.objects.filter(season=season)
all_tempo_values = np.array([t.adj_tempo for t in all_teams])
all_em_values = np.array([t.adj_em for t in all_teams])

# Compute trapezoid boundaries
trapezoid = compute_trapezoid_boundaries(all_tempo_values, all_em_values)

print("TRAPEZOID BOUNDARIES:")
print(f"{'  x_left_top:':<20} {trapezoid['x_left_top']:.2f}")
print(f"{'  x_right_top:':<20} {trapezoid['x_right_top']:.2f}")
print(f"{'  x_left_bot:':<20} {trapezoid['x_left_bot']:.2f}")
print(f"{'  x_right_bot:':<20} {trapezoid['x_right_bot']:.2f}")
print(f"{'  y_top:':<20} {trapezoid['y_top']:.2f}")
print(f"{'  y_bot:':<20} {trapezoid['y_bot']:.2f}")
print()

# Get Louisville, Arizona, Michigan, and Gonzaga
test_teams = ['Louisville', 'Arizona', 'Michigan', 'Gonzaga']

for team_name in test_teams:
    try:
        # Special handling for Michigan to avoid Central/Eastern/Western Michigan
        if team_name == 'Michigan':
            rating = TeamSeasonRatings.objects.filter(
                season=season,
                team__name='Michigan'
            ).first()
        else:
            rating = TeamSeasonRatings.objects.filter(
                season=season,
                team__name__icontains=team_name
            ).first()
        
        if not rating:
            print(f"❌ {team_name} not found")
            continue
        
        print(f"\n{'='*80}")
        print(f"{rating.team.name.upper()}")
        print(f"{'='*80}")
        
        tempo = rating.adj_tempo
        em = rating.adj_em
        inside = is_inside_trapezoid(tempo, em, trapezoid)
        
        print(f"{'  Adj Tempo (x):':<25} {tempo:.2f}")
        print(f"{'  Adj EM (y):':<25} {em:.2f}")
        print(f"{'  Rank:':<25} {rating.rank_adj_em}")
        print(f"{'  Record:':<25} {rating.wins}-{rating.losses}")
        print()
        
        # Determine which region of trapezoid this point is in
        x = tempo
        y = em
        
        # Check basic bounds
        x_in_range = trapezoid['x_left_top'] <= x <= trapezoid['x_right_top']
        y_below_top = y <= trapezoid['y_top']
        
        print(f"BOUNDARY CHECKS:")
        print(f"{'  X in range?':<25} {x_in_range} "
              f"({trapezoid['x_left_top']:.2f} <= {x:.2f} <= {trapezoid['x_right_top']:.2f})")
        print(f"{'  Y below top?':<25} {y_below_top} "
              f"({y:.2f} <= {trapezoid['y_top']:.2f})")
        
        # Calculate bottom boundary at this x position
        if x <= trapezoid['x_left_bot']:
            # Left slant
            if trapezoid['x_left_bot'] == trapezoid['x_left_top']:
                y_min = trapezoid['y_bot']
            else:
                slope = (trapezoid['y_bot'] - trapezoid['y_top']) / (trapezoid['x_left_bot'] - trapezoid['x_left_top'])
                y_min = trapezoid['y_top'] + slope * (x - trapezoid['x_left_top'])
            region = "LEFT SLANT"
        elif x < trapezoid['x_right_bot']:
            # Flat bottom
            y_min = trapezoid['y_bot']
            region = "FLAT BOTTOM"
        else:
            # Right slant: interpolate between (x_right_bot, y_bot) and (x_right_top, y_top)
            if trapezoid['x_right_top'] == trapezoid['x_right_bot']:
                y_min = trapezoid['y_bot']
            else:
                slope = (trapezoid['y_top'] - trapezoid['y_bot']) / (trapezoid['x_right_top'] - trapezoid['x_right_bot'])
                y_min = trapezoid['y_bot'] + slope * (x - trapezoid['x_right_bot'])
            region = "RIGHT SLANT"
        
        y_above_bottom = y >= y_min
        
        print(f"{'  Region:':<25} {region}")
        print(f"{'  Bottom boundary:':<25} y_min = {y_min:.2f}")
        print(f"{'  Y above bottom?':<25} {y_above_bottom} "
              f"({y:.2f} >= {y_min:.2f})")
        print()
        
        print(f"RESULT:")
        print(f"{'  inside_trapezoid:':<25} {inside}")
        
        if inside:
            print(f"  ✅ {rating.team.name} IS inside trapezoid")
        else:
            print(f"  ❌ {rating.team.name} IS NOT inside trapezoid")
            
            # Calculate how far from boundary
            if not y_above_bottom:
                distance = y_min - y
                print(f"  📏 Distance below bottom boundary: {distance:.2f}")
        
    except Exception as e:
        print(f"❌ Error checking {team_name}: {e}")
        import traceback
        traceback.print_exc()

print(f"\n{'='*80}")
print("Investigation complete")
print(f"{'='*80}\n")
