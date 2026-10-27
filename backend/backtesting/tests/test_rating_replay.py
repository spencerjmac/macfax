"""
Tests for backtesting.rating_replay, the rating loop shared by the tuning
backtests (backtest_shrinkage, _hca, _recency, _importance, _opponent_adjust,
_pace_adjust, _clutch).

Three kinds of test:
  * golden values: ratings for a tiny hand-built season. The numbers were
    captured from the original per-command copies of the code before they were
    merged here, so they prove the merge did not change the maths.
  * behaviour: each option (recency lambda, importance on/off, hca override,
    freeze iteration) does what its name says.
  * drift guard: the constants still match the production command
    (compute_adjusted_ratings) and PipelineConfig. If one of these fails,
    production changed; decide whether the backtests should follow.

No database is needed.
"""
import math
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from django.test import SimpleTestCase

from backtesting import rating_replay as rr
from ncaa.management.commands import compute_adjusted_ratings
from ncaa.models import PipelineConfig

NAT_AVG = SimpleNamespace(avg_ortg=105.0, avg_pace=68.0, hca_points=3.5)
CUTOFF = date(2026, 2, 1)
TEAM_IDS = [1, 2, 3, 4]


def _toy_season():
    """4 teams (1 strongest ... 4 weakest), double round robin = 12 games."""
    strength = {1: 12.0, 2: 4.0, 3: -3.0, 4: -10.0}
    stats, game_dates = [], {}
    pairs = [(a, b) for a in strength for b in strength if a != b]
    for i, (home, away) in enumerate(pairs):
        game_id = i + 1
        game_dates[game_id] = date(2026, 1, 1 + i)
        margin = strength[home] - strength[away] + 3.0 + (i % 3 - 1) * 2.0
        poss = 66.0 + (i % 4)
        pts_home = round((105.0 + margin / 2) * poss / 100)
        pts_away = round((105.0 - margin / 2) * poss / 100)
        stats.append(SimpleNamespace(
            game_id=game_id, team_id=home, opponent_id=away, poss_team=poss,
            pts=pts_home, game_minutes=40, site_factor=0.99, defensive_site_factor=1.01))
        stats.append(SimpleNamespace(
            game_id=game_id, team_id=away, opponent_id=home, poss_team=poss,
            pts=pts_away, game_minutes=40 if i % 5 else None,
            site_factor=1.01, defensive_site_factor=0.99))
    lookup = {(s.game_id, s.team_id): s for s in stats}
    by_team = defaultdict(list)
    for s in stats:
        by_team[s.team_id].append(s)
    return stats, game_dates, lookup, by_team


class ReplayTestCase(SimpleTestCase):
    def setUp(self):
        self.stats, self.game_dates, self.lookup, self.by_team = _toy_season()
        self.gtw, self.tts = rr.time_weights(self.stats, self.game_dates, CUTOFF)

    def _run(self, k=100.0, **kwargs):
        return rr.run_ratings(
            self.by_team, self.stats, self.lookup, TEAM_IDS, NAT_AVG,
            self.gtw, self.tts, k, **kwargs)

    def assertRatings(self, actual, expected):
        self.assertEqual(set(actual), set(expected))
        for team_id, values in expected.items():
            for key, value in values.items():
                self.assertAlmostEqual(actual[team_id][key], value, places=8, msg=f"team {team_id} {key}")


