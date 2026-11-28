"""
Player impact and MPR use D-I v D-I games only (ncaa/analytics/player_value/d1_games.py).

2026-11-27: syncing 2025-26's missing D-I v non-D-I games lifted every D-I player's MPR by about 0.47
(RAPM shrinks the non-D-I opponents toward an average D-I level, so beating them by 40 credits everyone).

Invariants:
- d1_vs_d1_games_q keeps games between two teams that were D-I that season (TeamSeasonMembership);
- the RAPM dataset (stints, possessions) holds only D-I v D-I games;
- d1_box_lines / overlay_d1_box: box rates over D-I v D-I games, rows without one dropped, possessions
  recomputed from D-I v D-I stints when asked;
- compute_ncaa_player_impact rates on-court play from D-I v D-I stints only;
- season stat lines keep every game;
- the players API lists D-I teams' players only.
"""
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from ncaa.analytics.player_value.bpr.datasets import build_rapm_dataset
from ncaa.analytics.player_value.d1_games import d1_box_lines, d1_vs_d1_games_q, overlay_d1_box
from ncaa.models import (Game, Player, PlayerGameStats, PlayerGameStint, PlayerSeasonStats, Season, Team,
                         TeamSeasonMembership)

Y = 2027


def stint(player, team, game, pts_scored, pts_allowed):
    box = {"team_fgm": 30, "team_fga": 60, "team_fg3m": 8, "team_fta": 20, "team_tov": 10, "team_oreb": 8,
           "team_dreb": 25, "opp_fgm": 25, "opp_fga": 60, "opp_fg3m": 6, "opp_fta": 15, "opp_tov": 12,
           "opp_oreb": 7, "opp_dreb": 24}
    return PlayerGameStint(player=player, team=team, game=game, stint_index=0, period=1, clock_start_secs=1200,
                           clock_end_secs=0, secs_on=1200, pts_scored=pts_scored, pts_allowed=pts_allowed,
                           plus_minus=pts_scored - pts_allowed, **box)


