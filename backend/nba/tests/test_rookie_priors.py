"""
Phase 4 Stage 2: rookie priors wiring.

D3 — drafted rookies carry a population-mean prior, not an observed stat, so
_project_bpr must pass their BPR through UNCHANGED (no shrinkage toward the
league mean). A non-rookie acquisition with the same numbers must still shrink.
D2 — pick-binned MPG; unknown pick → second-round default.
"""

from django.test import SimpleTestCase

from nba.management.commands.compute_nba_team_outlooks import (
    Command,
    ROOKIE_PRIOR_OBPR,
    ROOKIE_PRIOR_DBPR,
    ROOKIE_MPG_DEFAULT,
    rookie_mpg_for_pick,
)


def _rookie_slot():
    return {
        "player_name": "Rookie X",
        "acquisition_type": "drafted",
        "is_rookie_prior": True,
        "obpr": ROOKIE_PRIOR_OBPR,
        "dbpr": ROOKIE_PRIOR_DBPR,
        "bpr": ROOKIE_PRIOR_OBPR + ROOKIE_PRIOR_DBPR,
        "stats_obj": None,
    }


class RookiePriorTests(SimpleTestCase):
    def test_rookie_prior_passes_through_unchanged(self):
        cmd = Command()
        cmd.rapm_gap_sigma = 3.5
        o, d, b = cmd._project_bpr(
            _rookie_slot(), league_obpr_avg=1.0, league_dbpr_avg=1.0, league_bpr_avg=2.0
        )
        self.assertEqual(o, ROOKIE_PRIOR_OBPR)
        self.assertEqual(d, ROOKIE_PRIOR_DBPR)
        self.assertEqual(b, ROOKIE_PRIOR_OBPR + ROOKIE_PRIOR_DBPR)

    def test_non_rookie_same_numbers_still_shrinks(self):
        # identical BPR values but NOT flagged is_rookie_prior → shrinkage applies,
        # pulling the projection toward the (nonzero) league mean.
        cmd = Command()
        cmd.rapm_gap_sigma = 3.5
        slot = _rookie_slot()
        slot["acquisition_type"] = "signed"
        slot.pop("is_rookie_prior")
        o, d, b = cmd._project_bpr(
            slot, league_obpr_avg=1.0, league_dbpr_avg=1.0, league_bpr_avg=2.0
        )
        self.assertGreater(o, ROOKIE_PRIOR_OBPR)  # shrunk upward toward league mean 1.0
        self.assertGreater(d, ROOKIE_PRIOR_DBPR)

    def test_pick_bin_mpg(self):
        self.assertEqual(rookie_mpg_for_pick(1), 27.9)
        self.assertEqual(rookie_mpg_for_pick(5), 27.9)
        self.assertEqual(rookie_mpg_for_pick(6), 20.9)
        self.assertEqual(rookie_mpg_for_pick(14), 20.9)
        self.assertEqual(rookie_mpg_for_pick(30), 16.4)
        self.assertEqual(rookie_mpg_for_pick(45), 13.0)

    def test_unknown_pick_defaults_to_second_round(self):
        self.assertEqual(rookie_mpg_for_pick(None), ROOKIE_MPG_DEFAULT)
        self.assertEqual(rookie_mpg_for_pick(99), ROOKIE_MPG_DEFAULT)  # out of range