class TestGoldenRatings(ReplayTestCase):
    def test_default_ratings_match_the_original_code(self):
        self.assertRatings(self._run(), {
            1: {"aor": 109.8650526517, "adr": 99.6484893589, "pace": 67.7173462098},
            2: {"aor": 106.6360730891, "adr": 103.5954280314, "pace": 67.7341622911},
            3: {"aor": 103.2949204427, "adr": 106.6612297766, "pace": 67.729846454},
            4: {"aor": 100.1015445579, "adr": 109.6609091131, "pace": 67.7235269973},
        })

    def test_ratings_without_importance_match_the_original_code(self):
        self.assertRatings(self._run(importance=rr.NO_IMPORTANCE), {
            1: {"aor": 109.8658291135, "adr": 99.6513305469, "pace": 67.7198832627},
            2: {"aor": 106.6230830906, "adr": 103.6183150464, "pace": 67.7339615344},
            3: {"aor": 103.2819236611, "adr": 106.6882469626, "pace": 67.7341947817},
            4: {"aor": 100.0581260408, "adr": 109.7115427893, "pace": 67.7200741479},
        })

    def test_recency_weights_match_the_original_code(self):
        self.assertAlmostEqual(self.gtw[1], 0.8833798409, places=8)
        self.assertAlmostEqual(self.gtw[3], 0.8904752233, places=8)
        self.assertAlmostEqual(self.tts[1], 1.1161543808, places=8)
        self.assertAlmostEqual(self.tts[4], 1.0984370996, places=8)

    def test_margin_matches_the_original_code(self):
        ratings = self._run()
        self.assertAlmostEqual(rr.predict_margin(ratings[1], ratings[4], NAT_AVG, False), 16.8695224263, places=8)
        self.assertAlmostEqual(rr.predict_margin(ratings[1], ratings[4], NAT_AVG, True), 13.3695224263, places=8)


class TestTimeWeights(ReplayTestCase):
    def test_default_lambda_is_the_production_value(self):
        # game 1 was played 31 days before the cutoff
        self.assertAlmostEqual(self.gtw[1], math.exp(-rr.RECENCY_LAMBDA * 31), places=12)

    def test_zero_lambda_gives_every_game_weight_one(self):
        gtw, tts = rr.time_weights(self.stats, self.game_dates, CUTOFF, lam=0.0)
        self.assertEqual(set(gtw.values()), {1.0})
        self.assertEqual(set(tts.values()), {1.0})

    def test_recent_games_weigh_more_than_old_ones(self):
        self.assertGreater(self.gtw[12], self.gtw[1])

    def test_bigger_lambda_decays_faster(self):
        slow, _ = rr.time_weights(self.stats, self.game_dates, CUTOFF, lam=0.002)
        fast, _ = rr.time_weights(self.stats, self.game_dates, CUTOFF, lam=0.01)
        self.assertGreater(slow[1], fast[1])


class TestImportanceOptions(ReplayTestCase):
    def _weights(self, **kwargs):
        _, weights = rr.run_ratings_with_importance_weights(
            self.by_team, self.stats, self.lookup, TEAM_IDS, NAT_AVG,
            self.gtw, self.tts, 100.0, **kwargs)
        return weights

    def test_with_weights_returns_the_same_ratings_as_run_ratings(self):
        ratings, _ = rr.run_ratings_with_importance_weights(
            self.by_team, self.stats, self.lookup, TEAM_IDS, NAT_AVG,
            self.gtw, self.tts, 100.0)
        self.assertEqual(ratings, self._run())

    def test_one_weight_per_team_game_at_the_freeze_iteration(self):
        weights = self._weights()
        self.assertEqual(len(weights), len(self.stats))
        self.assertEqual(max(weights), 1.0)
        self.assertAlmostEqual(min(weights), 0.8826695516, places=8)

    def test_no_weights_when_importance_is_off(self):
        self.assertEqual(self._weights(importance=rr.NO_IMPORTANCE), [])

    def test_importance_changes_the_ratings(self):
        self.assertNotEqual(self._run(), self._run(importance=rr.NO_IMPORTANCE))

    def test_weights_never_drop_below_the_floor(self):
        harsh = rr.ImportanceParams(c=1.0, floor=0.6)
        self.assertGreaterEqual(min(self._weights(importance=harsh)), 0.6)

    def test_freeze_iteration_is_honoured(self):
        self.assertNotEqual(self._run(), self._run(freeze_iteration=12))


