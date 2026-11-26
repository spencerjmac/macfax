from datetime import datetime, timezone as dt_timezone

from django.urls import reverse

from api.tests.base import IsolatedCacheTestCase
from ncaa.models import Season, Team, TeamSeasonRatings


class RankingsTimestampTests(IsolatedCacheTestCase):
    def test_rankings_rows_expose_computed_timestamp_as_updated_at(self):
        season = Season.objects.create(
            year=2026,
            display_name="2025-26",
            is_current=True,
        )
        team = Team.objects.create(slug="duke", name="Duke", is_d1=True)
        ratings = TeamSeasonRatings.objects.create(
            team=team,
            season=season,
            adj_o=120.0,
            adj_d=90.0,
            adj_em=30.0,
            adj_tempo=68.0,
            games_played=1,
            wins=1,
            losses=0,
        )
        expected = datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt_timezone.utc)
        TeamSeasonRatings.all_objects.filter(pk=ratings.pk).update(computed_at=expected)

        response = self.client.get(reverse("rankings-list"), {"season": "2026"})

        self.assertEqual(response.status_code, 200)
        row = response.json()["results"][0]
        self.assertEqual(row["computed_at"], "2026-01-02T03:04:05Z")
        self.assertEqual(row["updated_at"], "2026-01-02T03:04:05Z")


class RankingsSeasonMembershipTests(IsolatedCacheTestCase):
    """The table lists the teams that were D1 that season (TeamSeasonMembership), not D1 today."""

    def test_past_season_uses_membership_not_team_is_d1(self):
        from ncaa.models import TeamSeasonMembership

        season = Season.objects.create(year=2005, display_name="2004-05", is_current=False)
        Season.objects.create(year=2026, display_name="2025-26", is_current=True)
        hartford = Team.objects.create(slug="hartford", name="Hartford", is_d1=False)     # D1 then, not now
        duke = Team.objects.create(slug="duke", name="Duke", is_d1=True)                  # D1 then and now
        cbu = Team.objects.create(slug="cal-baptist", name="Cal Baptist", is_d1=True)      # D1 now, not then
        TeamSeasonMembership.objects.create(season=season, team=hartford, is_d1=True)
        TeamSeasonMembership.objects.create(season=season, team=duke, is_d1=True)
        TeamSeasonMembership.objects.create(season=season, team=cbu, is_d1=False)
        for team, em in ((hartford, -5.0), (duke, 25.0), (cbu, 0.0)):
            TeamSeasonRatings.objects.create(team=team, season=season, adj_o=100.0 + em, adj_d=100.0,
                                             adj_em=em, adj_tempo=68.0, games_played=30, wins=15, losses=15)

        response = self.client.get(reverse("rankings-list"), {"season": "2005"})

        self.assertEqual(response.status_code, 200)
        slugs = [r["team_slug"] for r in response.json()["results"]]
        self.assertEqual(slugs, ["duke", "hartford"])
