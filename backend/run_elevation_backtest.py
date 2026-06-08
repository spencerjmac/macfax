import os, django
import pandas as pd
import numpy as np

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from ncaa.models.games import Game
from ncaa.models.teams import TeamSeasonRatings
from django.db.models import F

def run_backtest():
    print("--- Phase 3: Model Backtesting (NCAA) ---")
    # Fetch all games from 2024 to 2026
    games = Game.objects.filter(
        status='final',
        neutral_site=False,
        season_year__in=[2024, 2025, 2026]
    ).select_related('home_team', 'away_team')
    
    baseline_correct = 0
    elev_correct = 0
    total = 0
    
    baseline_brier = 0.0
    elev_brier = 0.0
    
    baseline_logloss = 0.0
    elev_logloss = 0.0
    
    ELEV_COEF = 0.2055 # Points per 1k feet
    
    print(f"Testing {games.count()} games...")
    
    for g in games:
        if g.home_score is None or g.away_score is None:
            continue
            
        home_rating = TeamSeasonRatings.objects.filter(team=g.home_team, season__year=g.season_year, is_pre_tournament=False).first()
        away_rating = TeamSeasonRatings.objects.filter(team=g.away_team, season__year=g.season_year, is_pre_tournament=False).first()
        
        if not home_rating or not away_rating or not home_rating.adj_em or not away_rating.adj_em:
            continue
            
        margin = g.home_score - g.away_score
        home_win = 1 if margin > 0 else 0
        
        # Base expected margin (Baseline Model)
        # HCA is approx 3.0 points based on our OLS
        base_exp_margin = (home_rating.adj_em - away_rating.adj_em) + 2.97
        
        # Elev Expected Margin (New Model)
        elev_diff_1k = max(0, (g.elevation or 0) - (g.away_team.elevation or 0)) / 1000.0
        elev_exp_margin = base_exp_margin + (ELEV_COEF * elev_diff_1k)
        
        # Win Probabilities (using simple sigmoid approximation for basketball margins)
        # Prob = 1 / (1 + exp(-margin / 10.5)) -> 10.5 is standard scale factor for hoops
        scale = 10.5
        base_prob = 1.0 / (1.0 + np.exp(-base_exp_margin / scale))
        elev_prob = 1.0 / (1.0 + np.exp(-elev_exp_margin / scale))
        
        # Accuracy
        if (base_exp_margin > 0 and home_win) or (base_exp_margin < 0 and not home_win):
            baseline_correct += 1
        if (elev_exp_margin > 0 and home_win) or (elev_exp_margin < 0 and not home_win):
            elev_correct += 1
            
        # Brier Score (lower is better: sum of squared errors)
        baseline_brier += (base_prob - home_win) ** 2
        elev_brier += (elev_prob - home_win) ** 2
        
        # Log loss (lower is better)
        # clip to avoid log(0)
        eps = 1e-15
        bp = max(eps, min(1-eps, base_prob))
        ep = max(eps, min(1-eps, elev_prob))
        
        baseline_logloss += - (home_win * np.log(bp) + (1 - home_win) * np.log(1 - bp))
        elev_logloss += - (home_win * np.log(ep) + (1 - home_win) * np.log(1 - ep))
        
        total += 1
        
    print("\nRESULTS (Sample size: {} games)".format(total))
    print("--------------------------------------------------")
    print("Baseline Model:")
    print(f"  Accuracy:    {(baseline_correct / total) * 100:.2f}%")
    print(f"  Brier Score: {baseline_brier / total:.4f}")
    print(f"  Log-Loss:    {baseline_logloss / total:.4f}")
    print("\nElevation-Adjusted Model:")
    print(f"  Accuracy:    {(elev_correct / total) * 100:.2f}%")
    print(f"  Brier Score: {elev_brier / total:.4f}")
    print(f"  Log-Loss:    {elev_logloss / total:.4f}")
    print("--------------------------------------------------")
    
    if elev_logloss < baseline_logloss:
        print("CONCLUSION: Elevation Model performs BETTER than baseline!")
    else:
        print("CONCLUSION: Elevation Model performs WORSE than baseline.")

if __name__ == "__main__":
    run_backtest()
