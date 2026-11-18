"""
Management command: nba_compute_native_bpr

Production native BPR for one season (Phase 5, task 5.3): the final recipe of
nba_experiment_final_bpr's native chain (w_box 0.5, rho 1.0, lambda tiers x8,
age-mult 1), run on stored values instead of an in-memory chain.

Per season Y, offense and defense separately:
  prev   = Y-1's stored obpr_raw / dbpr_raw (native only) + aging curve(age at
           Y), the curve fitted (nba.analytics.aging) on the stored raw native
           ratings of the seasons before Y, weighted by each season's on-court
           possessions
  prior  = native_prior(stored box_obpr / box_dbpr for Y, prev, 0.5, 1.0)
  fit    = Y's stints only (RAPM window 1), within-season half-life 90 days,
           lambda = minutes tiers (A_conservative) x 8, from every player's
           full-season regular minutes (sum of mpg x gp over his team rows),
           box row or not

Centring (task 5.6): the fit is stored as obpr_raw / dbpr_raw, and obpr / dbpr =
raw minus Y's minutes-weighted league mean (full-season minutes, every rated
player), so each averages 0 and bpr 0 is a league-average player. Constant
shifts do not change lineup predictions, so the centred ratings predict exactly
as the raw ones. The chain itself runs on the raw values.

The season's centring and Wins Added constants are also written to
NBASeasonRatingScale (task 5.10b), which consumers read through nba.rating_scale.

Wins Added (task 5.5c fit 2): on every rated regular row,
  wins_added = (bpr - WA_REPLACEMENT) x row minutes / 48 / WA_DIVISOR,
replacement level -1.918, divisor 37.73; rows without a rating get null.

Stored ratings are read in NBA.com id order, the order the fit returns them, so
the aging fit sees its pairs in one fixed order and a rerun is bit-identical to
the in-memory chain.

Possessions for the aging weights come from a per-season cache
(POSS_CACHE_DIR/<season>.json), keyed by a fingerprint of that season's stint
rows (count, total seconds, largest id): a season is loaded from stints only the
first time, or after its stints change.

The fit is the harness's own code (nba_experiment_final_bpr: _aging_curve,
_fit_chain_season; nba_compute_final_bpr: _load_priors, _load_stints), so a
season computed here equals that season of the harness's native chain given
the same box values and previous ratings.

Refuses when Y-1 holds ratings written by another model (bpr_model other than
'native-1'): the chain must run in order. With no Y-1 ratings (the chain's
first season, 2006) the prior is box only.

--write: one transaction. Clears obpr, dbpr, obpr_raw, dbpr_raw, bpr,
bpr_last_updated, bpr_model and wins_added on Y's regular rows, then writes this
fit to every row of each rated player (every team row of a traded player):
obpr_raw / dbpr_raw (unrounded: the next season reads them back as its previous
ratings), the centred obpr / dbpr, bpr = obpr + dbpr, wins_added, and bpr_model
'native-1'.

--dry-run: prints the top 20 and writes nothing.

Usage:
  python manage.py nba_compute_native_bpr --season 2006 --dry-run
  python manage.py nba_compute_native_bpr --season 2006 --write
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from nba.analytics import aging
from nba.analytics.native_prior import native_prior
from nba.analytics.rapm import build_nba_observations
from nba.management.commands.nba_compute_final_bpr import Command as FinalBprCommand
from nba.management.commands.nba_experiment_final_bpr import Command as Harness
from nba.rating_scale import WA_DIVISOR, WA_REPLACEMENT

NATIVE_MODEL = "native-1"
W_BOX = 0.5
RHO = 1.0
LAMBDA_MULT = 8.0
AGE_MULT = 1.0
TIER = "A_conservative"
HALF_LIFE = 90.0
RAPM_WINDOW = 1
TOP_N = 20
# Wins Added constants (task 5.5c fit 2 on centred ratings) live in nba.rating_scale.
# Per-season on-court possession totals for the aging weights (gitignored, as data/nba/pbp_cache/).
POSS_CACHE_DIR = Path(__file__).resolve().parents[4] / "data" / "nba" / "native_poss_cache"


# ── stored inputs ─────────────────────────────────────────────────────────────

def stored_ratings(season: int) -> tuple[dict[int, float], dict[int, float], Counter]:
    """
    Y's stored regular-season ratings as the chain sees them, keyed by NBA.com id (one value
    per player: every team row of a traded player carries the same rating), in id order, and
    a count of rated rows per bpr_model. Native rows give obpr_raw / dbpr_raw (the fit before
    centring); rows of other models give obpr / dbpr (the command refuses those seasons).
    A native row without raw values was written before centring: rerun that season first.
    """
    from nba.models import NBAPlayerSeasonStats

    o: dict[int, float] = {}
    d: dict[int, float] = {}
    models: Counter = Counter()
    for nba_id, obpr, dbpr, obpr_raw, dbpr_raw, model in NBAPlayerSeasonStats.objects.filter(
            season__year=season, season_type="regular", obpr__isnull=False,
    ).order_by("player__player_id", "id").values_list(
            "player__player_id", "obpr", "dbpr", "obpr_raw", "dbpr_raw", "bpr_model"):
        models[model] += 1
        if model == NATIVE_MODEL:
            if obpr_raw is None:
                raise CommandError(f"{season} holds native ratings without obpr_raw (written before centring); "
                                   f"run nba_compute_native_bpr --season {season} --write first")
            obpr, dbpr = obpr_raw, dbpr_raw
        o[nba_id] = obpr
        d[nba_id] = dbpr if dbpr is not None else 0.0
    return o, d, models


def league_means(o: dict[int, float], d: dict[int, float], minutes: dict[int, float]) -> tuple[float, float]:
    """Minutes-weighted league means of obpr and dbpr over every rated player (full-season minutes)."""
    w = sum(minutes.get(p, 0.0) for p in o)
    if w <= 0:
        raise CommandError("no minutes for the rated players: cannot centre")
    c_o = sum(minutes.get(p, 0.0) * v for p, v in o.items()) / w
    c_d = sum(minutes.get(p, 0.0) * v for p, v in d.items()) / w
    return c_o, c_d


def native_seasons_before(season: int) -> list[int]:
    """Seasons before Y with any regular row written by the native model."""
    from nba.models import NBAPlayerSeasonStats

    return sorted(set(NBAPlayerSeasonStats.objects.filter(
        season__year__lt=season, season_type="regular", bpr_model=NATIVE_MODEL,
    ).values_list("season__year", flat=True)))


def full_season_minutes(season: int) -> dict[int, float]:
    """Every player's regular-season minutes, summed over his team rows (mpg x gp), box row or not."""
    from nba.models import NBAPlayerSeasonStats

    minutes: dict[int, float] = defaultdict(float)
    for nba_id, mpg, gp in NBAPlayerSeasonStats.objects.filter(
            season__year=season, season_type="regular").values_list("player__player_id", "mpg", "gp"):
        minutes[nba_id] += (mpg or 0.0) * (gp or 0)
    return dict(minutes)


