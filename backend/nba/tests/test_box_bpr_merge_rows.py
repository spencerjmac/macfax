"""
Box BPR uses one row per player-season. A traded player has one regular-season
row per team; the command merges them (rules as career_stats): on_court_poss
max, rate stats GP-weighted, per-game stats sum(stat x gp) / total gp, team
= the team with the most minutes.
"""

from django.test import SimpleTestCase

from nba.management.commands.nba_compute_box_bpr import _merge_player_rows


def _row(player_id, team_id, gp, mpg, pts, ts_pct, usg_pct=None, **kw):
    row = {"player_id": player_id, "team_id": team_id, "gp": gp, "mpg": mpg, "pts": pts,
           "ast": 2.0, "stl": 1.0, "blk": 0.5, "tov": 1.0, "oreb_pg": 1.0, "dreb_pg": 3.0,
           "fga_pg": 10.0, "fg3a_pg": 4.0, "fta_pg": 2.0,
           "efg_pct": 0.5, "ts_pct": ts_pct, "usg_pct": usg_pct, "ast_pct": 0.1, "oreb_pct": 0.05,
           "dreb_pct": 0.15, "ast_to": 2.0, "stl_pct": 0.01, "blk_pct": 0.01, "tov_pct": 0.1,
           "on_court_poss": 3000.0, "on_court_adj_em": 1.5, "on_court_adj_o": 112.0,
           "on_court_adj_d": 110.5, "o_mpir": 0.4, "d_mpir": -0.2,
           "baseline_obpr": 1.1, "baseline_dbpr": 0.3}
    row.update(kw)
    return row


class MergePlayerRowsTests(SimpleTestCase):

    def test_traded_player_rows_merge_into_one(self):
        rows = [
            _row(1, 10, gp=20, mpg=30.0, pts=20.0, ts_pct=0.60, usg_pct=None),
            _row(2, 10, gp=70, mpg=25.0, pts=12.0, ts_pct=0.55),
            _row(1, 20, gp=40, mpg=20.0, pts=11.0, ts_pct=0.54, usg_pct=0.22, on_court_poss=3100.0),
        ]

        merged, n_merged = _merge_player_rows(rows)

        self.assertEqual(n_merged, 1)
        self.assertEqual([r["player_id"] for r in merged], [1, 2])   # first-row order
        p = merged[0]
        self.assertEqual(p["gp"], 60)
        self.assertAlmostEqual(p["mpg"], (20 * 30 + 40 * 20) / 60)
        self.assertEqual(p["team_id"], 20)                     # 800 minutes vs 600
        self.assertEqual(p["on_court_poss"], 3100.0)           # max, not sum
        self.assertAlmostEqual(p["pts"], (20 * 20 + 11 * 40) / 60)
        self.assertAlmostEqual(p["ts_pct"], (0.60 * 20 + 0.54 * 40) / 60)
        self.assertAlmostEqual(p["usg_pct"], 0.22)             # only the row that has it
        self.assertEqual(p["baseline_obpr"], 1.1)              # player-level: kept
        self.assertIs(merged[1], rows[1])                      # untraded: untouched

    def test_one_row_per_player_after_merge(self):
        rows = [_row(pid, team, gp=10, mpg=10.0, pts=5.0, ts_pct=0.5)
                for pid, team in ((1, 10), (1, 20), (1, 30), (2, 10), (3, 20), (3, 10))]

        merged, n_merged = _merge_player_rows(rows)

        self.assertEqual(n_merged, 2)
        self.assertEqual(sorted(r["player_id"] for r in merged), [1, 2, 3])
