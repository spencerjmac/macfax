"""
compute_sos: luck, opponent ratings and non-conference SOS beside SOS.

- luck = (wins - expected wins) / games (ncaa.analytics.luck): unshrunk solver ratings (stood in here),
  the season's HCA and a sigma fitted to the results; neutral site from Game.neutral_site (2026 rows
  keep H/A); canceled 0-0 'final' games have no result and are left out.
- Across the teams of a season, wins minus expected wins sum to 0.
- opp_adj_* are the means of the opponents' ratings in those games.
- nc_sos uses the SOS formula over non-conference regular-season games; two independents are
  non-conference.
"""
import math
from datetime import date
from io import StringIO

from unittest import mock

import numpy as np
from django.core.management import call_command
from django.test import SimpleTestCase
from django.urls import reverse

from api.tests.base import IsolatedCacheTestCase

from ncaa.analytics import luck as luck_model
from ncaa.models import (Conference, Game, NationalAverages, PipelineConfig, Season, Team, TeamGameStats,
                         TeamSeasonMetrics, TeamSeasonRatings)

RATINGS = {  # adj_o, adj_d, tempo
    "a": (112.0, 98.0, 68.0), "b": (108.0, 100.0, 67.0), "c": (104.0, 101.0, 70.0),
    "d": (100.0, 104.0, 66.0), "e": (98.0, 106.0, 69.0),
}


