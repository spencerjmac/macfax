import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, TeamSeasonStats, Season
from collections import defaultdict

# Try to get conference data from ANY available season
try:
    # Get the most recent season with data
    latest_season = Season.objects.filter(
        team_stats__isnull=False
    ).order_by('-year').first()
    
    if latest_season:
        print(f"Using conference data from {latest_season.display_name}")
        print()
        
        # Get all teams with their conference from that season
        teams_with_conf = TeamSeasonStats.objects.filter(
            season=latest_season
        ).select_related('team', 'conference')
        
        # Group teams by conference
        teams_by_conf = defaultdict(list)
        teams_found = set()
        
        for stat in teams_with_conf:
            conf_name = stat.conference.name if stat.conference else "Independent"
            teams_by_conf[conf_name].append(stat.team.name)
            teams_found.add(stat.team.id)
        
        # Get teams that don't have conference data
        teams_without_conf = Team.objects.exclude(id__in=teams_found)
        if teams_without_conf.exists():
            no_conf_teams = [team.name for team in teams_without_conf]
            teams_by_conf["No Conference Data"] = sorted(no_conf_teams)
        
        # Sort conferences and teams within each conference
        sorted_conferences = sorted(teams_by_conf.keys())
        
        print("ALL 365 D1 TEAMS IN DATABASE (Sorted by Conference):")
        print("=" * 60)
        print()
        
        team_number = 1
        for conf in sorted_conferences:
            conf_teams = sorted(teams_by_conf[conf])
            print(f"\n{conf} ({len(conf_teams)} teams)")
            print("-" * 60)
            for team_name in conf_teams:
                print(f"{team_number:3d}. {team_name}")
                team_number += 1
        
        print()
        print("=" * 60)
        print(f"Total: {Team.objects.count()} teams")
        print(f"Conferences: {len(sorted_conferences)}")
    else:
        raise Exception("No season data found")
        
except Exception as e:
    # Fallback to alphabetical if no conference data available
    print(f"No conference data available, listing alphabetically")
    print()
    teams = Team.objects.all().order_by('name')
    
    print("ALL 365 D1 TEAMS IN DATABASE:")
    print("=" * 60)
    print()
    
    for i, team in enumerate(teams, 1):
        print(f"{i:3d}. {team.name}")
    
    print()
    print("=" * 60)
    print(f"Total: {teams.count()} teams")
