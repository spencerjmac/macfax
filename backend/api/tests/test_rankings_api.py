from datetime import datetime, timezone as dt_timezone

from django.test import TestCase
from django.urls import reverse

from ncaa.models import Season, Team, TeamSeasonRatings


class RankingsTimestampTests(TestCase):
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
