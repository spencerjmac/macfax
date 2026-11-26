"""
Task 5.3: nba_compute_native_bpr, the production native BPR.

- native_season builds the prior and fits exactly as nba_experiment_final_bpr's
  native chain at the recipe (w_box 0.5, rho 1.0, tiers x8, age-mult 1): run
  season by season on its own outputs it gives the harness chain's ratings.
- The command refuses when Y-1 holds non-native ratings, uses Y-1's stored
  native ratings as prev (box only when Y-1 has none), and fits the aging curve
  on stored native seasons before Y.
- --write clears and writes obpr, dbpr, bpr, bpr_last_updated and bpr_model on
  Y's regular rows (every team row of a traded player), leaving wins_added,
  other seasons and playoff rows alone. --dry-run writes nothing.

Task 5.4e:
- The lambda tiers get every player's full-season minutes (mpg x gp summed over
  team rows), box row or not.
- Stored ratings come back in NBA.com id order whatever the row order.
- Aging-weight possessions are cached per season and reloaded from stints only
  when the season's stint fingerprint changes.

Task 5.6:
- The chain reads Y-1's obpr_raw / dbpr_raw; it refuses a native Y-1 row with
  no raw values (written before centring).
- --write stores the fit as obpr_raw / dbpr_raw, obpr / dbpr = raw minus the
  minutes-weighted league means (so they average 0), bpr = obpr + dbpr, and
  wins_added = (bpr + 1.918) x row minutes / 48 / WA_DIVISOR on every rated row;
  unrated rows get null wins_added.

Stint loading and the RAPM fit are stood in for; the write tests use the real
test database.
"""

import tempfile
from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from nba.management.commands import nba_compute_native_bpr as nb
from nba.management.commands.nba_experiment_final_bpr import Command as Harness
from nba.models import NBAPlayer, NBAPlayerSeasonStats, NBASeason, NBATeam
from nba.rating_scale import WA_DIVISOR

MOD = "nba.management.commands.nba_compute_native_bpr"
HARNESS = "nba.management.commands.nba_experiment_final_bpr.Command"
OLD_STAMP = datetime(2026, 7, 5, tzinfo=timezone.utc)


def _fake_fit(calls=None):
    """Stand-in for the chain fit: every prior player plus a stint-only player, deterministic."""
    def fit(loader, season, prior_o, prior_d, minutes, tier, whl, window, lambda_mult=1.0,
            newcomer_fill=None, info=None, lambda_mult_new=None, prev_ids=None, poss_out=None):
        if calls is not None:
            calls.append({"season": season, "prior_o": dict(prior_o), "prior_d": dict(prior_d),
                          "tier": tier, "whl": whl, "window": window, "lambda_mult": lambda_mult,
                          "lambda_mult_new": lambda_mult_new})
        players = sorted(set(prior_o) | {9000 + season})
        o = {p: 0.8 * prior_o.get(p, 0.0) + 0.01 * (p % 7) + 0.001 * season for p in players}
        d = {p: 0.7 * prior_d.get(p, 0.0) - 0.02 * (p % 5) for p in players}
        if poss_out is not None:
            poss_out.update(_poss(season))
        return o, d
    return fit


def _poss(season):
    return {p: 1000.0 + 37.0 * (p % 11) + season for p in range(100, 160)} | {9000 + season: 300.0}


def _box(season):
    o = {p: 0.05 * ((p * season) % 13) - 0.3 for p in range(100, 160) if (p + season) % 9}
    d = {p: 0.04 * ((p + season) % 11) - 0.2 for p in o}
    return o, d, {p: 400.0 * (p % 6) for p in o}


DOBS = {p: date(1980 + p % 15, 1 + p % 12, 1 + p % 27) for p in range(100, 160)}


