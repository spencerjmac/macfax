"""
Phase 2 task 2.1: native_prior blends box rating with last season's rating
shrunk by rho; a player with only one of the two gets that one.
"""

from django.test import SimpleTestCase

from nba.analytics.native_prior import native_prior


class NativePriorTests(SimpleTestCase):

    def test_both_present_blends_box_with_shrunk_prev(self):
        out = native_prior({1: 4.0}, {1: 2.0}, w_box=0.6, rho=0.5)
        self.assertAlmostEqual(out[1], 0.6 * 4.0 + 0.4 * 0.5 * 2.0)

    def test_box_only_returns_box(self):
        self.assertEqual(native_prior({1: -1.5}, {}, w_box=0.3, rho=0.8), {1: -1.5})

    def test_prev_only_returns_rho_times_prev(self):
        out = native_prior({}, {2: 3.0}, w_box=0.3, rho=0.8)
        self.assertAlmostEqual(out[2], 2.4)

    def test_mixed_players_cover_the_union(self):
        out = native_prior({1: 1.0, 2: 2.0}, {2: 4.0, 3: -2.0}, w_box=0.5, rho=0.5)
        self.assertEqual(set(out), {1, 2, 3})
        self.assertAlmostEqual(out[1], 1.0)
        self.assertAlmostEqual(out[2], 0.5 * 2.0 + 0.5 * 0.5 * 4.0)
        self.assertAlmostEqual(out[3], -1.0)

    def test_w_box_one_ignores_prev(self):
        out = native_prior({1: 3.0}, {1: 10.0}, w_box=1.0, rho=0.9)
        self.assertAlmostEqual(out[1], 3.0)

    def test_w_box_zero_uses_only_shrunk_prev(self):
        out = native_prior({1: 3.0}, {1: 10.0}, w_box=0.0, rho=0.9)
        self.assertAlmostEqual(out[1], 9.0)

    def test_empty_inputs_give_empty_prior(self):
        self.assertEqual(native_prior({}, {}, w_box=0.5, rho=0.5), {})

    def test_inputs_are_not_modified(self):
        box, prev = {1: 1.0}, {1: 2.0, 2: 3.0}
        native_prior(box, prev, w_box=0.5, rho=0.5)
        self.assertEqual(box, {1: 1.0})
        self.assertEqual(prev, {1: 2.0, 2: 3.0})
