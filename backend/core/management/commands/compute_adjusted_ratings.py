"""
Management command: compute_adjusted_ratings
Computes adjusted offensive/defensive ratings using iterative opponent-adjustment

Usage:
    python manage.py compute_adjusted_ratings --season 2026 --iterations 3
"""

import logging
import math
from collections import defaultdict
from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q, Count, Case, When, IntegerField, F

from core.models import (
    Season,
    Team,
    Game,
    TeamGameStats,
    TeamSeasonMetrics,
    TeamSeasonRatings,
    NationalAverages,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Compute adjusted offensive/defensive ratings (iterative)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=int,
            required=True,
            help="Season year (ending year, e.g., 2026 for 2025-26 season)",
        )
        parser.add_argument(
            "--iterations",
            type=int,
            default=None,
            help="Maximum number of iterations (default: from PipelineConfig)",
        )
        parser.add_argument(
            "--convergence",
            type=float,
            default=None,
            help="Convergence threshold for max AdjEM change (default: from PipelineConfig)",
        )
        parser.add_argument(
            "--shrinkage",
            type=float,
            default=None,
            help="Shrinkage constant in possessions (default: from PipelineConfig; auto-adjusts by schedule depth)",
        )
        parser.add_argument(
            "--recency-lambda",
            type=float,
            default=0.0040,
            help="Exponential decay rate for recency weighting (default: 0.0040; set to 0 to disable)",
        )
        parser.add_argument(
            "--no-importance",
            action="store_true",
            default=False,
            help="Disable importance weighting (default: enabled)",
        )
        parser.add_argument(
<<<<<<< HEAD
            '--imp-c',
            type=float,
            default=40.0,
            help='Importance: AdjEM gap where base weight drops to 0.5 (default: 40.0)'
        )
        parser.add_argument(
            '--imp-floor',
            type=float,
            default=0.35,
            help='Importance: minimum importance weight (default: 0.35)'
        )
        parser.add_argument(
            '--close-m',
            type=float,
            default=12.0,
            help='Importance: closeness boost scale in margin/100poss (default: 12.0)'
        )
        parser.add_argument(
            '--boost-max',
            type=float,
            default=1.40,
            help='Importance: maximum closeness boost multiplier (default: 1.40)'
        )
        parser.add_argument(
            '--update-natavg',
            action='store_true',
=======
            "--update-natavg",
            action="store_true",
>>>>>>> f30abb3a38b0de62245663674e7c4d3e39719121
            default=False,
            help="Overwrite NationalAverages.avg_ortg with mean of computed AdjO (default: off)",
        )

    def handle(self, *args, **options):
        from core.models import PipelineConfig

        cfg = PipelineConfig.get_config()

        season_year = options["season"]
        max_iterations = options["iterations"] or cfg.adj_ratings_iterations
        convergence_threshold = options["convergence"] or cfg.adj_ratings_convergence
        shrinkage_k = options[
            "shrinkage"
        ]  # None = dynamic (from cfg below), float = fixed override
        recency_lambda = options["recency_lambda"]
        importance_enabled = not options["no_importance"]
        update_natavg = options["update_natavg"]

        # --- Importance weight constants ---
<<<<<<< HEAD
        IMP_C            = options['imp_c']       # gap (AdjEM pts) where base weight drops to 0.5
        IMP_FLOOR        = options['imp_floor']   # minimum importance weight
        FREEZE_ITERATION = 6                      # freeze weights after this iteration
        CLOSE_M          = options['close_m']     # closeness scale (margin per 100 poss)
        BOOST_MAX        = options['boost_max']   # max boost for unexpectedly close mismatches
        
=======
        IMP_C = 40.0  # gap (AdjEM pts) where base weight drops to 0.5
        IMP_FLOOR = 0.35  # minimum importance weight
        FREEZE_ITERATION = 6  # freeze weights after this iteration
        CLOSE_M = 12.0  # closeness scale (margin per 100 poss)
        BOOST_MAX = 1.25  # max boost for unexpectedly close mismatches

