"""
backtest_bpr_vs_evan_miya — Compare our BPR ratings against Evan Miya's published values.

Usage:
    python manage.py backtest_bpr_vs_evan_miya --season 2026
    python manage.py backtest_bpr_vs_evan_miya --season 2026 --min-poss 500 --verbose
    python manage.py backtest_bpr_vs_evan_miya --season 2026 --top 50

Outputs a structured diagnostic report:
  - Overall Pearson r, Spearman ρ, RMSE, MAE (total / offensive / defensive)
  - Systematic bias and scale check
  - Stratified analysis (high minutes, top players, offensive vs defensive)
  - Top discrepancies (players where |ours - EM| > threshold)
"""

from __future__ import annotations

import difflib
import logging
import math
from collections import defaultdict
from typing import Optional

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stats helpers (no scipy dependency)
# ---------------------------------------------------------------------------

def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _std(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = _mean(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))


def _pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 3:
        return float("nan")
    mx, my = _mean(xs), _mean(ys)
    sx, sy = _std(xs), _std(ys)
    if sx == 0 or sy == 0:
        return float("nan")
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (len(xs) - 1)
    return cov / (sx * sy)


def _spearman(xs: list[float], ys: list[float]) -> float:
    """Rank-based Spearman correlation."""
    n = len(xs)
    if n < 3:
        return float("nan")

    def _ranks(vals: list[float]) -> list[float]:
        sorted_vals = sorted(enumerate(vals), key=lambda kv: kv[1])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j < n - 1 and sorted_vals[j + 1][1] == sorted_vals[i][1]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                ranks[sorted_vals[k][0]] = avg_rank
            i = j + 1
        return ranks

    return _pearson(_ranks(xs), _ranks(ys))


def _rmse(xs: list[float], ys: list[float]) -> float:
    if not xs:
        return float("nan")
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(xs, ys)) / len(xs))


def _mae(xs: list[float], ys: list[float]) -> float:
    if not xs:
        return float("nan")
    return sum(abs(x - y) for x, y in zip(xs, ys)) / len(xs)


def _ols_slope(xs: list[float], ys: list[float]) -> float:
    """OLS slope of ys ~ xs (no intercept forced; intercept free)."""
    n = len(xs)
    if n < 2:
        return float("nan")
    mx, my = _mean(xs), _mean(ys)
    ssxx = sum((x - mx) ** 2 for x in xs)
    ssxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return ssxy / ssxx if ssxx > 0 else float("nan")


# ---------------------------------------------------------------------------
# Fuzzy matching helpers
# ---------------------------------------------------------------------------

def _best_match(target: str, candidates: list[str], cutoff: float = 0.75) -> Optional[str]:
    """Return the best fuzzy match from candidates, or None if below cutoff."""
    matches = difflib.get_close_matches(target.lower(), [c.lower() for c in candidates], n=1, cutoff=cutoff)
    if not matches:
        return None
    matched_lower = matches[0]
    for c in candidates:
        if c.lower() == matched_lower:
            return c
    return None


def _normalize(s: str) -> str:
    """Lowercase + strip punctuation for robust matching."""
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def _name_match_score(em_name: str, db_name: str) -> float:
    return difflib.SequenceMatcher(None, _normalize(em_name), _normalize(db_name)).ratio()


import re


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def _fmt(val: float, decimals: int = 2) -> str:
    if math.isnan(val):
        return "   N/A"
    return f"{val:+.{decimals}f}" if val != 0 else f" {val:.{decimals}f}"


