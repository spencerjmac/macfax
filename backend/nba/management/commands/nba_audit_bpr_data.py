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
  B5  Stint points vs final score per game
  B6  Stint seconds vs box-score seconds per player-game
  B7  Stint plus-minus vs box-score plus_minus per player-game

B5-B7 split every metric by NBAGame.lineup_source ("rotation", "parser",
"unknown" for games synced before the field existed).
"""

from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand

ALL_CHECKS = ["B1", "B2", "B3", "B4", "B5", "B6", "B7"]
LINEUP_SOURCES = ("rotation", "parser", "unknown")


class Command(BaseCommand):
    help = "Read-only data integrity audit for the NBA BPR pipeline (checks B1-B7)."

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

    # ── B5-B7: stints vs the box score ────────────────────────────────────────

    def _stints_vs_box(self, season: int) -> dict:
        """
        Per season, loaded once for B5-B7: each synced game's final score and
        lineup source, its stints' points per lineup window, and per
        player-game stint seconds and plus-minus next to the box score's.
        A window is (period, window_index) when the sync stored one, else
        (period, clock_start, clock_end), as in build_nba_observations.
        """
        cache = self.__dict__.setdefault("_stints_vs_box_cache", {})
        if season in cache:
            return cache[season]
        from nba.models import NBAGame, NBAPlayerGameStats, NBAPlayerGameStint

        games = {
            pk: {"home_team": home, "home_score": hs, "away_score": as_,
                 "source": source or "unknown", "windows": {}}
            for pk, home, hs, as_, source in NBAGame.objects
            .filter(season__year=season, status="Final")
            .values_list("pk", "home_team_id", "home_score", "away_score", "lineup_source")
        }
        stint_secs: dict[tuple, int] = defaultdict(int)
        stint_pm: dict[tuple, int] = defaultdict(int)
        synced: set[int] = set()
        for gid, pid, tid, period, cs, ce, win, secs, pm, scored, allowed in (
            NBAPlayerGameStint.objects.filter(game__season__year=season)
            .values_list("game_id", "player_id", "team_id", "period", "clock_start_secs",
                         "clock_end_secs", "window_index", "secs_on", "plus_minus",
                         "pts_scored", "pts_allowed")
            .iterator(chunk_size=50000)
        ):
            g = games.get(gid)
            if g is None:
                continue
            synced.add(gid)
            stint_secs[(gid, pid)] += secs
            stint_pm[(gid, pid)] += pm
            key = (period, win) if win is not None else (period, cs, ce)
            if key not in g["windows"]:
                home = tid == g["home_team"]
                g["windows"][key] = (scored, allowed) if home else (allowed, scored)

        box: dict[tuple, tuple] = {}
        for gid, pid, secs, pm in (NBAPlayerGameStats.objects
                                   .filter(game__season__year=season, game_id__in=synced)
                                   .values_list("game_id", "player_id", "seconds_played", "plus_minus")):
            box[(gid, pid)] = (secs or 0, pm)

        player_games = []
        for key in set(stint_secs) | {k for k, (secs, _) in box.items() if secs > 0}:
            box_secs, box_pm = box.get(key, (0, None))
            player_games.append({
                "game_pk": key[0], "player_pk": key[1], "source": games[key[0]]["source"],
                "stint_secs": stint_secs.get(key, 0), "box_secs": box_secs,
                "stint_pm": stint_pm.get(key, 0), "box_pm": box_pm,
            })
        cache[season] = {"games": {pk: g for pk, g in games.items() if pk in synced},
                         "player_games": player_games}
        return cache[season]

    @staticmethod
    def _by_source(rows: list[dict]) -> dict[str, list[dict]]:
        split = defaultdict(list)
        for r in rows:
            split[r["source"]].append(r)
        return {src: split[src] for src in LINEUP_SOURCES if split[src]}

    # ── B5: stint points vs final score ───────────────────────────────────────

    def check_b5(self, season: int, out_dir: Path) -> dict:
        data = self._stints_vs_box(season)
        rows = []
        for pk, g in data["games"].items():
            if g["home_score"] is None or g["away_score"] is None:
                continue
            home = sum(w[0] for w in g["windows"].values())
            away = sum(w[1] for w in g["windows"].values())
            rows.append({"game_pk": pk, "source": g["source"],
                         "stint_home": home, "final_home": g["home_score"],
                         "stint_away": away, "final_away": g["away_score"],
                         "off_by": max(abs(home - g["home_score"]), abs(away - g["away_score"]))})

        metrics, worst = {}, 0.0
        for src, rs in self._by_source(rows).items():
            final = sum(r["final_home"] + r["final_away"] for r in rs)
            n_off = sum(1 for r in rs if r["off_by"] > 2)
            metrics[f"{src}.n_games"] = len(rs)
            metrics[f"{src}.pts_ratio"] = round(sum(r["stint_home"] + r["stint_away"] for r in rs) / final, 4) if final else None
            metrics[f"{src}.n_off_gt2"] = n_off
            worst = max(worst, n_off / len(rs))
        off = sorted((r for r in rows if r["off_by"] > 2), key=lambda r: -r["off_by"])
        self._write_csv(out_dir / f"b5_stint_points_off_{season}.csv", off[:200])
        if not rows:
            return {"check": "B5", "season": season, "status": "WARN", "metrics": {"note": "no stints"}}
        return {"check": "B5", "season": season,
                "status": "PASS" if worst <= 0.01 else "WARN", "metrics": metrics}

    # ── B6: stint seconds vs box-score seconds ────────────────────────────────

    def check_b6(self, season: int, out_dir: Path) -> dict:
        rows = self._stints_vs_box(season)["player_games"]
        metrics, worst = {}, 0.0
        for src, rs in self._by_source(rows).items():
            errs = [abs(r["stint_secs"] - r["box_secs"]) for r in rs]
            over = sum(1 for e in errs if e > 60) / len(errs)
            metrics[f"{src}.n_player_games"] = len(rs)
            metrics[f"{src}.median_abs_err_secs"] = statistics.median(errs)
            metrics[f"{src}.share_over_60s"] = round(over, 4)
            worst = max(worst, over)
        off = sorted((r for r in rows if abs(r["stint_secs"] - r["box_secs"]) > 60),
                     key=lambda r: -abs(r["stint_secs"] - r["box_secs"]))
        self._write_csv(out_dir / f"b6_stint_seconds_off_{season}.csv", off[:200])
        if not rows:
            return {"check": "B6", "season": season, "status": "WARN", "metrics": {"note": "no stints"}}
        return {"check": "B6", "season": season,
                "status": "PASS" if worst <= 0.01 else "WARN", "metrics": metrics}

    # ── B7: stint plus-minus vs box-score plus_minus ──────────────────────────

    def check_b7(self, season: int, out_dir: Path) -> dict:
        rows = [r for r in self._stints_vs_box(season)["player_games"] if r["box_pm"] is not None]
        metrics, worst = {}, 1.0
        for src, rs in self._by_source(rows).items():
            equal = sum(1 for r in rs if r["stint_pm"] == r["box_pm"]) / len(rs)
            metrics[f"{src}.n_player_games"] = len(rs)
            metrics[f"{src}.share_pm_equal"] = round(equal, 4)
            worst = min(worst, equal)
        off = sorted((r for r in rows if r["stint_pm"] != r["box_pm"]),
                     key=lambda r: -abs(r["stint_pm"] - r["box_pm"]))
        self._write_csv(out_dir / f"b7_stint_plus_minus_off_{season}.csv", off[:200])
        if not rows:
            return {"check": "B7", "season": season, "status": "WARN", "metrics": {"note": "no stints"}}
        return {"check": "B7", "season": season,
                "status": "PASS" if worst >= 0.99 else "WARN", "metrics": metrics}
