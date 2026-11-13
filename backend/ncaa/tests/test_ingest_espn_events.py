"""
ingest_gamelogs --espn-event-ids (Task 6f.3): add games by ESPN event id.

Invariants pinned here:
- Both teams resolve by ESPN id only; an unmapped opponent is reported and no team or mapping is created.
- A stored game of the same two teams tipping < 12 h apart is a duplicate (skipped); the second game of a
  two-game series on the next day is not.
- Existing event ids are skipped; the Game and both box rows are written; period_count comes from status.period.
"""

import json
import tempfile
from datetime import date
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from ncaa.models import Game, Season, Team, TeamExternalId, TeamGameStats


def summary(eid, when, home, away, hs, as_, period=2):
    comps = [{"homeAway": "home", "team": {"id": home, "displayName": f"T{home}"}, "score": str(hs),
              "linescores": [{}] * period},
             {"homeAway": "away", "team": {"id": away, "displayName": f"T{away}"}, "score": str(as_),
              "linescores": [{}] * period}]
    return {"header": {"id": eid, "competitions": [{"date": when, "neutralSite": False, "competitors": comps,
                                                     "status": {"type": {"state": "post", "completed": True, "name": "STATUS_FINAL"}}}]},
            "boxscore": {"teams": [{"team": {"id": t}, "statistics": [
                {"name": "fieldGoalsMade-fieldGoalsAttempted", "displayValue": "25-55"},
                {"name": "freeThrowsMade-freeThrowsAttempted", "displayValue": "10-15"}]} for t in (home, away)],
                "players": []}}


class EspnEventIngestTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2021, display_name="2020-21", is_current=False)
        self.a = Team.objects.create(name="Alpha", slug="alpha", is_d1=True)
        self.b = Team.objects.create(name="Beta", slug="beta", is_d1=True)
        for t, eid in ((self.a, "1"), (self.b, "2")):
            TeamExternalId.objects.create(team=t, source="espn", external_id=eid, external_name=t.name, confidence=1.0)
        self.summaries = {
            "e1": summary("e1", "2021-01-09T19:00Z", "1", "2", 70, 60),
            "e2": summary("e2", "2021-01-10T19:00Z", "2", "1", 65, 64, period=3),   # next-day series game
            "e3": summary("e3", "2021-01-09T23:00Z", "1", "2", 70, 60),             # same game, other id
            "e4": summary("e4", "2021-01-12T19:00Z", "1", "999", 90, 40),           # unmapped opponent
        }

    def ingest(self, ids):
        from ncaa.utils.ncaa_api import ESPNAPIClient
        with tempfile.TemporaryDirectory() as d:
            rep = Path(d) / "r.json"
            with mock.patch.object(ESPNAPIClient, "get_summary", side_effect=lambda e: json.loads(json.dumps(self.summaries[e]))):
                call_command("ingest_gamelogs", season=2021, source="espn", espn_event_ids=",".join(ids),
                             report=str(rep), stdout=StringIO())
            return json.loads(rep.read_text())

    def test_series_kept_duplicate_and_unmapped_skipped(self):
        r = self.ingest(["e1", "e2", "e3", "e4"])
        self.assertEqual(sorted(r["created"]), ["e1", "e2"])
        self.assertEqual([s["event"] for s in r["skipped_same_pair"]], ["e3"])
        self.assertEqual([u["event"] for u in r["unresolved"]], ["e4"])
        self.assertFalse(TeamExternalId.objects.filter(external_id="999").exists())
        self.assertEqual(Team.objects.count(), 2)
        g2 = Game.objects.get(source_game_id="e2")
        self.assertEqual((g2.home_team, g2.away_team, g2.home_score, g2.away_score), (self.b, self.a, 65, 64))
        self.assertEqual((g2.period_count, g2.went_to_ot), (3, True))
        self.assertEqual(TeamGameStats.objects.filter(game=g2).count(), 2)
        self.assertEqual(Game.objects.get(source_game_id="e1").game_date, date(2021, 1, 9))

    def test_existing_event_skipped(self):
        self.ingest(["e1"])
        r = self.ingest(["e1"])
        self.assertEqual(r["skipped_existing"], ["e1"])
        self.assertEqual(Game.objects.filter(source_game_id="e1").count(), 1)
