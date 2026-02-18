"""
Django management command to ingest data from CSV files into the database

Usage:
    python manage.py ingest_data --season 2026
"""

import os
import pandas as pd
from pathlib import Path
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.db.models import F, Avg, StdDev
from core.models import Season, Conference, Team, TeamSeasonStats, DataIngestionRun
from core.constants import FOUR_FACTOR_SCALE, FOUR_FACTOR_WEIGHTS


class Command(BaseCommand):
    help = 'Ingest CBB data from CSV files into the database'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            required=True,
            help='Season year (e.g., 2026 for 2025-26 season)'
        )
        parser.add_argument(
            '--kenpom',
            type=str,
            help='Path to KenPom CSV file'
        )
        parser.add_argument(
            '--torvik',
            type=str,
            help='Path to Torvik CSV file'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-import even if data exists'
        )
    
    def handle(self, *args, **options):
        season_year = options['season']
        force = options.get('force', False)
        
        self.stdout.write(f"\n🏀 CBB Analytics Data Ingestion")
        self.stdout.write(f"{'=' * 50}\n")
        
        # Create or get season
        season, created = Season.objects.get_or_create(
            year=season_year,
            defaults={
                'display_name': f'{season_year-1}-{str(season_year)[-2:]}',
                'is_current': True
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS(f'✓ Created season: {season.display_name}'))
        else:
            self.stdout.write(f'Season: {season.display_name}')
        
        # Create ingestion run
        ingestion_run = DataIngestionRun.objects.create(
            season=season,
            status='running'
        )
        
        try:
            # Determine CSV paths
            base_dir = Path(__file__).resolve().parent.parent.parent.parent.parent
            
            kenpom_path = options.get('kenpom') or base_dir / 'KenPom Data' / 'kenpom_tableau.csv'
            torvik_path = options.get('torvik') or base_dir / 'Bart Torvik' / 'torvik_tableau.csv'
            evan_miya_path = base_dir / 'Evan Miya' / 'scraper' / 'team_ratings.csv'
            cbb_analytics_path = base_dir / 'CBB Analytics' / 'cbb_analytics_tableau_cleaned.csv'
            ap_poll_path = base_dir / 'ESPN AP Poll' / 'ap_poll_week6.csv'
            
            self.stdout.write(f'\n📂 Loading CSVs...')
            self.stdout.write(f'  KenPom: {kenpom_path}')
            self.stdout.write(f'  Torvik: {torvik_path}')
            self.stdout.write(f'  Evan Miya: {evan_miya_path}')
            self.stdout.write(f'  CBB Analytics: {cbb_analytics_path}')
            self.stdout.write(f'  AP Poll Week 6: {ap_poll_path}')
            
            # Load CSVs
            df_kenpom = pd.read_csv(kenpom_path) if os.path.exists(kenpom_path) else None
            df_torvik = pd.read_csv(torvik_path) if os.path.exists(torvik_path) else None
            df_evan_miya = pd.read_csv(evan_miya_path) if os.path.exists(evan_miya_path) else None
            df_cbb_analytics = pd.read_csv(cbb_analytics_path) if os.path.exists(cbb_analytics_path) else None
            df_ap_poll = pd.read_csv(ap_poll_path) if os.path.exists(ap_poll_path) else None
            
            if df_kenpom is None and df_torvik is None:
                raise Exception('No CSV files found!')
            
            self.stdout.write(self.style.SUCCESS(f'✓ Loaded CSVs'))
            if df_kenpom is not None:
                self.stdout.write(f'  KenPom: {len(df_kenpom)} teams')
            if df_torvik is not None:
                self.stdout.write(f'  Torvik: {len(df_torvik)} teams')
            if df_evan_miya is not None:
                self.stdout.write(f'  Evan Miya: {len(df_evan_miya)} teams')
            if df_cbb_analytics is not None:
                self.stdout.write(f'  CBB Analytics: {len(df_cbb_analytics)} teams')
            if df_ap_poll is not None:
                self.stdout.write(f'  AP Poll: {len(df_ap_poll)} teams')
            
            # Start ingestion
            teams_processed = self._ingest_data(season, df_kenpom, df_torvik, df_evan_miya, df_cbb_analytics, df_ap_poll, force)
            
            # Compute Four Factor Index after all teams are ingested
            self.stdout.write(f'\n📊 Computing Four Factor Index...')
            self._compute_four_factor_index(season)
            self.stdout.write(self.style.SUCCESS(f'✓ Four Factor Index computed'))
            
            # Mark as success
            ingestion_run.status = 'success'
            ingestion_run.teams_ingested = teams_processed
            ingestion_run.completed_at = timezone.now()
            ingestion_run.save()
            
            self.stdout.write(self.style.SUCCESS(f'\n✅ Ingestion complete!'))
            self.stdout.write(f'   Teams processed: {teams_processed}')
            
        except Exception as e:
            ingestion_run.status = 'error'
            ingestion_run.error_log = str(e)
            ingestion_run.completed_at = timezone.now()
            ingestion_run.save()
            
            self.stdout.write(self.style.ERROR(f'\n❌ Error: {str(e)}'))
            raise
    
    @transaction.atomic
    def _ingest_data(self, season, df_kenpom, df_torvik, df_evan_miya, df_cbb_analytics, df_ap_poll, force):
        """Main ingestion logic"""
        
        # Team name normalization map (simplified - expand as needed)
        team_name_map = {
            'Michigan St.': 'Michigan State',
            'Miami FL': 'Miami (FL)',
            'Miami OH': 'Miami (OH)',
            'St. John\'s': 'St. John\'s',
            'Saint Louis': 'Saint Louis',
            'Saint Mary\'s': 'Saint Mary\'s',
            'N.C. State': 'NC State',
            'McNeese St.': 'McNeese',
            'Stephen F. Austin': 'Stephen F. Austin',
        }
        
        def normalize_name(name):
            return team_name_map.get(name, name)
        
        teams_processed = 0
        
        # Use Torvik as primary source (has more complete data)
        if df_torvik is not None:
            for idx, row in df_torvik.iterrows():
                team_name = normalize_name(row['team_name'])
                
                # Create or get team
                team, _ = Team.objects.get_or_create(
                    name=team_name,
                    defaults={'slug': team_name.lower().replace(' ', '-').replace('.', '')}
                )
                
                # Create or get conference
                conf_code = row.get('conference', 'IND')
                conference, _ = Conference.objects.get_or_create(
                    code=conf_code,
                    defaults={'name': conf_code}
                )
                
                # Parse record (e.g., "22-1")
                record_str = row.get('record', '0-0')
                wins, losses = 0, 0
                if isinstance(record_str, str) and '-' in record_str:
                    parts = record_str.split('-')
                    try:
                        wins = int(parts[0])
                        losses = int(parts[1])
                    except (ValueError, IndexError):
                        wins = 0
                        losses = 0
                
                # Find matching KenPom data
                kenpom_row = None
                if df_kenpom is not None:
                    kenpom_match = df_kenpom[
                        df_kenpom['team_name'].apply(normalize_name) == team_name
                    ]
                    if not kenpom_match.empty:
                        kenpom_row = kenpom_match.iloc[0]
                
                # Find matching Evan Miya data
                evan_miya_row = None
                if df_evan_miya is not None:
                    evan_miya_match = df_evan_miya[
                        df_evan_miya['Team'].apply(normalize_name) == team_name
                    ]
                    if not evan_miya_match.empty:
                        evan_miya_row = evan_miya_match.iloc[0]
                
                # Find matching CBB Analytics data
                cbb_analytics_row = None
                if df_cbb_analytics is not None:
                    # CBB Analytics uses team_kenpom field
                    cbb_match = df_cbb_analytics[
                        df_cbb_analytics['team_kenpom'].apply(normalize_name) == team_name
                    ] if 'team_kenpom' in df_cbb_analytics.columns else None
                    if cbb_match is not None and not cbb_match.empty:
                        cbb_analytics_row = cbb_match.iloc[0]
                
                # Find matching AP Poll Week 6 data
                ap_poll_rank = None
                if df_ap_poll is not None:
                    ap_match = df_ap_poll[
                        df_ap_poll['team_kenpom'].apply(normalize_name) == team_name
                    ]
                    if not ap_match.empty:
                        ap_poll_rank = int(ap_match.iloc[0]['rank'])
                
                # Create or update stats
                stats, created = TeamSeasonStats.objects.update_or_create(
                    team=team,
                    season=season,
                    defaults={
                        'conference': conference,
                        'games': int(row.get('games', wins + losses)) if pd.notna(row.get('games')) else wins + losses,
                        'wins': wins,
                        'losses': losses,
                        'rank': int(row.get('rank', 0)) if pd.notna(row.get('rank')) else None,
                        't_rank': int(row.get('rank', 0)) if pd.notna(row.get('rank')) else None,
                        'ap_poll_week6': ap_poll_rank,
                        
                        # KenPom metrics (from KenPom sheet if available, else from Torvik)
                        'adj_em': float(kenpom_row.get('adj_em', 0)) if kenpom_row is not None else float(row.get('adj_oe', 0) - row.get('adj_de', 0)) if pd.notna(row.get('adj_oe')) else 0,
                        'adj_o': float(kenpom_row.get('adj_o', 100)) if kenpom_row is not None else float(row.get('adj_oe', 100)),
                        'adj_d': float(kenpom_row.get('adj_d', 100)) if kenpom_row is not None else float(row.get('adj_de', 100)),
                        'adj_tempo': float(kenpom_row.get('adj_tempo', 68)) if kenpom_row is not None else float(row.get('adj_tempo', 68)) if pd.notna(row.get('adj_tempo')) else 68,
                        'luck': float(kenpom_row.get('luck', 0)) if kenpom_row is not None and pd.notna(kenpom_row.get('luck')) else None,
                        'sos_adj_em': float(kenpom_row.get('sos_adj_em', 0)) if kenpom_row is not None and pd.notna(kenpom_row.get('sos_adj_em')) else None,
                        'ncsos_adj_em': float(kenpom_row.get('ncsos_adj_em', 0)) if kenpom_row is not None and pd.notna(kenpom_row.get('ncsos_adj_em')) else None,
                        
                        # Torvik metrics
                        'efg_pct': float(row.get('efg_pct', 50)) if pd.notna(row.get('efg_pct')) else 50.0,
                        'tov_pct': float(row.get('tor', 15)) if pd.notna(row.get('tor')) else 15.0,
                        'orb_pct': float(row.get('orb', 30)) if pd.notna(row.get('orb')) else 30.0,
                        'ftr': float(row.get('ftr', 30)) if pd.notna(row.get('ftr')) else 30.0,
                        
                        'efg_pct_d': float(row.get('efg_pct_d', 50)) if pd.notna(row.get('efg_pct_d')) else 50.0,
                        'tov_pct_d': float(row.get('tord', 15)) if pd.notna(row.get('tord')) else 15.0,
                        'drb_pct': float(row.get('drb', 70)) if pd.notna(row.get('drb')) else 70.0,
                        'ftr_d': float(row.get('ftrd', 30)) if pd.notna(row.get('ftrd')) else 30.0,
                        
                        'fg2_pct': float(row.get('two_p_pct', 50)) if pd.notna(row.get('two_p_pct')) else None,
                        'fg2_pct_d': float(row.get('two_p_pct_d', 50)) if pd.notna(row.get('two_p_pct_d')) else None,
                        'fg3_pct': float(row.get('three_p_pct', 33)) if pd.notna(row.get('three_p_pct')) else None,
                        'fg3_pct_d': float(row.get('three_p_pct_d', 33)) if pd.notna(row.get('three_p_pct_d')) else None,
                        'fg3_rate': float(row.get('three_pr', 35)) if pd.notna(row.get('three_pr')) else None,
                        'fg3_rate_d': float(row.get('three_prd', 35)) if pd.notna(row.get('three_prd')) else None,
                        
                        # FT% from CBB Analytics (stored as percentage 0-100)
                        'ft_pct': self._get_ft_pct_from_cbb(cbb_analytics_row) if cbb_analytics_row is not None else None,
                        
                        'wab': float(row.get('wab', 0)) if pd.notna(row.get('wab')) else None,
                        'barthag': float(row.get('barthag', 0.5)) if pd.notna(row.get('barthag')) else None,
                        
                        # Evan Miya relative ratings
                        'em_o_rate': float(evan_miya_row.get('O-Rate', 0)) if evan_miya_row is not None and pd.notna(evan_miya_row.get('O-Rate')) else None,
                        'em_d_rate': float(evan_miya_row.get('D-Rate', 0)) if evan_miya_row is not None and pd.notna(evan_miya_row.get('D-Rate')) else None,
                        'em_rating': float(evan_miya_row.get('Relative Rating', 0)) if evan_miya_row is not None and pd.notna(evan_miya_row.get('Relative Rating')) else None,
                        'rank_em': int(evan_miya_row.get('Relative Ranking', 0)) if evan_miya_row is not None and pd.notna(evan_miya_row.get('Relative Ranking')) else None,
                        
                        # Evan Miya kill shots
                        'em_kill_shots_pg': float(evan_miya_row.get('Kill Shots Per Game', 0)) if evan_miya_row is not None and pd.notna(evan_miya_row.get('Kill Shots Per Game')) else None,
                        'em_kill_shots_conceded_pg': float(evan_miya_row.get('Kill Shots Conceded Per Game', 0)) if evan_miya_row is not None and pd.notna(evan_miya_row.get('Kill Shots Conceded Per Game')) else None,
                        'em_kill_shot_margin_pg': float(evan_miya_row.get('Kill Shots Margin Per Game', 0)) if evan_miya_row is not None and pd.notna(evan_miya_row.get('Kill Shots Margin Per Game')) else None,
                        
                        # CBB Analytics per-game and percentage stats
                        'cbb_ast_g': self._get_float_from_cbb(cbb_analytics_row, 'AST/G'),
                        'cbb_ast_pct': self._get_float_from_cbb(cbb_analytics_row, 'AST%'),
                        'cbb_blk_g': self._get_float_from_cbb(cbb_analytics_row, 'BLK/G'),
                        'cbb_blk_pct': self._get_float_from_cbb(cbb_analytics_row, 'BLK%'),
                        'cbb_dpf_g': self._get_float_from_cbb(cbb_analytics_row, 'DPF/G'),
                        'cbb_drb_g': self._get_float_from_cbb(cbb_analytics_row, 'DRB/G'),
                        'cbb_fg_pct': self._get_float_from_cbb(cbb_analytics_row, 'FG%'),
                        'cbb_hkm_pct': self._get_float_from_cbb(cbb_analytics_row, 'HKM%'),
                        'cbb_opf_g': self._get_float_from_cbb(cbb_analytics_row, 'OPF/G'),
                        'cbb_pace_raw': self._get_float_from_cbb(cbb_analytics_row, 'Pace'),
                        'cbb_pf_g': self._get_float_from_cbb(cbb_analytics_row, 'PF/G'),
                        'cbb_pts_g': self._get_float_from_cbb(cbb_analytics_row, 'PTS/G'),
                        'cbb_reb_g': self._get_float_from_cbb(cbb_analytics_row, 'REB/G'),
                        'cbb_stl_g': self._get_float_from_cbb(cbb_analytics_row, 'STL/G'),
                        'cbb_tov_g': self._get_float_from_cbb(cbb_analytics_row, 'TOV/G'),
                        
                        # Data provenance
                        'has_kenpom': kenpom_row is not None,
                        'has_torvik': True,
                        'has_cbb_analytics': cbb_analytics_row is not None,
                        'has_evan_miya': evan_miya_row is not None,
                    }
                )
                
                # Call save() to trigger margin calculations
                stats.save()
                
                teams_processed += 1
                
                if teams_processed % 50 == 0:
                    self.stdout.write(f'  Processed {teams_processed} teams...')
        
        # Fallback: if no Torvik data, use KenPom
        elif df_kenpom is not None:
            for idx, row in df_kenpom.iterrows():
                team_name = normalize_name(row['team_name'])
                
                # Create or get team
                team, _ = Team.objects.get_or_create(
                    name=team_name,
                    defaults={'slug': team_name.lower().replace(' ', '-').replace('.', '')}
                )
                
                # Create or get conference
                conf_code = row.get('conference', 'IND')
                conference, _ = Conference.objects.get_or_create(
                    code=conf_code,
                    defaults={'name': conf_code}
                )
                
                # Create or update stats (KenPom only)
                stats, created = TeamSeasonStats.objects.update_or_create(
                    team=team,
                    season=season,
                    defaults={
                        'conference': conference,
                        'rank': int(row.get('rank', 0)) if pd.notna(row.get('rank')) else None,
                        'adj_em': float(row.get('adj_em', 0)),
                        'adj_o': float(row.get('adj_o', 100)),
                        'adj_d': float(row.get('adj_d', 100)),
                        'adj_tempo': float(row.get('adj_tempo', 68)),
                        'luck': float(row.get('luck', 0)) if pd.notna(row.get('luck')) else None,
                        'sos_adj_em': float(row.get('sos_adj_em', 0)) if pd.notna(row.get('sos_adj_em')) else None,
                        'ncsos_adj_em': float(row.get('ncsos_adj_em', 0)) if pd.notna(row.get('ncsos_adj_em')) else None,
                        'has_kenpom': True,
                        'has_torvik': False,
                        'has_cbb_analytics': False,
                        'has_evan_miya': False,
                    }
                )
                
                teams_processed += 1
                
                if teams_processed % 50 == 0:
                    self.stdout.write(f'  Processed {teams_processed} teams...')
        
        return teams_processed
    
    def _get_ft_pct_from_cbb(self, cbb_row):
        """
        Extract FT% from CBB Analytics row.
        FT% is stored as a string with % sign (e.g., "75.0%").
        """
        if cbb_row is None:
            return None
        
        try:
            ft_pct_str = cbb_row.get('FT%', None)
            if pd.isna(ft_pct_str) or ft_pct_str == '' or ft_pct_str == '-':
                return None
            
            # Remove % sign if present and convert to float
            ft_pct_clean = str(ft_pct_str).replace('%', '').strip()
            return float(ft_pct_clean)
        except (ValueError, TypeError):
            return None
    
    def _get_float_from_cbb(self, cbb_row, field_name, default=None):
        """
        Extract a float value from CBB Analytics row.
        Handles percentage formatting (removes '%' sign) and 'x' suffix for ratios.
        """
        if cbb_row is None:
            return default
        
        try:
            value_str = cbb_row.get(field_name, None)
            if pd.isna(value_str) or value_str == '' or value_str == '-':
                return default
            
            # Remove % sign, 'x' suffix, and whitespace
            value_clean = str(value_str).replace('%', '').replace('x', '').strip()
            return float(value_clean)
        except (ValueError, TypeError):
            return default
    
    @transaction.atomic
    def _compute_four_factor_index(self, season):
        """
        Compute Four Factor Index for all teams in a season
        
        Steps:
        1. Calculate season-wide statistics (mean, std) for four factors
        2. Compute Z-scores for each team
        3. Calculate weighted Z-score (Four Factor WZ)
        4. Convert to 0-100 scale with clamping
        5. Compute national rankings
        """
        # Get all teams with complete four factor data
        teams = TeamSeasonStats.objects.filter(
            season=season
        ).exclude(
            efg_margin__isnull=True
        ).exclude(
            tov_edge__isnull=True
        ).exclude(
            reb_edge__isnull=True
        ).exclude(
            ftr_margin__isnull=True
        )
        
        if teams.count() == 0:
            self.stdout.write(self.style.WARNING('  No teams with complete four factor data'))
            return
        
        # Calculate season-wide statistics for each margin
        stats = teams.aggregate(
            efg_mean=Avg('efg_margin'),
            efg_std=StdDev('efg_margin'),
            tov_mean=Avg('tov_edge'),
            tov_std=StdDev('tov_edge'),
            reb_mean=Avg('reb_edge'),
            reb_std=StdDev('reb_edge'),
            ftr_mean=Avg('ftr_margin'),
            ftr_std=StdDev('ftr_margin'),
        )
        
        self.stdout.write(f'  Season statistics:')
        self.stdout.write(f'    eFG Margin: μ={stats["efg_mean"]:.3f}, σ={stats["efg_std"]:.3f}')
        self.stdout.write(f'    TOV Edge:   μ={stats["tov_mean"]:.3f}, σ={stats["tov_std"]:.3f}')
        self.stdout.write(f'    Reb Edge:   μ={stats["reb_mean"]:.3f}, σ={stats["reb_std"]:.3f}')
        self.stdout.write(f'    FTR Margin: μ={stats["ftr_mean"]:.3f}, σ={stats["ftr_std"]:.3f}')
        
        # Check for zero standard deviations (would cause division by zero)
        if any(stats[f'{key}_std'] == 0 or stats[f'{key}_std'] is None 
               for key in ['efg', 'tov', 'reb', 'ftr']):
            self.stdout.write(self.style.WARNING('  Cannot compute Z-scores: zero standard deviation'))
            return
        
        # Compute Z-scores and Four Factor Index for each team
        weights = FOUR_FACTOR_WEIGHTS
        scale = FOUR_FACTOR_SCALE
        
        for team_stats in teams:
            # Calculate Z-scores
            efg_z = (team_stats.efg_margin - stats['efg_mean']) / stats['efg_std']
            tov_z = (team_stats.tov_edge - stats['tov_mean']) / stats['tov_std']
            reb_z = (team_stats.reb_edge - stats['reb_mean']) / stats['reb_std']
            ftr_z = (team_stats.ftr_margin - stats['ftr_mean']) / stats['ftr_std']
            
            # Calculate weighted Z-score (NO division by 4)
            # Formula: 0.4069*eFG_Z + 0.4069*TOV_Z + 0.1432*REB_Z + 0.0428*FTR_Z
            wz = (weights['efg'] * efg_z + 
                  weights['tov'] * tov_z + 
                  weights['reb'] * reb_z + 
                  weights['ftr'] * ftr_z)
            
            # Convert to 0-100 scale with clamping
            # Formula: MIN(100, MAX(0, 50 + SCALE * WZ))
            ffi_100 = max(0, min(100, 50 + scale * wz))
            
            # Update team stats
            team_stats.efg_margin_z = efg_z
            team_stats.tov_edge_z = tov_z
            team_stats.reb_edge_z = reb_z
            team_stats.ftr_margin_z = ftr_z
            team_stats.four_factor_index_wz = wz
            team_stats.four_factor_index_100 = ffi_100
            team_stats.save()
        
        # Compute rankings (1 = best/highest score)
        ranked_teams = TeamSeasonStats.objects.filter(
            season=season,
            four_factor_index_100__isnull=False
        ).order_by('-four_factor_index_100')
        
        for rank, team_stats in enumerate(ranked_teams, start=1):
            team_stats.rank_four_factor_index_100 = rank
            team_stats.save(update_fields=['rank_four_factor_index_100'])
        
        self.stdout.write(f'  Computed for {teams.count()} teams')
        self.stdout.write(f'  Rankings: #1 = {ranked_teams.first().team.name} ({ranked_teams.first().four_factor_index_100:.1f})')