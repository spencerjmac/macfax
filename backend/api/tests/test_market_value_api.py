"""
Phase 6 Stage 2: Market Value API tests (serve-only endpoints).
"""

from django.test import TestCase

from ncaa.models import Player, PlayerMarketValue, PlayerSeasonStats, Season, Team


class MarketValueApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.season = Season.objects.create(year=2026, display_name="2025-26", is_current=True)
        cls.team = Team.objects.create(slug="mv-team", name="MV Team", is_d1=True)
        for i, (bpr, mwins) in enumerate([(8.0, 5.0), (4.0, 2.0), (-1.0, -0.3)]):
            p = Player.objects.create(espn_athlete_id=f"mv_{i}", display_name=f"MV Player {i}")
            PlayerSeasonStats.objects.create(
                player=p, team=cls.team, season=cls.season,
                gp=30, mpg=30.0 - i * 8,
            )
            PlayerMarketValue.objects.create(
                player=p, season=cls.season,
                bpr=bpr, minutes_share=(30.0 - i * 8) / 40.0,
                marginal_em=mwins, marginal_wins=mwins,
                value_low=mwins * 192_914, value_high=mwins * 261_002,
                pipeline_version="6.2", constants_hash="testhash",
            )

    def test_player_list_ordered_and_versioned(self):
        r = self.client.get("/api/market-value/players/?season=2026")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["season"], 2026)
        self.assertIn("methodology_version", d)
        wins = [p["marginal_wins"] for p in d["results"]]
        self.assertEqual(wins, sorted(wins, reverse=True))
        self.assertEqual(d["results"][0]["team_slug"], "mv-team")

    def test_min_gp_filter(self):
        r = self.client.get("/api/market-value/players/?season=2026&min_gp=99")
        self.assertEqual(r.json()["count"], 0)

    def test_team_rollup_totals_positive_only(self):
        r = self.client.get("/api/market-value/teams/mv-team/?season=2026")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(len(d["players"]), 3)
        # negative-value player must not subtract from the roster total
        expected_low = round(5.0 * 192_914 + 2.0 * 192_914)
        self.assertEqual(d["team_total_value_low"], expected_low)

    def test_unknown_team_404(self):
        r = self.client.get("/api/market-value/teams/no-such-team/")
        self.assertEqual(r.status_code, 404)

    def test_unknown_season_404(self):
        r = self.client.get("/api/market-value/players/?season=1900")
        self.assertEqual(r.status_code, 404)