>>>>>>> f30abb3a38b0de62245663674e7c4d3e39719121
        # Get season
        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            self.stderr.write(f"Season {season_year} not found")
            return

        # Get national averages
        try:
            nat_avg = NationalAverages.objects.get(season=season)
        except NationalAverages.DoesNotExist:
            self.stderr.write(
                f"National averages not found. Run compute_national_averages first."
            )
            return

        self.stdout.write(f"\nComputing Adjusted Ratings for {season.display_name}")
        self.stdout.write(f"National Average ORtg: {nat_avg.avg_ortg:.2f}")
        self.stdout.write(f"National Average Pace: {nat_avg.avg_pace:.2f}")
        self.stdout.write(f"Max Iterations: {max_iterations}")
        self.stdout.write(f"Convergence Threshold: {convergence_threshold}")
        if recency_lambda > 0:
            self.stdout.write(
                f"Recency Lambda: {recency_lambda} (half-life ≈ {math.log(2)/recency_lambda:.0f} days)"
            )
        else:
            self.stdout.write("Recency Weighting: disabled (λ=0)")
        self.stdout.write(
            f"Importance Weighting: {'enabled' if importance_enabled else 'disabled'} "
            f"(IMP_C={IMP_C}, IMP_FLOOR={IMP_FLOOR}, freeze@iter {FREEZE_ITERATION})"
        )

        # Get all D1 teams with season metrics
        teams = Team.objects.filter(season_metrics__season=season, is_d1=True)

        if teams.count() == 0:
            self.stderr.write("No teams found with season metrics")
            return

        num_d1_teams = teams.count()

        # Calculate dynamic shrinkage k based on average games played
        # Count team-games (NOT matchups - each game counts twice, once per team)
        team_games_count = TeamGameStats.objects.filter(
            game__season_year=season_year,
            game__status="final",
            opponent__is_d1=True,
            team__is_d1=True,
        ).count()

        avg_games_played = team_games_count / num_d1_teams if num_d1_teams > 0 else 0
<<<<<<< HEAD
        
        # Dynamic k: starts at 300, decays to floor of 150
        # At 16 games (midseason): k ≈ 200
        # At ~24+ games: k = 150 (floor)
=======

        # Dynamic k: starts at 300, decays to floor of 150
        # At 16 games (midseason): k ≈ 200
        # At 21+ games: k = 150 (floor)
