import os, django
import pandas as pd
import numpy as np
import statsmodels.api as sm

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from nba.models import NBAGame, NBATeamSeasonRatings
from ncaa.models.games import Game
from ncaa.models.teams import TeamSeasonRatings

def analyze_nba():
    print("\n--- NBA Elevation Analysis ---")
    games = NBAGame.objects.filter(
        counts_toward_regular_season=True,
        status='Final',
        elevation__isnull=False
    ).select_related('home_team', 'away_team', 'season')

    data = []
    for g in games:
        if g.home_score is None or g.away_score is None:
            continue
            
        # Get team ratings
        home_rating = NBATeamSeasonRatings.objects.filter(team=g.home_team, season=g.season).first()
        away_rating = NBATeamSeasonRatings.objects.filter(team=g.away_team, season=g.season).first()
        
        if not home_rating or not away_rating or home_rating.adj_net is None or away_rating.adj_net is None:
            continue
            
        margin = g.home_score - g.away_score
        rating_diff = home_rating.adj_net - away_rating.adj_net
        
        # Calculate elevation difference (if away team travels UP to altitude)
        away_team_elev = g.away_team.elevation or 0
        game_elev = g.elevation or 0
        
        # We only care about positive elevation difference (traveling up)
        elev_diff = max(0, game_elev - away_team_elev)
        elev_diff_thousands = elev_diff / 1000.0  # Scale to thousands of feet
        
        # B2B penalties
        home_b2b = 1 if g.home_b2b else 0
        away_b2b = 1 if g.away_b2b else 0
        
        data.append({
            'margin': margin,
            'rating_diff': rating_diff,
            'elev_diff_1k': elev_diff_thousands,
            'home_b2b': home_b2b,
            'away_b2b': away_b2b
        })
        
    df = pd.DataFrame(data)
    if df.empty:
        print("No NBA data found. Did you run the elevation population script?")
        return
        
    print(f"Analyzing {len(df)} NBA games...")
    
    # OLS: margin ~ const + rating_diff + home_b2b + away_b2b + elev_diff
    X = df[['rating_diff', 'home_b2b', 'away_b2b', 'elev_diff_1k']]
    X = sm.add_constant(X)  # const = flat home court advantage
    y = df['margin']
    
    model = sm.OLS(y, X).fit()
    print(model.summary())
    

def analyze_ncaa():
    print("\n--- NCAA Elevation Analysis ---")
    # For NCAA, we use games from the last few seasons
    games = Game.objects.filter(
        status='final',
        neutral_site=False,
        elevation__isnull=False,
        season_year__gte=2020
    ).select_related('home_team', 'away_team')

    data = []
    for g in games:
        if g.home_score is None or g.away_score is None:
            continue
            
        # Get team ratings
        # Use PostTournament ratings if available to avoid pre-tournament filtering issues
        home_rating = TeamSeasonRatings.objects.filter(team=g.home_team, season__year=g.season_year, is_pre_tournament=False).first()
        away_rating = TeamSeasonRatings.objects.filter(team=g.away_team, season__year=g.season_year, is_pre_tournament=False).first()
        
        if not home_rating or not away_rating or not home_rating.adj_em or not away_rating.adj_em:
            continue
            
        margin = g.home_score - g.away_score
        rating_diff = home_rating.adj_em - away_rating.adj_em
        
        away_team_elev = g.away_team.elevation or 0
        game_elev = g.elevation or 0
        
        elev_diff = max(0, game_elev - away_team_elev)
        elev_diff_thousands = elev_diff / 1000.0
        
        data.append({
            'margin': margin,
            'rating_diff': rating_diff,
            'elev_diff_1k': elev_diff_thousands,
        })
        
    df = pd.DataFrame(data)
    if df.empty:
        print("No NCAA data found.")
        return
        
    print(f"Analyzing {len(df)} NCAA games...")
    
    X = df[['rating_diff', 'elev_diff_1k']]
    X = sm.add_constant(X)
    y = df['margin']
    
    model = sm.OLS(y, X).fit()
    print(model.summary())

if __name__ == "__main__":
    analyze_nba()
    analyze_ncaa()
