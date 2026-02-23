import os
import django
import time
import subprocess
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Game, TeamGameStats

print('=' * 80)
print('WAITING FOR IMPORT TO COMPLETE, THEN RUNNING COMPUTE COMMANDS')
print('=' * 80)

# Wait for import to finish
print('\n[1/3] Monitoring import progress...\n')
last_count = 0
stable_count = 0

while True:
    current_count = Game.objects.filter(season_year=2026).count()
    recent = Game.objects.filter(season_year=2026).order_by('-game_date').first()
    recent_date = recent.game_date if recent else None
    
    if current_count == last_count and current_count > 0:
        stable_count += 1
        if stable_count >= 3:  # No change for 30 seconds = complete
            print(f"\n{datetime.now().strftime('%H:%M:%S')} - Import complete!")
            print(f"Final count: {current_count} games")
            print(f"Most recent game: {recent_date}")
            break
    else:
        stable_count = 0
        if current_count > last_count:
            print(f"{datetime.now().strftime('%H:%M:%S')} - Games: {current_count:4d} | Latest: {recent_date}")
            last_count = current_count
    
    time.sleep(10)

# Run compute_team_metrics
print('\n' + '=' * 80)
print('[2/3] RUNNING: compute_team_metrics --season 2026')
print('=' * 80 + '\n')

result = subprocess.run(
    [r'.\venv\Scripts\python.exe', 'manage.py', 'compute_team_metrics', '--season', '2026'],
    capture_output=False
)

if result.returncode != 0:
    print(f'\n❌ Error running compute_team_metrics (exit code: {result.returncode})')
    exit(1)

# Run compute_adjusted_four_factors  
print('\n' + '=' * 80)
print('[3/3] RUNNING: compute_adjusted_four_factors --season 2026')
print('=' * 80 + '\n')

result = subprocess.run(
    [r'.\venv\Scripts\python.exe', 'manage.py', 'compute_adjusted_four_factors', '--season', '2026'],
    capture_output=False
)

if result.returncode != 0:
    print(f'\n❌ Error running compute_adjusted_four_factors (exit code: {result.returncode})')
    exit(1)

print('\n' + '=' * 80)
print('✅ ALL COMPLETE!')
print('=' * 80)
print('\nTeam mapping fixes have been successfully applied:')
print('  ✓ Game logs imported with corrected team mappings')
print('  ✓ Team metrics computed')
print('  ✓ Adjusted four factors computed')
print('\nYou can now verify that:')
print('  - Mississippi (Ole Miss) has correct SEC schedule and stats')
print('  - Mississippi Valley St. has correct SWAC schedule')
print('  - Michigan and Michigan State are properly separated')
print('  - Boston College and Boston University are properly separated')
