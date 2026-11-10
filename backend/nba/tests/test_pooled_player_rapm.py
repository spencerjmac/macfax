"""
Phase 3 task 3.6: rapm.fit_pooled_player_rapm is fit_baseline_rapm's ridge
(global prior 0, intercept and HCA unpenalized, λ by game CV) with ONE column
per player across all the seasons passed in.
"""

from datetime import date

import numpy as np
from django.test import SimpleTestCase

from nba.analytics.rapm import (
    POOLED_RAPM_LAMBDA_CANDIDATES,
    RAPM_LAMBDA_CANDIDATES,
    fit_baseline_rapm,
    fit_pooled_player_rapm,
)


def _obs(game, season, home, away, hp, ap, hposs=10.0, aposs=10.0):
    return {"game_id": game, "game_date": date(season, 1, 1), "season_year": season,
            "home_player_ids": home, "away_player_ids": away,
            "home_pts": hp, "away_pts": ap, "home_poss": hposs, "away_poss": aposs}


TEAM_A, TEAM_B, TEAM_C = [1, 2, 3, 4, 5], [6, 7, 8, 9, 10], [1, 2, 3, 11, 12]
TOY = [  # two seasons; players 1-3 play in both
    _obs("g1", 2017, TEAM_A, TEAM_B, 12, 9),
    _obs("g2", 2017, TEAM_B, TEAM_A, 10, 11),
    _obs("g3", 2018, TEAM_C, TEAM_B, 13, 10, 12.0, 11.0),
    _obs("g4", 2018, TEAM_B, TEAM_C, 9, 12),
]


def _closed_form(observations, lam):
    """Dense weighted ridge with one column per player: (X'WX + λP) b = X'Wy."""
    players = sorted({p for o in observations for p in o["home_player_ids"] + o["away_player_ids"]})
    col = {p: i for i, p in enumerate(players)}
    n = len(players)
    rows, y, w = [], [], []
    for o in observations:
        for off, dfn, pts, poss, s in ((o["home_player_ids"], o["away_player_ids"], o["home_pts"], o["home_poss"], 1.0),
                                       (o["away_player_ids"], o["home_player_ids"], o["away_pts"], o["away_poss"], -1.0)):
            x = np.zeros(2 + 2 * n)
            x[0], x[1] = 1.0, s
            for p in off:
                x[2 + col[p]] = 1.0
            for p in dfn:
                x[2 + n + col[p]] = 1.0
            rows.append(x); y.append(pts / poss * 100.0); w.append(poss)
    X, y, W = np.array(rows), np.array(y), np.diag(w)
    P = np.diag([0.0, 0.0] + [lam] * (2 * n))
    beta = np.linalg.solve(X.T @ W @ X + P, X.T @ W @ y)
    return ({p: beta[2 + i] for p, i in col.items()}, {p: -beta[2 + n + i] for p, i in col.items()}, beta)


class PooledPlayerRapmTests(SimpleTestCase):

    def test_one_column_per_player_matches_closed_form(self):
        res = fit_pooled_player_rapm(TOY, lambda_override=5.0)
        o, d, beta = _closed_form(TOY, 5.0)
        self.assertEqual(set(res["obpr"]), set(range(1, 13)))   # player ids, not (player, season)
        self.assertEqual(res["n_players"], 12)
        for p in o:
            self.assertAlmostEqual(res["obpr"][p], o[p], places=4)
            self.assertAlmostEqual(res["dbpr"][p], d[p], places=4)   # positive = good defense
        self.assertAlmostEqual(res["intercept"], beta[0], places=4)
        self.assertAlmostEqual(res["hca"], beta[1], places=4)

    def test_single_season_equals_fit_baseline_rapm(self):
        one = [o for o in TOY if o["season_year"] == 2017]
        index = {(p, 2017): i for i, p in enumerate(range(1, 11))}
        base = fit_baseline_rapm(one, index, 10, lambda_override=5.0)
        pooled = fit_pooled_player_rapm(one, lambda_override=5.0)
        for p in range(1, 11):
            self.assertAlmostEqual(pooled["obpr"][p], base["obpr"][(p, 2017)], places=6)
            self.assertAlmostEqual(pooled["dbpr"][p], base["dbpr"][(p, 2017)], places=6)

    def test_pooling_differs_from_player_season_columns(self):
        # A player seen in both seasons gets one rating, not one per season.
        index = {(p, s): i for i, (p, s) in enumerate(sorted({(p, o["season_year"]) for o in TOY
                                                               for p in o["home_player_ids"] + o["away_player_ids"]}))}
        split = fit_baseline_rapm(TOY, index, len(index), lambda_override=5.0)
        self.assertIn((1, 2017), split["obpr"])
        self.assertIn((1, 2018), split["obpr"])
        pooled = fit_pooled_player_rapm(TOY, lambda_override=5.0)
        self.assertNotIn((1, 2017), pooled["obpr"])
        self.assertIn(1, pooled["obpr"])

    def test_lambda_chosen_by_game_cv(self):
        rng = np.random.default_rng(3)
        obs = []
        for g in range(20):
            home, away = (TEAM_A, TEAM_B) if g % 2 else (TEAM_C, TEAM_B)
            obs.append(_obs(f"g{g}", 2017 + g % 2, home, away, int(rng.integers(8, 14)), int(rng.integers(8, 14))))
        res = fit_pooled_player_rapm(obs)
        self.assertIn(res["lambda"], POOLED_RAPM_LAMBDA_CANDIDATES)
        self.assertEqual(res["cv_metrics"]["n_folds"], 5)

    def test_pooled_grid_reaches_10000_and_baseline_grid_is_unchanged(self):
        self.assertEqual(RAPM_LAMBDA_CANDIDATES, [1.0, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0])
        self.assertEqual(POOLED_RAPM_LAMBDA_CANDIDATES[-3:], [2500.0, 5000.0, 10000.0])
        obs = [_obs(f"g{g}", 2017 + g % 2, TEAM_A if g % 2 else TEAM_C, TEAM_B, 11, 10) for g in range(20)]
        pooled = fit_pooled_player_rapm(obs)
        self.assertEqual(pooled["cv_metrics"]["lambda_candidates"], POOLED_RAPM_LAMBDA_CANDIDATES)
        index = {(p, s): i for i, (p, s) in enumerate(sorted({(p, o["season_year"]) for o in obs
                                                               for p in o["home_player_ids"] + o["away_player_ids"]}))}
        base = fit_baseline_rapm(obs, index, len(index))
        self.assertEqual(base["cv_metrics"]["lambda_candidates"], RAPM_LAMBDA_CANDIDATES)