class NativeSeasonTests(SimpleTestCase):

    def test_box_only_without_previous_ratings(self):
        calls = []
        box_o, box_d, minutes = _box(2006)
        with mock.patch(f"{HARNESS}._fit_chain_season", staticmethod(_fake_fit(calls))):
            nb.native_season(None, 2006, box_o, box_d, minutes, {}, {}, {}, {}, {}, {})
        c, = calls
        self.assertEqual((c["prior_o"], c["prior_d"]), (box_o, box_d))
        self.assertEqual((c["tier"], c["whl"], c["window"], c["lambda_mult"]), ("A_conservative", 90.0, 1, 8.0))

    def test_prior_blends_box_with_aged_previous(self):
        calls = []
        curve = {"o": (1.0, 0.0, 0.0), "d": (-0.5, 0.0, 0.0), "n_pairs": 40}
        box_o, box_d = {1: 2.0, 2: 1.0}, {1: 0.4, 2: -0.2}
        prev_o, prev_d = {1: 3.0, 3: -1.0}, {1: 1.0, 3: 0.5}
        dobs = {1: date(1995, 1, 1), 3: date(1990, 1, 1)}
        with mock.patch(f"{HARNESS}._fit_chain_season", staticmethod(_fake_fit(calls))), \
             mock.patch(f"{HARNESS}._aging_curve", return_value=curve):
            nb.native_season(None, 2010, box_o, box_d, {}, prev_o, prev_d, {}, {}, {}, dobs)
        c, = calls
        self.assertEqual(c["prior_o"], {1: 0.5 * 2.0 + 0.5 * (3.0 + 1.0), 2: 1.0, 3: -1.0 + 1.0})
        self.assertEqual(c["prior_d"], {1: 0.5 * 0.4 + 0.5 * (1.0 - 0.5), 2: -0.2, 3: 0.5 - 0.5})

    def test_chained_seasons_equal_the_harness_chain(self):
        """Same box, same fit: native_season on its own outputs gives the harness native chain."""
        seasons = list(range(2006, 2012))
        harness_out = {}

        def evaluate(self_, src, o, d, row, opts, out_dir):
            harness_out[src] = (dict(o), dict(d))
            return row

        opts = {"source_seasons": seasons[1:], "chain_start": 2006, "w_box": 0.5, "rho": 1.0,
                "tier": "A_conservative", "within_season_half_life": 90.0, "lambda_mult": 8.0,
                "lambda_mult_new": None, "age_mult": 1.0, "rapm_window": 1, "newcomer_prior": False,
                "run_name": "t"}
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with mock.patch(f"{HARNESS}._fit_chain_season", staticmethod(_fake_fit())), \
             mock.patch(f"{HARNESS}._load_box_priors", lambda self_, loader, s, opts: _box(s)), \
             mock.patch(f"{HARNESS}._load_birth_dates", return_value=DOBS), \
             mock.patch(f"{HARNESS}._evaluate", evaluate):
            h = Harness(stdout=StringIO())
            h._run_native_chain(None, opts, Path(tmp.name))

            hist_o, hist_d, poss = {}, {}, {}
            prev_o, prev_d = {}, {}
            for s in seasons:
                box_o, box_d, minutes = _box(s)
                prev_o, prev_d, info = nb.native_season(
                    None, s, box_o, box_d, minutes, prev_o, prev_d, dict(hist_o), dict(hist_d), dict(poss), DOBS)
                hist_o[s], hist_d[s], poss[s] = prev_o, prev_d, _poss(s)
                if s in harness_out:
                    self.assertEqual((prev_o, prev_d), harness_out[s], s)
        self.assertEqual(sorted(harness_out), seasons[1:])
        self.assertGreater(info["curve"]["n_pairs"], 30)   # the aging curve was in play


def _row(player, season, team=None, season_type="regular", **kw):
    return NBAPlayerSeasonStats.objects.create(
        player=player, season=season, team=team, season_type=season_type, gp=60, mpg=25.0, **kw)


class CommandTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.seasons = {y: NBASeason.objects.create(year=y, display_name=f"{y - 1}-{y % 100:02d}")
                       for y in (2008, 2009, 2010)}
        cls.bos = NBATeam.objects.create(
            nba_team_id=1610612738, slug="boston-celtics", name="Boston Celtics",
            abbreviation="BOS", city="Boston", conference="East", division="Atlantic")
        cls.gsw = NBATeam.objects.create(
            nba_team_id=1610612744, slug="golden-state-warriors", name="Golden State Warriors",
            abbreviation="GSW", city="Golden State", conference="West", division="Pacific")

    def setUp(self):
        self.players = [NBAPlayer.objects.create(player_id=100 + n, name=f"Player {n:02d}") for n in range(25)]
        s10 = self.seasons[2010]
        for p in self.players[1:]:
            _row(p, s10, wins_added=1.5)
        self.traded = [_row(self.players[0], s10, team=self.bos, wins_added=0.5),
                       _row(self.players[0], s10, team=self.gsw, wins_added=0.25)]
        self.unrated = _row(NBAPlayer.objects.create(player_id=999, name="No Stints"), s10,
                            obpr=1.0, dbpr=1.0, bpr=2.0, bpr_model="native-1", bpr_last_updated=OLD_STAMP,
                            wins_added=3.0)
        self.playoff = _row(self.players[1], s10, season_type="playoffs", obpr=0.5, dbpr=0.5, bpr=1.0)
        self.ratings = ({100 + n: 0.1 * n - 1.0 for n in range(25)}, {100 + n: 0.5 - 0.02 * n for n in range(25)})
        self.native_calls = []

        def native(loader, season, box_o, box_d, minutes, prev_o, prev_d, hist_o, hist_d, poss_hist, dobs):
            self.native_calls.append({"season": season, "box_o": box_o, "prev_o": prev_o, "prev_d": prev_d,
                                      "hist": sorted(hist_o), "poss": sorted(poss_hist), "minutes": minutes,
                                      "poss_hist": poss_hist})
            return self.ratings[0], self.ratings[1], {"curve": {"n_pairs": 0, "o": None, "d": None},
                                                      "n_prior": 1, "n_box_prev": 0, "n_box_only": 1,
                                                      "n_prev_only": 0, "n_rated": 25}

        cache = tempfile.TemporaryDirectory()
        self.addCleanup(cache.cleanup)
        self.cache_dir = Path(cache.name)
        self.poss_loads = []

        def possessions(s):
            self.poss_loads.append(s)
            return {1: float(s)}

        for target, value in {
            f"{MOD}.native_season": native,
            f"{MOD}.season_possessions": possessions,
            f"{MOD}.POSS_CACHE_DIR": self.cache_dir,
            f"{MOD}.load_box": lambda loader, s: ({100: 1.0}, {100: 0.0}),
        }.items():
            patcher = mock.patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _call(self, *args):
        out = StringIO()
        call_command("nba_compute_native_bpr", "--season", "2010", *args, stdout=out)
        return out.getvalue()

    def _rate(self, season, model, raw=True):
        for n, p in enumerate(self.players[:5]):
            kw = {"obpr_raw": 0.1 * n, "dbpr_raw": -0.1 * n} if model == "native-1" and raw else {}
            _row(p, self.seasons[season], obpr=0.1 * n - 1.0, dbpr=-0.1 * n + 0.25, bpr=0.0,
                 bpr_model=model, **kw)

    def test_refuses_when_previous_season_is_not_native(self):
        self._rate(2009, None)
        with self.assertRaises(CommandError):
            self._call("--dry-run")
        self.assertEqual(self.native_calls, [])

    def test_no_previous_ratings_means_box_only(self):
        self._call("--dry-run")
        c, = self.native_calls
        self.assertEqual((c["prev_o"], c["hist"]), ({}, []))
        self.assertEqual(c["box_o"], {100: 1.0})

    def test_previous_native_ratings_and_history(self):
        self._rate(2008, "native-1")
        self._rate(2009, "native-1")
        self._call("--dry-run")
        c, = self.native_calls
        self.assertEqual(c["prev_o"], {100 + n: 0.1 * n for n in range(5)})
        self.assertEqual(c["prev_d"], {100 + n: -0.1 * n for n in range(5)})
        self.assertEqual((c["hist"], c["poss"]), ([2008, 2009], [2008, 2009]))

    def test_dry_run_prints_top_20_and_writes_nothing(self):
        out = self._call("--dry-run")
        lines = [l for l in out.splitlines() if "nba_id=" in l]
        self.assertEqual(len(lines), 20)
        self.assertIn("Player 24", lines[0])
        self.unrated.refresh_from_db()
        self.assertEqual((self.unrated.bpr, self.unrated.bpr_model), (2.0, "native-1"))
        self.assertFalse(NBAPlayerSeasonStats.objects.filter(
            season=self.seasons[2010], season_type="regular", player__player_id__lt=200, obpr__isnull=False).exists())

    def _means(self):
        """Expected centring: minutes-weighted means over the rated players (players[0] has two team rows)."""
        o, d = self.ratings
        m = {p: 1500.0 for p in o} | {self.players[0].player_id: 3000.0}
        w = sum(m.values())
        return sum(m[p] * v for p, v in o.items()) / w, sum(m[p] * v for p, v in d.items()) / w

    def test_write(self):
        self._call("--write")
        o, d = self.ratings
        c_o, c_d = self._means()
        for p in self.players:
            for row in NBAPlayerSeasonStats.objects.filter(player=p, season=self.seasons[2010], season_type="regular"):
                self.assertEqual((row.obpr_raw, row.dbpr_raw), (o[p.player_id], d[p.player_id]))
                self.assertAlmostEqual(row.obpr, o[p.player_id] - c_o, places=12)
                self.assertAlmostEqual(row.dbpr, d[p.player_id] - c_d, places=12)
                self.assertEqual(row.bpr, row.obpr + row.dbpr)
                self.assertAlmostEqual(row.wins_added, (row.bpr + 1.918) * 60 * 25.0 / 48.0 / WA_DIVISOR, places=12)
                self.assertEqual(row.bpr_model, "native-1")
                self.assertIsNotNone(row.bpr_last_updated)
        for row in self.traded:                                # both team rows, each its own minutes
            row.refresh_from_db()
            self.assertEqual(row.bpr_model, "native-1")
            self.assertAlmostEqual(row.wins_added, (row.bpr + 1.918) * 1500.0 / 48.0 / WA_DIVISOR, places=12)
        self.unrated.refresh_from_db()                         # everything cleared, wins_added too
        self.assertEqual((self.unrated.obpr, self.unrated.dbpr, self.unrated.obpr_raw, self.unrated.dbpr_raw,
                          self.unrated.bpr, self.unrated.bpr_model, self.unrated.bpr_last_updated,
                          self.unrated.wins_added),
                         (None, None, None, None, None, None, None, None))
        self.playoff.refresh_from_db()
        self.assertEqual((self.playoff.obpr, self.playoff.bpr, self.playoff.bpr_model), (0.5, 1.0, None))

    def test_written_ratings_average_zero(self):
        self._call("--write")
        rows = NBAPlayerSeasonStats.objects.filter(season=self.seasons[2010], season_type="regular",
                                                   obpr__isnull=False)
        m = sum(r.mpg * r.gp for r in rows)
        self.assertAlmostEqual(sum(r.obpr * r.mpg * r.gp for r in rows) / m, 0.0, places=12)
        self.assertAlmostEqual(sum(r.dbpr * r.mpg * r.gp for r in rows) / m, 0.0, places=12)

    def test_refuses_native_previous_season_without_raw(self):
        self._rate(2009, "native-1", raw=False)
        with self.assertRaisesRegex(CommandError, "without obpr_raw"):
            self._call("--dry-run")
        self.assertEqual(self.native_calls, [])

    def test_write_leaves_other_seasons_alone(self):
        self._rate(2009, "native-1")
        self._call("--write")
        self.assertEqual(NBAPlayerSeasonStats.objects.filter(
            season=self.seasons[2009], bpr_model="native-1", bpr=0.0).count(), 5)

    def test_needs_a_mode(self):
        with self.assertRaises(CommandError):
            call_command("nba_compute_native_bpr", "--season", "2010", stdout=StringIO())

    def test_lambda_minutes_are_full_season_for_every_player(self):
        self._call("--dry-run")
        c, = self.native_calls
        self.assertEqual(c["minutes"][self.players[0].player_id], 2 * 60 * 25.0)   # both team rows
        self.assertEqual(c["minutes"][self.players[5].player_id], 60 * 25.0)       # no box row
        self.assertEqual(c["minutes"][999], 60 * 25.0)
        self.assertEqual(len(c["minutes"]), 26)

    def test_aging_possessions_cached_across_runs(self):
        self._rate(2008, "native-1")
        self._rate(2009, "native-1")
        self._call("--dry-run")
        self.assertEqual(sorted(self.poss_loads), [2008, 2009])
        self.assertEqual(sorted(p.name for p in self.cache_dir.iterdir()), ["2008.json", "2009.json"])
        self.poss_loads.clear()
        self._call("--dry-run")
        self.assertEqual(self.poss_loads, [])                                     # all from the cache
        self.assertEqual(self.native_calls[1]["poss_hist"], {2008: {1: 2008.0}, 2009: {1: 2009.0}})

    def test_cache_reloads_a_season_whose_stints_changed(self):
        self._rate(2008, "native-1")
        self._rate(2009, "native-1")
        self._call("--dry-run")
        self.poss_loads.clear()
        fp = {2008: {"n": 0, "secs": None, "max_id": None, "content": "0"},   # unchanged (no stints)
              2009: {"n": 5, "secs": 100, "max_id": 7, "content": "123"}}
        with mock.patch(f"{MOD}.stint_fingerprint", lambda s: fp[s]):
            self._call("--dry-run")
        self.assertEqual(self.poss_loads, [2009])

    def test_stored_ratings_in_id_order(self):
        s9 = self.seasons[2009]
        for p in reversed(self.players[:6]):
            _row(p, s9, obpr=0.01 * p.player_id, dbpr=0.0, bpr=0.0, bpr_model="native-1",
                 obpr_raw=0.01 * p.player_id, dbpr_raw=0.0)
        o, d, models = nb.stored_ratings(2009)
        self.assertEqual(list(o), sorted(o))
        self.assertEqual(list(d), sorted(d))
        self.assertEqual(models, {"native-1": 6})


class EarlySeasonTests(TestCase):
    """Task 5.8: a season in progress with no player yet meeting the box rule still rates."""

    @classmethod
    def setUpTestData(cls):
        cls.season = NBASeason.objects.create(year=2027, display_name="2026-27")
        cls.player = NBAPlayer.objects.create(player_id=101, name="Early")
        _row(cls.player, cls.season)                                   # no box values yet

    def test_load_box_is_empty_without_box_rows(self):
        self.assertEqual(nb.load_box(None, 2027), ({}, {}))

    def test_load_box_reads_box_rows(self):
        NBAPlayerSeasonStats.objects.filter(season=self.season).update(box_obpr=1.5, box_dbpr=-0.5)
        from nba.management.commands.nba_compute_final_bpr import Command as FinalBprCommand
        loader = FinalBprCommand()
        loader.stdout = loader.stderr = StringIO()
        self.assertEqual(nb.load_box(loader, 2027), ({101: 1.5}, {101: -0.5}))
