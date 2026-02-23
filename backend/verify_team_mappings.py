"""
Verify team mappings for problematic teams
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, Game, TeamSeasonMetrics, TeamSeasonRatings, Season

# Teams to check
teams_to_check = [
    ('Michigan', 'Michigan State'),
    ('Boston College', 'Boston University'),
    ('Mississippi', 'Mississippi Valley St.'),
]

season = Season.objects.get(year=2026)

print("=" * 80)
print("VERIFICATION OF PROBLEMATIC TEAM MAPPINGS")
print("=" * 80)

for team1_name, team2_name in teams_to_check:
    print(f"\n{'='*80}")
    print(f"Checking: {team1_name} vs {team2_name}")
    print(f"{'='*80}")
    
    for team_name in [team1_name, team2_name]:
        try:
            team = Team.objects.get(name=team_name)
            
            # Count games
            home_games = Game.objects.filter(home_team=team, season_year=2026).count()
            away_games = Game.objects.filter(away_team=team, season_year=2026).count()
            total_games = home_games + away_games
            
            # Get metrics
            metrics = TeamSeasonMetrics.objects.filter(team=team, season=season).first()
            
            # Get ratings
            ratings = TeamSeasonRatings.objects.filter(team=team, season=season).first()
            
            print(f"\n{team_name}:")
            print(f"  Games: {total_games} ({home_games} home, {away_games} away)")
            
            if metrics:
                print(f"  Games in metrics: {metrics.games}")
                print(f"  PPG: {metrics.ppg:.1f}")
            else:
                print(f"  Metrics: NOT FOUND")
            
            if ratings:
                print(f"  AdjEM: {ratings.adj_em:+.2f}")
                if ratings.rank_adj_em:
                    print(f"  Rank: #{ratings.rank_adj_em}")
            else:
                print(f"  Ratings: NOT FOUND")
                
            # Sample games
            recent_games = Game.objects.filter(
                season_year=2026
            ).filter(
                home_team=team
            ) | Game.objects.filter(
                season_year=2026,
                away_team=team
            )
            recent_games = recent_games.order_by('-game_date')[:3]
            
            if recent_games:
                print(f"  Recent games:")
                for game in recent_games:
                    if game.home_team == team:
                        print(f"    vs {game.away_team.name} (home)")
                    else:
                        print(f"    @ {game.home_team.name} (away)")
        
        except Team.DoesNotExist:
            print(f"\n{team_name}: DOES NOT EXIST IN DATABASE")

print("\n" + "=" * 80)
print("VERIFICATION COMPLETE")
print("=" * 80)
