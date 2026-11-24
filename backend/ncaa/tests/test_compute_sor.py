"""
compute_sor: home-court advantage applies (lowercase sites; the Game's neutral flag counts), canceled 0-0
'final' games are skipped, and a seeded generator makes reruns identical.
"""
from datetime import date
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from api.matchup_engine import forecast_game
from ncaa.models import Game, NationalAverages, PipelineConfig, Season, Team, TeamGameStats, TeamSeasonRatings


class ComputeSorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.season = Season.objects.create(year=2025, display_name="2024-25")
        NationalAverages.objects.create(
            season=cls.season, avg_ortg=105.0, avg_pace=68.0, avg_efg=0.5, avg_tov=0.18, avg_orb=0.3, avg_ftr=0.3,
            total_possessions=1.0, total_games=3, hca_points=3.0, prediction_sigma=11.0, coef_efg=0.0,
            coef_tov=0.0, coef_orb=0.0, coef_ftr=0.0, coef_intercept=0.0, coef_r_squared=0.0)
        PipelineConfig.objects.update_or_create(pk=1, defaults=dict(
            sor_baseline_rank_min=1, sor_baseline_rank_max=3, sor_fallback_rank_min=1, sor_fallback_rank_max=3))
        cls.teams = [Team.objects.create(slug=f"s{i}", name=f"S{i}", is_d1=True) for i in range(3)]
        for rank, t in enumerate(cls.teams, start=1):
            TeamSeasonRatings.all_objects.create(team=t, season=cls.season, is_pre_tournament=False, adj_o=105.0 - rank,
                                                 adj_d=100.0, adj_em=5.0 - rank, adj_tempo=68.0, rank_adj_em=rank)
        # (home, away, neutral flag, home pts, away pts); the last is canceled ('final' 0-0)
        for n, (h, a, neutral, hs, as_) in enumerate(
                [(0, 1, False, 70, 60), (2, 0, False, 70, 60), (1, 2, True, 70, 60), (0, 2, False, 0, 0)], start=1):
            g = Game.objects.create(season_year=2025, game_date=date(2025, 1, n), home_team=cls.teams[h],
                                    away_team=cls.teams[a], status="final", home_score=hs, away_score=as_,
                                    neutral_site=neutral, source="espn", source_game_id=f"sor{n}")
            TeamGameStats.objects.create(game=g, team=cls.teams[h], opponent=cls.teams[a], home_away="H", pts=hs)
            TeamGameStats.objects.create(game=g, team=cls.teams[a], opponent=cls.teams[h], home_away="A", pts=as_)

    def _run(self):
        seen = []

        def spy(**kw):
            seen.append(kw["site"])
            return forecast_game(**kw)

        with mock.patch("ncaa.management.commands.compute_sor.forecast_game", side_effect=spy):
            call_command("compute_sor", season=2025, trials=2000, stdout=StringIO())
        return seen

    def test_sites_lowercase_neutral_flag_and_canceled_skipped(self):
        seen = self._run()
        # 3 played games x 2 sides; the canceled game is never forecast
        self.assertEqual(len(seen), 6)
        self.assertEqual(sorted(seen), ["away", "away", "home", "home", "neutral", "neutral"])

    def test_rerun_gives_same_ranks(self):
        self._run()
        first = list(TeamSeasonRatings.all_objects.order_by("team_id").values_list("sor_rank", flat=True))
        self._run()
        second = list(TeamSeasonRatings.all_objects.order_by("team_id").values_list("sor_rank", flat=True))
        self.assertEqual(first, second)
