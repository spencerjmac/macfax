"""
Phase 2 task 2.3: eval_stints.score on a two-stint toy example. Predictions use
rapm.py's signs, so the score matches rapm.py's own design matrix with the
same coefficients; league mean and HCA are fitted from the rows alone.
"""

from datetime import date

import numpy as np
from django.test import SimpleTestCase

from nba.analytics.eval_stints import score, stint_rows
from nba.analytics.rapm import build_design_matrix

HOME_A, AWAY_A = [1, 2, 3, 4, 5], [6, 7, 8, 9, 10]
HOME_B, AWAY_B = [1, 2, 3, 4, 11], [6, 7, 8, 9, 12]


def _obs(home, away, home_pts, away_pts, home_poss, away_poss):
    return {"game_id": "0029900001", "game_date": date(2026, 1, 1), "season_year": 2026,
            "home_player_ids": home, "away_player_ids": away,
            "home_pts": home_pts, "away_pts": away_pts,
            "home_poss": home_poss, "away_poss": away_poss}


TOY = [_obs(HOME_A, AWAY_A, 12, 9, 10.0, 10.0),    # rows: 120 (w 10), 90 (w 10)
       _obs(HOME_B, AWAY_B, 22, 18, 20.0, 20.0)]   # rows: 110 (w 20), 90 (w 20)


class EvalStintsToyTests(SimpleTestCase):

    def test_two_stints_give_four_rows(self):
        rows = stint_rows(TOY)
        self.assertEqual([(round(r[0], 9), r[1], r[2]) for r in rows],
                         [(120.0, 10.0, 1.0), (90.0, 10.0, -1.0), (110.0, 20.0, 1.0), (90.0, 20.0, -1.0)])
        self.assertEqual((rows[1][3], rows[1][4]), (AWAY_A, HOME_A))   # away offense vs home defense

    def test_baseline_and_all_zero_mse(self):
        res = score({}, {}, 2026, observations=TOY)
        # Weighted fit on [1, s]: home rows mean (1200+2200)/30 = 113.33, away rows 90 -> mu 101.67, hca 11.67
        self.assertAlmostEqual(res["league_mean"], (340 / 3 + 90) / 2)
        self.assertAlmostEqual(res["hca"], (340 / 3 - 90) / 2)
        # Residuals: home rows 120-113.33, 110-113.33; away rows 0.
        expected = (10 * (20 / 3) ** 2 + 20 * (10 / 3) ** 2) / 60
        self.assertAlmostEqual(res["mse_zero"], expected)
        self.assertAlmostEqual(res["mse"], res["mse_zero"])
        self.assertEqual((res["n_rows"], res["poss"]), (4, 60.0))

    def test_ratings_enter_with_rapm_signs(self):
        # Player 5 (home only in stint A): +O helps home offense; +D lowers away scoring.
        res = score({5: 6.0}, {5: 2.0}, 2026, observations=TOY)
        mu, hca = res["league_mean"], res["hca"]
        preds = [mu + hca + 6.0, mu - hca - 2.0, mu + hca, mu - hca]
        ys, ws = [120, 90, 110, 90], [10, 10, 20, 20]
        expected = sum(w * (y - p) ** 2 for y, p, w in zip(ys, preds, ws)) / 60
        self.assertAlmostEqual(res["mse"], expected)

    def test_matches_rapm_design_matrix_with_same_coefficients(self):
        ratings_o = {1: 1.5, 6: -0.5, 11: 2.0}
        ratings_d = {2: 0.7, 7: -1.2, 12: 0.4}
        res = score(ratings_o, ratings_d, 2026, observations=TOY)

        ids = sorted({p for o in TOY for p in o["home_player_ids"] + o["away_player_ids"]})
        index = {(p, 2026): i for i, p in enumerate(ids)}
        n = len(ids)
        X, y, w = build_design_matrix(TOY, index, n)
        beta = np.zeros(2 + 2 * n)
        beta[0], beta[1] = res["league_mean"], res["hca"]
        for p, i in ((p, index[(p, 2026)]) for p in ids):
            beta[2 + i] = ratings_o.get(p, 0.0)
            beta[2 + n + i] = -ratings_d.get(p, 0.0)   # rapm.py stores DBPR negated
        mse_x = float((w * (y - X @ beta) ** 2).sum() / w.sum())
        self.assertAlmostEqual(res["mse"], mse_x)

    def test_missing_players_count_as_zero(self):
        self.assertAlmostEqual(score({999: 5.0}, {998: 3.0}, 2026, observations=TOY)["mse"],
                               score({}, {}, 2026, observations=TOY)["mse_zero"])

    def test_rows_under_min_possessions_are_dropped(self):
        res = score({}, {}, 2026, observations=[_obs(HOME_A, AWAY_A, 3, 0, 1.0, 10.0)])
        self.assertEqual(res["n_rows"], 1)

    def test_empty_season(self):
        res = score({1: 1.0}, {}, 2026, observations=[])
        self.assertEqual((res["mse"], res["mse_zero"], res["n_rows"]), (None, None, 0))