class D1OnlyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.season = Season.objects.create(year=Y, display_name="2026-27")
        cls.a, cls.b = (Team.objects.create(slug=s, name=s.upper(), is_d1=True) for s in ("a", "b"))
        cls.c = Team.objects.create(slug="c-nond1", name="C", is_d1=False)
        for t, d1 in ((cls.a, True), (cls.b, True), (cls.c, False)):
            TeamSeasonMembership.objects.create(season=cls.season, team=t, is_d1=d1)
        g = lambda h, a, d, hs, as_: Game.objects.create(  # noqa: E731
            home_team=h, away_team=a, game_date=d, season_year=Y, status="final", home_score=hs,
            away_score=as_, source="espn", source_game_id=f"{h.slug}{a.slug}")
        cls.ab = g(cls.a, cls.b, date(2026, 11, 20), 70, 66)       # D-I v D-I
        cls.ac = g(cls.a, cls.c, date(2026, 11, 22), 110, 50)      # D-I v non-D-I blowout
        cls.players = {k: [Player.objects.create(espn_athlete_id=f"{k}{i}", display_name=f"{k} {i}")
                           for i in range(5)] for k, t in (("a", cls.a), ("b", cls.b), ("c", cls.c))}
        label = {cls.a.pk: "a", cls.b.pk: "b", cls.c.pk: "c"}
        stints, rows = [], []
        for game, home, away, hp, ap in ((cls.ab, cls.a, cls.b, 70, 66), (cls.ac, cls.a, cls.c, 110, 50)):
            for team, scored, allowed in ((home, hp, ap), (away, ap, hp)):
                for p in cls.players[label[team.pk]]:
                    stints.append(stint(p, team, game, scored, allowed))
                    # a scores 10 a man against b and 22 against c (the blowout)
                    pts = scored // 5
                    rows.append(PlayerGameStats(player=p, game=game, team=team, starter=True, minutes=40,
                                                points=pts, fg_made=pts // 2, fg_attempted=pts, fg3_made=0,
                                                fg3_attempted=2, ft_made=0, ft_attempted=2, rebounds=6,
                                                offensive_rebounds=2, defensive_rebounds=4, assists=3,
                                                turnovers=2, steals=1, blocks=1, fouls=2))
        PlayerGameStint.objects.bulk_create(stints)
        PlayerGameStats.objects.bulk_create(rows)

    def test_game_filter_keeps_d1_v_d1_only(self):
        self.assertEqual(list(Game.objects.filter(d1_vs_d1_games_q([Y])).values_list("pk", flat=True)), [self.ab.pk])
        self.assertEqual(set(PlayerGameStint.objects.filter(d1_vs_d1_games_q([Y], "game__"))
                             .values_list("game_id", flat=True)), {self.ab.pk})

    def test_rapm_dataset_has_no_non_d1_game(self):
        ds = build_rapm_dataset([Y], verbose=False)
        ids = set(ds["player_ids"])
        self.assertTrue({p.pk for p in self.players["a"] + self.players["b"]} <= ids)
        self.assertFalse({p.pk for p in self.players["c"]} & ids)
        a0 = self.players["a"][0].pk
        one_game = ds["possession_totals"][a0]["off"]
        self.assertGreater(one_game, 0)
        self.assertAlmostEqual(one_game, 60 + 0.44 * 20 + 10 - 8)   # the a-b game only

    def test_box_lines_and_overlay(self):
        lines = d1_box_lines(Y)
        a0 = self.players["a"][0]
        line = lines[(a0.pk, self.a.pk)]
        self.assertEqual((line["gp"], line["pts"]), (1, 14.0))      # the a-b game only (22 against c dropped)
        self.assertAlmostEqual(line["d1_minutes_share"], 0.5)
        self.assertNotIn((self.players["c"][0].pk, self.c.pk), lines)
        rows = [{"player_id": a0.pk, "team_id": self.a.pk, "gp": 2, "pts": 18.0, "off_poss": 999.0, "def_poss": 999.0},
                {"player_id": self.players["c"][0].pk, "team_id": self.c.pk, "gp": 1, "pts": 10.0,
                 "off_poss": 50.0, "def_poss": 50.0}]
        out = overlay_d1_box(rows, year=Y, replace_poss=True)
        self.assertEqual(len(out), 1)                                # the non-D-I player is dropped
        self.assertEqual((out[0]["gp"], out[0]["pts"]), (1, 14.0))
        self.assertAlmostEqual(out[0]["off_poss"], 60 + 0.44 * 20 + 10 - 8)
        self.assertAlmostEqual(out[0]["def_poss"], 60 + 0.44 * 15 + 12 - 7)
        kept = overlay_d1_box(rows[:1], year=Y)
        self.assertEqual(kept[0]["off_poss"], 999.0)                 # stored possessions kept unless asked

    def test_impact_rates_d1_v_d1_stints_and_season_lines_keep_every_game(self):
        call_command("compute_ncaa_player_season_stats", "--season", str(Y), stdout=StringIO())
        a0 = self.players["a"][0]
        self.assertEqual(PlayerSeasonStats.objects.get(player=a0, season=self.season).gp, 2)   # every game
        call_command("compute_ncaa_player_impact", "--season", str(Y), stdout=StringIO())
        st = PlayerSeasonStats.objects.get(player=a0, season=self.season)
        self.assertEqual(st.on_court_net_pg, 4.0)    # +4 in the a-b game; the +60 against c is not counted
        self.assertIsNone(PlayerSeasonStats.objects.get(player=self.players["c"][0], season=self.season).on_court_net_pg)

    def test_players_api_lists_d1_players_only(self):
        call_command("compute_ncaa_player_season_stats", "--season", str(Y), stdout=StringIO())
        r = APIClient().get("/api/players/", {"season": Y, "min_gp": 1})
        self.assertEqual(r.status_code, 200)
        rows = r.json()
        rows = rows.get("results", rows) if isinstance(rows, dict) else rows
        self.assertEqual({x["team_slug"] for x in rows}, {"a", "b"})
        self.assertEqual(len(rows), 10)