>>>>>>> f30abb3a38b0de62245663674e7c4d3e39719121
        # Clamped between 150 and 300 for safety
        if shrinkage_k is None:  # dynamic schedule using PipelineConfig bounds
            shrinkage_k = min(
                cfg.adj_ratings_shrinkage_ceiling,
                max(
                    cfg.adj_ratings_shrinkage_floor,
                    cfg.adj_ratings_shrinkage_ceiling
                    - (avg_games_played * cfg.adj_ratings_shrinkage_decay),
                ),
            )
            self.stdout.write(
                f"Dynamic Shrinkage: k={shrinkage_k:.1f} (avg {avg_games_played:.1f} games/team)"
            )
        else:
            self.stdout.write(
                f"Fixed Shrinkage: k={shrinkage_k:.1f} possessions (user override)"
            )

        self.stdout.write("=" * 60)
        self.stdout.write(f"Processing {num_d1_teams} teams...")

        # --- Recency weighting precomputation (done once, outside iterations) ---
        game_time_weights = {}
        team_time_scale = {}

        if recency_lambda > 0:
            today = date.today()

            # Exponential decay weight per game
            for g in Game.objects.filter(
                season_year=season_year, status="final"
            ).values("id", "game_date"):
                days_ago = max(0, (today - g["game_date"]).days)
                game_time_weights[g["id"]] = math.exp(-recency_lambda * days_ago)
            self.stdout.write(
                f"\nPre-computed recency weights for {len(game_time_weights)} games"
            )

            # Per-team rescale factor: keeps sum(poss * w_time * scale) == sum(poss)
            # so shrinkage denominator stays calibrated to real possessions.
            sum_poss: defaultdict = defaultdict(float)
            sum_poss_w: defaultdict = defaultdict(float)
            for row in TeamGameStats.objects.filter(
                game__season_year=season_year,
                game__status="final",
                team__is_d1=True,
                opponent__is_d1=True,
            ).values("team_id", "game_id", "fga", "oreb", "tov", "fta"):
                poss = row["fga"] - row["oreb"] + row["tov"] + 0.475 * (row["fta"] or 0)
                w = game_time_weights.get(row["game_id"], 1.0)
                sum_poss[row["team_id"]] += poss
                sum_poss_w[row["team_id"]] += poss * w

            for tid, total_poss in sum_poss.items():
                denom = sum_poss_w[tid]
                scale = (total_poss / denom) if denom > 0 else 1.0
                team_time_scale[tid] = max(0.80, min(1.25, scale))
            self.stdout.write(
                f"Computed recency rescale factors for {len(team_time_scale)} teams"
            )
        else:
            self.stdout.write(
                "\nRecency weighting disabled — using uniform game weights"
            )
        # -----------------------------------------------------------------------

        # Initialize ratings dictionary {team_id: {'aor': float, 'adr': float, 'pace': float}}
        ratings = {}

        # Step 1: Initialize with raw ORtg/DRtg/Pace
        self.stdout.write("\n[1/1] Initializing with raw ratings...")
        for team in teams:
            metrics = TeamSeasonMetrics.objects.get(team=team, season=season)
            ratings[team.id] = {
                "aor": metrics.ortg,
                "adr": metrics.drtg,
                "pace": metrics.pace,
            }

        # Importance weight storage
        frozen_importance_weights: dict = {}  # locked after FREEZE_ITERATION
        current_importance_weights: dict = {}  # accumulated during early iterations
        team_imp_scale: dict = (
            {}
        )  # per-team rescale so Σ(poss*w_time*w_imp) ≈ Σ(poss*w_time)

        # Step 2: Iterate until convergence
        converged = False
        iteration = 0

        for iteration in range(1, max_iterations + 1):
            self.stdout.write(f"\n[Iteration {iteration}]")

            new_ratings = {}
            max_aem_change = 0.0

            for team in teams:
                # Get all games for this team (D1 vs D1 only)
                games = TeamGameStats.objects.filter(
                    team=team,
                    game__season_year=season_year,
                    game__status="final",
                    opponent__is_d1=True,  # Only include games vs D1 opponents
                ).select_related("game", "opponent")

                if games.count() == 0:
                    continue

                # Pre-fetch opponent stats for all games (optimize: single query instead of N queries)
                game_ids = [g.game_id for g in games]
                all_game_stats = TeamGameStats.objects.filter(
                    game_id__in=game_ids
                ).select_related("team")

                # Build dict: (game_id, team_id) -> stats
                stats_lookup = {(gs.game_id, gs.team_id): gs for gs in all_game_stats}

                # Compute game-level adjusted ratings
                sum_weighted_aor = 0.0
                sum_weighted_adr = 0.0
                sum_weighted_pace = 0.0
                sum_weights = 0.0

                for game_stat in games:
                    # Get opponent's current ratings
                    opp_id = game_stat.opponent.id
                    if opp_id not in ratings:
                        continue  # Skip if opponent has no ratings

                    opp_aor = ratings[opp_id]["aor"]
                    opp_adr = ratings[opp_id]["adr"]
                    opp_pace = ratings[opp_id]["pace"]

                    # Get game possessions (use poss_team directly to avoid property queries)
                    poss_g = game_stat.poss_team
                    if not poss_g or poss_g == 0:
                        continue

                    # Get opponent stats for this game (use dict lookup)
                    opp_stats = stats_lookup.get(
                        (game_stat.game_id, game_stat.opponent_id)
                    )

                    if not opp_stats:
                        continue

                    # Calculate raw game efficiencies and pace manually
                    raw_oe_g = 100 * game_stat.pts / poss_g if poss_g > 0 else None
                    raw_de_g = 100 * opp_stats.pts / poss_g if poss_g > 0 else None
                    minutes = game_stat.game_minutes or 40
                    raw_pace_g = 40 * poss_g / minutes if minutes > 0 else None

                    if raw_oe_g is None or raw_de_g is None or raw_pace_g is None:
                        continue

                    # Get site factors (different for offense vs defense)
                    off_site_factor = (
                        game_stat.site_factor
                    )  # Home: 0.9862, Away: 1.0140
                    def_site_factor = (
                        game_stat.defensive_site_factor
                    )  # Home: 1.0140, Away: 0.9862

                    # Compute adjusted game ratings
                    # AOR_g = RawOE_g * (NatAvg / OppAdjD) * OffSiteFactor
                    aor_g = (
                        raw_oe_g * (nat_avg.avg_ortg / opp_adr) * off_site_factor
                        if opp_adr > 0
                        else raw_oe_g
                    )

                    # ADR_g = RawDE_g * (NatAvg / OppAdjO) * DefSiteFactor
                    adr_g = (
                        raw_de_g * (nat_avg.avg_ortg / opp_aor) * def_site_factor
                        if opp_aor > 0
                        else raw_de_g
                    )

                    # AdjPace_g = RawPace_g * (NatAvgPace / OppPace)
                    # Note: Site factor is typically not applied to pace
                    pace_g = (
                        raw_pace_g * (nat_avg.avg_pace / opp_pace)
                        if opp_pace > 0
                        else raw_pace_g
                    )

                    # Weight by possessions * recency (w_time=1.0 when recency disabled)
                    w_time = (
                        (
                            game_time_weights.get(game_stat.game_id, 1.0)
                            * team_time_scale.get(game_stat.team_id, 1.0)
                        )
                        if recency_lambda > 0
                        else 1.0
                    )

                    # --- Importance weight ---
                    imp_key = (team.id, game_stat.game_id)
                    if not importance_enabled:
                        w_imp = 1.0
                    elif iteration <= FREEZE_ITERATION:
                        # Compute from current ratings
                        team_aem = (
                            (ratings[team.id]["aor"] - ratings[team.id]["adr"])
                            if team.id in ratings
                            else 0.0
                        )
                        opp_aem = opp_aor - opp_adr
                        gap = abs(team_aem - opp_aem)

                        # Lorentzian base: smooth downweight for mismatches
                        base = 1.0 / (1.0 + (gap / IMP_C) ** 2)
                        base = max(IMP_FLOOR, base)

                        # Closeness boost: use site-adjusted margin (aor_g - adr_g) so the
                        # observed performance is in the same neutral world as the expected margin.
                        obs_margin_100 = aor_g - adr_g
                        exp_margin_100 = team_aem - opp_aem
                        
                        closer_than_expected = max(0.0, abs(exp_margin_100) - abs(obs_margin_100))
                        closeness_factor = 1.0 - math.exp(-closer_than_expected / CLOSE_M)
                        
                        boost = 1.0 + (BOOST_MAX - 1.0) * closeness_factor

                        w_imp = min(1.0, base * boost)

                        current_importance_weights[imp_key] = w_imp
                    else:
                        # After freeze: reuse locked weights
                        w_imp = frozen_importance_weights.get(imp_key, 1.0)

                    weight = poss_g * w_time * w_imp * team_imp_scale.get(team.id, 1.0)

                    sum_weighted_aor += weight * aor_g
                    sum_weighted_adr += weight * adr_g
                    sum_weighted_pace += weight * pace_g
                    sum_weights += weight

                # Aggregate to season rating with shrinkage
                # AOR = (SUM(w*AOR_g) + k*NatAvg) / (SUM(w) + k)
                if sum_weights > 0:
                    aor_season = (sum_weighted_aor + shrinkage_k * nat_avg.avg_ortg) / (
                        sum_weights + shrinkage_k
                    )
                    adr_season = (sum_weighted_adr + shrinkage_k * nat_avg.avg_ortg) / (
                        sum_weights + shrinkage_k
                    )
                    pace_season = (
                        sum_weighted_pace + shrinkage_k * nat_avg.avg_pace
                    ) / (sum_weights + shrinkage_k)
                else:
                    aor_season = nat_avg.avg_ortg
                    adr_season = nat_avg.avg_ortg
                    pace_season = nat_avg.avg_pace

                new_ratings[team.id] = {
                    "aor": aor_season,
                    "adr": adr_season,
                    "pace": pace_season,
                }

                # Track max change in AdjEM for convergence check
                if team.id in ratings:
                    old_aem = ratings[team.id]["aor"] - ratings[team.id]["adr"]
                    new_aem = aor_season - adr_season
                    aem_change = abs(new_aem - old_aem)
                    max_aem_change = max(max_aem_change, aem_change)

            # Freeze importance weights after FREEZE_ITERATION
            if importance_enabled and iteration == FREEZE_ITERATION:
                frozen_importance_weights = dict(current_importance_weights)
                self.stdout.write(
                    f"  ✓ Importance weights frozen ({len(frozen_importance_weights)} team-game entries)"
                )

                # Compute per-team importance rescale so Σ(poss*w_time*w_imp*scale) == Σ(poss*w_time)
                # This prevents w_imp < 1 from silently tightening the Bayesian prior.
                # Note: poss_team is a @property, so we recompute from box score fields.
                sum_base: defaultdict = defaultdict(float)
                sum_weighted_imp: defaultdict = defaultdict(float)
                for row in TeamGameStats.objects.filter(
                    game__season_year=season_year,
                    game__status="final",
                    team__is_d1=True,
                    opponent__is_d1=True,
                ).values("team_id", "game_id", "fga", "oreb", "tov", "fta"):
                    tid = row["team_id"]
                    gid = row["game_id"]
                    poss = (
                        row["fga"]
                        - row["oreb"]
                        + row["tov"]
                        + 0.475 * (row["fta"] or 0)
                    )
                    if poss <= 0:
                        continue
                    w_t = (
                        (
                            game_time_weights.get(gid, 1.0)
                            * team_time_scale.get(tid, 1.0)
                        )
                        if recency_lambda > 0
                        else 1.0
                    )
                    w_i = frozen_importance_weights.get((tid, gid), 1.0)
                    base = poss * w_t
                    sum_base[tid] += base
                    sum_weighted_imp[tid] += base * w_i

                for tid, base_total in sum_base.items():
                    denom = sum_weighted_imp[tid]
                    scale = (base_total / denom) if denom > 0 else 1.0
                    team_imp_scale[tid] = max(0.85, min(1.30, scale))
                self.stdout.write(
                    f"  ✓ Importance rescale computed for {len(team_imp_scale)} teams"
                )

                # Diagnostics
                import statistics as _stats

                wvals = list(frozen_importance_weights.values())
                floor_hits = sum(1 for w in wvals if w <= IMP_FLOOR + 1e-9)
                self.stdout.write(
                    f"  Importance stats: mean={_stats.fmean(wvals):.4f}, "
                    f"median={_stats.median(wvals):.4f}, "
                    f"floor_hit_rate={floor_hits/len(wvals):.4f}"
                )

            # Check for convergence
            self.stdout.write(f"  Max AdjEM change: {max_aem_change:.4f}")

            if max_aem_change < convergence_threshold:
                self.stdout.write(f"  ✓ Converged! (change < {convergence_threshold})")
                converged = True
                # Update ratings one last time before breaking
                ratings = new_ratings
                break

            # Update ratings for next iteration
            ratings = new_ratings

        # Report convergence status
        if converged:
            self.stdout.write(f"\n✓ Converged after {iteration} iterations")
        else:
            self.stdout.write(
                f"\n⚠ Did not converge after {max_iterations} iterations (max change: {max_aem_change:.4f})"
            )

        # Capture current DB ratings for comparison before overwriting
        old_ratings_db = {
            r.team_id: {
                "adj_em": r.adj_em,
                "adj_o": r.adj_o,
                "adj_d": r.adj_d,
                "name": r.team.name,
            }
            for r in TeamSeasonRatings.objects.filter(
                season=season, team__is_d1=True
            ).select_related("team")
        }

        # Step 3: Save to database
        self.stdout.write(f"\n[3/3] Saving to database...")

        created = 0
        updated = 0

        with transaction.atomic():
            for team in teams:
                if team.id not in ratings:
                    continue

                metrics = TeamSeasonMetrics.objects.get(team=team, season=season)

                # Record = ALL games (D1 + non-D1). Computations use D1-only; display record uses all.
                all_games = TeamGameStats.objects.filter(
                    team=team, game__season_year=season_year, game__status="final"
                ).select_related("game", "opponent")

                total_games = all_games.count()
                total_wins = 0

                # Count wins by comparing team pts to opponent pts
                for game_stat in all_games:
                    # Get opponent's stats for this game
                    opp_stats = TeamGameStats.objects.filter(
                        game=game_stat.game, team=game_stat.opponent
                    ).first()

                    if opp_stats and game_stat.pts > opp_stats.pts:
                        total_wins += 1

                total_losses = total_games - total_wins

                # D1 games count (from metrics which filters to D1 only)
                d1_games_count = metrics.games

                aor = ratings[team.id]["aor"]
                adr = ratings[team.id]["adr"]
                aem = aor - adr
                adj_pace = ratings[team.id]["pace"]

                rating_obj, is_created = TeamSeasonRatings.objects.update_or_create(
                    team=team,
                    season=season,
                    defaults={
                        "adj_o": round(aor, 4),
                        "adj_d": round(adr, 4),
                        "adj_em": round(aem, 4),
                        "adj_tempo": round(adj_pace, 4),
                        "games_played": total_games,  # All games for record
                        "wins": total_wins,
                        "losses": total_losses,
                        "d1_games_played": d1_games_count,  # D1 games only
                        "total_possessions": metrics.total_possessions,
                    },
                )

                if is_created:
                    created += 1
                else:
                    updated += 1

        # Compute rankings — only among D1 teams so non-D1 stale records don't skew numbers
        self.stdout.write(f"Computing rankings...")
        d1_ratings_qs = TeamSeasonRatings.objects.filter(
            season=season, team__is_d1=True
        )

        all_ratings = d1_ratings_qs.order_by("-adj_em")
        for rank, rating in enumerate(all_ratings, start=1):
            rating.rank_adj_em = rank
            rating.save(update_fields=["rank_adj_em"])

        all_ratings = d1_ratings_qs.order_by("-adj_o")
        for rank, rating in enumerate(all_ratings, start=1):
            rating.rank_adj_o = rank
            rating.save(update_fields=["rank_adj_o"])

        all_ratings = d1_ratings_qs.order_by("adj_d")
        for rank, rating in enumerate(all_ratings, start=1):
            rating.rank_adj_d = rank
            rating.save(update_fields=["rank_adj_d"])

        # Update nat_avg.avg_ortg to match actual average of D1 adjusted ratings
        # Only runs when --update-natavg is passed to prevent run-to-run drift.
        if update_natavg:
            self.stdout.write(f"Updating national average offensive rating...")
            from django.db.models import Avg

            old_avg_ortg = nat_avg.avg_ortg
            actual_avg_adj_o = d1_ratings_qs.aggregate(Avg("adj_o"))["adj_o__avg"]

            if actual_avg_adj_o:
                nat_avg.avg_ortg = round(actual_avg_adj_o, 4)
                nat_avg.save(update_fields=["avg_ortg"])
                self.stdout.write(
                    f"  Updated avg_ortg: {old_avg_ortg:.4f} → {nat_avg.avg_ortg:.4f} "
                    f"(Δ {abs(nat_avg.avg_ortg - old_avg_ortg):.4f})"
                )
        else:
            self.stdout.write(
                "National average ortg unchanged (pass --update-natavg to update)"
            )

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("SUMMARY")
        self.stdout.write("=" * 60)
        self.stdout.write(f"Created:  {created}")
        self.stdout.write(f"Updated:  {updated}")
        self.stdout.write("=" * 60)

        # Show top 10
        self.stdout.write("\nTop 10 Teams by Adjusted Net Rating:")
        self.stdout.write("=" * 60)
        top_10 = d1_ratings_qs.order_by("-adj_em")[:10]
        for i, rating in enumerate(top_10, start=1):
            self.stdout.write(
                f"{i:2}. {rating.team.name:30} AOR={rating.adj_o:6.2f} ADR={rating.adj_d:6.2f} "
                f"Net={rating.adj_em:+6.2f} Pace={rating.adj_tempo:5.1f}"
            )
        self.stdout.write("=" * 60)

        # Comparison vs previous DB ratings
        if old_ratings_db:
            self.stdout.write("\nBiggest Movers vs Previous Ratings (AdjEM):")
            self.stdout.write("=" * 60)
            movers = []
            for r in d1_ratings_qs.select_related("team"):
                if r.team_id not in old_ratings_db:
                    continue
                old_em = old_ratings_db[r.team_id]["adj_em"]
                delta = r.adj_em - old_em
                movers.append((r.team.name, old_em, r.adj_em, delta))
            movers.sort(key=lambda x: abs(x[3]), reverse=True)
            self.stdout.write(f"{'Team':30} {'Old':>8} {'New':>8} {'Δ':>7}")
            self.stdout.write("-" * 60)
            for name, old_em, new_em, delta in movers[:20]:
                sign = "+" if delta >= 0 else ""
                self.stdout.write(
                    f"{name:30} {old_em:>8.2f} {new_em:>8.2f} {sign}{delta:>6.2f}"
                )
            self.stdout.write("=" * 60)