def stint_fingerprint(season: int) -> dict:
    """Count, total seconds and largest id of the season's stint rows: changes whenever they are re-synced."""
    from django.db.models import Count, Max, Sum
    from nba.models import NBAPlayerGameStint

    agg = NBAPlayerGameStint.objects.filter(game__season__year=season).aggregate(
        n=Count("id"), secs=Sum("secs_on"), max_id=Max("id"))
    return {"n": agg["n"], "secs": agg["secs"], "max_id": agg["max_id"]}


def cached_season_possessions(season: int, cache_dir: Path | None = None) -> tuple[dict[int, float], bool]:
    """
    season_possessions(season), from the cache when its fingerprint matches the stints; else
    computed and stored. Returns (possessions, came from cache).
    """
    path = Path(cache_dir or POSS_CACHE_DIR) / f"{season}.json"
    fp = stint_fingerprint(season)
    if path.exists():
        cached = json.loads(path.read_text())
        if cached.get("fingerprint") == fp:
            return {int(k): v for k, v in cached["poss"].items()}, True
    poss = season_possessions(season)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"season": season, "fingerprint": fp, "poss": poss}))
    tmp.replace(path)
    return poss, False


def season_possessions(season: int) -> dict[int, float]:
    """
    On-court possessions per player in one season, from the same observations the fit uses
    ((home_poss + away_poss) / 2 per stint), as the harness weights its aging pairs.
    """
    poss: dict[int, float] = {}
    for obs in build_nba_observations(season_year=season, rapm_years=[season]):
        if obs["season_year"] != season:
            continue
        p = (obs["home_poss"] + obs["away_poss"]) / 2.0
        for pid in obs["home_player_ids"] + obs["away_player_ids"]:
            poss[pid] = poss.get(pid, 0.0) + p
    return poss


