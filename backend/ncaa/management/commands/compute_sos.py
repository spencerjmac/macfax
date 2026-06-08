"""
Management command to compute Strength of Schedule (SOS) for all teams

SOS is computed as "Expected Win% for an average D1 team"
Lower win% = harder schedule → lower rank number

Algorithm:
1. Baseline team: AdjEM = 0.0 (average D1 team)
2. For each game: compute win prob using standard model
   diff = baseline_adjEM - opp_adjEM + site_adj
   p = 1 / (1 + EXP(-diff / SIGMA))
3. SOS_win_pct = AVERAGE(p_i) across all games
4. Rank by ascending SOS_win_pct (hardest = rank 1)

Constants:
- SIGMA = 10.0 (spread parameter)
- Site adjustments: HOME +1.5, NEUTRAL 0.0, AWAY -1.5
"""

from django.core.management.base import BaseCommand
from django.db.models import Count
from ncaa.models import TeamSeasonRatings, TeamGameStats, Season
import math


class Command(BaseCommand):
    help = 'Compute Strength of Schedule (SOS) for all teams'

    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            default=2026,
            help='Season year to compute SOS for (default: 2026)'
        )
        parser.add_argument(
            '--pre_tournament',
            action='store_true',
            help='If set, computes SOS using only games up to Selection Sunday'
        )

    def handle(self, *args, **options):
        from ncaa.models import PipelineConfig
        cfg = PipelineConfig.get_config()

        season_year = options['season']

        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Season {season_year} not found'))
            return

        is_pre_tournament = options.get('pre_tournament', False)

        # Constants from config
        BASELINE_ADJEM = cfg.sos_baseline_adjem
        SIGMA = cfg.sos_logistic_sigma
        SITE_ADJ = {
            'H': cfg.sos_home_advantage,
            'N': 0.0,
            'A': -cfg.sos_away_penalty,
        }

        self.stdout.write(f'\n{"="*60}')
        mode_str = "(Pre-Tournament)" if is_pre_tournament else "(Full Season)"
        self.stdout.write(f'Computing SOS for {season.display_name} {mode_str}')
        self.stdout.write(f'{"="*60}')
        self.stdout.write(f'Baseline team: AdjEM = {BASELINE_ADJEM:.2f} (average D1)')
        self.stdout.write(f'SIGMA = {SIGMA:.2f}')
        self.stdout.write(f'Site adjustments: HOME +{SITE_ADJ["H"]:.1f}, NEUTRAL {SITE_ADJ["N"]:.1f}, AWAY {SITE_ADJ["A"]:.1f}')
        self.stdout.write(f'{"="*60}\n')

        # Get all teams with ratings for this season
        teams_with_ratings = TeamSeasonRatings.all_objects.filter(
            season=season,
            rank_adj_em__isnull=False,
            is_pre_tournament=is_pre_tournament
        ).select_related('team').order_by('rank_adj_em')

        if not teams_with_ratings.exists():
            self.stdout.write(self.style.ERROR('No teams with ratings found'))
            return

        sos_results = []

        for team_ratings in teams_with_ratings:
            team = team_ratings.team
            
            # Get all games for this team this season
            games = TeamGameStats.objects.filter(
                team=team,
                game__season_year=season_year,
                opponent__isnull=False,
                game__status='final'
            ).select_related('opponent', 'game')

            if is_pre_tournament and season.selection_sunday_date:
                games = games.filter(game__game_date__lte=season.selection_sunday_date)

            if not games.exists():
                self.stdout.write(self.style.WARNING(f'⚠️  {team.name}: No games found'))
                continue

            win_probs = []
            
            for game_stat in games:
                # Get opponent's AdjEM
                try:
                    opp_ratings = TeamSeasonRatings.all_objects.get(
                        team=game_stat.opponent,
                        season=season,
                        is_pre_tournament=is_pre_tournament
                    )
                    opp_adjem = opp_ratings.adj_em or 0.0
                except TeamSeasonRatings.DoesNotExist:
                    # If opponent has no ratings, skip this game
                    continue

                # Determine site adjustment
                site_adj = SITE_ADJ.get(game_stat.home_away, 0.0)

                # Compute win probability for baseline team
                diff = BASELINE_ADJEM - opp_adjem + site_adj
                win_prob = 1.0 / (1.0 + math.exp(-diff / SIGMA))
                
                win_probs.append(win_prob)

            if not win_probs:
                self.stdout.write(self.style.WARNING(f'⚠️  {team.name}: No valid games with opponent ratings'))
                continue

            # SOS = average win probability
            sos_win_pct = sum(win_probs) / len(win_probs)
            
            sos_results.append({
                'team': team,
                'team_ratings': team_ratings,
                'sos_win_pct': sos_win_pct,
                'games_counted': len(win_probs)
            })

        if not sos_results:
            self.stdout.write(self.style.ERROR('No SOS results computed'))
            return

        # Sort by SOS win% (ascending = hardest schedule first)
        sos_results.sort(key=lambda x: x['sos_win_pct'])

        # Assign ranks
        for rank, result in enumerate(sos_results, start=1):
            result['rank'] = rank

        # Update database
        updated_count = 0
        for result in sos_results:
            result['team_ratings'].sos_win_pct = result['sos_win_pct']
            result['team_ratings'].sos_rank = result['rank']
            result['team_ratings'].save(update_fields=['sos_win_pct', 'sos_rank'])
            updated_count += 1

        self.stdout.write(self.style.SUCCESS(f'\n✅ Updated {updated_count} teams with SOS rankings'))

        # Display top 10 hardest schedules
        self.stdout.write(f'\n{"="*80}')
        self.stdout.write('TOP 10 HARDEST SCHEDULES (Lowest Expected Win%)')
        self.stdout.write(f'{"="*80}')
        self.stdout.write(f'{"Rank":<6} {"Team":<30} {"SOS Win%":<12} {"Games":<8}')
        self.stdout.write(f'{"-"*80}')
        
        for result in sos_results[:10]:
            self.stdout.write(
                f'{result["rank"]:<6} '
                f'{result["team"].name:<30} '
                f'{result["sos_win_pct"]*100:>6.2f}%     '
                f'{result["games_counted"]:<8}'
            )

        # Display bottom 10 easiest schedules
        self.stdout.write(f'\n{"="*80}')
        self.stdout.write('BOTTOM 10 EASIEST SCHEDULES (Highest Expected Win%)')
        self.stdout.write(f'{"="*80}')
        self.stdout.write(f'{"Rank":<6} {"Team":<30} {"SOS Win%":<12} {"Games":<8}')
        self.stdout.write(f'{"-"*80}')
        
        for result in sos_results[-10:]:
            self.stdout.write(
                f'{result["rank"]:<6} '
                f'{result["team"].name:<30} '
                f'{result["sos_win_pct"]*100:>6.2f}%     '
                f'{result["games_counted"]:<8}'
            )

        self.stdout.write(f'\n{"="*80}')
        self.stdout.write(self.style.SUCCESS('✅ SOS computation complete!'))
        self.stdout.write(f'{"="*80}\n')
