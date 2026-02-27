"""
Management command: compute_game_adjusted_ratings
Computes adjusted offensive/defensive ratings from game log pipeline data

This is the NEW implementation using Game/TeamGameStats models (not old GameLog)

Methodology:
- Model: PPP = baseline + Off(team) - Def(opponent) + HCA + error
- Use ridge regression with possessions as weights
- Solve for team offensive and defensive parameters
- Output: adj_o, adj_d, adj_em, adj_tempo

Usage:
    python manage.py compute_game_adjusted_ratings --season 2026
    python manage.py compute_game_adjusted_ratings --season 2026 --hca 3.5
"""

import logging
import numpy as np
from typing import Dict, List, Tuple
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q, Count, Avg
from django.db import transaction

from core.models import (
    Season, Team, Game, TeamGameStats, TeamSeasonRatings
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Compute adjusted team ratings using regression (new game log pipeline)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            required=True,
            help='Season year (ending year, e.g., 2026)'
        )
        parser.add_argument(
            '--hca',
            type=float,
            default=None,
            help='Fixed home court advantage (pts/100 poss). If not set, will estimate from data.'
        )
        parser.add_argument(
            '--alpha',
            type=float,
            default=1.0,
            help='Ridge regression regularization parameter (default: 1.0)'
        )
    
    def handle(self, *args, **options):
        season_year = options['season']
        fixed_hca = options.get('hca')
        alpha = options['alpha']
        
        # Get season
        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            raise CommandError(f"Season {season_year} not found")
        
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{'='*60}\n"
                f"COMPUTING ADJUSTED RATINGS: {season.display_name}\n"
                f"Fixed HCA: {fixed_hca if fixed_hca else 'Estimate from data'}\n"
                f"Regularization (alpha): {alpha}\n"
                f"{'='*60}\n"
            )
        )
        
        # Get all completed games for this season
        games = Game.objects.filter(
            season_year=season_year,
            status='final'
        ).select_related('home_team', 'away_team')
        
        if not games.exists():
            raise CommandError(f"No completed games found for season {season_year}")
        
        self.stdout.write(f"Found {games.count()} completed games")
        
        # Build game data matrix
        game_data = self._build_game_data(games)
        
        if not game_data:
            raise CommandError("No valid game data found")
        
        self.stdout.write(f"Processed {len(game_data)} game records")
        
        # Get unique teams
        teams = Team.objects.filter(
            Q(home_games__season_year=season_year) | 
            Q(away_games__season_year=season_year)
        ).distinct()
        
        team_list = list(teams)
        team_to_idx = {team.id: idx for idx, team in enumerate(team_list)}
        n_teams = len(team_list)
        
        self.stdout.write(f"Found {n_teams} teams")
        
        # Solve for offensive and defensive ratings
        self.stdout.write("\nSolving regression model...")
        
        off_ratings, def_ratings, baseline, hca_est, tempo_ratings = self._solve_ratings(
            game_data=game_data,
            team_to_idx=team_to_idx,
            n_teams=n_teams,
            fixed_hca=fixed_hca,
            alpha=alpha,
        )
        
        self.stdout.write(
            self.style.SUCCESS(
                f"✓ Model solved\n"
                f"  Baseline PPP: {baseline:.3f}\n"
                f"  HCA estimate: {hca_est:.2f} pts/100\n"
                f"  Off rating range: [{off_ratings.min():.3f}, {off_ratings.max():.3f}]\n"
                f"  Def rating range: [{def_ratings.min():.3f}, {def_ratings.max():.3f}]\n"
            )
        )
        
        # Save ratings to database
        self.stdout.write("\nSaving ratings...")
        
        saved_count = 0
        
        with transaction.atomic():
            for idx, team in enumerate(team_list):
                # Get game counts and total possessions
                team_stats = TeamGameStats.objects.filter(
                    team=team,
                    game__season_year=season_year,
                    game__status='final'
                )
                
                games_played = team_stats.count()
                total_poss = sum(gs.possessions_est for gs in team_stats)
                
                # Count wins and losses by comparing team pts to opponent pts
                total_wins = 0
                for game_stat in team_stats:
                    # Get opponent's stats for this game
                    opp_stats = TeamGameStats.objects.filter(
                        game=game_stat.game,
                        team=game_stat.opponent
                    ).first()
                    
                    if opp_stats and game_stat.pts > opp_stats.pts:
                        total_wins += 1
                
                total_losses = games_played - total_wins
                
                # Count D1 games only (for advanced metrics)
                d1_games = team_stats.filter(opponent__is_d1=True).count()
                
                # Compute adjusted ratings
                # Scale so that 100 = average (baseline is in PPP, off/def_ratings are deviations)
                adj_o = 100.0 + (100 * off_ratings[idx])
                adj_d = 100.0 - (100 * def_ratings[idx])
                adj_em = adj_o - adj_d
                adj_tempo = tempo_ratings.get(team.id, 0.0)
                
                # Save
                TeamSeasonRatings.objects.update_or_create(
                    team=team,
                    season=season,
                    defaults={
                        'adj_o': adj_o,
                        'adj_d': adj_d,
                        'adj_em': adj_em,
                        'adj_tempo': adj_tempo,
                        'games_played': games_played,
                        'wins': total_wins,
                        'losses': total_losses,
                        'd1_games_played': d1_games,
                        'total_possessions': total_poss,
                        'hca_estimate': hca_est,
                    }
                )
                
                saved_count += 1
        
        # Compute and assign rankings
        self._assign_rankings(season)
        
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{'='*60}\n"
                f"COMPLETE\n"
                f"Ratings computed for {saved_count} teams\n"
                f"{'='*60}\n"
            )
        )
    
    def _build_game_data(self, games) -> List[Dict]:
        """Build list of game data for regression"""
        game_data = []
        
        for game in games:
            # Get team stats for both teams
            home_stats = TeamGameStats.objects.filter(
                game=game,
                team=game.home_team
            ).first()
            
            away_stats = TeamGameStats.objects.filter(
                game=game,
                team=game.away_team
            ).first()
            
            if not home_stats or not away_stats:
                continue
            
            # Compute possessions-per-game and points-per-possession
            home_poss = home_stats.possessions_est
            away_poss = away_stats.possessions_est
            
            if home_poss <= 0 or away_poss <= 0:
                continue
            
            # Two observations per game (one per team)
            # Home team offensive possession
            game_data.append({
                'team': game.home_team,
                'opponent': game.away_team,
                'ppp': home_stats.pts / home_poss,
                'possessions': home_poss,
                'is_home': True,
                'game': game,
            })
            
            # Away team offensive possession
            game_data.append({
                'team': game.away_team,
                'opponent': game.home_team,
                'ppp': away_stats.pts / away_poss,
                'possessions': away_poss,
                'is_home': False,
                'game': game,
            })
        
        return game_data
    
    def _solve_ratings(
        self,
        game_data: List[Dict],
        team_to_idx: Dict[int, int],
        n_teams: int,
        fixed_hca: float = None,
        alpha: float = 1.0,
    ) -> Tuple[np.ndarray, np.ndarray, float, float, Dict]:
        """
        Solve for offensive and defensive ratings using ridge regression
        
        Model: PPP = baseline + Off(team) - Def(opponent) + HCA*is_home + error
        
        Returns:
            (off_ratings, def_ratings, baseline, hca, tempo_ratings)
        """
        n_obs = len(game_data)
        
        # Build design matrix X and response vector y
        # X has columns: [1 (intercept), team_off_1, ..., team_off_n, team_def_1, ..., team_def_n, hca]
        n_params = 1 + n_teams + n_teams + (1 if fixed_hca is None else 0)
        
        X = np.zeros((n_obs, n_params))
        y = np.zeros(n_obs)
        weights = np.zeros(n_obs)
        
        for i, obs in enumerate(game_data):
            team_idx = team_to_idx[obs['team'].id]
            opp_idx = team_to_idx[obs['opponent'].id]
            
            # Intercept
            X[i, 0] = 1.0
            
            # Offensive rating for team
            X[i, 1 + team_idx] = 1.0
            
            # Defensive rating for opponent (negative sign)
            X[i, 1 + n_teams + opp_idx] = -1.0
            
            # Home court advantage
            if fixed_hca is None:
                # Estimate HCA from data
                hca_idx = 1 + 2*n_teams
                X[i, hca_idx] = 1.0 if obs['is_home'] else 0.0
            else:
                # Use fixed HCA (add to response)
                if obs['is_home']:
                    y[i] -= fixed_hca / 100.0  # Convert to PPP scale
            
            # Response (points per possession)
            y[i] += obs['ppp']
            
            # Weight by possessions
            weights[i] = obs['possessions']
        
        # Weighted ridge regression (memory-efficient: avoid creating full diagonal matrix)
        # Instead of W = diag(weights), use: X'WX = X' @ diag(w) @ X = sum_i w[i] * X[i,:].T @ X[i,:]
        # Equivalently: X'WX = X.T @ (X * weights[:, None])
        weighted_X = X * weights[:, np.newaxis]
        XtWX = X.T @ weighted_X
        XtWy = X.T @ (weights * y)
        
        # Add L2 regularization (ridge)
        reg_matrix = alpha * np.eye(n_params)
        reg_matrix[0, 0] = 0  # Don't regularize intercept
        
        # Solve: (X'WX + alpha*I) beta = X'Wy
        try:
            from scipy.linalg import solve
            beta = solve(XtWX + reg_matrix, XtWy, assume_a='pos')
        except:
            # Fallback to numpy
            beta = np.linalg.solve(XtWX + reg_matrix, XtWy)
        
        # Extract parameters
        baseline = beta[0]
        off_ratings = beta[1:1+n_teams]
        def_ratings = beta[1+n_teams:1+2*n_teams]
        
        if fixed_hca is None:
            hca_est = beta[1+2*n_teams] * 100  # Convert to pts/100
        else:
            hca_est = fixed_hca
        
        # Compute tempo ratings (possessions per game)
        tempo_ratings = self._compute_tempo(game_data, team_to_idx)
        
        return off_ratings, def_ratings, baseline, hca_est, tempo_ratings
    
    def _compute_tempo(
        self,
        game_data: List[Dict],
        team_to_idx: Dict[int, int],
    ) -> Dict[int, float]:
        """Compute adjusted tempo for each team"""
        # Simple approach: average possessions per game
        team_poss_sum = defaultdict(float)
        team_games = defaultdict(int)
        
        processed_games = set()
        
        for obs in game_data:
            game_id = obs['game'].id
            team_id = obs['team'].id
            
            # Only count each game once per team
            key = (game_id, team_id)
            if key in processed_games:
                continue
            
            processed_games.add(key)
            team_poss_sum[team_id] += obs['possessions']
            team_games[team_id] += 1
        
        tempo_ratings = {}
        for team_id, total_poss in team_poss_sum.items():
            games = team_games[team_id]
            tempo_ratings[team_id] = total_poss / games if games > 0 else 0
        
        return tempo_ratings
    
    def _assign_rankings(self, season: Season):
        """Assign rankings based on adjusted ratings"""
        # Rank by adj_em
        ratings = TeamSeasonRatings.objects.filter(
            season=season
        ).order_by('-adj_em')
        
        for rank, rating in enumerate(ratings, start=1):
            rating.rank_adj_em = rank
            rating.save(update_fields=['rank_adj_em'])
        
        # Rank by adj_o
        ratings = TeamSeasonRatings.objects.filter(
            season=season
        ).order_by('-adj_o')
        
        for rank, rating in enumerate(ratings, start=1):
            rating.rank_adj_o = rank
            rating.save(update_fields=['rank_adj_o'])
        
        # Rank by adj_d (lower is better)
        ratings = TeamSeasonRatings.objects.filter(
            season=season
        ).order_by('adj_d')
        
        for rank, rating in enumerate(ratings, start=1):
            rating.rank_adj_d = rank
            rating.save(update_fields=['rank_adj_d'])