# ── one season (pure apart from the stint load inside the fit) ────────────────

def native_season(loader, season: int, box_o: dict, box_d: dict, minutes: dict,
                  prev_o: dict, prev_d: dict, hist_o: dict, hist_d: dict,
                  poss_hist: dict, dobs: dict) -> tuple[dict, dict, dict]:
    """
    One native-chain season, exactly as nba_experiment_final_bpr's native chain at the recipe
    (w_box 0.5, rho 1.0, x8, age-mult 1). hist_* / poss_hist: {season: {nba_id: value}} for
    seasons before Y only. Returns ({nba_id: obpr}, {nba_id: dbpr}, info).
    """
    curve = Harness._aging_curve(season, hist_o, hist_d, poss_hist, dobs)
    mem_o = {p: v + AGE_MULT * aging.curve_value(curve["o"], aging.age_at(dobs.get(p), season))
             for p, v in prev_o.items()}
    mem_d = {p: v + AGE_MULT * aging.curve_value(curve["d"], aging.age_at(dobs.get(p), season))
             for p, v in prev_d.items()}
    prior_o = native_prior(box_o, mem_o, W_BOX, RHO)
    prior_d = native_prior(box_d, mem_d, W_BOX, RHO)
    o, d = Harness._fit_chain_season(loader, season, prior_o, prior_d, minutes, TIER, HALF_LIFE,
                                     RAPM_WINDOW, lambda_mult=LAMBDA_MULT)
    info = {"curve": curve, "n_prior": len(prior_o),
            "n_box_prev": len(box_o.keys() & prev_o.keys()),
            "n_box_only": len(box_o.keys() - prev_o.keys()),
            "n_prev_only": len(prev_o.keys() - box_o.keys()),
            "n_rated": len(o)}
    return o, d, info


def write_native(season: int, o: dict[int, float], d: dict[int, float], c_o: float, c_d: float) -> dict:
    """
    One transaction: clear obpr, dbpr, obpr_raw, dbpr_raw, bpr, bpr_last_updated, bpr_model and
    wins_added on Y's regular rows, then write to every row of each rated player (keyed by NBA.com
    id): the raw fit, obpr / dbpr = raw - (c_o, c_d), bpr = obpr + dbpr, and wins_added from the
    row's own minutes; and Y's NBASeasonRatingScale row (c_o, c_d, D, R) for the consumers.
    """
    from django.db import transaction
    from django.utils import timezone
    from nba.models import NBAPlayerSeasonStats, NBASeason, NBASeasonRatingScale

    qs = NBAPlayerSeasonStats.objects.filter(season__year=season, season_type="regular")
    now = timezone.now()
    updated = skipped = 0
    with transaction.atomic():
        cleared = qs.update(obpr=None, dbpr=None, obpr_raw=None, dbpr_raw=None, bpr=None,
                            bpr_last_updated=None, bpr_model=None, wins_added=None)
        for row in qs.select_related("player"):
            nba_id = row.player.player_id
            if nba_id not in o:
                skipped += 1
                continue
            row.obpr_raw = o[nba_id]
            row.dbpr_raw = d.get(nba_id, 0.0)
            row.obpr = row.obpr_raw - c_o
            row.dbpr = row.dbpr_raw - c_d
            row.bpr = row.obpr + row.dbpr
            row.wins_added = (row.bpr - WA_REPLACEMENT) * (row.mpg or 0.0) * (row.gp or 0) / 48.0 / WA_DIVISOR
            row.bpr_last_updated = now
            row.bpr_model = NATIVE_MODEL
            row.save(update_fields=["obpr", "dbpr", "obpr_raw", "dbpr_raw", "bpr", "wins_added",
                                    "bpr_last_updated", "bpr_model"])
            updated += 1
        NBASeasonRatingScale.objects.update_or_create(
            season=NBASeason.objects.get(year=season),
            defaults={"bpr_model": NATIVE_MODEL, "centre_obpr": c_o, "centre_dbpr": c_d,
                      "wins_divisor": WA_DIVISOR, "replacement": WA_REPLACEMENT})
    return {"cleared": cleared, "updated": updated, "skipped": skipped}


