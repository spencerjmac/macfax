import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, TeamSeasonRatings

# Check the updated records
teams_to_check = ['New Mexico', 'Saint Louis']

print("\n" + "="*70)
print("UPDATED TEAM RECORDS (with non-D1 games included)")
print("="*70)

for team_name in teams_to_check:
    team = Team.objects.get(name=team_name)
    ratings = TeamSeasonRatings.objects.filter(team=team, season__year=2026).first()
    
    if ratings:
        print(f"\n{team_name}:")
        print(f"  Total Record (all games): {ratings.wins}-{ratings.losses} ({ratings.games_played} games)")
        print(f"  D1 games only: {ratings.d1_games_played} games")
        print(f"  Adj EM: {ratings.adj_em:+.2f}")
    else:
        print(f"\n{team_name}: No ratings found")

print("\n" + "="*70)
