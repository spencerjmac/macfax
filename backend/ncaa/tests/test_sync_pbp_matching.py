"""
sync_ncaa_pbp event matching (the shared ncaa/espn_event_matching.py, as in sync_ncaa_player_gamelogs):

- a one-team match (non-D1 opponent without an ESPN id) is processed: the event's other team fills the
  unmapped side, that side's starters come from its team-less player rows, and its stints belong to the
  game's own team row;
- a late tip is matched on the day before;
- plays naming a team that isn't one of the game's two count as a team mismatch and are never written;
- a game with no ESPN event is printed with its reason;
- --dry-run writes nothing.
"""
from datetime import date
from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from ncaa.models import Game, Player, PlayerGameStats, PlayerGameStint, Season, Team, TeamExternalId

MOD = "ncaa.management.commands.sync_ncaa_pbp"
D, PREV = date(2026, 11, 25), date(2026, 11, 24)


def stint(player, team, idx=0):
    base = {"player": player, "team": team, "stint_index": idx, "period": 1, "clock_start_secs": 1200,
            "clock_end_secs": 600, "secs_on": 600, "pts_scored": 10, "pts_allowed": 8, "plus_minus": 2}
    for k in ("team_fgm", "team_fga", "team_fg3m", "team_fta", "team_tov", "team_oreb", "team_dreb",
              "opp_fgm", "opp_fga", "opp_fg3m", "opp_fta", "opp_tov", "opp_oreb", "opp_dreb"):
        base[k] = 1
    return base


class PbpMatchingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Season.objects.create(year=2027, display_name="2026-27")
        mk = lambda slug: Team.objects.create(slug=slug, name=slug.upper())
        cls.a, cls.b, cls.c, cls.d, cls.e = (mk(s) for s in ("a", "b", "c-nond1", "d", "e-nond1"))
        for t, eid in ((cls.a, "100"), (cls.b, "200"), (cls.d, "400")):
            TeamExternalId.objects.create(team=t, source="espn", external_id=eid, external_name=t.name)

        def g(h, a, day, hs, as_, sid):
            return Game.objects.create(home_team=h, away_team=a, game_date=day, season_year=2027, status="final",
                                       home_score=hs, away_score=as_, source="ncaa", source_game_id=sid)
        cls.one = g(cls.a, cls.c, D, 80, 60, "1")        # one team: c has no ESPN id
        cls.late = g(cls.b, cls.a, D, 70, 66, "2")       # late tip: ESPN lists it on PREV
        cls.wrong = g(cls.d, cls.e, D, 77, 50, "3")      # matched event, but its plays name another team
        cls.none = g(cls.a, cls.e, PREV, 90, 40, "4")    # no ESPN event
        cls.players = {}
        for game in (cls.one, cls.late, cls.wrong, cls.none):
            for team, mapped in ((game.home_team, True), (game.away_team, game.away_team in (cls.a, cls.b))):
                for i in range(5):
                    p, _ = Player.objects.get_or_create(espn_athlete_id=f"{team.slug}-{i}",
                                                        defaults={"display_name": f"{team.slug} {i}"})
                    cls.players[p.espn_athlete_id] = p
                    # the player sync leaves an unmapped (non-D1) team's rows without a team
                    PlayerGameStats.objects.create(player=p, game=game, team=team if mapped else None, starter=True)

    def _client(self):
        events = {
            "20261125": [
                {"id": "E1", "competitions": [{"competitors": [{"team": {"id": "100"}, "score": "80"},
                                                               {"team": {"id": "9001"}, "score": "60"}]}]},
                {"id": "E3", "competitions": [{"competitors": [{"team": {"id": "400"}, "score": "77"},
                                                               {"team": {"id": "9002"}, "score": "50"}]}]},
            ],
            "20261124": [
                {"id": "E2", "competitions": [{"competitors": [{"team": {"id": "200"}, "score": "70"},
                                                               {"team": {"id": "100"}, "score": "66"}]}]},
            ],
        }

        class Resp:
            def __init__(self, day): self.day = day
            def raise_for_status(self): pass
            def json(self): return {"events": events.get(self.day, [])}

        class FakeClient:
            BASE_URL, timeout = "https://espn.test", 5
            def __init__(self, *a, **k):
                self.session = SimpleNamespace(get=lambda url, params, timeout: Resp(params["dates"]))
            def _rate_limit(self): pass
        return FakeClient

    def _run(self, *args):
        plays = {"E1": [{"team": {"id": "100"}}, {"team": {"id": "9001"}}],
                 "E2": [{"team": {"id": "200"}}, {"team": {"id": "100"}}],
                 "E3": [{"team": {"id": "400"}}, {"team": {"id": "7777"}}]}       # 7777: not this game
        header_home = {"E1": "100", "E2": "200", "E3": "400"}
        calls = []

        def fake_reconstruct(plays, starters, home_espn_team_id, away_espn_team_id, player_map, team_map):
            calls.append({"home": home_espn_team_id, "away": away_espn_team_id, "starters": dict(starters),
                          "team_map": dict(team_map)})
            return [stint(player_map[a], team_map[t], 0) for a, t in starters.items()]

        out = StringIO()
        with mock.patch(f"{MOD}.ESPNAPIClient", self._client()), \
             mock.patch(f"{MOD}._fetch_plays", side_effect=lambda eid, sleep: (plays[eid], header_home[eid])), \
             mock.patch(f"{MOD}.reconstruct_stints", side_effect=fake_reconstruct):
            call_command("sync_ncaa_pbp", "--season", "2027", "--sleep", "0", *args, stdout=out)
        return out.getvalue(), calls

    def test_resolution_report_and_dry_run(self):
        text, calls = self._run("--dry-run")
        self.assertIn("Resolved 3/4 NCAA games to ESPN event IDs (both teams, day before: 1, one team: 2)", text)
        self.assertIn(f"Unresolved: 1 games — ids [{self.none.pk}]", text)
        self.assertIn(f"team mismatch: game {self.wrong.pk}", text)
        self.assertIn("games_processed=2", text)
        self.assertIn("team_mismatches=1", text)
        one = next(c for c in calls if "9001" in (c["home"], c["away"]))
        self.assertEqual((one["home"], one["away"]), ("100", "9001"))
        self.assertEqual(sum(1 for t in one["starters"].values() if t == "9001"), 5)   # c's team-less starters
        self.assertEqual(one["team_map"]["9001"], self.c)                              # c's own team row
        self.assertEqual(PlayerGameStint.objects.count(), 0)                           # dry run

    def test_writes_stints_with_the_unmapped_side_on_its_own_team(self):
        text, _ = self._run()
        self.assertIn("games_processed=2", text)
        self.assertEqual(PlayerGameStint.objects.filter(game=self.one, team=self.c).count(), 5)
        self.assertEqual(PlayerGameStint.objects.filter(game=self.one, team=self.a).count(), 5)
        self.assertEqual(PlayerGameStint.objects.filter(game=self.late).count(), 10)
        self.assertFalse(PlayerGameStint.objects.filter(game=self.wrong).exists())