class ComputeSosTests(IsolatedCacheTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.season = Season.objects.create(year=2026, display_name="2025-26", is_current=True)
        x = Conference.objects.create(code="X", name="Conf X")
        y = Conference.objects.create(code="Y", name="Conf Y")
        ind = Conference.objects.create(code="IND", name="Independent")
        conf = {"a": x, "b": x, "c": y, "d": ind, "e": ind}
        cls.t = {}
        for rank, slug in enumerate(RATINGS, start=1):
            team = Team.objects.create(slug=slug, name=slug.upper(), is_d1=True)
            cls.t[slug] = team
            o, d, tempo = RATINGS[slug]
            TeamSeasonRatings.all_objects.create(
                team=team, season=cls.season, is_pre_tournament=False, adj_o=o, adj_d=d, adj_em=o - d,
                adj_tempo=tempo, rank_adj_em=rank)
            TeamSeasonMetrics.all_objects.create(team=team, season=cls.season, is_pre_tournament=False,
                                                 conference=conf[slug])
        cls.n = 0
        # (home, away, home pts, away pts, neutral)
        cls._game("a", "b", 80, 70)                 # conference
        cls._game("a", "c", 70, 75, neutral=True)   # neutral site, stored H/A as in 2026
        cls._game("b", "c", 77, 66)
        cls._game("d", "e", 60, 58)                 # two independents: non-conference
        cls._game("d", "a", 65, 81)
        cls._game("a", "c", 0, 0)                   # canceled, 'final' 0-0
        with mock.patch("ncaa.analytics.luck.unshrunk_ratings", return_value=cls.unshrunk()):
            call_command("compute_sos", season=2026, stdout=StringIO())

    @classmethod
    def unshrunk(cls):
        """What the solver would return at k=0 (stood in: the fixture ratings, slightly spread)."""
        return {cls.t[s].id: {"aor": o + 1.0, "adr": d - 1.0, "pace": tempo} for s, (o, d, tempo) in RATINGS.items()}

    @classmethod
    def _game(cls, home, away, hs, as_, neutral=False):
        cls.n += 1
        g = Game.objects.create(season_year=2026, game_date=date(2026, 1, cls.n), home_team=cls.t[home],
                                away_team=cls.t[away], status="final", home_score=hs, away_score=as_,
                                neutral_site=neutral, source="espn", source_game_id=f"g{cls.n}")
        TeamGameStats.objects.create(game=g, team=cls.t[home], opponent=cls.t[away], home_away="H", pts=hs)
        TeamGameStats.objects.create(game=g, team=cls.t[away], opponent=cls.t[home], home_away="A", pts=as_)

    def _row(self, slug):
        return TeamSeasonRatings.all_objects.get(team=self.t[slug], season=self.season, is_pre_tournament=False)

    # every played team-game: (team, opponent, site, won); the canceled game is not here
    GAMES = [("a", "b", "home", 1), ("b", "a", "away", 0), ("a", "c", "neutral", 0), ("c", "a", "neutral", 1),
             ("b", "c", "home", 1), ("c", "b", "away", 0), ("d", "e", "home", 1), ("e", "d", "away", 0),
             ("d", "a", "home", 0), ("a", "d", "away", 1)]

    def test_luck_uses_unshrunk_ratings_fitted_sigma_neutral_site_and_skips_canceled(self):
        from scipy.stats import norm
        cfg = PipelineConfig.get_config()
        R = {s: v for s, v in zip(RATINGS, self.unshrunk().values())}
        m = [luck_model.forecast_margin(R[t], R[o], cfg.fallback_avg_ortg, cfg.fallback_hca, site)
             for t, o, site, _ in self.GAMES]
        sigma = luck_model.fit_sigma(m, [w for *_, w in self.GAMES])
        # A: beat B at home, lost to C on a neutral floor, won at D
        a = [(mi, w) for (t, *_, w), mi in zip(self.GAMES, m) if t == "a"]
        expected = sum(norm.cdf(mi / sigma) for mi, _ in a)
        self.assertAlmostEqual(self._row("a").luck, (2 - expected) / 3, places=9)

    def test_wins_minus_expected_sum_to_zero(self):
        games = {"a": 3, "b": 2, "c": 2, "d": 2, "e": 1}
        total = sum(self._row(s).luck * n for s, n in games.items())
        self.assertAlmostEqual(total, 0.0, places=9)

    def test_opponent_means(self):
        a = self._row("a")
        self.assertAlmostEqual(a.opp_adj_em, (8.0 + 3.0 - 4.0) / 3)
        self.assertAlmostEqual(a.opp_adj_o, (108.0 + 104.0 + 100.0) / 3)
        self.assertAlmostEqual(a.opp_adj_d, (100.0 + 101.0 + 104.0) / 3)

    def test_non_conference_sos(self):
        cfg = PipelineConfig.get_config()
        site = {"H": cfg.sos_home_advantage, "N": 0.0, "A": -cfg.sos_away_penalty}

        def p(opp, ha):
            o, d, _ = RATINGS[opp]
            diff = cfg.sos_baseline_adjem - (o - d) + site[ha]
            return 1.0 / (1.0 + math.exp(-diff / cfg.sos_logistic_sigma))

        # A's non-conference games: C (neutral site, stored H: counted neutral) and at D; the canceled C game
        # is left out
        self.assertAlmostEqual(self._row("a").nc_sos_win_pct, (p("c", "N") + p("d", "A")) / 2)
        # D and E are both independents: their game is non-conference
        self.assertAlmostEqual(self._row("e").nc_sos_win_pct, p("d", "A"))
        ranks = sorted(self._row(s).nc_sos_rank for s in RATINGS)
        self.assertEqual(ranks, [1, 2, 3, 4, 5])

    def test_postseason_games_are_not_non_conference_schedule(self):
        from ncaa.models import Season as S
        S.objects.filter(pk=self.season.pk).update(selection_sunday_date=date(2026, 1, 4))
        before = self._row("a").nc_sos_win_pct
        with mock.patch("ncaa.analytics.luck.unshrunk_ratings", return_value=self.unshrunk()):
            call_command("compute_sos", season=2026, stdout=StringIO())
        cfg = PipelineConfig.get_config()
        # A's non-conference games: C on 1/2 (neutral) stays; at D on 1/5 is after Selection Sunday now
        p = 1.0 / (1.0 + math.exp(-(cfg.sos_baseline_adjem - 3.0) / cfg.sos_logistic_sigma))
        self.assertAlmostEqual(self._row("a").nc_sos_win_pct, p)
        self.assertNotAlmostEqual(before, p)

    def test_canceled_game_not_in_sos(self):
        cfg = PipelineConfig.get_config()
        site = {"H": cfg.sos_home_advantage, "N": 0.0, "A": -cfg.sos_away_penalty}
        p = lambda opp, ha: 1.0 / (1.0 + math.exp(-(cfg.sos_baseline_adjem - (RATINGS[opp][0] - RATINGS[opp][1]) + site[ha])
                                                   / cfg.sos_logistic_sigma))
        # C: at A on a neutral floor (stored A, counted neutral), at B; the canceled game is left out
        self.assertAlmostEqual(self._row("c").sos_win_pct, (p("a", "N") + p("b", "A")) / 2)

    def test_one_row_per_team_season(self):
        self.assertEqual(TeamSeasonRatings.all_objects.filter(season=self.season).count(), 5)

    def test_rankings_api_fields(self):
        TeamSeasonRatings.all_objects.filter(season=self.season).update(d1_games_played=3, games_played=3)
        response = self.client.get(reverse("rankings-list"), {"season": "2026"})
        self.assertEqual(response.status_code, 200)
        row = next(r for r in response.json()["results"] if r["team_slug"] == "a")
        a = self._row("a")
        self.assertAlmostEqual(row["luck"], a.luck)
        self.assertAlmostEqual(row["luck_wins"], round(a.luck * 3, 2))
        for f in ("opp_adj_em", "opp_adj_o", "opp_adj_d", "nc_sos_rank", "sos_rank"):
            self.assertEqual(row[f], getattr(a, f), f)



class LuckModelTests(SimpleTestCase):
    def test_fit_sigma_recovers_the_generating_sigma(self):
        rng = np.random.default_rng(1)
        m = rng.normal(0, 12, 20000)
        w = (rng.normal(m, 10.0) > 0).astype(int)        # outcomes with sigma 10
        self.assertAlmostEqual(luck_model.fit_sigma(m, w), 10.0, delta=0.4)

    def test_unshrunk_ratings_asks_the_solver_for_k0_no_prior_no_write(self):
        with mock.patch("django.core.management.call_command") as cc:
            luck_model.unshrunk_ratings(2026, True)
        kwargs = cc.call_args.kwargs
        self.assertEqual((kwargs["season"], kwargs["shrinkage"], kwargs["no_bpr_prior"], kwargs["no_write"],
                          kwargs["pre_tournament"]), (2026, 0.0, True, True, True))
