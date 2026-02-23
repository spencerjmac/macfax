import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, TeamSeasonRatings

# Check a few teams
sample_teams = ['Duke', 'Michigan State', 'Alabama', 'Mississippi', 'Mississippi Valley St.']

print("Sample TeamSeasonRatings data:")
print("=" * 80)

for team_name in sample_teams:
    team = Team.objects.get(name=team_name)
    ratings = TeamSeasonRatings.objects.filter(team=team, season__year=2026).first()
    
    if ratings:
        print(f"\n{team_name}:")
        print(f"  Adj eFG Margin: {ratings.adj_efg_margin:.2f}")
        print(f"  Adj TOV Edge: {ratings.adj_tov_edge:.2f}")
        print(f"  Adj ORB%: {ratings.adj_orb_pct:.2f}")
        print(f"  Adj FTR: {ratings.adj_ftr:.2f}")
        print(f"  Adj EM: {ratings.adj_em:.2f}")
        print(f"  Adj O: {ratings.adj_o:.2f}")
        print(f"  Adj D: {ratings.adj_d:.2f}")
    else:
        print(f"\n{team_name}: NO RATINGS")

# Check if any team has non-zero values
non_zero = TeamSeasonRatings.objects.filter(season__year=2026).exclude(adj_em=0).count()
print(f"\n Teams with non-zero AdjEM: {non_zero}")
