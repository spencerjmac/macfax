"""
ESPN event matching for NCAA-sourced games (ncaa/espn_event_matching.py, used by sync_ncaa_player_gamelogs).

Cases are the ones found on prod in 2026-11: non-D1 opponents without an ESPN team id (Missouri St. v
Lincoln (MO)), late tips stored a day after ESPN's date (Kansas St. v Gonzaga), a postponed event sharing
the day (UNC Wilmington v Montreat), and one game stored twice (Central Connecticut v VTSU Lyndon).
"""
from datetime import date
from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from ncaa.espn_event_matching import (
    EventEntry, Match, entries_from_scoreboard, flag_shared_events, match_espn_event,
)
from ncaa.models import Game, Season, Team, TeamExternalId

D = date(2026, 11, 25)
PREV = date(2026, 11, 24)


def board(by_day):
    return lambda day: by_day.get(day, [])


class MatchRulesTests(SimpleTestCase):
    def test_both_teams_same_day_needs_no_score(self):
        m = match_espn_event(D, "100", "200", 70, 60, board({D: [EventEntry("e1", {"100": None, "200": None})]}))
        self.assertEqual(m, Match("e1", "both teams", True))

    def test_both_teams_late_tip_matches_day_before_with_score(self):
        # Kansas St. v Gonzaga: game_date 2026-11-25 (UTC), ESPN lists it on 11-24
        m = match_espn_event(D, "2306", "2250", 61, 101,
                             board({PREV: [EventEntry("401909800", {"2306": 61, "2250": 101}, "STATUS_FINAL")]}))
        self.assertEqual(m, Match("401909800", "both teams, day before", True))

    def test_day_before_with_wrong_score_is_not_taken(self):
        m = match_espn_event(D, "100", "200", 70, 60, board({PREV: [EventEntry("e9", {"100": 55, "200": 50})]}))
        self.assertFalse(m.ok)

    def test_one_team_matches_by_that_team_and_score(self):
        # Missouri St. (2623) v Lincoln (MO), which had no ESPN id
        m = match_espn_event(D, "2623", "", 88, 60,
                             board({D: [EventEntry("401928621", {"2623": 88, "2876": 60}, "STATUS_FINAL")]}))
        self.assertEqual(m, Match("401928621", "one team", True, "2876"))

    def test_one_team_late_tip_day_before(self):
        # Hawaii (62) v Bethesda (no id), stored a day after ESPN's date
        m = match_espn_event(D, "62", "", 90, 52, board({PREV: [EventEntry("401929001", {"62": 90, "3246": 52})]}))
        self.assertEqual(m, Match("401929001", "one team, day before", True, "3246"))

    def test_one_team_drops_postponed_event_on_same_day(self):
        # UNC Wilmington (350): Montreat final + a postponed event the same day
        events = [EventEntry("401934189", {"350": 95, "2410": 61}, "STATUS_FINAL"),
                  EventEntry("401926864", {"350": None, "309": None}, "STATUS_POSTPONED")]
        m = match_espn_event(D, "350", "", 95, 61, board({D: events}))
        self.assertEqual(m, Match("401934189", "one team", True, "2410"))

    def test_one_team_rejects_event_against_another_known_team(self):
        # the anchor played a mapped team that day: a different game, even with the same score
        events = [EventEntry("e2", {"100": 70, "300": 60})]
        m = match_espn_event(D, "100", "", 70, 60, board({D: events}), known_espn_ids={"100", "300"})
        self.assertFalse(m.ok)
        # same score: reported as a likely duplicate team row, not as "no event"
        self.assertIn("ESPN id 300 belongs to another of our teams", m.how)

    def test_one_team_needs_the_score(self):
        m = match_espn_event(D, "100", "", 70, 60, board({D: [EventEntry("e3", {"100": 71, "999": 60})]}))
        self.assertFalse(m.ok)
        self.assertIn("score must match", m.how)

    def test_no_ids_and_fetch_failure_and_ambiguous(self):
        self.assertEqual(match_espn_event(D, "", "", 1, 0, board({})).how, "no ESPN id for either team")
        self.assertEqual(match_espn_event(D, "100", "200", 1, 0, lambda d: None).how, "scoreboard fetch failed")
        two = [EventEntry("a", {"100": 70, "200": 60}), EventEntry("b", {"100": 70, "200": 60})]
        self.assertTrue(match_espn_event(D, "100", "200", 70, 60, board({D: two})).how.startswith("ambiguous: 2"))

    def test_shared_event_flags_the_duplicate_game(self):
        out = flag_shared_events({124573: Match("401925751", "both teams, day before", True),
                                  124432: Match("401925751", "both teams", True),
                                  1: Match("x", "both teams", True)})
        self.assertTrue(out[124432].ok and out[1].ok)
        self.assertFalse(out[124573].ok)
        self.assertIn("game 124432", out[124573].how)

    def test_entries_from_scoreboard(self):
        events = [{"id": "401", "competitions": [{"status": {"type": {"name": "STATUS_FINAL"}}, "competitors": [
            {"team": {"id": 62}, "score": "90"}, {"team": {"id": "3246"}, "score": "52"}]}]},
            {"id": "402", "status": {"type": {"name": "STATUS_POSTPONED"}}, "competitions": [{"competitors": [
                {"team": {"id": "1"}}, {"team": {"id": "2"}, "score": ""}]}]}]
        a, b = entries_from_scoreboard(events)
        self.assertEqual((a.event_id, a.scores, a.dead), ("401", {"62": 90, "3246": 52}, False))
        self.assertEqual((b.scores, b.dead), ({"1": None, "2": None}, True))


