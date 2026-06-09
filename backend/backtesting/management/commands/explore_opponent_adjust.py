import argparse
from collections import defaultdict
import numpy as np
import pandas as pd
import scipy.stats
from django.core.management.base import BaseCommand

from nba.models import NBATeamGameStats
from services.ratings_engine import iterative_adjust, GameRecord, RatingsConfig

class Command(BaseCommand):
    help = "Explore and backtest Opponent Strength Adjustment"

    def add_arguments(self, parser):
        parser.add_argument("--seasons", type=int, nargs="+", default=[2022, 2023, 2024, 2025, 2026])

    def handle(self, *args, **options):
        seasons = options["seasons"]
        
        config = RatingsConfig(
            iterations=8,
            convergence_threshold=0.001,
            prior_games=5.0,
            prior_ortg=115.0,
            prior_drtg=115.0,
            home_court_adj=2.1,
            rest_adj_per_day=0.4,
            b2b_penalty=2.1,
        )

        total_base_brier = 0
        total_adj_brier = 0
        total_base_mae = 0
        total_adj_mae = 0
        total_games = 0

        for season in seasons:
            self.stdout.write(f"\n--- Backtesting Season {season} ---")
            res = self.run_season(season, config)
            if res:
                total_games += res["n"]
                total_base_brier += res["base_brier"] * res["n"]
                total_adj_brier += res["adj_brier"] * res["n"]
                total_base_mae += res["base_mae"] * res["n"]
                total_adj_mae += res["adj_mae"] * res["n"]

        if total_games > 0:
            self.stdout.write(f"\n=== Overall Results ({total_games} games) ===")
            self.stdout.write(f"Baseline MAE: {total_base_mae/total_games:.3f}")
            self.stdout.write(f"Adjusted MAE: {total_adj_mae/total_games:.3f}")
            self.stdout.write(f"Baseline Brier: {total_base_brier/total_games:.4f}")
            self.stdout.write(f"Adjusted Brier: {total_adj_brier/total_games:.4f}")

    def run_season(self, season_year: int, config: RatingsConfig):
        stats = list(
            NBATeamGameStats.objects.select_related("game", "team").filter(
                game__season__year=season_year,
                game__counts_toward_regular_season=True,
                game__status="Final",
                poss__isnull=False, poss__gt=0,
                raw_ortg__isnull=False, raw_drtg__isnull=False,
            ).order_by("game__date")
        )

        if not stats:
            self.stdout.write(f"No games found for {season_year}.")
            return None

        game_pair = defaultdict(dict)
        for s in stats:
            game_pair[s.game.game_id][s.team_id] = s

        games_data = []
        seen_gids = set()

        for s in stats:
            gid = s.game.game_id
            pair = game_pair.get(gid, {})
            opp = next((x for tid, x in pair.items() if tid != s.team_id), None)
            if opp is None:
                continue
            
            hs, aws = s.game.home_score, s.game.away_score
            if hs is None or aws is None:
                continue

            if gid not in seen_gids:
                seen_gids.add(gid)
                games_data.append({
                    "game_id": gid,
                    "date": s.game.date,
                    "home_team_id": s.game.home_team_id,
                    "away_team_id": s.game.away_team_id,
                    "margin": hs - aws,
                })

        games_df = pd.DataFrame(games_data)
        games_df["date"] = pd.to_datetime(games_df["date"])
        games_df = games_df.sort_values("date").reset_index(drop=True)
        if len(games_df) < 100:
             return None
             
        cutoff_date = games_df["date"].median().date()
        self.stdout.write(f"Cutoff Date: {cutoff_date}. Total Games: {len(games_df)}")

        train_gids = set(games_df[games_df["date"].dt.date <= cutoff_date]["game_id"])
        test_df = games_df[games_df["date"].dt.date > cutoff_date]

        train_recs = []
        train_stats = [s for s in stats if s.game.game_id in train_gids]

        for s in train_stats:
            pair = game_pair.get(s.game.game_id, {})
            opp = next((x for tid, x in pair.items() if tid != s.team_id), None)
            if not opp:
                continue
            train_recs.append(GameRecord(
                team_id=s.team_id,
                opp_id=opp.team_id,
                raw_ortg=s.raw_ortg,
                raw_drtg=s.raw_drtg,
                poss=s.poss,
                is_home=s.is_home,
                rest_days=s.game.rest_days_home if s.is_home else s.game.rest_days_away,
                is_b2b=s.game.home_b2b if s.is_home else s.game.away_b2b,
            ))

        # 1. Compute Base Ratings
        ratings = iterative_adjust(train_recs, config)

        # 2. Compute Opponent Adjust Slope per team
        # We need the game-level context-adjusted actual performance.
        # performance = raw_net_adj - opp_net_adj
        # Or more simply, game_adj_net = (raw_ortg - raw_drtg + ctx_net) - opp_adj_net
        # Wait, the true metric is whether they play better when opponent is good.
        # performance_vs_expectation = actual_margin - expected_margin
        
        team_performances = defaultdict(list)
        team_opp_strengths = defaultdict(list)

        for s in train_stats:
            gid = s.game.game_id
            pair = game_pair.get(gid, {})
            opp = next((x for tid, x in pair.items() if tid != s.team_id), None)
            if not opp: continue

            if s.team_id not in ratings or opp.team_id not in ratings: continue
            
            # Context Adjustment
            ctx = 0.0
            if s.is_home is not None and config.home_court_adj:
                ctx += config.home_court_adj if s.is_home else -config.home_court_adj
            is_b2b = s.game.home_b2b if s.is_home else s.game.away_b2b
            if is_b2b and config.b2b_penalty:
                ctx -= config.b2b_penalty
            rest_days = s.game.rest_days_home if s.is_home else s.game.rest_days_away
            if rest_days is not None and config.rest_adj_per_day:
                ctx += min(max(rest_days - 1, 0), 3) * config.rest_adj_per_day

            # What is the team's adjusted net rating FOR THIS GAME?
            # It is raw margin - context + opponent adj net
            actual_margin = (s.game.home_score - s.game.away_score) * (1 if s.is_home else -1)
            opp_adj_net = ratings[opp.team_id]["adj_net"]
            
            # Game Adjusted Net Rating
            game_adj_net = actual_margin - ctx + opp_adj_net
            
            team_performances[s.team_id].append(game_adj_net)
            team_opp_strengths[s.team_id].append(opp_adj_net)

        team_slopes = {}
        for tid in team_performances:
            y = np.array(team_performances[tid])
            x = np.array(team_opp_strengths[tid])
            
            if len(y) < 10:
                team_slopes[tid] = 0.0
                continue
                
            # OLS
            slope, intercept, r_value, p_value, std_err = scipy.stats.linregress(x, y)
            
            # Bayesian Shrinkage towards 0
            # weight by number of games. Let's shrink with k=10
            k = 15.0
            n = len(y)
            shrunk_slope = (slope * n + 0 * k) / (n + k)
            
            # clamp slope between -0.5 and 0.5 to prevent extreme explosions
            team_slopes[tid] = np.clip(shrunk_slope, -0.5, 0.5)

        # 3. Predict test games
        base_preds, adj_preds, actuals = [], [], []

        for _, row in test_df.iterrows():
            h, a = int(row["home_team_id"]), int(row["away_team_id"])
            if h not in ratings or a not in ratings: continue

            h_net = ratings[h]["adj_net"]
            a_net = ratings[a]["adj_net"]
            
            h_slope = team_slopes.get(h, 0.0)
            a_slope = team_slopes.get(a, 0.0)

            # Baseline Prediction
            base_pred = h_net - a_net + config.home_court_adj
            
            # Adjusted Prediction
            # Expected performance = avg_performance + slope * (opp_strength - avg_opp_strength)
            # Actually, the slope is `game_adj_net` regressed on `opp_adj_net`.
            # Pred `game_adj_net` = h_net + h_slope * a_net
            # Thus Pred_Margin = Pred_Home_Adj_Net - Pred_Away_Adj_Net + HCA (?)
            # Wait, if `game_adj_net = margin + opp_net - HCA`, then `margin = game_adj_net - opp_net + HCA`.
            # So `Pred_Margin = (h_net + h_slope * a_net) - a_net + HCA` for home perspective.
            # But wait, it should be symmetric.
            # Home perspective margin: `(h_net + h_slope * a_net) - a_net + HCA`
            # Away perspective margin: `(a_net + a_slope * h_net) - h_net - HCA`
            # The actual expected margin should be the average of these two perspectives, or just standard expectation.
            # Let's average them:
            h_perspective = (h_net + h_slope * a_net) - a_net
            a_perspective = h_net - (a_net + a_slope * h_net)
            adj_margin = (h_perspective + a_perspective) / 2.0 + config.home_court_adj
            
            base_preds.append(base_pred)
            adj_preds.append(adj_margin)
            actuals.append(row["margin"])

        base_preds = np.array(base_preds)
        adj_preds = np.array(adj_preds)
        actuals = np.array(actuals)
        
        sigma = float(np.std(base_preds - actuals))
        
        def calc_metrics(pred):
            p_home = np.clip(scipy.stats.norm.cdf(pred / sigma), 1e-7, 1 - 1e-7)
            y_true = (actuals > 0).astype(float)
            brier = float(np.mean((p_home - y_true) ** 2))
            mae = float(np.mean(np.abs(pred - actuals)))
            return brier, mae

        base_brier, base_mae = calc_metrics(base_preds)
        adj_brier, adj_mae = calc_metrics(adj_preds)

        self.stdout.write(f"  Base MAE:  {base_mae:.3f} | Base Brier:  {base_brier:.4f}")
        self.stdout.write(f"  Adj MAE:   {adj_mae:.3f} | Adj Brier:   {adj_brier:.4f}")

        # Let's print top 5 and bottom 5 "Play Up/Down" teams
        top_teams = sorted(team_slopes.items(), key=lambda x: x[1], reverse=True)[:5]
        bot_teams = sorted(team_slopes.items(), key=lambda x: x[1])[:5]
        
        # Get team names
        team_names = {s.team_id: s.team.name for s in stats}
        self.stdout.write("\n  Top 5 Plays Up:")
        for tid, slope in top_teams:
            self.stdout.write(f"    {team_names.get(tid)}: +{slope:.3f}")
        self.stdout.write("  Top 5 Plays Down:")
        for tid, slope in bot_teams:
            self.stdout.write(f"    {team_names.get(tid)}: {slope:.3f}")

        return {
            "n": len(actuals),
            "base_brier": base_brier,
            "adj_brier": adj_brier,
            "base_mae": base_mae,
            "adj_mae": adj_mae,
        }
