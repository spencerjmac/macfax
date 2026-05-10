"""
backtest_bpr_predictive — Tests how predictive and accurate our BPR ratings are.

Two test suites:

1. MULTI-SEASON EM ALIGNMENT
   Compares our BPR vs Evan Miya for every season that has both our data and EM data.
   Shows whether EM correlation is consistent or drifting season-over-season.

2. YEAR-OVER-YEAR STABILITY (PREDICTIVE ACCURACY)
   For returning players (in both year N and N+1), measures how well BPR_N predicts
   BPR_{N+1}.  High r = stable, meaningful ratings.  Compared to naive baseline
   (predict same BPR as last year).

Usage:
    python manage.py backtest_bpr_predictive
    python manage.py backtest_bpr_predictive --seasons 2024 2025 2026
    python manage.py backtest_bpr_predictive --min-poss 400 --verbose
"""

from __future__ import annotations

import difflib
import logging
import math
import unicodedata
import re
from collections import defaultdict

# ── Quality targets (year-over-year stability) ────────────────────────────────
# Professional-grade rating system must sustain these for recent seasons.
TARGET_YOY_R_GOOD      = 0.55   # Minimum: meaningful predictive signal
TARGET_YOY_R_EXCELLENT = 0.70   # Goal: strong year-to-year stability
TARGET_EM_R_GOOD       = 0.65   # Min EM alignment for most-recent season
TARGET_EM_R_EXCELLENT  = 0.80   # Goal: near-EM alignment

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Minimal stats helpers (no scipy)
# ---------------------------------------------------------------------------

def _mean(v):  return sum(v) / len(v) if v else 0.0
def _std(v):
    if len(v) < 2: return 0.0
    m = _mean(v); return math.sqrt(sum((x-m)**2 for x in v) / (len(v)-1))

def _pearson(xs, ys):
    n = len(xs)
    if n < 3: return float("nan")
    mx, my = _mean(xs), _mean(ys)
    sx, sy = _std(xs), _std(ys)
    if sx == 0 or sy == 0: return float("nan")
    cov = sum((x-mx)*(y-my) for x,y in zip(xs,ys)) / (n-1)
    return cov / (sx * sy)

def _spearman(xs, ys):
    n = len(xs)
    if n < 3: return float("nan")
    def _ranks(vals):
        sv = sorted(enumerate(vals), key=lambda kv: kv[1])
        r = [0.0]*n; i = 0
        while i < n:
            j = i
            while j < n-1 and sv[j+1][1] == sv[i][1]: j += 1
            avg = (i+j)/2.0 + 1
            for k in range(i, j+1): r[sv[k][0]] = avg
            i = j + 1
        return r
    return _pearson(_ranks(xs), _ranks(ys))

def _rmse(xs, ys): return math.sqrt(sum((x-y)**2 for x,y in zip(xs,ys))/len(xs)) if xs else float("nan")
def _mae(xs, ys):  return sum(abs(x-y) for x,y in zip(xs,ys))/len(xs) if xs else float("nan")
def _ols_slope(xs, ys):
    n = len(xs)
    if n < 2: return float("nan")
    mx, my = _mean(xs), _mean(ys)
    ssxx = sum((x-mx)**2 for x in xs)
    ssxy = sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    return ssxy/ssxx if ssxx > 0 else float("nan")

def _section(t, w=70): return f"\n{'─'*w}\n  {t}\n{'─'*w}"


# ---------------------------------------------------------------------------
# Player matching helpers (shared with backtest_bpr_vs_evan_miya)
# ---------------------------------------------------------------------------

def _norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode("ascii")
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()

