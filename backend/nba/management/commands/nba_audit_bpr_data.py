"""
Management command: nba_audit_bpr_data

Read-only data-integrity audit for the NBA BPR pipeline (mission Phase 2).
Lighter than the NCAA audit — targets the known NBA failure modes.

Never writes to any model.

Usage:
  python manage.py nba_audit_bpr_data --seasons 2022 2023 2024 2025 2026

Checks:
  B1  Stint duplication recurrence (the 2026 update_conflicts bug class)
  B2  Traded players: multi-team season handling in stats and stints
  B3  LEBRON CSV player-id match rate per season
  B4  d_mpir and pbp_quality_flag coverage per season
"""

from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand

ALL_CHECKS = ["B1", "B2", "B3", "B4"]


class Command(BaseCommand):
    help = "Read-only data integrity audit for the NBA BPR pipeline (checks B1-B4)."

    def add_arguments(self, parser):
        parser.add_argument("--seasons", nargs="+", type=int, required=True)
        parser.add_argument("--check", type=str, default=None)
        parser.add_argument("--out-dir", type=str,
                            default="backtest_output/bpr_audit")

    def handle(self, *args, **opts):
        seasons = sorted(opts["seasons"])
        checks = [opts["check"].upper()] if opts["check"] else ALL_CHECKS
        out_dir = Path(opts["out_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)

        results: list[dict] = []
        for check in checks:
            method = getattr(self, f"check_{check.lower()}", None)
            if method is None:
                self.stderr.write(f"Unknown check: {check}")
                continue
            self.stdout.write(f"\n=== {check} ===")
            for season in seasons:
                try:
                    res = method(season, out_dir)
                except Exception as exc:
                    res = {"check": check, "season": season,
                           "status": "ERROR", "metrics": {"error": str(exc)}}
                if res is None:
                    continue
                results.append(res)
                self.stdout.write(
                    f"  {season}: {res['status']}  "
                    + "  ".join(f"{k}={v}" for k, v in list(res["metrics"].items())[:6])
                )

        summary_path = out_dir / "nba_audit_summary.json"
        with open(summary_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        self.stdout.write(self.style.SUCCESS(f"\nSummary written to {summary_path}"))

    @staticmethod
    def _write_csv(path: Path, rows: list[dict]) -> None:
        if not rows:
            return
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    # ── B1: stint duplication recurrence ──────────────────────────────────────

    def check_b1(self, season: int, out_dir: Path) -> dict:
        from nba.models import NBAPlayerGameStint

        qs = (NBAPlayerGameStint.objects
              .filter(game__season__year=season)
              .values_list("player_id", "game_id", "period",
                           "clock_start_secs", "clock_end_secs", "secs_on"))

        seen: set = set()
        n_exact = 0
        by_pg: dict[tuple, list] = defaultdict(list)
        total_secs = 0
        for pid, gid, period, cs, ce, secs in qs.iterator(chunk_size=50000):
            key = (pid, gid, period, cs, ce)
            if key in seen:
                n_exact += 1
            else:
                seen.add(key)
            by_pg[(pid, gid, period)].append((cs, ce))
            total_secs += secs

        overlap_secs = 0
        examples = []
        for key, intervals in by_pg.items():
            if len(intervals) < 2:
                continue
            intervals.sort(key=lambda t: -t[0])
            for i in range(len(intervals) - 1):
                s1, e1 = intervals[i]
                s2, e2 = intervals[i + 1]
                ov = min(s1, s2) - max(e1, e2)
                if ov > 0:
                    overlap_secs += ov
                    if len(examples) < 200:
                        examples.append({"player_id": key[0], "game_id": key[1],
                                         "period": key[2],
                                         "stint_a": f"{s1}-{e1}",
                                         "stint_b": f"{s2}-{e2}",
                                         "overlap_secs": ov})

        self._write_csv(out_dir / f"b1_nba_overlaps_{season}.csv", examples)
        frac = overlap_secs / total_secs if total_secs else 0.0
        n_total = len(seen) + n_exact
        status = "PASS" if (n_exact == 0 and frac < 0.001) else "FAIL"
        return {"check": "B1", "season": season, "status": status,
                "metrics": {"n_stints": n_total, "n_exact_dupes": n_exact,
                            "overlap_frac": round(frac, 6)}}

    # ── B2: traded players ────────────────────────────────────────────────────

    def check_b2(self, season: int, out_dir: Path) -> dict:
        from nba.models import NBAPlayerGameStats, NBAPlayerSeasonStats

        team_by_pg: dict[int, set] = defaultdict(set)
        for pid, tid in (NBAPlayerGameStats.objects
                         .filter(game__season__year=season)
                         .values_list("player_id", "team_id")):
            team_by_pg[pid].add(tid)
        multi = {pid for pid, tids in team_by_pg.items() if len(tids) > 1}

        # Season-stat handling: traded players should have season rows;
        # check how many multi-team players have >1 PSS row (per-team rows)
        # vs a single TOT-style row — either is fine, zero rows is not.
        pss_counts: dict[int, int] = defaultdict(int)
        for pid in (NBAPlayerSeasonStats.objects
                    .filter(season__year=season, player_id__in=list(multi))
                    .values_list("player_id", flat=True)):
            pss_counts[pid] += 1
        n_missing = sum(1 for pid in multi if pss_counts.get(pid, 0) == 0)
        return {"check": "B2", "season": season,
                "status": "PASS" if n_missing == 0 else "WARN",
                "metrics": {"n_multi_team_players": len(multi),
                            "n_missing_season_row": n_missing,
                            "n_multi_pss_rows": sum(1 for v in pss_counts.values() if v > 1)}}

    # ── B3: LEBRON id match rate ──────────────────────────────────────────────

    def check_b3(self, season: int, out_dir: Path) -> dict:
        import csv as _csv
        from pathlib import Path as _P
        from nba.models import NBAPlayerSeasonStats

        # data/nba/lebron-data-{year}.csv at project root
        root = _P(__file__).resolve().parents[4]
        csv_path = root / "data" / "nba" / f"lebron-data-{season}.csv"
        if not csv_path.exists():
            return {"check": "B3", "season": season, "status": "WARN",
                    "metrics": {"note": f"missing {csv_path.name}"}}

        lebron_ids = set()
        with open(csv_path) as f:
            for row in _csv.DictReader(f):
                raw = row.get("_id") or row.get("nba_id") or row.get("player_id") or ""
                try:
                    lebron_ids.add(int(float(raw)))
                except (TypeError, ValueError):
                    continue

        db_ids = set(
            NBAPlayerSeasonStats.objects
            .filter(season__year=season, mpg__gte=12.0, gp__gte=20)
            .values_list("player__player_id", flat=True)
        )
        if not db_ids:
            return {"check": "B3", "season": season, "status": "WARN",
                    "metrics": {"note": "no qualified DB players"}}
        matched = db_ids & lebron_ids
        rate = len(matched) / len(db_ids)
        missing = sorted(db_ids - lebron_ids)
        rows = [{"nba_player_id": pid} for pid in missing[:100]]
        self._write_csv(out_dir / f"b3_lebron_unmatched_{season}.csv", rows)
        return {"check": "B3", "season": season,
                "status": "PASS" if rate >= 0.90 else "WARN",
                "metrics": {"n_qualified_db": len(db_ids),
                            "n_lebron_rows": len(lebron_ids),
                            "match_rate": round(rate, 3)}}

    # ── B4: d_mpir / pbp_quality_flag coverage ────────────────────────────────

    def check_b4(self, season: int, out_dir: Path) -> dict:
        from nba.models import NBAPlayerSeasonStats, NBAGame

        qual = NBAPlayerSeasonStats.objects.filter(
            season__year=season, mpg__gte=12.0, gp__gte=20)
        n_qual = qual.count()
        n_dmpir = qual.filter(d_mpir__isnull=False).count()

        games = NBAGame.objects.filter(season__year=season, status="Final")
        n_games = games.count()
        n_flagged = games.filter(pbp_quality_flag=True).count()
        cov = n_dmpir / n_qual if n_qual else 0.0
        return {"check": "B4", "season": season,
                "status": "PASS" if cov >= 0.90 else "WARN",
                "metrics": {"n_qualified": n_qual,
                            "d_mpir_coverage": round(cov, 3),
                            "n_final_games": n_games,
                            "n_pbp_flagged": n_flagged,
                            "pbp_flagged_frac": round(n_flagged / n_games, 4) if n_games else None}}
