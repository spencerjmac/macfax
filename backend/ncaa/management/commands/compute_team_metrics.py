"""
Management command: compute_team_metrics
Computes aggregated season metrics from game logs

Features:
- Per-game derived metrics (possessions, ORtg, DRtg, eFG%, etc.)
- Season aggregates (totals, per-game, per-possession)
- Four Factors and margins
- Kill Shots analysis from scoring sequences

Usage:
    python manage.py compute_team_metrics --season 2026
"""

import logging
from collections import defaultdict
from typing import Dict, List, Tuple

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q, Count, Sum, Avg
from django.db import transaction

from ncaa.models import (
    Season,
    Team,
    Game,
    TeamGameStats,
    ScoringEvent,
    TeamSeasonMetrics,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Compute team season metrics from game logs"

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=int,
            required=True,
            help="Season year (ending year, e.g., 2026)",
        )
        parser.add_argument(
            "--teams", nargs="+", help="Specific team slugs to process (default: all)"
        )
        parser.add_argument(
            "--pre-tournament",
            action="store_true",
            help="If set, only compute metrics for games on or before Selection Sunday.",
        )

    def handle(self, *args, **options):
        season_year = options["season"]
        team_slugs = options.get("teams")
        is_pre_tournament = options["pre_tournament"]

        # Get season
        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            raise CommandError(f"Season {season_year} not found")

        # Get teams to process (D1 only)
        teams_qs = Team.objects.filter(is_d1=True)
        if team_slugs:
            teams_qs = teams_qs.filter(slug__in=team_slugs)

        teams = list(teams_qs)

        if not teams:
            raise CommandError("No teams found to process")

        self.stdout.write(
            self.style.SUCCESS(
                f"\n{'='*60}\n"
                f"COMPUTING TEAM METRICS: {season.display_name}\n"
                f"Teams: {len(teams)}\n"
                f"{'='*60}\n"
            )
        )

        # Process each team
        processed = 0
        errors = 0

        for team in teams:
            try:
                self._compute_team_season_metrics(team, season, is_pre_tournament)
                processed += 1
                self.stdout.write(f"  OK - {team.name}")
            except Exception as e:
                errors += 1
                logger.error(f"Error processing {team.name}: {e}", exc_info=True)
                self.stdout.write(self.style.ERROR(f"  ERROR - {team.name}: {e}"))

        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{'='*60}\n"
                f"COMPLETE\n"
                f"Processed: {processed}\n"
                f"Errors: {errors}\n"
                f"{'='*60}\n"
            )
        )

    def _compute_team_season_metrics(self, team: Team, season: Season, is_pre_tournament: bool):
        """Compute all metrics for a team-season"""
        # Base filter
        filters = Q(
            team=team,
            game__season_year=season.year,
            game__status="final",
            opponent__is_d1=True,  # Only include games vs D1 opponents
        )
        
        # Exclude canceled games (where both teams scored 0 points despite 'final' status)
        filters &= ~Q(game__home_score=0, game__away_score=0)
        
        if is_pre_tournament and season.selection_sunday_date:
            filters &= Q(game__game_date__lte=season.selection_sunday_date)
            
        # Get all games for this team (D1 vs D1 only for metrics)
        game_stats = (
            TeamGameStats.objects.filter(filters)
            .select_related("game", "opponent")
            .order_by("game__game_date")
        )

        if not game_stats.exists():
            logger.warning(f"No game stats found for {team.name} in {season.year}")
            return

        # Compute aggregates
        totals = self._compute_totals(game_stats)

        # Compute kill shots
        kill_shots_data = self._compute_kill_shots(team, season, is_pre_tournament)

        # Compute derived metrics
        metrics = self._compute_derived_metrics(totals, kill_shots_data)

        # Save to DB
        metrics["is_pre_tournament"] = is_pre_tournament
        TeamSeasonMetrics.all_objects.update_or_create(
            team=team, season=season, is_pre_tournament=is_pre_tournament, defaults=metrics
        )

    def _compute_totals(self, game_stats) -> Dict:
        """Compute season totals from game stats"""
        totals = {
            "games": 0,
            "total_pts": 0,
            "total_pts_allowed": 0,
            "total_possessions": 0.0,
            "total_opp_possessions": 0.0,
            "total_fgm": 0,
            "total_fga": 0,
            "total_fg3m": 0,
            "total_fg3a": 0,
            "total_ftm": 0,
            "total_fta": 0,
            "total_oreb": 0,
            "total_dreb": 0,
            "total_reb": 0,
            "total_opp_dreb": 0,
            "total_opp_oreb": 0,
            # Opponent offensive stats for opp_efg_pct, opp_tov_pct, opp_ftr
            "total_opp_fgm": 0,
            "total_opp_fga": 0,
            "total_opp_fg3m": 0,
            "total_opp_fta": 0,
            "total_opp_tov": 0,
            "total_ast": 0,
            "total_stl": 0,
            "total_blk": 0,
            "total_tov": 0,
            "total_pf": 0,
        }

        for gs in game_stats:
            totals["games"] += 1
            totals["total_pts"] += gs.pts
            totals["total_fgm"] += gs.fgm
            totals["total_fga"] += gs.fga
            totals["total_fg3m"] += gs.fg3m
            totals["total_fg3a"] += gs.fg3a
            totals["total_ftm"] += gs.ftm
            totals["total_fta"] += gs.fta
            totals["total_oreb"] += gs.oreb
            totals["total_dreb"] += gs.dreb
            totals["total_reb"] += gs.reb
            totals["total_ast"] += gs.ast
            totals["total_stl"] += gs.stl
            totals["total_blk"] += gs.blk
            totals["total_tov"] += gs.tov
            totals["total_pf"] += gs.pf

            # Possessions (team)
            poss = gs.possessions_est
            totals["total_possessions"] += poss

            # Get opponent stats for defensive metrics
            opp_stats = TeamGameStats.objects.filter(
                game=gs.game, team=gs.opponent
            ).first()

            if opp_stats:
                totals["total_pts_allowed"] += opp_stats.pts
                totals["total_opp_dreb"] += opp_stats.dreb
                totals["total_opp_oreb"] += opp_stats.oreb
                totals["total_opp_possessions"] += opp_stats.possessions_est
                # Track opponent offensive stats
                totals["total_opp_fgm"] += opp_stats.fgm
                totals["total_opp_fga"] += opp_stats.fga
                totals["total_opp_fg3m"] += opp_stats.fg3m
                totals["total_opp_fta"] += opp_stats.fta
                totals["total_opp_tov"] += opp_stats.tov

        return totals

    def _compute_kill_shots(self, team: Team, season: Season, is_pre_tournament: bool) -> Dict:
        """
        Compute Kill Shots from scoring events

        Kill Shot: When a team goes on a run of 10+ points before opponent scores
        Algorithm:
        - Iterate through scoring events in order
        - Track current run for each team
        - When run first reaches >=10, count 1 kill shot
        - Reset run when opponent scores
        """
        kill_shots_for = 0
        kill_shots_against = 0

        # Base filters
        filters = Q(home_team=team) | Q(away_team=team)
        
        games_qs = Game.objects.filter(
            filters,
            season_year=season.year,
            status="final",
        )
        
        if is_pre_tournament and season.selection_sunday_date:
            games_qs = games_qs.filter(game_date__lte=season.selection_sunday_date)

        # Get all games for this team
        games = games_qs

        for game in games:
            # Get scoring events in order
            events = ScoringEvent.objects.filter(game=game).order_by("seq")

            if not events.exists():
                continue

            # Determine opponent
            opponent = game.away_team if game.home_team == team else game.home_team

            # Track runs
            team_run = 0
            opp_run = 0
            team_kill_shot_awarded = False
            opp_kill_shot_awarded = False

            for event in events:
                if event.scoring_team == team:
                    # Team scores
                    team_run += event.points
                    opp_run = 0  # Reset opponent run
                    opp_kill_shot_awarded = False  # Reset opponent flag

                    # Check for kill shot
                    if team_run >= 10 and not team_kill_shot_awarded:
                        kill_shots_for += 1
                        team_kill_shot_awarded = True

                elif event.scoring_team == opponent:
                    # Opponent scores
                    opp_run += event.points
                    team_run = 0  # Reset team run
                    team_kill_shot_awarded = False  # Reset team flag

                    # Check for opponent kill shot
                    if opp_run >= 10 and not opp_kill_shot_awarded:
                        kill_shots_against += 1
                        opp_kill_shot_awarded = True

        return {
            "kill_shots_for": kill_shots_for,
            "kill_shots_against": kill_shots_against,
        }

    def _compute_derived_metrics(self, totals: Dict, kill_shots_data: Dict) -> Dict:
        """Compute all derived metrics"""
        games = totals["games"]

        if games == 0:
            return {}

        # Per-game averages
        ppg = totals["total_pts"] / games
        papg = totals["total_pts_allowed"] / games
        pace = totals["total_possessions"] / games

        # Per-possession metrics (per 100 possessions)
        total_poss = totals["total_possessions"]
        total_opp_poss = totals["total_opp_possessions"]

        ortg = 100 * (totals["total_pts"] / total_poss) if total_poss > 0 else 0
        drtg = (
            100 * (totals["total_pts_allowed"] / total_opp_poss)
            if total_opp_poss > 0
            else 0
        )
        net_rtg = ortg - drtg

        # Four Factors - Offense
        fga = totals["total_fga"]
        fgm = totals["total_fgm"]
        fg3m = totals["total_fg3m"]
        fta = totals["total_fta"]
        oreb = totals["total_oreb"]
        dreb = totals["total_dreb"]
        opp_dreb = totals["total_opp_dreb"]
        opp_oreb = totals["total_opp_oreb"]
        tov = totals["total_tov"]

        efg_pct = ((fgm + 0.5 * fg3m) / fga * 100) if fga > 0 else 0
        tov_pct = (tov / total_poss * 100) if total_poss > 0 else 0
        orb_pct = (oreb / (oreb + opp_dreb) * 100) if (oreb + opp_dreb) > 0 else 0
        ftr = (fta / fga * 100) if fga > 0 else 0

        # Opponent Four Factors
        # Opponent ORB% = Opponent OREB / (Opponent OREB + Team DREB)
        opp_orb_pct = (
            (opp_oreb / (opp_oreb + dreb) * 100) if (opp_oreb + dreb) > 0 else 0
        )

        # Opponent offensive stats
        opp_fgm = totals["total_opp_fgm"]
        opp_fga = totals["total_opp_fga"]
        opp_fg3m = totals["total_opp_fg3m"]
        opp_fta = totals["total_opp_fta"]
        opp_tov = totals["total_opp_tov"]

        opp_efg_pct = ((opp_fgm + 0.5 * opp_fg3m) / opp_fga * 100) if opp_fga > 0 else 0
        opp_tov_pct = (opp_tov / total_opp_poss * 100) if total_opp_poss > 0 else 0
        drb_pct = (dreb / (dreb + opp_oreb) * 100) if (dreb + opp_oreb) > 0 else 0
        opp_ftr = (opp_fta / opp_fga * 100) if opp_fga > 0 else 0

        # Four Factor Margins
        efg_margin = efg_pct - opp_efg_pct
        tov_edge = opp_tov_pct - tov_pct
        reb_edge = orb_pct - opp_orb_pct  # Correct: ORB% - Opponent ORB%
        ftr_margin = ftr - opp_ftr

        # Kill Shots per game
        kill_shots_pg = kill_shots_data["kill_shots_for"] / games
        kill_shots_conceded_pg = kill_shots_data["kill_shots_against"] / games
        kill_shot_margin_pg = kill_shots_pg - kill_shots_conceded_pg

        # CBB Analytics stats
        ast_g = totals["total_ast"] / games
        blk_g = totals["total_blk"] / games
        # AST% = AST / FGM (simplified)
        ast_pct = (totals["total_ast"] / fgm * 100) if fgm > 0 else 0
        # BLK% = placeholder (needs opponent FGA)
        blk_pct = None
        # DPF = defensive personal fouls (simplified as opponent FTA)
        dpf_g = totals["total_pf"] / games  # Placeholder

        return {
            "games": games,
            # Team totals (only fields that exist in model)
            "total_pts": totals["total_pts"],
            "total_pts_allowed": totals["total_pts_allowed"],
            "total_possessions": totals["total_possessions"],
            "total_opp_possessions": totals["total_opp_possessions"],
            "total_fgm": totals["total_fgm"],
            "total_fga": totals["total_fga"],
            "total_fg3m": totals["total_fg3m"],
            "total_fg3a": totals["total_fg3a"],
            "total_ftm": totals["total_ftm"],
            "total_fta": totals["total_fta"],
            "total_oreb": totals["total_oreb"],
            "total_dreb": totals["total_dreb"],
            "total_reb": totals["total_reb"],
            "total_opp_dreb": totals["total_opp_dreb"],
            "total_ast": totals["total_ast"],
            "total_stl": totals["total_stl"],
            "total_blk": totals["total_blk"],
            "total_tov": totals["total_tov"],
            "total_pf": totals["total_pf"],
            # Per-game averages
            "ppg": ppg,
            "papg": papg,
            "pace": pace,
            # Ratings
            "ortg": ortg,
            "drtg": drtg,
            "net_rtg": net_rtg,
            # Four Factors - Offense
            "efg_pct": efg_pct,
            "tov_pct": tov_pct,
            "orb_pct": orb_pct,
            "ftr": ftr,
            # Four Factors - Defense
            "opp_efg_pct": opp_efg_pct,
            "opp_tov_pct": opp_tov_pct,
            "opp_orb_pct": opp_orb_pct,
            "drb_pct": drb_pct,
            "opp_ftr": opp_ftr,
            # Margins
            "efg_margin": efg_margin,
            "tov_edge": tov_edge,
            "reb_edge": reb_edge,
            "ftr_margin": ftr_margin,
            # Kill Shots
            **kill_shots_data,
            "kill_shots_pg": kill_shots_pg,
            "kill_shots_conceded_pg": kill_shots_conceded_pg,
            "kill_shot_margin_pg": kill_shot_margin_pg,
            # CBB Analytics
            "ast_g": ast_g,
            "ast_pct": ast_pct,
            "blk_g": blk_g,
            "blk_pct": blk_pct,
            "dpf_g": dpf_g,
        }
