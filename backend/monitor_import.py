import os
import django
import time
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Game, TeamGameStats

print('Monitoring game import progress...\n')

last_count = 0
while True:
    current_count = Game.objects.filter(season_year=2026).count()
    tgs_count = TeamGameStats.objects.filter(game__season_year=2026).count()
    
    # Get most recent game date
    recent = Game.objects.filter(season_year=2026).order_by('-game_date').first()
    recent_date = recent.game_date if recent else None
    
    progress = f"Games: {current_count:4d} | TeamGameStats: {tgs_count:5d}"
    if recent_date:
        progress += f" | Latest: {recent_date}"
    
    # Check if import is still progressing
    if current_count == last_count and current_count > 0:
        print(f"\n{datetime.now().strftime('%H:%M:%S')} - Import appears complete!")
        print(f"Final count: {current_count} games, {tgs_count} team stats")
        print(f"Most recent game: {recent_date}")
        break
    
    if current_count > last_count:
        print(f"{datetime.now().strftime('%H:%M:%S')} - {progress}")
        last_count = current_count
    
    time.sleep(10)  # Check every 10 seconds
