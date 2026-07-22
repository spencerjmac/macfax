"""
Phase 4 rookie priors wiring (Phase 4.6 Stage B form).

- Drafted rookies carry a population-mean BPR prior, not an observed stat, so
  _project_bpr passes their BPR through UNCHANGED (no shrinkage); a non-rookie
  with the same numbers still shrinks.
- Minutes: additive effective-MPG model — bin effect + wins slope, prior wins
  clamped to the fit range [15, 64], prediction floored at 0.5.
- Allocation: rookies PINNED at predicted_eff_mpg / 20 (default ON); veterans
  compete for the remainder.
"""

from django.test import SimpleTestCase

from nba.management.commands.compute_nba_team_outlooks import (
    Command,
    ROOKIE_PRIOR_OBPR,
    ROOKIE_PRIOR_DBPR,
    ROOKIE_EFF_MPG_BIN_EFFECTS,
    ROOKIE_EFF_MPG_FLOOR,
    ROOKIE_WINS_SLOPE,
    rookie_eff_mpg,
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

    def test_additive_model_bin_effects_at_average_context(self):
        # prior_wins = 41 (center) → prediction is the raw bin effect
        self.assertAlmostEqual(rookie_eff_mpg(1, 41), 20.79)
        self.assertAlmostEqual(rookie_eff_mpg(10, 41), 15.29)
        self.assertAlmostEqual(rookie_eff_mpg(25, 41), 12.66)
        self.assertAlmostEqual(rookie_eff_mpg(45, 41), 5.66)

    def test_wins_slope_direction(self):
        # worse prior team → more rookie minutes
        self.assertGreater(rookie_eff_mpg(1, 20), rookie_eff_mpg(1, 60))
        self.assertAlmostEqual(
            rookie_eff_mpg(1, 20), 20.79 + ROOKIE_WINS_SLOPE * (20 - 41)
        )

    def test_wins_clamp_at_fit_range(self):
        # 65+ contenders treated as 64-win contexts; sub-15 as 15 (D3)
        self.assertAlmostEqual(rookie_eff_mpg(1, 68), rookie_eff_mpg(1, 64))
        self.assertAlmostEqual(rookie_eff_mpg(1, 9), rookie_eff_mpg(1, 15))

    def test_prediction_floor(self):
        # 31-60 effect 5.66 − 0.152·23 = 2.16 > floor; force floor via clamp math:
        # even the worst context can't go below ROOKIE_EFF_MPG_FLOOR
        self.assertGreaterEqual(rookie_eff_mpg(60, 64), ROOKIE_EFF_MPG_FLOOR)
        self.assertGreaterEqual(rookie_eff_mpg(None, None), ROOKIE_EFF_MPG_FLOOR)

    def test_unknown_inputs_default_sanely(self):
        # unknown pick → second-round effect; unknown wins → center (no slope)
        self.assertAlmostEqual(
            rookie_eff_mpg(None, None), ROOKIE_EFF_MPG_BIN_EFFECTS[(31, 60)]
        )


def _vet(name, bpr, mpg=30.0):
    return {
        "player_name": name, "acquisition_type": "returner",
        "projected_bpr": bpr, "mpg": mpg,
    }


def _pinned_rookie(name, prior_mpg):
    return {
        "player_name": name, "acquisition_type": "drafted",
        "is_rookie_prior": True, "projected_bpr": -1.14, "mpg": prior_mpg,
    }


class PinnedAllocationTests(SimpleTestCase):
    """Phase 4.5 pin path — now gated behind --rookie-pin (Phase 4.6 rollback)."""

    def setUp(self):
        self.cmd = Command()
        self.cmd.rookie_pin = True  # explicitly enable the gated path

    def test_no_rookie_pin_fallback_rookies_compete(self):
        # --no-rookie-pin (or a Command used without handle()) leaves the flag
        # unset/False → rookies go through demand competition like every slot.
        # (CLI default is ON as of Stage B; this guards the debug fallback.)
        cmd = Command()  # no rookie_pin attribute → getattr default False
        slots = [_vet(f"V{i}", 2.0) for i in range(8)] + [_pinned_rookie("R1", 27.9)]
        cmd._allocate_minutes(slots)
        rookie = next(s for s in slots if s.get("is_rookie_prior"))
        self.assertIsNotNone(rookie["demand"])          # competed, not pinned
        self.assertNotIn("pinned_share", rookie)
        self.assertLess(rookie["minutes_share"], 27.9 / 20.0)  # demand-swamped
        self.assertAlmostEqual(sum(s["minutes_share"] for s in slots), 5.0, places=4)

    def test_pinned_share_equals_prior_over_20(self):
        slots = [_vet(f"V{i}", 2.0) for i in range(8)] + [_pinned_rookie("R1", 27.9)]
        self.cmd._allocate_minutes(slots)
        rookie = next(s for s in slots if s.get("is_rookie_prior"))
        self.assertAlmostEqual(rookie["minutes_share"], 27.9 / 20.0, places=6)
        self.assertIsNone(rookie["demand"])  # exempt from V3

    def test_veterans_compete_for_remaining_pool(self):
        slots = [_vet(f"V{i}", 2.0) for i in range(8)] + [_pinned_rookie("R1", 27.9)]
        self.cmd._allocate_minutes(slots)
        vet_total = sum(s["minutes_share"] for s in slots if not s.get("is_rookie_prior"))
        self.assertAlmostEqual(vet_total, 5.0 - 27.9 / 20.0, places=4)
        self.assertAlmostEqual(sum(s["minutes_share"] for s in slots), 5.0, places=4)

    def test_rookie_stack_scales_down_to_preserve_competitive_pool(self):
        # 3 lottery rookies pin 3×1.395 = 4.185 → must scale so vets keep 2.5
        slots = [_vet(f"V{i}", 1.0) for i in range(6)] + [
            _pinned_rookie(f"R{i}", 27.9) for i in range(3)
        ]
        self.cmd._allocate_minutes(slots)
        pinned_total = sum(s["minutes_share"] for s in slots if s.get("is_rookie_prior"))
        vet_total = sum(s["minutes_share"] for s in slots if not s.get("is_rookie_prior"))
        self.assertAlmostEqual(pinned_total, 2.5, places=4)
        self.assertAlmostEqual(vet_total, 2.5, places=4)
        self.assertAlmostEqual(sum(s["minutes_share"] for s in slots), 5.0, places=4)
