"""
BT-10 pure-Python tests — no Django, no DB.

Tests validate that compute_bucket_percentiles() and recommend_thresholds()
produce correct output from known synthetic datasets.
"""

import unittest
from dataclasses import dataclass, field

from backtesting.roster_outlook.bt10_threshold_calibration import (
    PlayerThresholdRow,
    ThresholdDataset,
    compute_bucket_percentiles,
    recommend_thresholds,
)


def _row(player_id, role_bucket, conf_group, blk_pg=0.0, stl_pg=0.0, fg3a_pg=0.0,
         projected_dbpr=1.0, source_year=2024):
    return PlayerThresholdRow(
        player_id=player_id,
        role_bucket=role_bucket,
        conf_group=conf_group,
        blk_pg=blk_pg,
        stl_pg=stl_pg,
        ast_pg=1.0,
        reb_pg=3.0,
        fg3a_pg=fg3a_pg,
        projected_dbpr=projected_dbpr,
        projected_obpr=1.0,
        minutes_share_p2=0.10,
        source_year=source_year,
    )


def _synthetic_dataset():
    """50 Bigs, 50 Guards, 50 Wings with known stat distributions."""
    players = []
    pid = 1
    # Bigs: blk_pg = 0.1, 0.2, …, 5.0 (evenly spaced), stl=0.5, fg3a=0.1
    for i in range(1, 51):
        players.append(_row(pid, "Big", "power", blk_pg=i * 0.1, stl_pg=0.5, fg3a_pg=0.1,
                            projected_dbpr=float(i)))
        pid += 1
    # Guards: stl_pg = 0.1–5.0, fg3a_pg = 0.1–5.0, blk=0.1
    for i in range(1, 51):
        players.append(_row(pid, "G", "power", blk_pg=0.1, stl_pg=i * 0.1, fg3a_pg=i * 0.1,
                            projected_dbpr=float(i)))
        pid += 1
    # Wings: stl_pg = 0.1–5.0, fg3a_pg = 0.1–5.0, blk=0.1, conf=mid_major
    for i in range(1, 51):
        players.append(_row(pid, "Wing", "mid_major", blk_pg=0.1, stl_pg=i * 0.1,
                            fg3a_pg=i * 0.1, projected_dbpr=float(i)))
        pid += 1
    return ThresholdDataset(players=players, source_years=[2024], n_players=len(players))


class TestComputeBucketPercentiles(unittest.TestCase):

    def setUp(self):
        self.dataset = _synthetic_dataset()
        self.percs = compute_bucket_percentiles(self.dataset)

    def test_all_buckets_present(self):
        for bucket in ("G", "Wing", "Big"):
            self.assertIn(bucket, self.percs.by_bucket, f"Missing bucket {bucket}")

    def test_big_blk_p50_correct(self):
        # Bigs: blk = 0.1, 0.2, ..., 5.0 → p50 ≈ 2.55 (median of 50 values)
        p50 = self.percs.by_bucket["Big"]["blk_pg_p50"]
        self.assertAlmostEqual(p50, 2.55, places=1)

    def test_guard_stl_p70_correct(self):
        # Guards: stl = 0.1, 0.2, ..., 5.0 → p70 should be around 3.5
        p70 = self.percs.by_bucket["G"]["stl_pg_p70"]
        self.assertGreater(p70, 2.5)
        self.assertLess(p70, 4.5)

    def test_conf_group_dbpr_present(self):
        self.assertIn("power", self.percs.by_conf_group)
        self.assertIn("projected_dbpr_p25", self.percs.by_conf_group["power"])

    def test_n_by_bucket_correct(self):
        self.assertEqual(self.percs.n_by_bucket["Big"], 50)
        self.assertEqual(self.percs.n_by_bucket["G"], 50)
        self.assertEqual(self.percs.n_by_bucket["Wing"], 50)


class TestRecommendThresholds(unittest.TestCase):

    def setUp(self):
        dataset = _synthetic_dataset()
        percs = compute_bucket_percentiles(dataset)
        self.result = recommend_thresholds(percs)
        self.recs = {r.threshold_name: r for r in self.result.recommendations}

    def test_all_expected_threshold_names_present(self):
        expected = {
            "RIM_PROTECTOR_BLK_BIG",
            "RIM_PROTECTOR_BLK_WING",
            "RIM_PROTECTOR_BLK_G",
            "DISRUPTOR_STL_G",
            "DISRUPTOR_STL_WING",
            "DISRUPTOR_STL_BIG",
            "SPACER_FG3A_G",
            "SPACER_FG3A_WING",
            "SPACER_FG3A_BIG",
            "WEAK_DEFENDER_DBPR_POWER",
        }
        for name in expected:
            self.assertIn(name, self.recs, f"Missing recommendation: {name}")

    def test_legacy_constants_kept_for_guard_wing_blk(self):
        # Guards and Wings keep legacy 0.70 for rim_protector
        self.assertAlmostEqual(self.recs["RIM_PROTECTOR_BLK_G"].recommended_value, 0.70)
        self.assertAlmostEqual(self.recs["RIM_PROTECTOR_BLK_WING"].recommended_value, 0.70)

    def test_big_blk_recommendation_higher_than_guard(self):
        big_rec = self.recs["RIM_PROTECTOR_BLK_BIG"].recommended_value
        g_rec   = self.recs["RIM_PROTECTOR_BLK_G"].recommended_value
        # Big p50 blk should be well above guard p50 blk (bigs block more)
        self.assertGreater(big_rec, g_rec)

    def test_summary_table_is_string(self):
        self.assertIsInstance(self.result.summary_table, str)
        self.assertIn("BT-10", self.result.summary_table)

    def test_confidence_set_on_all_recs(self):
        for rec in self.result.recommendations:
            self.assertIn(rec.confidence, ("high", "medium", "low"),
                          f"{rec.threshold_name} has invalid confidence: {rec.confidence}")


if __name__ == "__main__":
    unittest.main()
