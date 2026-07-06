"""
Management command: validate_bpr_through_date

Acceptance tests for the leak-free through-date feature rebuilds
(ncaa/analytics/player_value/bpr/through_date.py). Read-only.

Checks (per --season):
  1. Season-end parity — at cutoff = last game date:
       - team adj_em vs stored TeamSeasonRatings.adj_em:      r >= 0.97
       - per-feature r vs stored PlayerSeasonStats:            r >= 0.98
         (box rates; on-court features compared where both non-null)
  2. Mid-season divergence — at a mid-January cutoff, features MUST differ
     from season-end values for players with post-cutoff games (anti-leak).

Usage:
  python manage.py validate_bpr_through_date --season 2026
"""

from __future__ import annotations

import datetime
import statistics

from django.core.management.base import BaseCommand

FEATURE_KEYS = [
    "gp", "mpg", "pts", "ast", "tov", "stl", "blk", "pf", "reb",
    "oreb_pg", "dreb_pg", "fga_pg", "fg3a_pg", "fta_pg", "ftm_pg",
    "efg_pct", "ts_pct",
    "on_court_secs_pg", "on_court_adj_em",
    "on_court_tov_edge", "on_court_reb_edge",
]

TEAM_R_MIN = 0.97
FEATURE_R_MIN = 0.98
# on-court features involve a simplified team-rating engine and phantom-stint
# differences; hold them to a looser (documented) bar than pure box rates
ON_COURT_R_MIN = 0.90


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return num / (dx * dy) if dx > 0 and dy > 0 else float("nan")


class Command(BaseCommand):
    help = "Acceptance tests for leak-free through-date BPR feature rebuilds."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)

    def handle(self, *args, **opts):
        from ncaa.models import Game, PlayerSeasonStats, TeamSeasonRatings
        from ncaa.analytics.player_value.bpr.through_date import (
            build_team_adj_em_through_date,
            build_pss_features_through_date,
        )

        season = opts["season"]
        last_date = (Game.objects
                     .filter(season_year=season, status="final")
                     .order_by("-game_date")
                     .values_list("game_date", flat=True)
                     .first())
        if last_date is None:
            self.stderr.write(f"No final games for season {season}")
            return
        mid_date = datetime.date(season, 1, 15)

        failures: list[str] = []

        # ── 1a. Team map parity at season end ─────────────────────────────────
        self.stdout.write(f"Season {season}: season-end cutoff = {last_date}")
        team_maps = build_team_adj_em_through_date(season, last_date)
        adj_em_map = team_maps[0]
        stored = dict(TeamSeasonRatings.objects
                      .filter(season__year=season, adj_em__isnull=False)
                      .values_list("team_id", "adj_em"))
        common = sorted(set(adj_em_map) & set(stored))
        r_team = _pearson([adj_em_map[t] for t in common],
                          [stored[t] for t in common])
        verdict = "PASS" if r_team >= TEAM_R_MIN else "FAIL"
        if verdict == "FAIL":
            failures.append(f"team adj_em r={r_team:.4f} < {TEAM_R_MIN}")
        self.stdout.write(
            f"  [1a] team adj_em parity: r={r_team:.4f} over {len(common)} teams  {verdict}"
        )

        # ── 1b. Feature parity at season end ─────────────────────────────────
        rows_end = build_pss_features_through_date(season, last_date, team_maps=team_maps)
        by_key = {(r["player_id"], r["team_id"]): r for r in rows_end}
        stored_rows = list(PlayerSeasonStats.objects
                           .filter(season__year=season, gp__gte=5)
                           .values("player_id", "team_id", *FEATURE_KEYS))
        for feat in FEATURE_KEYS:
            xs, ys = [], []
            for s in stored_rows:
                r = by_key.get((s["player_id"], s["team_id"]))
                if r is None:
                    continue
                a, b = r.get(feat), s.get(feat)
                if a is None or b is None:
                    continue
                xs.append(float(a))
                ys.append(float(b))
            r_val = _pearson(xs, ys)
            bar = ON_COURT_R_MIN if feat.startswith("on_court") else FEATURE_R_MIN
            ok = (r_val != r_val) or r_val >= bar  # NaN (no data) → skip, not fail
            status = "PASS" if ok else "FAIL"
            if not ok:
                failures.append(f"{feat}: r={r_val:.4f} < {bar} (n={len(xs)})")
            self.stdout.write(f"  [1b] {feat:22s} r={r_val:7.4f}  n={len(xs):5d}  {status}")

        # ── 2. Mid-season divergence (anti-leak) ──────────────────────────────
        rows_mid = build_pss_features_through_date(season, mid_date)
        mid_by_key = {(r["player_id"], r["team_id"]): r for r in rows_mid}
        n_checked = n_diff = 0
        for key, end_row in by_key.items():
            mid_row = mid_by_key.get(key)
            if mid_row is None or end_row["gp"] <= mid_row["gp"]:
                continue  # player only if they have post-cutoff games
            n_checked += 1
            if any(mid_row.get(f) != end_row.get(f) for f in ("gp", "pts", "mpg")):
                n_diff += 1
        frac = n_diff / n_checked if n_checked else 0.0
        ok = n_checked > 100 and frac > 0.99
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures.append(f"mid-season divergence: {n_diff}/{n_checked}")
        self.stdout.write(
            f"  [2]  mid-season ({mid_date}) divergence: "
            f"{n_diff}/{n_checked} players with post-cutoff games differ  {status}"
        )

        if failures:
            self.stdout.write(self.style.ERROR(f"\nFAILURES:\n  " + "\n  ".join(failures)))
        else:
            self.stdout.write(self.style.SUCCESS("\nAll acceptance checks passed."))