class SyncCommandResolutionTests(TestCase):
    """The command resolves through the matcher and prints every game it cannot resolve."""

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
        cls.both = g(cls.a, cls.b, PREV, 70, 60, "1")          # both mapped, same day
        cls.one = g(cls.d, cls.c, PREV, 88, 61, "2")           # one mapped (c has no ESPN id)
        cls.late = g(cls.b, cls.d, D, 77, 75, "3")             # late tip: ESPN lists it on PREV
        cls.none = g(cls.a, cls.e, D, 80, 50, "4")             # one mapped, no ESPN event at all
        cls.dup = g(cls.a, cls.b, D, 70, 60, "5")              # same game stored again a day later

    def _fake_client(self):
        events = {"20261124": [
            {"id": "E1", "competitions": [{"competitors": [{"team": {"id": "100"}, "score": "70"},
                                                           {"team": {"id": "200"}, "score": "60"}]}]},
            {"id": "E2", "competitions": [{"competitors": [{"team": {"id": "400"}, "score": "88"},
                                                           {"team": {"id": "9001"}, "score": "61"}]}]},
            {"id": "E3", "competitions": [{"competitors": [{"team": {"id": "200"}, "score": "77"},
                                                           {"team": {"id": "400"}, "score": "75"}]}]},
        ]}

        class Resp:
            def __init__(self, day): self.day = day
            def raise_for_status(self): pass
            def json(self): return {"events": events.get(self.day, [])}

        class FakeClient:
            BASE_URL = "https://espn.test"
            timeout = 5

            def __init__(self, *a, **k):
                self.session = SimpleNamespace(get=lambda url, params, timeout: Resp(params["dates"]))

            def _rate_limit(self): pass
            def get_summary(self, eid): return None  # fetch phase isn't under test
        return FakeClient

    def test_resolves_three_and_reports_the_rest(self):
        out = StringIO()
        with mock.patch("ncaa.utils.ncaa_api.ESPNAPIClient", self._fake_client()):
            call_command("sync_ncaa_player_gamelogs", season=2027, stdout=out)
        text = out.getvalue()
        self.assertIn("Resolved 3/5 NCAA games", text)
        self.assertIn("both teams: 1", text)
        self.assertIn("one team: 1", text)
        self.assertIn("both teams, day before: 1", text)
        self.assertIn(f"Unresolved: 2 games — ids {sorted([self.none.pk, self.dup.pk])}", text)
        self.assertIn(f"same ESPN event E1 as game {self.both.pk}", text)
        self.assertIn(f"{self.none.pk}  2026-11-25  a v e-nond1: no ESPN event", text)
