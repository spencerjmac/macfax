"""
Management command: compute_sor
Computes SOR (Strength of Record) ranks for all teams in a season

SOR Definition:
  For each team, compute the probability that a baseline team (#20-30 AdjEM)
  would achieve >= W_actual wins given the same schedule.
  Lower probability = better SOR rank (harder schedule + better results)

Usage:
    python manage.py compute_sor --season 2026
"""

import logging
import numpy as np
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Season, TeamSeasonRatings, TeamGameStats, NationalAverages
from api.matchup_engine import forecast_game

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Compute SOR (Strength of Record) ranks for all teams'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            required=True,
            help='Season year (e.g., 2026)'
        )
        parser.add_argument(
            '--trials',
            type=int,
            default=10000,
            help='Number of Monte Carlo trials (default: 10000)'
        )
    
    def handle(self, *args, **options):
        season_year = options['season']
        num_trials = options['trials']
        
        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            self.stderr.write(f"❌ Season {season_year} not found")
            return
        
        self.stdout.write(f"\n{'='*80}")
        self.stdout.write(f"Computing SOR for {season.display_name}")
        self.stdout.write(f"  Monte Carlo trials: {num_trials:,}")
        self.stdout.write(f"{'='*80}\n")
        
        # Get national averages
        nat_avg = NationalAverages.objects.filter(season=season).first()
        if not nat_avg:
            self.stderr.write(f"❌ National averages not found for {season_year}")
            return
        
        nat_avg_ortg = nat_avg.avg_ortg or 108.0
        hca_points = nat_avg.hca_points if nat_avg.hca_points is not None else 1.85
        sigma = nat_avg.prediction_sigma if nat_avg.prediction_sigma is not None else 11.08

        self.stdout.write(f"📊 National Context:")
        self.stdout.write(f"  • Avg ORtg: {nat_avg_ortg:.2f}")
        self.stdout.write(f"  • HCA: {hca_points:.2f} pts")
        self.stdout.write(f"  • Sigma: {sigma:.2f}\n")
        
        # Get all teams with ratings (sorted by AdjEM rank)
        all_teams = list(TeamSeasonRatings.objects.filter(
            season=season
        ).select_related('team').order_by('rank_adj_em'))
        
        total_teams = len(all_teams)
        if total_teams == 0:
            self.stderr.write(f"❌ No teams found for {season_year}")
            return
        
        # Calculate baseline team (avg of ranks #20-30)
        baseline_teams = [t for t in all_teams if 20 <= (t.rank_adj_em or 999) <= 30]
        if len(baseline_teams) < 5:
            # Fallback to #15-35 if not enough teams in #20-30
            baseline_teams = [t for t in all_teams if 15 <= (t.rank_adj_em or 999) <= 35]
        
        if not baseline_teams:
            self.stderr.write(f"❌ Cannot compute baseline team (ranks #20-30 not found)")
            return
        
        baseline_adj_em = np.mean([t.adj_em for t in baseline_teams])
        baseline_adj_o = np.mean([t.adj_o for t in baseline_teams])
        baseline_adj_d = np.mean([t.adj_d for t in baseline_teams])
        baseline_adj_tempo = np.mean([t.adj_tempo for t in baseline_teams])
        
        self.stdout.write(f"📏 Baseline Team (ranks #{baseline_teams[0].rank_adj_em}-#{baseline_teams[-1].rank_adj_em}):")
        self.stdout.write(f"  • Avg AdjEM: {baseline_adj_em:.2f}")
        self.stdout.write(f"  • Avg AdjO: {baseline_adj_o:.2f}")
        self.stdout.write(f"  • Avg AdjD: {baseline_adj_d:.2f}\n")
        
        # Create baseline ratings object (for forecast_game)
        baseline_ratings = type('BaselineRatings', (), {
            'adj_o': baseline_adj_o,
            'adj_d': baseline_adj_d,
            'adj_em': baseline_adj_em,
            'adj_tempo': baseline_adj_tempo
        })()
        
        # Compute SOR probability for each team
        self.stdout.write(f"Computing SOR for {total_teams} teams...")
        sor_results = []
        teams_updated = 0
        teams_skipped = 0
        
        with transaction.atomic():
            for i, team_rating in enumerate(all_teams, 1):
                team = team_rating.team
                
                # Get team's completed games
                team_games = TeamGameStats.objects.filter(
                    team=team,
                    game__season_year=season_year,
                    game__status='final'
                ).select_related('game', 'opponent')
                
                games_count = team_games.count()
                if games_count == 0:
                    teams_skipped += 1
                    continue
                
                # Count actual wins - be careful with None checks
                actual_wins = 0
                for g in team_games:
                    opp_stat = g.game.team_stats.exclude(team=team).first()
                    if opp_stat and g.pts > opp_stat.pts:
                        actual_wins += 1
                
                # Compute win probability for baseline team in each game
                win_probs = []
                for game_stat in team_games:
                    # Get opponent ratings
                    try:
                        opp_ratings = TeamSeasonRatings.objects.get(
                            team=game_stat.opponent,
                            season=season
                        )
                    except TeamSeasonRatings.DoesNotExist:
                        # Skip game if opponent has no ratings
                        continue
                    
                    # Forecast game with baseline team vs opponent
                    # Location from baseline team's perspective (inverse of actual team's location)
                    if game_stat.home_away == 'H':
                        location = 'HOME'
                    elif game_stat.home_away == 'A':
                        location = 'AWAY'
                    else:
                        location = 'NEUTRAL'
                    
                    result = forecast_game(
                        adj_o_a=baseline_adj_o,
                        adj_d_a=baseline_adj_d,
                        adj_em_a=baseline_adj_em,
                        tempo_a=baseline_ratings.adj_tempo,
                        adj_o_b=opp_ratings.adj_o,
                        adj_d_b=opp_ratings.adj_d,
                        adj_em_b=opp_ratings.adj_em,
                        tempo_b=opp_ratings.adj_tempo,
                        nat_avg_ortg=nat_avg_ortg,
                        hca_points=hca_points,
                        sigma=sigma,
                        site=location
                    )
                    
                    win_probs.append(result['prob_a'])
                
                if len(win_probs) == 0:
                    teams_skipped += 1
                    continue
                
                # Monte Carlo simulation: how often does baseline team get >= actual_wins?
                wins_array = np.array(win_probs)
                simulated_wins = np.random.binomial(1, wins_array, size=(num_trials, len(wins_array)))
                total_wins_per_trial = simulated_wins.sum(axis=1)
                
                # Probability that baseline gets >= actual_wins
                sor_probability = (total_wins_per_trial >= actual_wins).mean()
                
                sor_results.append({
                    'team': team.name,
                    'actual_wins': actual_wins,
                    'games': len(win_probs),
                    'sor_prob': sor_probability
                })
                
                teams_updated += 1
                
                # Progress indicator
                if i % 50 == 0:
                    self.stdout.write(f"  Processed {i}/{total_teams} teams...")
        
        self.stdout.write(f"\n{'='*80}")
        self.stdout.write(f"✅ SOR Probability Computation Complete")
        self.stdout.write(f"{'='*80}")
        self.stdout.write(f"  • Teams processed: {teams_updated}")
        self.stdout.write(f"  • Teams skipped: {teams_skipped}\n")
        
        # Rank teams by SOR probability (lower = better)
        sor_results.sort(key=lambda x: x['sor_prob'])
        
        # Assign ranks and save
        self.stdout.write(f"📊 Computing SOR ranks...")
        with transaction.atomic():
            for rank, result in enumerate(sor_results, 1):
                team_name = result['team']
                team_rating = TeamSeasonRatings.objects.get(team__name=team_name, season=season)
                team_rating.sor_rank = rank
                team_rating.save(update_fields=['sor_rank'])
        
        # Show top 10 and bottom 10
        self.stdout.write(f"\n📈 TOP 10 SOR (Best Resumes):")
        for i, result in enumerate(sor_results[:10], 1):
            self.stdout.write(
                f"  {i:2d}. {result['team']:<30} "
                f"W={result['actual_wins']:2d}/{result['games']:2d}  "
                f"P(baseline >= {result['actual_wins']}) = {result['sor_prob']:.4f}"
            )
        
        self.stdout.write(f"\n📉 BOTTOM 10 SOR (Worst Resumes):")
        for i, result in enumerate(sor_results[-10:], 1):
            idx = len(sor_results) - 10 + i
            self.stdout.write(
                f"  {idx:2d}. {result['team']:<30} "
                f"W={result['actual_wins']:2d}/{result['games']:2d}  "
                f"P(baseline >= {result['actual_wins']}) = {result['sor_prob']:.4f}"
            )
        
        self.stdout.write(f"\n{'='*80}\n")
