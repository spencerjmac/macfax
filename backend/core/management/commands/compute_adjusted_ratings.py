"""
Django management command to compute AOR/ADR/AEM metrics

This computes Adjusted Offensive Rating (AOR), Adjusted Defensive Rating (ADR),
and Adjusted Net Rating (AEM) from game-level boxscore data with:
- Venue tax (home/away/neutral adjustments via SiteFactor)
- Opponent adjustments (using KenPom/Torvik adj_o/adj_d)
- Bayesian shrinkage (k=300 possessions toward national average)

Also computes 0-100 "2K-style" ratings via z-score mapping.

Usage:
    python manage.py compute_adjusted_ratings --season 2026
    
Requirements:
    - GameLog records with boxscore data (pts, fga, or_total, to, fta, location)
    - KenPom or Torvik opponent adjustments (adj_o, adj_d) by date
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum, Count, F, Q
from core.models import Season, Team, TeamSeasonStats, GameLog


# ==================== CONSTANTS ====================
VENUE_TAX = {
    'H': 0.9862,  # Home: slightly easier (multiply raw efficiency by this)
    'A': 1.0140,  # Away: slightly harder
    'N': 1.0000,  # Neutral: no adjustment
}

BAYESIAN_K = 300  # Shrinkage parameter: 300 possessions toward national average

Z_SCORE_SCALE = 15  # Standard deviations to map to +/- 50 points (0-100 scale)


# ==================== HELPER FUNCTIONS ====================

def compute_possessions(row):
    """
    Compute possessions for a game using the standard formula:
    Poss = FGA - OR + TO + 0.475 * FTA
    """
    fga = row.get('fga', 0) or 0
    or_total = row.get('or_total', 0) or 0
    to = row.get('to', 0) or 0
    fta = row.get('fta', 0) or 0
    
    return fga - or_total + to + 0.475 * fta


def compute_raw_efficiency(pts, possessions):
    """Compute raw efficiency: 100 * (pts / possessions)"""
    if possessions <= 0:
        return None
    return 100 * (pts / possessions)


def get_opponent_adjustments(game_date, opponent_name, season_year):
    """
    Retrieve opponent's adjusted offensive and defensive ratings
    for the given date and season.
    
    Priority:
    1. KenPom adj_o/adj_d from closest date <= game_date
    2. Torvik adj_oe/adj_de as fallback
    3. National average if not found
    
    Returns: (opp_adj_o, opp_adj_d) or (None, None)
    """
    # TODO: Implement opponent adjustment lookup
    # This requires:
    # 1. Daily snapshots of KenPom/Torvik data (adj_o, adj_d by date)
    # 2. Team name normalization/alias matching
    # 3. Temporal join: find closest snapshot before game_date
    
    # For now, return None (will use national average as fallback)
    return None, None


def apply_venue_tax(raw_efficiency, location):
    """Apply venue tax multiplier based on home/away/neutral"""
    site_factor = VENUE_TAX.get(location, 1.0)
    return raw_efficiency * site_factor if raw_efficiency else None


def compute_z_score_rating(values, invert=False):
    """
    Convert array of values to 0-100 rating via z-score mapping:
    rating = clamp(50 + Z_SCORE_SCALE * z_score, 0, 100)
    
    If invert=True (for defense), lower values are better, so invert before z-score.
    """
    arr = np.array([v for v in values if v is not None])
    if len(arr) == 0:
        return []
    
    if invert:
        # For defense: convert "lower is better" to "higher is better"
        # DEFPLUS = NatAvg - ADR (so lower ADR = higher DEFPLUS)
        nat_avg = arr.mean()
        arr = nat_avg - arr
    
    mean = arr.mean()
    std = arr.std()
    
    if std == 0:
        return [50.0] * len(arr)
    
    z_scores = (arr - mean) / std
    ratings = 50 + Z_SCORE_SCALE * z_scores
    
    # Clamp to [0, 100]
    ratings = np.clip(ratings, 0, 100)
    
    return ratings.tolist()


# ==================== MAIN COMPUTATION CLASS ====================

class Command(BaseCommand):
    help = 'Compute AOR/ADR/AEM metrics from game-level data'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            required=True,
            help='Season year (e.g., 2026 for 2025-26 season)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run computation without saving to database'
        )
    
    def handle(self, *args, **options):
        season_year = options['season']
        dry_run = options.get('dry_run', False)
        
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"COMPUTING ADJUSTED RATINGS FOR SEASON {season_year}")
        self.stdout.write(f"{'='*60}\n")
        
        # Get season
        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            self.stderr.write(f"ERROR: Season {season_year} not found")
            return
        
        # ==================== STEP 1: Load GameLog data ====================
        self.stdout.write(self.style.SUCCESS("\n[1/6] Loading game logs..."))
        
        game_logs = GameLog.objects.filter(season=season).select_related('team', 'opponent')
        game_count = game_logs.count()
        
        if game_count == 0:
            self.stderr.write(self.style.ERROR(
                "\n❌ NO GAME LOGS FOUND!\n\n"
                "To compute AOR/ADR/AEM metrics, you need game-level boxscore data.\n\n"
                "Required fields per game:\n"
                "  - pts, pts_allowed (points scored/allowed)\n"
                "  - fga (field goal attempts)\n"
                "  - or_total (offensive rebounds)\n"
                "  - to (turnovers)\n"
                "  - fta (free throw attempts)\n"
                "  - location (H/A/N for home/away/neutral)\n"
                "  - opponent_name (for opponent adjustment lookup)\n"
                "  - date (for temporal matching)\n\n"
                "TODO: Create a scraper or import process to populate the GameLog table.\n"
                "See documentation for details on data sources.\n"
            ))
            return
        
        self.stdout.write(f"  ✓ Found {game_count} game logs")
        
        # ==================== STEP 2: Compute national average ====================
        self.stdout.write(self.style.SUCCESS("\n[2/6] Computing national average efficiency..."))
        
        # Compute total points and possessions across all games
        total_pts = 0
        total_poss = 0
        
        for game in game_logs:
            if game.possessions and game.possessions > 0:
                total_pts += game.pts
                total_poss += game.possessions
        
        if total_poss == 0:
            self.stderr.write(self.style.ERROR("ERROR: No valid possessions found"))
            return
        
        nat_avg = 100 * (total_pts / total_poss)
        self.stdout.write(f"  ✓ National Average: {nat_avg:.4f} pts/100 poss")
        self.stdout.write(f"  ✓ Total Points: {total_pts:,}")
        self.stdout.write(f"  ✓ Total Possessions: {total_poss:,.1f}")
        
        # ==================== STEP 3: Compute game-level adjusted ratings ====================
        self.stdout.write(self.style.SUCCESS("\n[3/6] Computing game-level adjusted ratings..."))
        
        games_processed = 0
        games_skipped = 0
        
        # Convert to DataFrame for easier computation
        games_df = pd.DataFrame(list(game_logs.values(
            'id', 'team_id', 'date', 'opponent_name', 'location',
            'pts', 'pts_allowed', 'fga', 'or_total', 'to', 'fta',
            'possessions', 'raw_oe', 'raw_de', 'recency_mult', 'weight',
            'opp_adj_o', 'opp_adj_d'
        )))
        
        # Ensure all game logs have possessions computed (should be auto-computed in save())
        for idx, row in games_df.iterrows():
            if pd.isna(row['possessions']) or row['possessions'] <= 0:
                poss = compute_possessions(row)
                games_df.at[idx, 'possessions'] = poss
                
                if poss > 0:
                    games_df.at[idx, 'raw_oe'] = 100 * (row['pts'] / poss)
                    games_df.at[idx, 'raw_de'] = 100 * (row['pts_allowed'] / poss)
        
        # Get opponent adjustments
        # TODO: Implement proper opponent adjustment lookup
        # For now, use national average as fallback
        games_df['opp_adj_d'] = games_df['opp_adj_d'].fillna(nat_avg)
        games_df['opp_adj_o'] = games_df['opp_adj_o'].fillna(nat_avg)
        
        # Compute game-level adjusted ratings WITH venue tax
        games_df['aor_game'] = (
            games_df['raw_oe'] * 
            (nat_avg / games_df['opp_adj_d']) * 
            games_df['location'].map(VENUE_TAX)
        )
        
        games_df['adr_game'] = (
            games_df['raw_de'] * 
            (nat_avg / games_df['opp_adj_o']) * 
            games_df['location'].map(VENUE_TAX)
        )
        
        # Compute weights (possessions * recency_mult)
        games_df['recency_mult'] = games_df['recency_mult'].fillna(1.0)
        games_df['weight'] = games_df['possessions'] * games_df['recency_mult']
        
        self.stdout.write(f"  ✓ Computed adjusted ratings for {len(games_df)} games")
        
        # ==================== STEP 4: Aggregate to team-season level ====================
        self.stdout.write(self.style.SUCCESS("\n[4/6] Aggregating to team-season level..."))
        
        # Group by team
        team_metrics = []
        
        for team_id in games_df['team_id'].unique():
            team_games = games_df[games_df['team_id'] == team_id]
            
            total_weight = team_games['weight'].sum()
            
            if total_weight == 0:
                continue
            
            # Weighted average with Bayesian shrinkage (k=300)
            weighted_aor_sum = (team_games['aor_game'] * team_games['weight']).sum()
            weighted_adr_sum = (team_games['adr_game'] * team_games['weight']).sum()
            
            aor = (weighted_aor_sum + BAYESIAN_K * nat_avg) / (total_weight + BAYESIAN_K)
            adr = (weighted_adr_sum + BAYESIAN_K * nat_avg) / (total_weight + BAYESIAN_K)
            aem = aor - adr
            
            team_metrics.append({
                'team_id': team_id,
                'aor': round(aor, 4),
                'adr': round(adr, 4),
                'aem': round(aem, 4),
                'games_count': len(team_games),
                'total_possessions': team_games['possessions'].sum(),
            })
        
        metrics_df = pd.DataFrame(team_metrics)
        self.stdout.write(f"  ✓ Computed metrics for {len(metrics_df)} teams")
        
        # ==================== STEP 5: Compute 0-100 ratings ====================
        self.stdout.write(self.style.SUCCESS("\n[5/6] Computing 0-100 ratings..."))
        
        # AOR: higher is better
        aor_100 = compute_z_score_rating(metrics_df['aor'].values, invert=False)
        metrics_df['aor_100'] = [round(v, 2) for v in aor_100]
        
        # ADR: lower is better, so invert
        adr_100 = compute_z_score_rating(metrics_df['adr'].values, invert=True)
        metrics_df['adr_100'] = [round(v, 2) for v in adr_100]
        
        # NET: higher is better
        net_100 = compute_z_score_rating(metrics_df['aem'].values, invert=False)
        metrics_df['net_100'] = [round(v, 2) for v in net_100]
        
        self.stdout.write(f"  ✓ Computed 0-100 ratings")
        
        # ==================== STEP 6: Compute ranks ====================
        self.stdout.write(self.style.SUCCESS("\n[6/6] Computing ranks..."))
        
        # Rank by AOR (desc: higher is better)
        metrics_df['rank_aor'] = metrics_df['aor'].rank(ascending=False, method='min').astype(int)
        
        # Rank by ADR (asc: lower is better)
        metrics_df['rank_adr'] = metrics_df['adr'].rank(ascending=True, method='min').astype(int)
        
        # Rank by AEM/Net (desc: higher is better)
        metrics_df['rank_aem'] = metrics_df['aem'].rank(ascending=False, method='min').astype(int)
        
        self.stdout.write(f"  ✓ Computed ranks")
        
        # ==================== STEP 7: Save to database ====================
        if dry_run:
            self.stdout.write(self.style.WARNING("\n[DRY RUN] Would update database with:"))
            self.stdout.write(metrics_df.head(10).to_string())
            return
        
        self.stdout.write(self.style.SUCCESS("\n[7/7] Saving to database..."))
        
        updated_count = 0
        
        with transaction.atomic():
            for _, row in metrics_df.iterrows():
                try:
                    team_stats = TeamSeasonStats.objects.get(
                        team_id=row['team_id'],
                        season=season
                    )
                    
                    team_stats.aor = row['aor']
                    team_stats.adr = row['adr']
                    team_stats.aem = row['aem']
                    team_stats.aor_100 = row['aor_100']
                    team_stats.adr_100 = row['adr_100']
                    team_stats.net_100 = row['net_100']
                    team_stats.rank_aor = row['rank_aor']
                    team_stats.rank_adr = row['rank_adr']
                    team_stats.rank_aem = row['rank_aem']
                    
                    team_stats.save()
                    updated_count += 1
                    
                except TeamSeasonStats.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(f"  ⚠ TeamSeasonStats not found for team_id={row['team_id']}")
                    )
        
        self.stdout.write(self.style.SUCCESS(f"  ✓ Updated {updated_count} teams"))
        
        # ==================== SUMMARY ====================
        self.stdout.write(self.style.SUCCESS(f"\n{'='*60}"))
        self.stdout.write(self.style.SUCCESS("COMPUTATION COMPLETE"))
        self.stdout.write(self.style.SUCCESS(f"{'='*60}"))
        
        # Display top 10 teams by Net Rating
        top_teams_df = metrics_df.nlargest(10, 'aem')
        
        self.stdout.write("\nTop 10 Teams by Net Rating (AEM):")
        self.stdout.write("-" * 80)
        self.stdout.write(f"{'Rank':<6} {'Team ID':<10} {'AOR':<10} {'ADR':<10} {'Net':<10} {'Net_100':<10}")
        self.stdout.write("-" * 80)
        
        for _, row in top_teams_df.iterrows():
            try:
                team = Team.objects.get(id=row['team_id'])
                team_name = team.name[:30]
            except Team.DoesNotExist:
                team_name = f"Team {row['team_id']}"
            
            self.stdout.write(
                f"{row['rank_aem']:<6} {team_name:<30} "
                f"{row['aor']:<10.4f} {row['adr']:<10.4f} "
                f"{row['aem']:<10.4f} {row['net_100']:<10.2f}"
            )
        
        self.stdout.write("\n✅ Done! Use --dry-run to test without saving.\n")
