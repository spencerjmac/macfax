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

The same loop over each schedule (D1 opponents; full season, or up to Selection Sunday with
--pre_tournament) also writes:
- nc_sos_win_pct / nc_sos_rank: the SOS above over non-conference regular-season games only:
  conference from TeamSeasonMetrics (independents have none), and nothing after Selection Sunday, so
  NCAA tournament / NIT games are not part of the non-conference schedule (as KenPom's NCSOS; with
  them r vs KenPom 2026 was 0.899, without 0.954).
- opp_adj_em / opp_adj_o / opp_adj_d: mean stored ratings of the opponents in games with a result.
Canceled games (stored as 'final' 0-0) are left out of all of it, SOS included.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from ncaa.models import TeamSeasonMetrics, TeamSeasonRatings, TeamGameStats, Season
import math
from ncaa.seasons import resolve_season_year
from ncaa.utils.d1 import d1_q


# Written by compute_sos besides sos_win_pct / sos_rank
SCHEDULE_FIELDS = ['opp_adj_em', 'opp_adj_o', 'opp_adj_d', 'nc_sos_win_pct', 'nc_sos_rank']
INDEPENDENT = 'Independent'


def season_conferences(season) -> dict:
    """{team_id: conference_id} for the season, from TeamSeasonMetrics (every D1 team-season has one).

    Independents have no conference: a game between two of them is non-conference.
    """
    rows = (TeamSeasonMetrics.all_objects.filter(season=season, conference__isnull=False)
            .exclude(conference__name=INDEPENDENT)
            .order_by('is_pre_tournament')          # full-season row first
            .values_list('team_id', 'conference_id'))
    out = {}
    for team_id, conf_id in rows:
        out.setdefault(team_id, conf_id)
    return out


class Command(BaseCommand):
    help = 'Compute Strength of Schedule (SOS) for all teams'

    def add_arguments(self, parser):
        parser.add_argument(
            '--season', type=int, default=None,
            help='Season year to compute SOS for (default: the season in play)',
        )
        parser.add_argument(
            '--pre_tournament',
            action='store_true',
            help='If set, computes SOS using only games up to Selection Sunday'
        )

    def handle(self, *args, **options):
        from ncaa.models import PipelineConfig
        cfg = PipelineConfig.get_config()

        season_year = resolve_season_year(options['season'])

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
        teams_with_ratings = list(TeamSeasonRatings.all_objects.filter(
            d1_q(season, "team"),
            season=season,
            rank_adj_em__isnull=False,
            is_pre_tournament=is_pre_tournament
        ).select_related('team').order_by('rank_adj_em'))

        if not teams_with_ratings:
            self.stdout.write(self.style.ERROR('No teams with ratings found'))
            return

        # Opponent ratings: any row of this season and mode (as the per-game lookup did before)
        ratings_by_team = {
            r.team_id: r for r in TeamSeasonRatings.all_objects.filter(
                season=season, is_pre_tournament=is_pre_tournament)
        }
        conference_of = season_conferences(season)


        sos_results = []
        nc_results = []

        for team_ratings in teams_with_ratings:
            team = team_ratings.team

            # Get all games for this team this season
            games = TeamGameStats.objects.filter(
                d1_q(season, "opponent"),   # D1-vs-D1 games only (membership that season)
                team=team,
                game__season_year=season_year,
                opponent__isnull=False,
                game__status='final'
            ).exclude(
                # Canceled games stored as 'final' 0-0 (same filter as compute_wab / compute_adjusted_ratings)
                game__home_score=0, game__away_score=0,
            ).select_related('game')

            if is_pre_tournament and season.selection_sunday_date:
                games = games.filter(game__game_date__lte=season.selection_sunday_date)

            games = list(games)
            if not games:
                self.stdout.write(self.style.WARNING(f'⚠️  {team.name}: No games found'))
                continue

            win_probs = []      # SOS: baseline team vs each opponent
            nc_win_probs = []   # the same, non-conference games only
            opp_rows = []       # opponents' stored ratings, games with a result
            team_conf = conference_of.get(team.id)

            for game_stat in games:
                opp_ratings = ratings_by_team.get(game_stat.opponent_id)
                if opp_ratings is None:
                    # If opponent has no ratings, skip this game
                    continue
                opp_adjem = opp_ratings.adj_em or 0.0

                # Determine site adjustment
                site_adj = SITE_ADJ[game_stat.site_code]   # game_site: the Game's neutral flag wins

                # Compute win probability for baseline team
                diff = BASELINE_ADJEM - opp_adjem + site_adj
                win_prob = 1.0 / (1.0 + math.exp(-diff / SIGMA))

                win_probs.append(win_prob)
                regular_season = (season.selection_sunday_date is None
                                  or game_stat.game.game_date <= season.selection_sunday_date)
                if regular_season and (team_conf is None or conference_of.get(game_stat.opponent_id) != team_conf):
                    nc_win_probs.append(win_prob)

                # A game without both scores has no result
                won = game_stat.won
                if won is None:
                    continue
                opp_rows.append(opp_ratings)

            if not win_probs:
                self.stdout.write(self.style.WARNING(f'⚠️  {team.name}: No valid games with opponent ratings'))
                continue

            # SOS = average win probability
            sos_win_pct = sum(win_probs) / len(win_probs)

            n = len(opp_rows)
            team_ratings.opp_adj_em = sum(o.adj_em for o in opp_rows) / n if n else None
            team_ratings.opp_adj_o = sum(o.adj_o for o in opp_rows) / n if n else None
            team_ratings.opp_adj_d = sum(o.adj_d for o in opp_rows) / n if n else None
            team_ratings.nc_sos_win_pct = sum(nc_win_probs) / len(nc_win_probs) if nc_win_probs else None
            team_ratings.nc_sos_rank = None

            sos_results.append({
                'team': team,
                'team_ratings': team_ratings,
                'sos_win_pct': sos_win_pct,
                'games_counted': len(win_probs)
            })
            if nc_win_probs:
                nc_results.append(team_ratings)

        if not sos_results:
            self.stdout.write(self.style.ERROR('No SOS results computed'))
            return

        # Sort by SOS win% (ascending = hardest schedule first)
        sos_results.sort(key=lambda x: x['sos_win_pct'])

        # Assign ranks
        for rank, result in enumerate(sos_results, start=1):
            result['rank'] = rank
        nc_results.sort(key=lambda r: r.nc_sos_win_pct)
        for rank, r in enumerate(nc_results, start=1):
            r.nc_sos_rank = rank

        # Update database. Rows of rated D1 teams without a counted game keep nothing stale.
        counted = {r['team_ratings'].pk for r in sos_results}
        for r in teams_with_ratings:
            if r.pk not in counted:
                r.opp_adj_em = r.opp_adj_o = r.opp_adj_d = r.nc_sos_win_pct = r.nc_sos_rank = None
        for result in sos_results:
            result['team_ratings'].sos_win_pct = result['sos_win_pct']
            result['team_ratings'].sos_rank = result['rank']
        with transaction.atomic():
            TeamSeasonRatings.all_objects.bulk_update(
                [r['team_ratings'] for r in sos_results], ['sos_win_pct', 'sos_rank'], batch_size=500)
            TeamSeasonRatings.all_objects.bulk_update(teams_with_ratings, SCHEDULE_FIELDS, batch_size=500)
        updated_count = len(sos_results)

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
