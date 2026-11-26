"""
Crystal Ball single-team scoring (?team=<slug>) and the basis flag.

The team page reads its checklist from this endpoint, so a team scored alone
must match its row in the full Crystal Ball list (season context is always
built from every D1 team).
"""
from django.urls import reverse

from api.crystal_ball_views import wab_bar
from api.tests.base import IsolatedCacheTestCase
from ncaa.models import Season, Team, TeamSeasonMetrics, TeamSeasonRatings


def _rating(team, season, adj_em, pre, wab=None, games=2):
    return TeamSeasonRatings.all_objects.create(
        team=team,
        season=season,
        is_pre_tournament=pre,
        adj_o=105.0 + adj_em / 2,
        adj_d=105.0 - adj_em / 2,
        adj_em=adj_em,
        adj_tempo=68.0 + adj_em / 10,
        games_played=games,
        wins=games - 1,
        losses=1,
        wab=wab,
    )


class CrystalBallTeamTests(IsolatedCacheTestCase):
    def setUp(self):
        super().setUp()
        self.season = Season.objects.create(year=2027, display_name="2026-27", is_current=True)
        self.teams = [
            Team.objects.create(slug=f"team-{i}", name=f"Team {i}", is_d1=True) for i in range(6)
        ]
        for i, team in enumerate(self.teams):
            _rating(team, self.season, adj_em=float(10 - 3 * i), pre=False, wab=1.0 - i * 0.5)
            TeamSeasonMetrics.all_objects.create(team=team, season=self.season, is_pre_tournament=False)

    def _get(self, **params):
        return self.client.get(reverse("viz-crystal-ball"), {"season": "2027", **params})

    def test_team_param_matches_full_list_row(self):
        full = {t["team_slug"]: t for t in self._get().json()["teams"]}
        for team in self.teams:
            with self.subTest(team=team.slug):
                response = self._get(team=team.slug)
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["total_teams"], 1)
                self.assertEqual(body["teams"][0]["checklist"], full[team.slug]["checklist"])
                self.assertEqual(body["teams"][0]["rank"], full[team.slug]["rank"])

    def test_basis_live_without_snapshot(self):
        self.assertEqual(self._get().json()["basis"], "live")
        self.assertEqual(self._get(team="team-0").json()["basis"], "live")

    def test_basis_selection_sunday_with_snapshot(self):
        for i, team in enumerate(self.teams):
            _rating(team, self.season, adj_em=-5.0 - i, pre=True)
        body = self._get(team="team-0").json()
        self.assertEqual(body["basis"], "selection_sunday")
        self.assertEqual(body["teams"][0]["adj_em"], -5.0)

    def test_identical_snapshot_ratings_do_not_divide_by_zero(self):
        # Every team equal -> zero std for AdjO/AdjD/AdjEM; Balanced Dominance must not crash
        for team in self.teams:
            _rating(team, self.season, adj_em=-5.0, pre=True)
        response = self._get(team="team-0")
        self.assertEqual(response.status_code, 200)
        items = {i["key"]: i for i in response.json()["teams"][0]["checklist"]["items"]}
        self.assertIn("balanced_dominance", items)

    def test_unknown_team_404(self):
        self.assertEqual(self._get(team="no-such-team").status_code, 404)

    def test_wab_bar_scales_with_games(self):
        self.assertAlmostEqual(wab_bar(2), 0.2875)
        self.assertAlmostEqual(wab_bar(32), 4.6)
        self.assertAlmostEqual(wab_bar(40), 4.6)
        wab = {i["key"]: i for i in self._get(team="team-0").json()["teams"][0]["checklist"]["items"]}["wab"]
        self.assertEqual(wab["threshold"], "> 0.29")
        self.assertTrue(wab["pass"])  # 1.0 > 0.2875


def _full_rating(team, season, i, games, ap=None, **overrides):
    """A rating row with every checklist input filled; i spreads teams apart."""
    fields = dict(
        team=team, season=season, is_pre_tournament=False,
        adj_o=100.0 + i, adj_d=100.0 - i / 2, adj_em=1.5 * i, adj_tempo=66.0 + (i % 5),
        games_played=games, wins=max(games - (i % 4), 0), losses=min(i % 4, games),
        wab=i / 4.0, ap_poll_week6=ap,
        adj_efg_margin=i / 2.0, adj_ftr_margin=i / 3.0, adj_reb_edge=i / 5.0,
        adj_tov_edge=i / 6.0, ffi_adj=40.0 + i,
    )
    fields.update(overrides)
    return TeamSeasonRatings.all_objects.create(**fields)