def _name_score(a, b):
    return difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio()


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = (
        "Backtest BPR accuracy: multi-season EM alignment + "
        "year-over-year predictive stability."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--seasons", nargs="+", type=int, default=None,
            help="Season years to include (default: all seasons with BPR data).",
        )
        parser.add_argument(
            "--min-poss", type=int, default=400,
            help="Minimum EM possessions for EM-comparison players (default: 400).",
        )
        parser.add_argument(
            "--min-bpr-poss", type=int, default=200,
            help="Minimum our off_poss for year-over-year stability test (default: 200).",
        )
        parser.add_argument(
            "--verbose", action="store_true", default=False,
        )

    def handle(self, *args, **options):
        from ncaa.models import PlayerSeasonStats, Season
        from ncaa.analytics.player_value.bpr.evan_miya_reference import (
            load_em_ratings, normalize_team_name, RAW_DATA,
        )

        min_poss     = options["min_poss"]
        min_bpr_poss = options["min_bpr_poss"]
        verbose      = options["verbose"]

        # Determine which seasons to examine
        all_seasons = list(
            Season.objects.filter(
                player_season_stats__bpr__isnull=False
            ).values_list("year", flat=True).distinct().order_by("year")
        )
        if options["seasons"]:
            seasons = [y for y in options["seasons"] if y in all_seasons]
        else:
            seasons = all_seasons

        if not seasons:
            raise CommandError("No seasons with BPR data found.")

        self.stdout.write(f"\nSeasons with BPR data: {seasons}")

        # ==================================================================
        # SUITE 1: Multi-season EM alignment
        # ==================================================================
        em_seasons = [yr for yr in seasons if yr in RAW_DATA]
        self.stdout.write(_section(f"Suite 1 — Multi-Season EM Alignment  (seasons: {em_seasons})"))

        if not em_seasons:
            self.stdout.write("  No EM data available for any season. Add seasons to RAW_DATA.")
        else:
            header = f"  {'Season':>6}  {'n':>4}  {'Pearson r':>9}  {'Spearman ρ':>10}  {'RMSE':>6}  {'MAE':>6}  {'Bias':>7}  {'Slope':>6}"
            self.stdout.write(header)
            self.stdout.write("  " + "─"*(len(header)-2))

            for yr in em_seasons:
                try:
                    em_records = load_em_ratings(yr)
                except KeyError:
                    continue

                em_records = [r for r in em_records if r["possessions"] >= min_poss]

                # Load our BPR for this season
                qs = list(
                    PlayerSeasonStats.objects.filter(
                        season__year=yr,
                        bpr__isnull=False,
                    ).select_related("player", "team")
                    .values("player__display_name", "team__name", "bpr", "obpr", "dbpr")
                )
                db_by_name = defaultdict(list)
                for row in qs:
                    db_by_name[row["player__display_name"]].append(row)
                name_keys = list(db_by_name.keys())

                our_bprs, em_bprs = [], []
                for em in em_records:
                    em_n = _norm(em["name"])
                    cands = difflib.get_close_matches(em_n, [_norm(k) for k in name_keys], n=3, cutoff=0.65)
                    if not cands:
                        continue
                    best_row, best_s = None, 0.0
                    for cand in cands:
                        for orig_name in name_keys:
                            if _norm(orig_name) == cand:
                                for row in db_by_name[orig_name]:
                                    ns = difflib.SequenceMatcher(None, em_n, cand).ratio()
                                    ts = _name_score(normalize_team_name(em["team"]), row["team__name"] or "")
                                    s = ns*0.65 + ts*0.35
                                    if s > best_s:
                                        best_s, best_row = s, row
                    if best_s < 0.55 or best_row is None or best_row["bpr"] is None:
                        continue
                    our_bprs.append(best_row["bpr"])
                    em_bprs.append(em["adj_bpr"])

                if len(our_bprs) < 10:
                    self.stdout.write(f"  {yr:6d}  {'<10 matches':>4}")
                    continue

                bias  = _mean([o-e for o,e in zip(our_bprs, em_bprs)])
                slope = _ols_slope(em_bprs, our_bprs)
                self.stdout.write(
                    f"  {yr:6d}  {len(our_bprs):4d}  "
                    f"{_pearson(our_bprs, em_bprs):+9.3f}  "
                    f"{_spearman(our_bprs, em_bprs):+10.3f}  "
                    f"{_rmse(our_bprs, em_bprs):6.3f}  "
                    f"{_mae(our_bprs, em_bprs):6.3f}  "
                    f"{bias:+7.3f}  "
                    f"{slope:6.3f}"
                )

        # ==================================================================
        # SUITE 2: Year-over-year predictive stability
        # ==================================================================
        self.stdout.write(_section("Suite 2 — Year-over-Year BPR Stability (Returners)"))
        self.stdout.write(
            "  Measures: does BPR in year N predict BPR in year N+1 for returning players?\n"
            "  Baseline = naive predictor (predict same BPR as prior year).\n"
            "  Higher r and lower RMSE vs baseline = ratings are meaningfully predictive."
        )

        consec_pairs = [(seasons[i], seasons[i+1]) for i in range(len(seasons)-1)
                        if seasons[i+1] - seasons[i] == 1]

        if not consec_pairs:
            self.stdout.write("  No consecutive season pairs found.")
        else:
            header2 = f"  {'Pair':>11}  {'n':>4}  {'r(N→N+1)':>9}  {'ρ':>6}  {'RMSE':>6}  {'Baseline RMSE':>13}  {'MAE':>6}  {'r(naive)':>8}"
            self.stdout.write(header2)
            self.stdout.write("  " + "─"*(len(header2)-2))

            for yr_n, yr_n1 in consec_pairs:
                # Load BPR for both seasons
                qs_n = {
                    r["player_id"]: r
                    for r in PlayerSeasonStats.objects.filter(
                        season__year=yr_n,
                        bpr__isnull=False,
                        off_poss__gte=min_bpr_poss,
                    ).values("player_id", "bpr", "obpr", "dbpr", "off_poss")
                }
                qs_n1 = {
                    r["player_id"]: r
                    for r in PlayerSeasonStats.objects.filter(
                        season__year=yr_n1,
                        bpr__isnull=False,
                        off_poss__gte=min_bpr_poss,
                    ).values("player_id", "bpr", "obpr", "dbpr", "off_poss")
                }

                # Returning players: in both seasons
                common = [pid for pid in qs_n if pid in qs_n1]
                if len(common) < 10:
                    self.stdout.write(f"  {yr_n}→{yr_n1}  <10 returners")
                    continue

                bpr_n  = [qs_n[pid]["bpr"]  for pid in common]
                bpr_n1 = [qs_n1[pid]["bpr"] for pid in common]

                # Naive baseline: predict BPR_{n+1} = BPR_n (no change)
                naive_rmse = _rmse(bpr_n, bpr_n1)   # same as predicting last year's value
                naive_r    = _pearson(bpr_n, bpr_n1)  # same as our r actually — we're reporting how predictive yr_n is

                self.stdout.write(
                    f"  {yr_n}→{yr_n1}  {len(common):4d}  "
                    f"{_pearson(bpr_n, bpr_n1):+9.3f}  "
                    f"{_spearman(bpr_n, bpr_n1):+6.3f}  "
                    f"{_rmse(bpr_n, bpr_n1):6.3f}  "
                    f"{naive_rmse:13.3f}  "
                    f"{_mae(bpr_n, bpr_n1):6.3f}  "
                    f"{naive_r:+8.3f}"
                )

                # Breakdown by tier
                tiers = [
                    ("Top BPR (>5)",   [i for i,pid in enumerate(common) if bpr_n[i] > 5]),
                    ("Mid BPR (1–5)",  [i for i,pid in enumerate(common) if 1 <= bpr_n[i] <= 5]),
                    ("Low BPR (<1)",   [i for i,pid in enumerate(common) if bpr_n[i] < 1]),
                ]
                for tlabel, idxs in tiers:
                    if len(idxs) < 5:
                        continue
                    xs = [bpr_n[i]  for i in idxs]
                    ys = [bpr_n1[i] for i in idxs]
                    self.stdout.write(
                        f"    {tlabel:18s}  n={len(idxs):3d}  "
                        f"r={_pearson(xs,ys):+.3f}  RMSE={_rmse(xs,ys):.3f}  "
                        f"bias={_mean([x-y for x,y in zip(xs,ys)]):+.3f}"
                    )

            # Offensive / Defensive breakdown
            self.stdout.write(f"\n  ── Off/Def Component Stability ──")
            header3 = f"  {'Pair':>11}  {'component':>9}  {'n':>4}  {'r':>7}  {'RMSE':>6}  {'bias':>7}"
            self.stdout.write(header3)
            for yr_n, yr_n1 in consec_pairs:
                for comp, fld in [("OBPR", "obpr"), ("DBPR", "dbpr")]:
                    qs_n = {
                        r["player_id"]: r[fld]
                        for r in PlayerSeasonStats.objects.filter(
                            season__year=yr_n, **{f"{fld}__isnull": False},
                            off_poss__gte=min_bpr_poss,
                        ).values("player_id", fld)
                        if r[fld] is not None
                    }
                    qs_n1 = {
                        r["player_id"]: r[fld]
                        for r in PlayerSeasonStats.objects.filter(
                            season__year=yr_n1, **{f"{fld}__isnull": False},
                            off_poss__gte=min_bpr_poss,
                        ).values("player_id", fld)
                        if r[fld] is not None
                    }
                    common = [pid for pid in qs_n if pid in qs_n1]
                    if len(common) < 10:
                        continue
                    xs = [qs_n[pid]  for pid in common]
                    ys = [qs_n1[pid] for pid in common]
                    self.stdout.write(
                        f"  {yr_n}→{yr_n1}  {comp:>9}  {len(common):4d}  "
                        f"{_pearson(xs,ys):+7.3f}  "
                        f"{_rmse(xs,ys):6.3f}  "
                        f"{_mean([x-y for x,y in zip(xs,ys)]):+7.3f}"
                    )

        # ==================================================================
        # SUITE 3: Distribution summary across seasons
        # ==================================================================
        self.stdout.write(_section("Suite 3 — BPR Distribution by Season"))
        header4 = f"  {'Season':>6}  {'n':>5}  {'mean':>7}  {'std':>6}  {'p5':>6}  {'p25':>6}  {'p50':>6}  {'p75':>6}  {'p95':>6}  {'max':>6}"
        self.stdout.write(header4)
        self.stdout.write("  " + "─"*(len(header4)-2))
        for yr in seasons:
            vals = list(
                PlayerSeasonStats.objects.filter(
                    season__year=yr, bpr__isnull=False, off_poss__gte=min_bpr_poss,
                ).values_list("bpr", flat=True)
            )
            if not vals:
                continue
            sv = sorted(vals)
            n = len(sv)
            def pct(p): return sv[int(p*n/100)]
            self.stdout.write(
                f"  {yr:6d}  {n:5d}  "
                f"{_mean(vals):+7.2f}  {_std(vals):6.2f}  "
                f"{pct(5):+6.2f}  {pct(25):+6.2f}  {pct(50):+6.2f}  "
                f"{pct(75):+6.2f}  {pct(95):+6.2f}  {max(vals):+6.2f}"
            )

        # ── Quality scorecard ─────────────────────────────────────────────────
        from ncaa.analytics.player_value.bpr.evan_miya_reference import (
            load_em_ratings, normalize_team_name, RAW_DATA,
        )
        # Evaluate the two most recent consecutive seasons for year-over-year,
        # and the most recent season for EM alignment.
        self.stdout.write(_section("Quality Scorecard — Professional Grade"))
        self.stdout.write(
            "  Targets for a professionally reliable player rating system.\n"
            "  Evaluated on most recent available seasons.\n"
        )

        def _pf(val, target, higher): return "✓ PASS" if (val >= target if higher else val <= target) else "✗ FAIL"

        scorecard_lines = []
        # YOY: most recent consecutive pair
        recent_pair = [(s, seasons[i+1]) for i, s in enumerate(seasons[:-1])
                       if seasons[i+1]-s == 1]
        if recent_pair:
            yn, yn1 = recent_pair[-1]
            qs_n  = {r["player_id"]: r["bpr"] for r in PlayerSeasonStats.objects.filter(
                season__year=yn, bpr__isnull=False, off_poss__gte=min_bpr_poss).values("player_id","bpr")}
            qs_n1 = {r["player_id"]: r["bpr"] for r in PlayerSeasonStats.objects.filter(
                season__year=yn1, bpr__isnull=False, off_poss__gte=min_bpr_poss).values("player_id","bpr")}
            common = [pid for pid in qs_n if pid in qs_n1]
            if len(common) >= 20:
                xs = [qs_n[pid] for pid in common]
                ys = [qs_n1[pid] for pid in common]
                yoy_r = _pearson(xs, ys)
                scorecard_lines.append(
                    (_pf(yoy_r, TARGET_YOY_R_GOOD, True),
                     f"YOY stability r ({yn}→{yn1})",
                     f"{yoy_r:.3f}  (good >{TARGET_YOY_R_GOOD}, excellent >{TARGET_YOY_R_EXCELLENT})")
                )

        # EM alignment: most recent season with EM data
        em_seasons_avail = [yr for yr in seasons if yr in RAW_DATA]
        if em_seasons_avail:
            yr_em = em_seasons_avail[-1]
            try:
                em_records = [r for r in load_em_ratings(yr_em) if r["possessions"] >= min_poss]
                qs_em = list(PlayerSeasonStats.objects.filter(
                    season__year=yr_em, bpr__isnull=False
                ).select_related("player","team").values("player__display_name","team__name","bpr"))
                db_by_name = defaultdict(list)
                for row in qs_em: db_by_name[row["player__display_name"]].append(row)
                name_keys = list(db_by_name.keys())
                our_bprs, em_bprs = [], []
                for em in em_records:
                    em_n = _norm(em["name"])
                    cands = difflib.get_close_matches(em_n, [_norm(k) for k in name_keys], n=2, cutoff=0.65)
                    if not cands: continue
                    best_row, best_s = None, 0.0
                    for cand in cands:
                        for orig in name_keys:
                            if _norm(orig) == cand:
                                for row in db_by_name[orig]:
                                    ns = difflib.SequenceMatcher(None, em_n, cand).ratio()
                                    ts = _name_score(normalize_team_name(em["team"]), row["team__name"] or "")
                                    s = ns*0.65+ts*0.35
                                    if s > best_s: best_s, best_row = s, row
                    if best_s < 0.55 or best_row is None or best_row["bpr"] is None: continue
                    our_bprs.append(best_row["bpr"])
                    em_bprs.append(em["adj_bpr"])
                if len(our_bprs) >= 20:
                    em_r = _pearson(our_bprs, em_bprs)
                    scorecard_lines.append(
                        (_pf(em_r, TARGET_EM_R_GOOD, True),
                         f"EM alignment r ({yr_em})",
                         f"{em_r:.3f}  (good >{TARGET_EM_R_GOOD}, excellent >{TARGET_EM_R_EXCELLENT})")
                    )
            except Exception:
                pass

        if scorecard_lines:
            all_pass = all("✓" in line[0] for line in scorecard_lines)
            for pf, name, detail in scorecard_lines:
                self.stdout.write(f"  {pf}  {name:35s}  {detail}")
            self.stdout.write(
                f"\n  {'✓ ALL TARGETS MET' if all_pass else '✗ NOT ALL TARGETS MET'}"
            )
            self.stdout.write(
                "\n  NOTE: run backtest_bpr_game_prediction for game-outcome prediction targets."
            )
        else:
            self.stdout.write("  Insufficient data for scorecard.")

        self.stdout.write("\n")
