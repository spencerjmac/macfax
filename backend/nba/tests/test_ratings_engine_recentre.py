"""
services.ratings_engine re-centring (RatingsConfig.recentre): after the solve, mean adj_net is 0 and
mean adj_off = mean adj_def = the league's actual points per 100 possessions; every team moves by the
same amount, so ranks and gaps match the un-centred solve.
"""
import random

from django.test import SimpleTestCase

from nba.ratings_config import NBA_RATINGS_CONFIG
from services.ratings_engine import GameRecord, RatingsConfig, iterative_adjust


def _config(**over):
    keys = ("iterations", "convergence_threshold", "prior_games", "prior_ortg", "prior_drtg",
            "home_court_adj", "rest_adj_per_day", "b2b_penalty")
    return RatingsConfig(**{k: NBA_RATINGS_CONFIG[k] for k in keys}, **over)


def _season(n_teams=8, rounds=6, seed=7):
    """Round-robin games with uneven B2B and rest: teams 0-2 play many back-to-backs, the rest are
    usually rested, so the B2B/rest context doesn't balance (the case that drifts)."""
    rng = random.Random(seed)
    strength = {t: rng.uniform(-6, 6) for t in range(n_teams)}
    records, total_pts, total_poss = [], 0.0, 0.0
    for r in range(rounds):
        for a in range(n_teams):
            for b in range(a + 1, n_teams):
                home, away = (a, b) if (r + a + b) % 2 else (b, a)
                pace = rng.uniform(94, 104)
                pts = {
                    home: 111 + (strength[home] - strength[away]) / 2 + 1.5 + rng.gauss(0, 9),
                    away: 111 + (strength[away] - strength[home]) / 2 - 1.5 + rng.gauss(0, 9),
                }
                poss = {home: pace + rng.uniform(-1, 1), away: pace + rng.uniform(-1, 1)}
                for team, opp in ((home, away), (away, home)):
                    tired = team < 3 and rng.random() < 0.45
                    records.append(GameRecord(
                        team_id=team, opp_id=opp,
                        raw_ortg=100 * pts[team] / poss[team], raw_drtg=100 * pts[opp] / poss[opp],
                        poss=poss[team], is_home=team == home,
                        rest_days=1 if tired else rng.choice([2, 3, 4]), is_b2b=tired,
                    ))
                    total_pts += pts[team]
                    total_poss += poss[team]
    return records, 100 * total_pts / total_poss


class RecentreTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.records, cls.league_pp100 = _season()
        cls.new = iterative_adjust(cls.records, _config())
        cls.old = iterative_adjust(cls.records, _config(recentre=False))

    def test_recentre_is_the_default(self):
        self.assertTrue(RatingsConfig().recentre)

    def test_uncentred_solve_drifts(self):
        # guard: the fixture really has the B2B/rest imbalance that moves the league mean
        mean_old = sum(r["adj_net"] for r in self.old.values()) / len(self.old)
        self.assertGreater(abs(mean_old), 0.2)

    def test_league_mean_net_is_zero(self):
        mean_net = sum(r["adj_net"] for r in self.new.values()) / len(self.new)
        self.assertAlmostEqual(mean_net, 0.0, places=9)

    def test_level_anchored_to_actual_points_per_100(self):
        n = len(self.new)
        self.assertAlmostEqual(sum(r["adj_off"] for r in self.new.values()) / n, self.league_pp100, places=9)
        self.assertAlmostEqual(sum(r["adj_def"] for r in self.new.values()) / n, self.league_pp100, places=9)

    def test_every_team_moves_by_the_same_amount(self):
        off = {t: self.new[t]["adj_off"] - self.old[t]["adj_off"] for t in self.new}
        de = {t: self.new[t]["adj_def"] - self.old[t]["adj_def"] for t in self.new}
        self.assertLess(max(off.values()) - min(off.values()), 1e-9)
        self.assertLess(max(de.values()) - min(de.values()), 1e-9)

    def test_ranks_and_gaps_unchanged(self):
        order = lambda res: sorted(res, key=lambda t: -res[t]["adj_net"])
        self.assertEqual(order(self.new), order(self.old))
        teams = sorted(self.new)
        for a in teams:
            for b in teams:
                self.assertAlmostEqual(self.new[a]["adj_net"] - self.new[b]["adj_net"],
                                       self.old[a]["adj_net"] - self.old[b]["adj_net"], places=9)

    def test_raw_values_untouched(self):
        for t in self.new:
            self.assertEqual(self.new[t]["raw_off"], self.old[t]["raw_off"])
            self.assertEqual(self.new[t]["raw_def"], self.old[t]["raw_def"])
            self.assertEqual(self.new[t]["game_count"], self.old[t]["game_count"])

    def test_small_pool_anchors_to_its_own_games(self):
        # a playoff-style pool: 4 teams, anchored to the points per 100 of those games only
        records, pp100 = _season(n_teams=4, rounds=3, seed=11)
        res = iterative_adjust(records, _config())
        self.assertAlmostEqual(sum(r["adj_off"] for r in res.values()) / 4, pp100, places=9)
        self.assertAlmostEqual(sum(r["adj_net"] for r in res.values()) / 4, 0.0, places=9)

    def test_no_games(self):
        self.assertEqual(iterative_adjust([], _config()), {})
