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
from django.core.cache import cache

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q, Count, Case, When, IntegerField, F

from ncaa.models import (
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
            default=None,
            help="Exponential decay rate for recency weighting (default: from PipelineConfig; set to 0 to disable)",
        )
        parser.add_argument(
            "--no-importance",
            action="store_true",
            default=False,
            help="Disable importance weighting (default: enabled)",
        )
        parser.add_argument(
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
            '--freeze-iter',
            type=int,
            default=0,
            help='Importance: iteration to freeze weights (default: 0). 0 = adaptive based on season length.'
        )
        parser.add_argument(
            "--update-natavg",
            action="store_true",
            default=False,
            help="Overwrite NationalAverages.avg_ortg with mean of computed AdjO (default: off)",
        )
        parser.add_argument(
            "--pre-tournament",
            action="store_true",
            help="If set, compute ratings using only games on or before Selection Sunday.",
        )
        parser.add_argument(
            "--use-bpr-prior",
            action="store_true",
            default=False,
            help="Anchor early-season shrinkage to team BPR projections (default: disabled)",
        )
        parser.add_argument(
            "--prior-decay-games",
            type=int,
            default=None,
            help="Games over which BPR prior fades to league average (default: from PipelineConfig)",
        )

    def handle(self, *args, **options):
        from ncaa.models import PipelineConfig

        cfg = PipelineConfig.get_config()

        season_year = options["season"]
        max_iterations = options["iterations"] or cfg.adj_ratings_iterations
        convergence_threshold = options["convergence"] or cfg.adj_ratings_convergence
        shrinkage_k = options[
            "shrinkage"
        ]  # None = dynamic (from cfg below), float = fixed override
        recency_lambda = options["recency_lambda"] if options["recency_lambda"] is not None else cfg.recency_lambda
        importance_enabled = False if options["no_importance"] else cfg.importance_enabled
        update_natavg = options["update_natavg"]
        is_pre_tournament = options["pre_tournament"]
        use_bpr_prior = options["use_bpr_prior"] or cfg.use_bpr_prior
        prior_decay_games = options["prior_decay_games"] if options["prior_decay_games"] is not None else cfg.bpr_prior_decay_games

        # --- Importance weight constants ---
        IMP_C = 40.0          # gap (AdjEM pts) where base weight drops to 0.5
        IMP_FLOOR = 0.35      # minimum importance weight
        FREEZE_ITERATION = options["freeze_iter"]
        CLOSE_M = 12.0        # closeness scale (margin per 100 poss)
        BOOST_MAX = 1.40      # max boost for unexpectedly close mismatches
        
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

        # Bulk-load BPR projections (one-time query, used inside iteration loop)
        proj_ratings = {}
        if use_bpr_prior:
            from ncaa.models import TeamSeasonProjection
            for r in TeamSeasonProjection.objects.filter(
                projected_season_year=season_year,
                projected_adj_o__isnull=False,
                projected_adj_d__isnull=False,
            ).values("team_id", "projected_adj_o", "projected_adj_d"):
                proj_ratings[r["team_id"]] = {
                    "adj_o": r["projected_adj_o"],
                    "adj_d": r["projected_adj_d"],
                }
            self.stdout.write(
                f"BPR prior: {len(proj_ratings)} teams with projections "
                f"(decay over {prior_decay_games} games)"
            )

        # Get all D1 teams with season metrics
        teams = Team.objects.filter(season_metrics__season=season, season_metrics__is_pre_tournament=is_pre_tournament, is_d1=True)

        if teams.count() == 0:
            self.stderr.write("No teams found with season metrics")
            return

        num_d1_teams = teams.count()

        # Coverage guard: auto-disable BPR prior if projection coverage is too low.
        # Count only D1 teams (not extras in proj_ratings from non-D1 teams).
        if use_bpr_prior and num_d1_teams > 0:
            d1_team_ids = {t.id for t in teams}
            n_covered = len(d1_team_ids & proj_ratings.keys())
            coverage = n_covered / num_d1_teams
            if coverage < cfg.bpr_prior_min_coverage:
                self.stdout.write(
                    f"WARNING: BPR prior disabled — only {n_covered}/{num_d1_teams} "
                    f"D1 teams have projections ({coverage:.1%} < {cfg.bpr_prior_min_coverage:.0%} threshold). "
                    f"Falling back to flat prior."
                )
                use_bpr_prior = False
                proj_ratings = {}
            else:
                self.stdout.write(
                    f"BPR prior coverage: {n_covered}/{num_d1_teams} D1 teams ({coverage:.1%}) ✓"
                )

        # Calculate dynamic shrinkage k based on average games played
        # Count team-games (NOT matchups - each game counts twice, once per team)
        team_games_filters = Q(
            game__season_year=season_year,
            game__status="final",
            opponent__is_d1=True,
            team__is_d1=True,
        )
        if is_pre_tournament and season.selection_sunday_date:
            team_games_filters &= Q(game__game_date__lte=season.selection_sunday_date)

        team_games_count = TeamGameStats.objects.filter(team_games_filters).count()

        avg_games_played = team_games_count / num_d1_teams if num_d1_teams > 0 else 0
        
        # Dynamic k: starts at 300, decays to floor of 150
        # At 16 games (midseason): k ≈ 200
        # At 21+ games: k = 150 (floor)
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

        if FREEZE_ITERATION <= 0:
            # Adaptive freeze based on avg games played
            # Midseason (15 games) -> freeze at 7. End of season (35 games) -> freeze at 17.
            FREEZE_ITERATION = max(4, min(20, int(avg_games_played / 2.0)))
            self.stdout.write(f"Adaptive Freeze Iteration: {FREEZE_ITERATION} (based on {avg_games_played:.1f} avg games)")
        else:
            self.stdout.write(f"Fixed Freeze Iteration: {FREEZE_ITERATION}")

        self.stdout.write("=" * 60)
        self.stdout.write(f"Processing {num_d1_teams} teams...")

        # --- Recency weighting precomputation (done once, outside iterations) ---
        game_time_weights = {}
        team_time_scale = {}

        if recency_lambda > 0:
            # Use the last game date in the season as the "today" reference so that
            # recency weighting is calibrated within the season (not from wall-clock
            # today, which would give ~zero weight to all games in historical seasons).
            last_game_qs = Game.objects.filter(season_year=season_year, status="final")
            if is_pre_tournament and season.selection_sunday_date:
                last_game_qs = last_game_qs.filter(game_date__lte=season.selection_sunday_date)

            last_game = (
                last_game_qs
                .order_by("-game_date")
                .values("game_date")
                .first()
            )
            today = last_game["game_date"] if last_game else date.today()

            game_qs = Game.objects.filter(season_year=season_year, status="final")
            if is_pre_tournament and season.selection_sunday_date:
                game_qs = game_qs.filter(game_date__lte=season.selection_sunday_date)

            # Exponential decay weight per game
            for g in game_qs.values("id", "game_date"):
                days_ago = max(0, (today - g["game_date"]).days)
                game_time_weights[g["id"]] = math.exp(-recency_lambda * days_ago)
            self.stdout.write(
                f"\nPre-computed recency weights for {len(game_time_weights)} games"
            )

            # Per-team rescale factor: keeps sum(poss * w_time * scale) == sum(poss)
            # so shrinkage denominator stays calibrated to real possessions.
            sum_poss: defaultdict = defaultdict(float)
            sum_poss_w: defaultdict = defaultdict(float)
            tgs_qs = TeamGameStats.objects.filter(
                game__season_year=season_year,
                game__status="final",
                team__is_d1=True,
                opponent__is_d1=True,
            )
            if is_pre_tournament and season.selection_sunday_date:
                tgs_qs = tgs_qs.filter(game__game_date__lte=season.selection_sunday_date)

            for row in tgs_qs.values("team_id", "game_id", "fga", "oreb", "tov", "fta"):
                poss = row["fga"] - row["oreb"] + row["tov"] + 0.44 * (row["fta"] or 0)
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

        # ── Bulk-load all game data before the iteration loop ─────────────────
        # Prevents up to 75 × 365 ≈ 27,000 DB round-trips inside the loop.
        # All iteration math reads from these in-memory dicts — zero DB queries inside the loop.
        self.stdout.write("\nPre-loading game data into memory...")
        _tgs_filter = dict(
            game__season_year=season_year,
            game__status="final",
            team__is_d1=True,
            opponent__is_d1=True,
        )
        if is_pre_tournament and season.selection_sunday_date:
            _tgs_filter["game__game_date__lte"] = season.selection_sunday_date

        _all_tgs_rows = list(
            TeamGameStats.objects.filter(**_tgs_filter).values(
                "team_id", "opponent_id", "game_id",
                "fga", "oreb", "tov", "fta", "pts",
                "home_away", "minutes",
                "game__neutral_site", "game__elevation",
                "opponent__elevation",
            )
        )

        # (game_id, team_id) → row  — for opponent stat lookups
        _stats_lookup: dict = {(r["game_id"], r["team_id"]): r for r in _all_tgs_rows}

        # team_id → list[row]  — for per-team game iteration
        _by_team: dict = defaultdict(list)
        for _r in _all_tgs_rows:
            _by_team[_r["team_id"]].append(_r)

        # elevation per entity — merged from team objects + preloaded opponent__elevation
        _team_elevation: dict = {t.id: (t.elevation or 0) for t in teams}
        for _r in _all_tgs_rows:
            oid = _r["opponent_id"]
            if oid not in _team_elevation:
                _team_elevation[oid] = _r["opponent__elevation"] or 0

        self.stdout.write(
            f"Loaded {len(_all_tgs_rows)} team-game rows across {len(_by_team)} teams"
        )
        # -----------------------------------------------------------------------

        # Initialize ratings dictionary {team_id: {'aor': float, 'adr': float, 'pace': float}}
        ratings = {}

        # Step 1: Initialize with raw ORtg/DRtg/Pace
        self.stdout.write("\n[1/1] Initializing with raw ratings...")
        for team in teams:
            metrics = TeamSeasonMetrics.all_objects.get(team=team, season=season, is_pre_tournament=is_pre_tournament)
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
                team_id = team.id
                team_elev = _team_elevation.get(team_id, 0)

                sum_weighted_aor = 0.0
                sum_weighted_adr = 0.0
                sum_weighted_pace = 0.0
                sum_weights = 0.0
                n_valid_games = 0

                for row in _by_team.get(team_id, []):
                    opp_id = row["opponent_id"]
                    if opp_id not in ratings:
                        continue

                    opp_aor = ratings[opp_id]["aor"]
                    opp_adr = ratings[opp_id]["adr"]
                    opp_pace = ratings[opp_id]["pace"]

                    poss_g = (
                        (row["fga"] or 0)
                        - (row["oreb"] or 0)
                        + (row["tov"] or 0)
                        + 0.44 * (row["fta"] or 0)
                    )
                    if poss_g <= 0:
                        continue

                    opp_row = _stats_lookup.get((row["game_id"], opp_id))
                    if not opp_row:
                        continue

                    n_valid_games += 1
                    raw_oe_g = 100 * row["pts"] / poss_g
                    raw_de_g = 100 * opp_row["pts"] / poss_g
                    minutes = row["minutes"] or 40
                    raw_pace_g = 40 * poss_g / minutes

                    # Site factors (inlined: avoids property call overhead)
                    ha = row["home_away"]
                    if ha == "H":
                        off_site_factor, def_site_factor = 0.9862, 1.0140
                    elif ha == "A":
                        off_site_factor, def_site_factor = 1.0140, 0.9862
                    else:
                        off_site_factor, def_site_factor = 1.0, 1.0

                    # Elevation penalty: +0.2 margin/100poss per 1,000 ft for away team
                    if not row["game__neutral_site"]:
                        game_elev = row["game__elevation"] or 0
                        opp_elev = _team_elevation.get(opp_id, 0)
                        elev_diff_team = max(0, game_elev - team_elev) / 1000.0
                        elev_diff_opp = max(0, game_elev - opp_elev) / 1000.0
                        if elev_diff_team > 0:
                            off_site_factor += 0.001 * elev_diff_team
                            def_site_factor -= 0.001 * elev_diff_team
                        if elev_diff_opp > 0:
                            off_site_factor -= 0.001 * elev_diff_opp
                            def_site_factor += 0.001 * elev_diff_opp

                    aor_g = (
                        raw_oe_g * (nat_avg.avg_ortg / opp_adr) * off_site_factor
                        if opp_adr > 0 else raw_oe_g
                    )
                    adr_g = (
                        raw_de_g * (nat_avg.avg_ortg / opp_aor) * def_site_factor
                        if opp_aor > 0 else raw_de_g
                    )
                    pace_g = (
                        raw_pace_g * (nat_avg.avg_pace / opp_pace)
                        if opp_pace > 0 else raw_pace_g
                    )

                    w_time = (
                        game_time_weights.get(row["game_id"], 1.0)
                        * team_time_scale.get(team_id, 1.0)
                        if recency_lambda > 0 else 1.0
                    )

                    imp_key = (team_id, row["game_id"])
                    if not importance_enabled:
                        w_imp = 1.0
                    elif iteration <= FREEZE_ITERATION:
                        team_aem = (
                            ratings[team_id]["aor"] - ratings[team_id]["adr"]
                            if team_id in ratings else 0.0
                        )
                        opp_aem = opp_aor - opp_adr
                        gap = abs(team_aem - opp_aem)
                        base = max(IMP_FLOOR, 1.0 / (1.0 + (gap / IMP_C) ** 2))
                        obs_margin_100 = aor_g - adr_g
                        exp_margin_100 = team_aem - opp_aem
                        closer_than_expected = max(0.0, abs(exp_margin_100) - abs(obs_margin_100))
                        closeness_factor = 1.0 - math.exp(-closer_than_expected / CLOSE_M)
                        boost = 1.0 + (BOOST_MAX - 1.0) * closeness_factor
                        w_imp = min(1.0, base * boost)
                        current_importance_weights[imp_key] = w_imp
                    else:
                        w_imp = frozen_importance_weights.get(imp_key, 1.0)

                    weight = poss_g * w_time * w_imp * team_imp_scale.get(team_id, 1.0)
                    sum_weighted_aor += weight * aor_g
                    sum_weighted_adr += weight * adr_g
                    sum_weighted_pace += weight * pace_g
                    sum_weights += weight

                # BPR prior blend: alpha=1 at 0 games (full projection), 0 at decay_games (flat)
                if use_bpr_prior and team_id in proj_ratings:
                    alpha = max(0.0, 1.0 - n_valid_games / prior_decay_games)
                    proj = proj_ratings[team_id]
                    prior_off = alpha * proj["adj_o"] + (1 - alpha) * nat_avg.avg_ortg
                    prior_def = alpha * proj["adj_d"] + (1 - alpha) * nat_avg.avg_ortg
                else:
                    prior_off = nat_avg.avg_ortg
                    prior_def = nat_avg.avg_ortg

                if sum_weights > 0:
                    aor_season = (sum_weighted_aor + shrinkage_k * prior_off) / (
                        sum_weights + shrinkage_k
                    )
                    adr_season = (sum_weighted_adr + shrinkage_k * prior_def) / (
                        sum_weights + shrinkage_k
                    )
                    pace_season = (sum_weighted_pace + shrinkage_k * nat_avg.avg_pace) / (
                        sum_weights + shrinkage_k
                    )
                else:
                    aor_season = prior_off
                    adr_season = prior_def
                    pace_season = nat_avg.avg_pace

                new_ratings[team_id] = {
                    "aor": aor_season,
                    "adr": adr_season,
                    "pace": pace_season,
                }

                if team_id in ratings:
                    old_aem = ratings[team_id]["aor"] - ratings[team_id]["adr"]
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

                for row in _all_tgs_rows:
                    tid = row["team_id"]
                    gid = row["game_id"]
                    poss = (
                        row["fga"]
                        - row["oreb"]
                        + row["tov"]
                        + 0.44 * (row["fta"] or 0)
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
            for r in TeamSeasonRatings.all_objects.filter(
                season=season, team__is_d1=True, is_pre_tournament=is_pre_tournament
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

                metrics = TeamSeasonMetrics.all_objects.get(team=team, season=season, is_pre_tournament=is_pre_tournament)

                # Record = ALL games (D1 + non-D1). Computations use D1-only; display record uses all.
                all_games_filters = Q(
                    team=team, game__season_year=season_year, game__status="final"
                )
                
                # Exclude canceled games (where both teams scored 0 points despite 'final' status)
                all_games_filters &= ~Q(game__home_score=0, game__away_score=0)
                if is_pre_tournament and season.selection_sunday_date:
                    all_games_filters &= Q(game__game_date__lte=season.selection_sunday_date)

                all_games = TeamGameStats.objects.filter(all_games_filters).select_related("game", "opponent")

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

                rating_obj, is_created = TeamSeasonRatings.all_objects.update_or_create(
                    team=team,
                    season=season,
                    is_pre_tournament=is_pre_tournament,
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
        d1_ratings_qs = TeamSeasonRatings.all_objects.filter(
            season=season, team__is_d1=True, is_pre_tournament=is_pre_tournament
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
