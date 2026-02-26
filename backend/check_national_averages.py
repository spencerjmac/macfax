"""Check if NationalAverages data exists"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import NationalAverages, Season

season = Season.objects.filter(is_current=True).first()
print(f'Current Season: {season}')

if not season:
    print('ERROR: No current season found!')
    sys.exit(1)

na = NationalAverages.objects.filter(season=season).first()
if na:
    print(f'\n✓ National Averages exist for {season}:')
    print(f'  avg_ortg: {na.avg_ortg:.2f}')
    print(f'  avg_pace: {na.avg_pace:.2f}')
    print(f'  avg_efg: {na.avg_efg:.3f}')
    print(f'  avg_tov: {na.avg_tov:.3f}')
    print(f'  avg_orb: {na.avg_orb:.3f}')
    print(f'  avg_ftr: {na.avg_ftr:.3f}')
    print(f'  total_games: {na.total_games}')
else:
    print(f'\n✗ No NationalAverages found for {season}!')
    print('  Need to compute national averages first.')
