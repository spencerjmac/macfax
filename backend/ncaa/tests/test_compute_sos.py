"""
compute_sos: opponent ratings and non-conference SOS beside SOS.

- opp_adj_* are the means of the opponents' ratings in D1 games with a result; canceled 0-0 'final'
  games are left out (of SOS too).
- nc_sos uses the SOS formula over non-conference regular-season games; two independents are
  non-conference; neutral site from Game.neutral_site (2026 rows keep H/A).
"""
import math
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.urls import reverse

from api.tests.base import IsolatedCacheTestCase

from ncaa.models import (Conference, Game, NationalAverages, PipelineConfig, Season, Team, TeamGameStats,
                         TeamSeasonMetrics, TeamSeasonRatings)

RATINGS = {  # adj_o, adj_d, tempo
    "a": (112.0, 98.0, 68.0), "b": (108.0, 100.0, 67.0), "c": (104.0, 101.0, 70.0),
    "d": (100.0, 104.0, 66.0), "e": (98.0, 106.0, 69.0),
}


class ComputeSosScheduleTests(IsolatedCacheTestCase):
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
        call_command("compute_sos", season=2026, stdout=StringIO())

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
        for f in ("opp_adj_em", "opp_adj_o", "opp_adj_d", "nc_sos_rank", "sos_rank"):
            self.assertEqual(row[f], getattr(a, f), f)