def _section(title: str, width: int = 70) -> str:
    return f"\n{'─' * width}\n  {title}\n{'─' * width}"


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Compare our BPR ratings against Evan Miya's published BPR for a season."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season", type=int, required=True,
            help="Season ending year (e.g. 2026 for 2025-26).",
        )
        parser.add_argument(
            "--min-poss", type=int, default=400,
            help="Minimum EM possessions to include a player (default: 400).",
        )
        parser.add_argument(
            "--top", type=int, default=None,
            help="Restrict analysis to top-N EM-ranked players.",
        )
        parser.add_argument(
            "--discrepancy-threshold", type=float, default=2.0,
            help="Report players with |ours - EM| above this (default: 2.0).",
        )
        parser.add_argument(
            "--verbose", action="store_true", default=False,
            help="Print matched/unmatched player details.",
        )
        parser.add_argument(
            "--use-box-bpr", action="store_true", default=False,
            help="Compare against our box_bpr instead of final bpr (useful when RAPM is missing).",
        )

    def handle(self, *args, **options):
        from ncaa.analytics.player_value.bpr.evan_miya_reference import (
            load_em_ratings, normalize_team_name,
        )
        from ncaa.models import PlayerSeasonStats, Season, Player, Team

        season_year = options["season"]
        min_poss    = options["min_poss"]
        top_n       = options["top"]
        threshold   = options["discrepancy_threshold"]
        verbose     = options["verbose"]
        use_box     = options["use_box_bpr"]

        # ── Load EM data ──────────────────────────────────────────────────
        try:
            em_records = load_em_ratings(season_year)
        except KeyError as e:
            raise CommandError(str(e))

        if top_n:
            em_records = [r for r in em_records if r["rank"] <= top_n]

        em_records = [r for r in em_records if r["possessions"] >= min_poss]
        self.stdout.write(
            f"\nLoaded {len(em_records)} EM players "
            f"(season={season_year}, min_poss={min_poss}"
            + (f", top_n={top_n}" if top_n else "")
            + ")"
        )

        # ── Load our DB data ──────────────────────────────────────────────
        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            raise CommandError(f"Season {season_year} not found in DB.")

        bpr_field  = "box_bpr"  if use_box else "bpr"
        obpr_field = "box_obpr" if use_box else "obpr"
        dbpr_field = "box_dbpr" if use_box else "dbpr"

        qs = (
            PlayerSeasonStats.objects
            .filter(season=season)
            .select_related("player", "team")
            .values(
                "player_id", "player__display_name", "team__name",
                "obpr", "dbpr", "bpr",
                "box_obpr", "box_dbpr", "box_bpr",
                "off_poss", "def_poss",
                "bpr_source",
            )
        )

        db_by_name: dict[str, list[dict]] = defaultdict(list)
        for row in qs:
            db_by_name[row["player__display_name"]].append(row)

        all_names = list(db_by_name.keys())

        # ── Match EM → DB players ─────────────────────────────────────────
        matched: list[dict] = []       # {em, db, delta_bpr, delta_obpr, delta_dbpr}
        unmatched_em: list[dict] = []

        for em in em_records:
            em_team_norm = normalize_team_name(em["team"])
            best_row   = None
            best_score = 0.0

            for db_name, rows in db_by_name.items():
                score = _name_match_score(em["name"], db_name)
                if score < 0.5:
                    continue
                # Pick the specific row with the best team match (handles duplicate names)
                for row in rows:
                    team_score = _name_match_score(em_team_norm, row["team__name"] or "")
                    combined = score * 0.7 + team_score * 0.3
                    if combined > best_score:
                        best_score = combined
                        best_row = row

            if best_score < 0.55 or best_row is None:
                unmatched_em.append(em)
                if verbose:
                    self.stdout.write(
                        f"  [UNMATCHED] {em['name']} ({em['team']}) rank={em['rank']}"
                    )
                continue

            our_bpr  = best_row[bpr_field]
            our_obpr = best_row[obpr_field]
            our_dbpr = best_row[dbpr_field]

            if our_bpr is None and our_obpr is None:
                if verbose:
                    self.stdout.write(
                        f"  [NO BPR]    {em['name']} ({em['team']}) rank={em['rank']}"
                    )
                unmatched_em.append(em)
                continue

            if verbose:
                self.stdout.write(
                    f"  [MATCHED]   {em['name']:30s} → {best_row['player__display_name']:30s}"
                    f"  score={best_score:.2f}"
                )

            matched.append({
                "em":          em,
                "db":          best_row,
                "our_bpr":     our_bpr,
                "our_obpr":    our_obpr,
                "our_dbpr":    our_dbpr,
                "em_bpr":      em["adj_bpr"],
                "em_obpr":     em["adj_obpr"],
                "em_dbpr":     em["adj_dbpr"],
                "em_raw_bpr":  em["raw_bpr"],
                "em_raw_obpr": em["raw_obpr"],
                "em_raw_dbpr": em["raw_dbpr"],
            })

        self.stdout.write(
            f"Matched {len(matched)} / {len(em_records)} EM players  "
            f"({len(unmatched_em)} unmatched)"
        )

        if len(matched) < 20:
            raise CommandError(
                f"Too few matched players ({len(matched)}). "
                "Check that compute_ncaa_bpr has run for this season."
            )

        # ── Extract parallel arrays ───────────────────────────────────────
        def _pairs(field_ours: str, field_em: str):
            xs, ys = [], []
            for m in matched:
                o = m[field_ours]
                e = m[field_em]
                if o is not None and e is not None:
                    xs.append(o)
                    ys.append(e)
            return xs, ys

        our_bpr_vals,  em_bpr_vals  = _pairs("our_bpr",  "em_bpr")
        our_obpr_vals, em_obpr_vals = _pairs("our_obpr", "em_obpr")
        our_dbpr_vals, em_dbpr_vals = _pairs("our_dbpr", "em_dbpr")

        # Also compare against raw EM (unajusted)
        our_bpr_raw,  em_raw_bpr  = _pairs("our_bpr",  "em_raw_bpr")
        our_obpr_raw, em_raw_obpr = _pairs("our_obpr", "em_raw_obpr")
        our_dbpr_raw, em_raw_dbpr = _pairs("our_dbpr", "em_raw_dbpr")

        # ── Print report ──────────────────────────────────────────────────
        label = "box_bpr" if use_box else "bpr"

        self.stdout.write(_section(f"BPR Comparison — season {season_year}  (ours={label})"))

        self._print_metric_block(
            "vs. EM ADJUSTED BPR", our_bpr_vals, em_bpr_vals,
            our_obpr_vals, em_obpr_vals, our_dbpr_vals, em_dbpr_vals,
        )
        self._print_metric_block(
            "vs. EM RAW BPR (unajusted)", our_bpr_raw, em_raw_bpr,
            our_obpr_raw, em_raw_obpr, our_dbpr_raw, em_raw_dbpr,
        )

        # ── Bias & scale ─────────────────────────────────────────────────
        self.stdout.write(_section("Bias & Scale (vs. EM adjusted)"))
        bias_bpr  = _mean([o - e for o, e in zip(our_bpr_vals,  em_bpr_vals)])
        bias_obpr = _mean([o - e for o, e in zip(our_obpr_vals, em_obpr_vals)])
        bias_dbpr = _mean([o - e for o, e in zip(our_dbpr_vals, em_dbpr_vals)])
        slope_bpr  = _ols_slope(em_bpr_vals,  our_bpr_vals)
        slope_obpr = _ols_slope(em_obpr_vals, our_obpr_vals)
        slope_dbpr = _ols_slope(em_dbpr_vals, our_dbpr_vals)

        self.stdout.write(
            f"  Mean bias (ours − EM):  BPR={bias_bpr:+.3f}  "
            f"OBPR={bias_obpr:+.3f}  DBPR={bias_dbpr:+.3f}"
        )
        self.stdout.write(
            f"  OLS slope (ours~EM):    BPR={slope_bpr:.3f}  "
            f"OBPR={slope_obpr:.3f}  DBPR={slope_dbpr:.3f}"
        )
        self.stdout.write(
            "  (slope < 1 → ours compressed vs EM; "
            "slope > 1 → ours more spread; "
            "bias < 0 → ours lower on average)"
        )

        # ── Stratified analysis ───────────────────────────────────────────
        self.stdout.write(_section("Stratified Analysis (vs. EM adjusted BPR)"))

        # By EM rank tier
        for tier_label, lo, hi in [("Top 25", 1, 25), ("26–100", 26, 100), ("101–200", 101, 200)]:
            tier = [m for m in matched if lo <= m["em"]["rank"] <= hi
                    and m["our_bpr"] is not None]
            if tier:
                xs = [m["our_bpr"] for m in tier]
                ys = [m["em_bpr"]  for m in tier]
                self.stdout.write(
                    f"  {tier_label:12s}  n={len(tier):3d}  "
                    f"r={_pearson(xs, ys):+.3f}  "
                    f"RMSE={_rmse(xs, ys):.3f}  "
                    f"bias={_mean([x-y for x,y in zip(xs,ys)]):+.3f}"
                )

        # By possession tier
        for poss_label, lo, hi in [("High (>1500)", 1500, 9999), ("Mid (800-1500)", 800, 1500)]:
            tier = [m for m in matched if lo <= m["em"]["possessions"] < hi
                    and m["our_bpr"] is not None]
            if tier:
                xs = [m["our_bpr"] for m in tier]
                ys = [m["em_bpr"]  for m in tier]
                self.stdout.write(
                    f"  {poss_label:18s}  n={len(tier):3d}  "
                    f"r={_pearson(xs, ys):+.3f}  "
                    f"RMSE={_rmse(xs, ys):.3f}  "
                    f"bias={_mean([x-y for x,y in zip(xs,ys)]):+.3f}"
                )

        # Offensive-heavy vs defensive-heavy (EM)
        off_heavy = [m for m in matched if m["em_obpr"] > m["em_dbpr"] and m["our_bpr"] is not None]
        def_heavy = [m for m in matched if m["em_dbpr"] > m["em_obpr"] and m["our_bpr"] is not None]
        for label_s, subset in [("Off-dominant", off_heavy), ("Def-dominant", def_heavy)]:
            if subset:
                xs = [m["our_bpr"] for m in subset]
                ys = [m["em_bpr"]  for m in subset]
                self.stdout.write(
                    f"  {label_s:18s}  n={len(subset):3d}  "
                    f"r={_pearson(xs, ys):+.3f}  "
                    f"RMSE={_rmse(xs, ys):.3f}  "
                    f"bias={_mean([x-y for x,y in zip(xs,ys)]):+.3f}"
                )

        # ── Top discrepancies ─────────────────────────────────────────────
        self.stdout.write(_section(f"Top Discrepancies  |ours − EM adj_bpr| > {threshold}"))
        discrepancies = [
            m for m in matched
            if m["our_bpr"] is not None
            and abs(m["our_bpr"] - m["em_bpr"]) > threshold
        ]
        discrepancies.sort(key=lambda m: abs(m["our_bpr"] - m["em_bpr"]), reverse=True)

        if not discrepancies:
            self.stdout.write(f"  None — all matched players within {threshold} pts/100.")
        else:
            header = f"  {'Player':30s} {'Team':20s} {'Rank':>4} {'EM':>6} {'Ours':>6} {'Diff':>6} {'OBPR diff':>9} {'DBPR diff':>9}"
            self.stdout.write(header)
            self.stdout.write("  " + "─" * (len(header) - 2))
            for m in discrepancies[:40]:
                em   = m["em"]
                diff = m["our_bpr"] - m["em_bpr"]
                odiff = (m["our_obpr"] or 0.0) - m["em_obpr"]
                ddiff = (m["our_dbpr"] or 0.0) - m["em_dbpr"]
                self.stdout.write(
                    f"  {em['name']:30s} {em['team']:20s} "
                    f"{em['rank']:4d} "
                    f"{m['em_bpr']:+6.2f} "
                    f"{m['our_bpr']:+6.2f} "
                    f"{diff:+6.2f} "
                    f"{odiff:+9.2f} "
                    f"{ddiff:+9.2f}"
                )

        # ── Scale summary ─────────────────────────────────────────────────
        self.stdout.write(_section("Distribution Comparison (vs. EM adjusted)"))
        em_all  = em_bpr_vals
        our_all = our_bpr_vals
        self.stdout.write(
            f"  EM:   mean={_mean(em_all):+.2f}  std={_std(em_all):.2f}  "
            f"max={max(em_all):.2f}  min={min(em_all):.2f}"
        )
        self.stdout.write(
            f"  Ours: mean={_mean(our_all):+.2f}  std={_std(our_all):.2f}  "
            f"max={max(our_all):.2f}  min={min(our_all):.2f}"
        )

        # ── Top 15 by EM rank side-by-side ────────────────────────────────
        self.stdout.write(_section("Top 15 by EM Rank — Side by Side"))
        top15 = sorted(
            [m for m in matched if m["em"]["rank"] <= 20 and m["our_bpr"] is not None],
            key=lambda m: m["em"]["rank"],
        )[:15]
        self.stdout.write(
            f"  {'Rk':>3} {'Player':28s} {'EM bpr':>7} {'Ours':>7} "
            f"{'EM o/d':>11} {'Ours o/d':>11} {'Δ':>6}"
        )
        for m in top15:
            em = m["em"]
            delta = m["our_bpr"] - m["em_bpr"]
            self.stdout.write(
                f"  {em['rank']:3d} {em['name']:28s} "
                f"{m['em_bpr']:+7.2f} {m['our_bpr']:+7.2f} "
                f"{m['em_obpr']:+5.2f}/{m['em_dbpr']:+5.2f} "
                f"{(m['our_obpr'] or 0):+5.2f}/{(m['our_dbpr'] or 0):+5.2f} "
                f"{delta:+6.2f}"
            )

        self.stdout.write("\n")

    def _print_metric_block(
        self,
        label: str,
        our_bpr, em_bpr,
        our_obpr, em_obpr,
        our_dbpr, em_dbpr,
    ):
        self.stdout.write(f"\n  ── {label} ──")
        self.stdout.write(
            f"  {'':6s}  {'n':>4}  {'Pearson r':>9}  {'Spearman ρ':>10}  {'RMSE':>6}  {'MAE':>6}"
        )
        for col_label, xs, ys in [
            ("BPR",  our_bpr,  em_bpr),
            ("OBPR", our_obpr, em_obpr),
            ("DBPR", our_dbpr, em_dbpr),
        ]:
            if not xs:
                self.stdout.write(f"  {col_label:6s}  {'─':>4}  {'no data':>9}")
                continue
            self.stdout.write(
                f"  {col_label:6s}  {len(xs):4d}  "
                f"{_pearson(xs, ys):+9.3f}  "
                f"{_spearman(xs, ys):+10.3f}  "
                f"{_rmse(xs, ys):6.3f}  "
                f"{_mae(xs, ys):6.3f}"
            )