class TestShrinkage(ReplayTestCase):
    def test_huge_k_pulls_every_team_to_the_national_average(self):
        for rating in self._run(k=1e9).values():
            self.assertAlmostEqual(rating["aor"], NAT_AVG.avg_ortg, places=3)
            self.assertAlmostEqual(rating["adr"], NAT_AVG.avg_ortg, places=3)

    def test_zero_k_spreads_the_teams_out_more(self):
        spread = lambda r: r[1]["aor"] - r[4]["aor"]  # noqa: E731
        self.assertGreater(spread(self._run(k=0.0)), spread(self._run(k=500.0)))

    def test_stronger_team_is_rated_higher(self):
        ratings = self._run()
        aem = {t: r["aor"] - r["adr"] for t, r in ratings.items()}
        self.assertEqual(sorted(aem, key=aem.get, reverse=True), [1, 2, 3, 4])


class TestPredictMargin(ReplayTestCase):
    def setUp(self):
        super().setUp()
        ratings = self._run()
        self.home, self.away = ratings[1], ratings[4]

    def test_home_court_adds_the_stored_hca_when_none_is_given(self):
        neutral = rr.predict_margin(self.home, self.away, NAT_AVG, True)
        home = rr.predict_margin(self.home, self.away, NAT_AVG, False)
        self.assertAlmostEqual(home - neutral, NAT_AVG.hca_points, places=9)

    def test_missing_stored_hca_falls_back_to_3_20(self):
        no_hca = SimpleNamespace(avg_ortg=105.0, avg_pace=68.0, hca_points=None)
        neutral = rr.predict_margin(self.home, self.away, no_hca, True)
        home = rr.predict_margin(self.home, self.away, no_hca, False)
        self.assertAlmostEqual(home - neutral, 3.20, places=9)

    def test_explicit_hca_overrides_the_stored_one(self):
        neutral = rr.predict_margin(self.home, self.away, NAT_AVG, True)
        self.assertAlmostEqual(rr.predict_margin(self.home, self.away, NAT_AVG, False, 5.0) - neutral, 5.0, places=9)

    def test_explicit_zero_hca_is_honoured_not_replaced_by_the_default(self):
        neutral = rr.predict_margin(self.home, self.away, NAT_AVG, True)
        self.assertAlmostEqual(rr.predict_margin(self.home, self.away, NAT_AVG, False, 0.0), neutral, places=9)

    def test_neutral_site_ignores_hca(self):
        self.assertEqual(
            rr.predict_margin(self.home, self.away, NAT_AVG, True, 0.0),
            rr.predict_margin(self.home, self.away, NAT_AVG, True, 9.0))


class TestMatchesProduction(SimpleTestCase):
    """If one of these fails, production changed. Decide whether the replay should follow."""

    @staticmethod
    def _production_constant(name):
        source = Path(compute_adjusted_ratings.__file__).read_text()
        match = re.search(rf"^\s*{name}\s*=\s*([0-9.]+)", source, re.MULTILINE)
        assert match, f"{name} not found in compute_adjusted_ratings.py; update this test"
        return float(match.group(1))

    def test_importance_constants_match_compute_adjusted_ratings(self):
        self.assertEqual(rr.IMP_C, self._production_constant("IMP_C"))
        self.assertEqual(rr.IMP_FLOOR, self._production_constant("IMP_FLOOR"))
        self.assertEqual(rr.CLOSE_M, self._production_constant("CLOSE_M"))
        self.assertEqual(rr.BOOST_MAX, self._production_constant("BOOST_MAX"))

    def test_recency_lambda_and_convergence_match_pipeline_config_defaults(self):
        self.assertEqual(rr.RECENCY_LAMBDA, PipelineConfig._meta.get_field("recency_lambda").default)
        self.assertEqual(rr.CONVERGENCE, PipelineConfig._meta.get_field("adj_ratings_convergence").default)

    def test_importance_is_on_by_default_in_production(self):
        self.assertTrue(PipelineConfig._meta.get_field("importance_enabled").default)
        self.assertTrue(rr.PRODUCTION_IMPORTANCE.enabled)

    def test_replay_never_runs_more_iterations_than_production(self):
        # 50 here vs 75 in production is intentional (speed); it must not exceed it
        self.assertLessEqual(rr.MAX_ITERATIONS, PipelineConfig._meta.get_field("adj_ratings_iterations").default)