class Command(BaseCommand):
    help = "Production native BPR for one season (final recipe); --dry-run or --write."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--dry-run", action="store_true", help="Fit and print the top 20; write nothing")
        mode.add_argument("--write", action="store_true",
                          help="Clear and write the raw and centred ratings, bpr, wins_added, bpr_last_updated "
                               "and bpr_model on Y's regular rows")

    def handle(self, *args, **opts):
        season = opts["season"]
        self.stdout.write(f"[NATIVE BPR] {season}  w_box={W_BOX} rho={RHO} tiers={TIER} x{LAMBDA_MULT:g} "
                          f"age-mult={AGE_MULT:g}  ({'write' if opts['write'] else 'dry run'})")

        prev_o, prev_d, prev_models = stored_ratings(season - 1)
        other = {(m or "null (LEBRON-prior)"): n for m, n in prev_models.items() if m != NATIVE_MODEL}
        if other:
            found = ", ".join(f"{m}: {n} rows" for m, n in sorted(other.items()))
            raise CommandError(f"{season - 1} holds ratings from another model ({found}); "
                               f"run nba_compute_native_bpr for {season - 1} first")
        if prev_o:
            self.stdout.write(f"  previous: {len(prev_o)} native ratings from {season - 1}")
        else:
            self.stdout.write(f"  previous: none in {season - 1}; prior is box only")

        hist_o: dict[int, dict] = {}
        hist_d: dict[int, dict] = {}
        poss_hist: dict[int, dict] = {}
        dobs: dict = {}
        if prev_o:
            n_cached = 0
            for s in native_seasons_before(season):
                hist_o[s], hist_d[s], _ = stored_ratings(s)
                poss_hist[s], hit = cached_season_possessions(s)
                n_cached += hit
            dobs = Harness._load_birth_dates()
            self.stdout.write(f"  aging history: native seasons {min(hist_o)}-{max(hist_o)} ({len(hist_o)}); "
                              f"possessions: {n_cached} cached, {len(hist_o) - n_cached} loaded from stints")

        loader = FinalBprCommand()
        loader.stdout, loader.stderr = self.stdout, self.stderr
        box_o, box_d, _box_minutes = loader._load_priors(season)
        minutes = full_season_minutes(season)
        o, d, info = native_season(loader, season, box_o, box_d, minutes, prev_o, prev_d,
                                   hist_o, hist_d, poss_hist, dobs)
        c = info["curve"]
        self.stdout.write(f"  aging curve from {c['n_pairs']} pairs: O {c['o']}  D {c['d']}")
        self.stdout.write(f"  prior: {info['n_prior']} players ({info['n_box_prev']} box+prev, "
                          f"{info['n_box_only']} box only, {info['n_prev_only']} prev only)")
        self.stdout.write(f"  rated: {info['n_rated']} players")
        c_o, c_d = league_means(o, d, minutes)
        self.stdout.write(f"  centring: minutes-weighted league means obpr {c_o:+.4f}, dbpr {c_d:+.4f}")

        names = loader._load_name_map(list(o))
        self.stdout.write(f"\nTop {TOP_N} by bpr (centred), {season}:")
        ranked = sorted(o, key=lambda p: o[p] + d.get(p, 0.0), reverse=True)
        for rank, p in enumerate(ranked[:TOP_N], start=1):
            co, cd = o[p] - c_o, d.get(p, 0.0) - c_d
            wa = (co + cd - WA_REPLACEMENT) * minutes.get(p, 0.0) / 48.0 / WA_DIVISOR
            self.stdout.write(f"  {rank:2d}. {names.get(p, str(p)):28s} nba_id={p:<8d} obpr={co:+.3f}  "
                              f"dbpr={cd:+.3f}  bpr={co + cd:+.3f}  wins_added={wa:5.1f}")
        if opts["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"Dry run: {len(o)} players, no DB writes."))
            return
        res = write_native(season, o, d, c_o, c_d)
        self.stdout.write(self.style.SUCCESS(
            f"[OK] {season} native BPR written: cleared {res['cleared']} regular rows, {res['updated']} updated, "
            f"{res['skipped']} rows without a rating left null"))
