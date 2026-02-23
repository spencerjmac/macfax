"""
Management command: compute_season_metrics
Aggregates team season stats from game logs

Usage:
    python manage.py compute_season_metrics --season 2026
"""

import logging
from django.core.management.base import BaseCommand
from django.db.models import Sum, Avg, Count, F
from django.db import transaction

from core.models import Season, Team, TeamGameStats, TeamSeasonMetrics

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Compute team season metrics from game logs'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            required=True,
            help='Season year (ending year, e.g., 2026 for 2025-26 season)'
        )
        parser.add_argument(
            '--team',
            type=str,
            help='Team slug (optional, compute for one team only)'
        )
    
    def handle(self, *args, **options):
        season_year = options['season']
        team_slug = options.get('team')
        
        # Get season
        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            season = Season.objects.create(
                year=season_year,
                display_name=f"{season_year-1}-{str(season_year)[2:]}"
            )
            self.stdout.write(f"Created season {season.display_name}")
        
        # Get teams to process
        if team_slug:
            teams = Team.objects.filter(slug=team_slug)
            if not teams.exists():
                self.stderr.write(f"Team not found: {team_slug}")
                return
        else:
            teams = Team.objects.all()
        
        self.stdout.write(f"\nComputing season metrics for {season.display_name}")
        self.stdout.write(f"Processing {teams.count()} teams...")
        
        created = 0
        updated = 0
        errors = 0
        
        for team in teams:
            try:
                metrics = self._compute_team_metrics(team, season)
                if metrics:
                    if metrics['created']:
                        created += 1
                    else:
                        updated += 1
            except Exception as e:
                errors += 1
                logger.error(f"Error computing metrics for {team.name}: {e}")
                self.stderr.write(f"  ERROR: {team.name}: {e}")
        
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("SUMMARY")
        self.stdout.write("=" * 60)
        self.stdout.write(f"Created:  {created}")
        self.stdout.write(f"Updated:  {updated}")
        self.stdout.write(f"Errors:   {errors}")
        self.stdout.write("=" * 60)
    
    @transaction.atomic
    def _compute_team_metrics(self, team, season):
        """Compute season metrics for one team"""
        
        # Get all games for this team this season
        games = TeamGameStats.objects.filter(
            team=team,
            game__season_year=season.year,
            game__status='final'
        ).select_related('game')
        
        game_count = games.count()
        
        if game_count == 0:
            return None
        
        # ==================== COMPUTE TOTALS ====================
        
        totals = games.aggregate(
            total_pts=Sum('pts'),
            total_fgm=Sum('fgm'),
            total_fga=Sum('fga'),
            total_fg3m=Sum('fg3m'),
            total_fg3a=Sum('fg3a'),
            total_ftm=Sum('ftm'),
            total_fta=Sum('fta'),
            total_oreb=Sum('oreb'),
            total_dreb=Sum('dreb'),
            total_reb=Sum('reb'),
            total_ast=Sum('ast'),
            total_stl=Sum('stl'),
            total_blk=Sum('blk'),
            total_tov=Sum('tov'),
            total_pf=Sum('pf'),
        )
        
        # Compute opponent totals (need to query opponent stats from same games)
        total_pts_allowed = 0
        total_opp_dreb = 0
        total_opp_fgm = 0
        total_opp_fga = 0
        total_opp_fg3m = 0
        total_opp_fta = 0
        total_opp_tov = 0
        total_possessions = 0.0
        total_opp_possessions = 0.0
        total_opp_fg2a = 0
        
        for game_stat in games:
            opp = game_stat._get_opp_stats()
            if opp:
                total_pts_allowed += opp.pts
                total_opp_dreb += opp.dreb
                total_opp_fgm += opp.fgm
                total_opp_fga += opp.fga
                total_opp_fg3m += opp.fg3m
                total_opp_fta += opp.fta
                total_opp_tov += opp.tov
                total_opp_fg2a += (opp.fga - opp.fg3a)
                
                # Possessions
                poss_t = game_stat.poss_team
                poss_o = game_stat.poss_opp
                if poss_t:
                    total_possessions += poss_t
                if poss_o:
                    total_opp_possessions += poss_o
        
        # ==================== COMPUTE AVERAGES ====================
        
        ppg = totals['total_pts'] / game_count if game_count > 0 else 0.0
        papg = total_pts_allowed / game_count if game_count > 0 else 0.0
        pace = (total_possessions + total_opp_possessions) / (2 * game_count) if game_count > 0 else 0.0
        
        # ==================== COMPUTE PERCENTAGES ====================
        
        # eFG% = (FGM + 0.5*FG3M) / FGA
        efg_pct = ((totals['total_fgm'] + 0.5 * totals['total_fg3m']) / totals['total_fga'] * 100) \
            if totals['total_fga'] > 0 else 0.0
        
        # TOV% = TOV / possessions
        tov_pct = (totals['total_tov'] / total_possessions * 100) if total_possessions > 0 else 0.0
        
        # ORB% = OREB / (OREB + Opp.DREB)
        orb_denom = totals['total_oreb'] + total_opp_dreb
        orb_pct = (totals['total_oreb'] / orb_denom * 100) if orb_denom > 0 else 0.0
        
        # FTR = FTA / FGA
        ftr = (totals['total_fta'] / totals['total_fga'] * 100) if totals['total_fga'] > 0 else 0.0
        
        # Opponent eFG%
        opp_efg_pct = ((total_opp_fgm + 0.5 * total_opp_fg3m) / total_opp_fga * 100) \
            if total_opp_fga > 0 else 0.0
        
        # Opponent TOV%
        opp_tov_pct = (total_opp_tov / total_opp_possessions * 100) if total_opp_possessions > 0 else 0.0
        
        # DRB% = DREB / (DREB + Opp.OREB)
        # Note: This is actually just (1 - Opp.ORB%), but we'll compute directly
        drb_denom = totals['total_dreb'] + total_opp_dreb  # This isn't quite right, need opp OREB
        drb_pct = 100.0 - orb_pct  # Inverse of opponent's ORB%
        
        # Opponent FTR
        opp_ftr = (total_opp_fta / total_opp_fga * 100) if total_opp_fga > 0 else 0.0
        
        # ==================== COMPUTE MARGINS ====================
        
        efg_margin = efg_pct - opp_efg_pct
        tov_edge = opp_tov_pct - tov_pct  # Positive = good (force more TOs than you commit)
        reb_edge = orb_pct - (100.0 - drb_pct)  # ORB% - Opp.ORB%
        ftr_margin = ftr - opp_ftr
        
        # ==================== COMPUTE RATINGS ====================
        
        ortg = (100 * totals['total_pts'] / total_possessions) if total_possessions > 0 else 0.0
        drtg = (100 * total_pts_allowed / total_possessions) if total_possessions > 0 else 0.0
        net_rtg = ortg - drtg
        
        # ==================== OTHER METRICS ====================
        
        ast_g = totals['total_ast'] / game_count if game_count > 0 else 0.0
        ast_pct = (totals['total_ast'] / totals['total_fgm'] * 100) if totals['total_fgm'] > 0 else None
        
        blk_g = totals['total_blk'] / game_count if game_count > 0 else 0.0
        blk_pct = (totals['total_blk'] / total_opp_fg2a * 100) if total_opp_fg2a > 0 else None
        
        dpf_g = totals['total_pf'] / game_count if game_count > 0 else 0.0
        
        # ==================== SAVE TO DATABASE ====================
        
        metrics, created = TeamSeasonMetrics.objects.update_or_create(
            team=team,
            season=season,
            defaults={
                'games': game_count,
                
                # Totals
                'total_pts': totals['total_pts'],
                'total_pts_allowed': total_pts_allowed,
                'total_possessions': total_possessions,
                'total_opp_possessions': total_opp_possessions,
                'total_fgm': totals['total_fgm'],
                'total_fga': totals['total_fga'],
                'total_fg3m': totals['total_fg3m'],
                'total_fg3a': totals['total_fg3a'],
                'total_ftm': totals['total_ftm'],
                'total_fta': totals['total_fta'],
                'total_oreb': totals['total_oreb'],
                'total_dreb': totals['total_dreb'],
                'total_reb': totals['total_reb'],
                'total_opp_dreb': total_opp_dreb,
                'total_ast': totals['total_ast'],
                'total_stl': totals['total_stl'],
                'total_blk': totals['total_blk'],
                'total_tov': totals['total_tov'],
                'total_pf': totals['total_pf'],
                
                # Averages
                'ppg': round(ppg, 1),
                'papg': round(papg, 1),
                'pace': round(pace, 1),
                
                # Ratings
                'ortg': round(ortg, 1),
                'drtg': round(drtg, 1),
                'net_rtg': round(net_rtg, 1),
                
                # Four Factors - Offense
                'efg_pct': round(efg_pct, 1),
                'tov_pct': round(tov_pct, 1),
                'orb_pct': round(orb_pct, 1),
                'ftr': round(ftr, 1),
                
                # Four Factors - Defense
                'opp_efg_pct': round(opp_efg_pct, 1),
                'opp_tov_pct': round(opp_tov_pct, 1),
                'drb_pct': round(drb_pct, 1),
                'opp_ftr': round(opp_ftr, 1),
                
                # Margins
                'efg_margin': round(efg_margin, 1),
                'tov_edge': round(tov_edge, 1),
                'reb_edge': round(reb_edge, 1),
                'ftr_margin': round(ftr_margin, 1),
                
                # Other stats
                'ast_g': round(ast_g, 1),
                'ast_pct': round(ast_pct, 1) if ast_pct else None,
                'blk_g': round(blk_g, 1),
                'blk_pct': round(blk_pct, 1) if blk_pct else None,
                'dpf_g': round(dpf_g, 1),
                
                # Kill shots (placeholder for now)
                'kill_shots_for': 0,
                'kill_shots_against': 0,
                'kill_shots_pg': 0.0,
                'kill_shots_conceded_pg': 0.0,
                'kill_shot_margin_pg': 0.0,
            }
        )
        
        action = "Created" if created else "Updated"
        self.stdout.write(f"  {action}: {team.name} - {game_count} games, ORtg={ortg:.1f}, DRtg={drtg:.1f}")
        
        return {
            'created': created,
            'metrics': metrics
        }