class CrystalBallInactiveChecksTests(IsolatedCacheTestCase):
    """Season-level 'inactive' checks: early season (few games, no AP poll) and thin inputs."""

    N = 20

    def _season(self, games, ap=True, metrics=True, override=None):
        season = Season.objects.create(year=2027, display_name="2026-27", is_current=True)
        for i in range(self.N):
            team = Team.objects.create(slug=f"t-{i}", name=f"T {i}", is_d1=True)
            extra = (override or {}).get(i, {})
            _full_rating(team, season, i, games, ap=(i + 1 if ap and i < 25 else None), **extra)
            m = dict(team=team, season=season, is_pre_tournament=False)
            if metrics:
                m.update(total_fg3m=60 + i, total_fg3a=180, total_ftm=100 + i, total_fta=140)
            TeamSeasonMetrics.all_objects.create(**m)
        return season

    def _get(self, **params):
        return self.client.get(reverse("viz-crystal-ball"), {"season": "2027", **params}).json()

    @staticmethod
    def _items(team):
        return {i["key"]: i for i in team["checklist"]["items"]}

    def test_early_season_ap_and_win_pct_inactive(self):
        self._season(games=4, ap=False)
        body = self._get()
        inactive = {c["key"]: c["reason"] for c in body["inactive_checks"]}
        self.assertEqual(set(inactive), {"ap_poll_week6", "win_pct"})
        self.assertEqual(inactive["ap_poll_week6"], "AP Week 6 poll not out yet")
        self.assertIn("Median 4 games", inactive["win_pct"])
        for team in body["teams"]:
            cl = team["checklist"]
            self.assertEqual(cl["totalCount"], 13)
            self.assertFalse(cl["titleProfile"])
            self.assertLessEqual(cl["passedCount"], 13)
            items = self._items(team)
            self.assertFalse(items["ap_poll_week6"]["active"])
            self.assertFalse(items["ap_poll_week6"]["pass"])
            self.assertEqual(items["win_pct"]["inactive_reason"], inactive["win_pct"])
            self.assertTrue(items["wab"]["active"])
        # the team endpoint carries the same season-level status
        one = self._get(team="t-3")
        self.assertEqual(one["inactive_checks"], body["inactive_checks"])
        self.assertEqual(one["teams"][0]["checklist"]["totalCount"], 13)

    def test_full_season_has_no_inactive_checks(self):
        self._season(games=30)
        body = self._get()
        self.assertEqual(body["inactive_checks"], [])
        self.assertTrue(all(t["checklist"]["totalCount"] == 15 for t in body["teams"]))
        self.assertTrue(all(i["active"] for t in body["teams"] for i in t["checklist"]["items"]))

    def test_input_coverage_threshold_is_90_percent(self):
        # 2 of 20 teams without WAB = 90% coverage -> active; those two fail with "No data"
        self._season(games=30, override={0: {"wab": None}, 1: {"wab": None}})
        body = self._get()
        self.assertNotIn("wab", {c["key"] for c in body["inactive_checks"]})
        t0 = self._items(next(t for t in body["teams"] if t["team_slug"] == "t-0"))
        self.assertTrue(t0["wab"]["active"])
        self.assertFalse(t0["wab"]["pass"])
        self.assertEqual(t0["wab"]["value"], "No data")

    def test_input_coverage_below_90_percent_inactive(self):
        # 3 of 20 without WAB = 85% -> inactive for the season
        self._season(games=30, override={i: {"wab": None} for i in range(3)})
        inactive = {c["key"]: c["reason"] for c in self._get()["inactive_checks"]}
        self.assertEqual(set(inactive), {"wab"})
        self.assertIn("85% of D1 teams", inactive["wab"])

    def test_missing_metrics_season_inactive(self):
        self._season(games=30, metrics=False)
        inactive = {c["key"] for c in self._get()["inactive_checks"]}
        self.assertEqual(inactive, {"three_point_pct", "ft_pct"})

    def test_win_pct_bar_above_100_inactive(self):
        # 12+ games but nearly everyone unbeaten: mean + 1.31 sd > 100%
        override = {i: {"wins": 12, "losses": 0} for i in range(self.N - 1)}
        override[self.N - 1] = {"wins": 0, "losses": 12}
        self._season(games=12, override=override)
        inactive = {c["key"]: c["reason"] for c in self._get()["inactive_checks"]}
        self.assertIn("above 100%", inactive["win_pct"])
