"""
sync_ncaa_player_gamelogs (player backfill prep):

- select_games never returns canceled 0-0 games; --d1-vs-d1 keeps only games between two teams that were D1 that
  season (TeamSeasonMembership).
- has_espn_event_id: ESPN-sourced games, and every 2005-2008 game (stored with ESPN's event id), use
  source_game_id directly; later NCAA-sourced games don't.
- write_player_rows bulk-upserts Player and PlayerGameStats: new rows counted, a rerun updates in place, rows
  without an athlete id are skipped, a repeated athlete keeps the last line, periods fill a NULL period_count.
- ESPNAPIClient.idless_athletes counts box entries with no athlete id and no stats per ESPN team.
"""

from datetime import date

from django.test import SimpleTestCase, TestCase

from ncaa.management.commands.sync_ncaa_player_gamelogs import has_espn_event_id, select_games, write_player_rows
from ncaa.models import Game, Player, PlayerGameStats, Season, Team, TeamSeasonMembership
from ncaa.utils.ncaa_api import ESPNAPIClient


def row(aid, team="38", minutes=20.0, points=8, **kw):
    r = {"espn_athlete_id": aid, "display_name": f"P {aid}", "short_name": f"P. {aid}", "jersey": "1", "position": "G",
         "headshot_url": "", "espn_team_id": team, "starter": False, "did_not_play": False, "minutes": minutes,
         "points": points, "game_period": 2}
    for k in ("fg_made", "fg_attempted", "fg3_made", "fg3_attempted", "ft_made", "ft_attempted", "rebounds",
              "offensive_rebounds", "defensive_rebounds", "assists", "turnovers", "steals", "blocks", "fouls"):
        r[k] = 1
    r.update(kw)
    return r


class SelectGamesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.season = Season.objects.create(year=2014, display_name="2013-14")
        cls.a, cls.b, cls.c = (Team.objects.create(slug=s, name=s.upper()) for s in ("a", "b", "c"))
        for t, d1 in ((cls.a, True), (cls.b, True), (cls.c, False)):
            TeamSeasonMembership.objects.create(season=cls.season, team=t, is_d1=d1, source="manual",
                                                is_reclassifying=False if d1 else None)

        def g(h, a, hs, as_):
            return Game.objects.create(home_team=h, away_team=a, game_date=date(2013, 12, 1), season_year=2014,
                                       status="final", home_score=hs, away_score=as_, source="espn",
                                       source_game_id=f"{h.slug}{a.slug}{hs}")
        cls.d1d1, cls.vs_nond1, cls.zero = g(cls.a, cls.b, 70, 60), g(cls.a, cls.c, 80, 50), g(cls.b, cls.a, 0, 0)

    def test_zero_zero_never_and_d1_filter(self):
        self.assertEqual({x.id for x in select_games(2014)}, {self.d1d1.id, self.vs_nond1.id})
        self.assertEqual([x.id for x in select_games(2014, d1_vs_d1=True)], [self.d1d1.id])


class EspnIdTests(SimpleTestCase):
    def test_has_espn_event_id(self):
        self.assertTrue(has_espn_event_id(Game(source="espn", season_year=2020, source_game_id="401")))
        self.assertTrue(has_espn_event_id(Game(source="ncaa", season_year=2006, source_game_id="253552754")))
        self.assertFalse(has_espn_event_id(Game(source="ncaa", season_year=2026, source_game_id="6534658")))

    def test_idless_athletes(self):
        data = {"boxscore": {"players": [{"team": {"id": 38}, "statistics": [{"keys": ["min"], "athletes": [
            {"athlete": {"id": "1"}, "stats": ["20"]},
            {"athlete": {"shortName": "E. Battey"}, "stats": [], "didNotPlay": True},
            {"athlete": {"id": "2"}, "stats": [], "didNotPlay": True},
        ]}]}]}}
        self.assertEqual(ESPNAPIClient.idless_athletes(data), {"38": 1})


class WritePlayerRowsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.team = Team.objects.create(slug="col", name="Colorado")
        cls.opp = Team.objects.create(slug="ari", name="Arizona")
        cls.game = Game.objects.create(home_team=cls.opp, away_team=cls.team, game_date=date(2013, 12, 1),
                                       season_year=2014, status="final", home_score=80, away_score=70)

    def test_insert_then_update_in_place(self):
        Player.objects.create(espn_athlete_id="1", display_name="Old Name")
        rows = [row("1"), row("2", team="12"), row("", points=99), row("3"), row("3", points=11)]
        self.assertEqual(write_player_rows(self.game.id, rows, {"38": self.team.id}), (2, 3, 1))
        self.assertEqual(Player.objects.get(espn_athlete_id="1").display_name, "P 1")
        st = {p.player.espn_athlete_id: p for p in PlayerGameStats.objects.select_related("player")}
        self.assertEqual((st["1"].team_id, st["2"].team_id, st["3"].points), (self.team.id, None, 11))
        self.game.refresh_from_db()
        self.assertEqual((self.game.period_count, self.game.went_to_ot), (2, False))
        # rerun: nothing new, values updated in place
        self.assertEqual(write_player_rows(self.game.id, [row("1", points=30)], {"38": self.team.id}), (0, 0, 0))
        self.assertEqual(PlayerGameStats.objects.count(), 3)
        self.assertEqual(PlayerGameStats.objects.get(player__espn_athlete_id="1").points, 30)
