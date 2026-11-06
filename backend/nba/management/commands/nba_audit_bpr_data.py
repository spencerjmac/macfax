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
  B6  Stint seconds vs box-score seconds per player-game (tolerance 60 s;
      120 s for seasons whose box scores hold only whole minutes)
  B7  Stint plus-minus vs box-score plus_minus per player-game (pass: no
      more than 1% off by more than 1 point)

B5-B7 split every metric by NBAGame.lineup_source ("rotation", "parser",
"unknown" for games synced before the field existed). Their headline covers
the games RAPM uses (pbp_quality_flag False); quality-flagged games get their
own line.
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
                    + "  ".join(self._console_metric(k, v) for k, v in res["metrics"].items())
                )
                flagged = res.get("flagged")
                if flagged is not None:
                    self.stdout.write(
                        f"  {season} quality-flagged games: {flagged['n_games']}"
                        + (f"  {flagged['status']}  " + "  ".join(
                            self._console_metric(k, v) for k, v in flagged["metrics"].items())
                           if flagged["n_games"] else "")
                    )

        summary_path = out_dir / "nba_audit_summary.json"
        with open(summary_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        self.stdout.write(self.style.SUCCESS(f"\nSummary written to {summary_path}"))

    @staticmethod
    def _console_metric(key: str, value) -> str:
        """key=value; a games_off_gt1 list prints as its count plus the first 10 ids."""
        if key.endswith("games_off_gt1") and isinstance(value, list):
            more = ", ..." if len(value) > 10 else ""
            return f"{key}={len(value)} [{', '.join(value[:10])}{more}]"
        return f"{key}={value}"

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
        Per season, loaded once for B5-B7: each synced game's final score,
        lineup source and quality flag, its stints' points per lineup window,
        and per player-game stint seconds and plus-minus next to the box
        score's. A window is (period, window_index) when the sync stored one,
        else (period, clock_start, clock_end), as in build_nba_observations.
        """
        cache = self.__dict__.setdefault("_stints_vs_box_cache", {})
        if season in cache:
            return cache[season]
        from nba.models import NBAGame, NBAPlayerGameStats, NBAPlayerGameStint

        games = {
            pk: {"game_id": game_id, "home_team": home, "home_score": hs, "away_score": as_,
                 "source": source or "unknown", "flagged": bool(flag), "windows": {}}
            for pk, game_id, home, hs, as_, source, flag in NBAGame.objects
            .filter(season__year=season, status="Final")
            .values_list("pk", "game_id", "home_team_id", "home_score", "away_score",
                         "lineup_source", "pbp_quality_flag")
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
            g = games[key[0]]
            box_secs, box_pm = box.get(key, (0, None))
            player_games.append({
                "game_pk": key[0], "game_id": g["game_id"], "player_pk": key[1],
                "source": g["source"], "flagged": g["flagged"],
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

    @staticmethod
    def _headline_and_flagged(check: str, season: int, rows: list[dict], measure) -> dict:
        """
        measure(rows) → (status, metrics). The headline covers the games RAPM
        uses (not quality-flagged); flagged games are measured on their own.
        """
        if not rows:
            return {"check": check, "season": season, "status": "WARN", "metrics": {"note": "no stints"}}
        used = [r for r in rows if not r["flagged"]]
        flagged = [r for r in rows if r["flagged"]]
        status, metrics = measure(used) if used else ("WARN", {"note": "no unflagged games"})
        f_status, f_metrics = measure(flagged) if flagged else ("PASS", {})
        return {"check": check, "season": season, "status": status, "metrics": metrics,
                "flagged": {"n_games": len({r["game_pk"] for r in flagged}),
                            "status": f_status, "metrics": f_metrics}}

    # ── B5: stint points vs final score ───────────────────────────────────────

    def _measure_b5(self, rows: list[dict]) -> tuple[str, dict]:
        metrics, worst = {}, 0.0
        for src, rs in self._by_source(rows).items():
            final = sum(r["final_home"] + r["final_away"] for r in rs)
            n_off = sum(1 for r in rs if r["off_by"] > 2)
            metrics[f"{src}.n_games"] = len(rs)
            metrics[f"{src}.pts_ratio"] = round(sum(r["stint_home"] + r["stint_away"] for r in rs) / final, 4) if final else None
            metrics[f"{src}.n_off_gt2"] = n_off
            worst = max(worst, n_off / len(rs))
        return ("PASS" if worst <= 0.01 else "WARN"), metrics

    def check_b5(self, season: int, out_dir: Path) -> dict:
        data = self._stints_vs_box(season)
        rows = []
        for pk, g in data["games"].items():
            if g["home_score"] is None or g["away_score"] is None:
                continue
            home = sum(w[0] for w in g["windows"].values())
            away = sum(w[1] for w in g["windows"].values())
            rows.append({"game_pk": pk, "source": g["source"], "flagged": g["flagged"],
                         "stint_home": home, "final_home": g["home_score"],
                         "stint_away": away, "final_away": g["away_score"],
                         "off_by": max(abs(home - g["home_score"]), abs(away - g["away_score"]))})
        off = sorted((r for r in rows if r["off_by"] > 2), key=lambda r: -r["off_by"])
        self._write_csv(out_dir / f"b5_stint_points_off_{season}.csv", off[:200])
        return self._headline_and_flagged("B5", season, rows, self._measure_b5)

    # ── B6: stint seconds vs box-score seconds ────────────────────────────────

    @staticmethod
    def _b6_tolerance(rows: list[dict]) -> int:
        """120 s when every box-score value in the season is whole minutes, else 60 s."""
        return 120 if all(r["box_secs"] % 60 == 0 for r in rows) else 60

    def _measure_b6(self, rows: list[dict], tolerance: int = 60) -> tuple[str, dict]:
        metrics, worst = {"tolerance_secs": tolerance}, 0.0
        for src, rs in self._by_source(rows).items():
            errs = [abs(r["stint_secs"] - r["box_secs"]) for r in rs]
            over = sum(1 for e in errs if e > tolerance) / len(errs)
            metrics[f"{src}.n_player_games"] = len(rs)
            metrics[f"{src}.median_abs_err_secs"] = statistics.median(errs)
            metrics[f"{src}.share_over_tol"] = round(over, 4)
            worst = max(worst, over)
        return ("PASS" if worst <= 0.01 else "WARN"), metrics

    def check_b6(self, season: int, out_dir: Path) -> dict:
        rows = self._stints_vs_box(season)["player_games"]
        tolerance = self._b6_tolerance(rows)
        off = sorted((r for r in rows if abs(r["stint_secs"] - r["box_secs"]) > tolerance),
                     key=lambda r: -abs(r["stint_secs"] - r["box_secs"]))
        self._write_csv(out_dir / f"b6_stint_seconds_off_{season}.csv", off[:200])
        return self._headline_and_flagged(
            "B6", season, rows, lambda rs: self._measure_b6(rs, tolerance))

    # ── B7: stint plus-minus vs box-score plus_minus ──────────────────────────

    def _measure_b7(self, rows: list[dict]) -> tuple[str, dict]:
        """Pass: no more than 1% of player-games off by more than 1 point."""
        metrics, worst = {}, 0.0
        for src, rs in self._by_source(rows).items():
            equal = sum(1 for r in rs if r["stint_pm"] == r["box_pm"]) / len(rs)
            off = [r for r in rs if abs(r["stint_pm"] - r["box_pm"]) > 1]
            metrics[f"{src}.n_player_games"] = len(rs)
            metrics[f"{src}.share_pm_equal"] = round(equal, 4)
            metrics[f"{src}.share_off_gt1"] = round(len(off) / len(rs), 4)
            metrics[f"{src}.games_off_gt1"] = sorted({r["game_id"] for r in off})
            worst = max(worst, len(off) / len(rs))
        return ("PASS" if worst <= 0.01 else "WARN"), metrics

    def check_b7(self, season: int, out_dir: Path) -> dict:
        rows = [r for r in self._stints_vs_box(season)["player_games"] if r["box_pm"] is not None]
        off = sorted((r for r in rows if r["stint_pm"] != r["box_pm"]),
                     key=lambda r: -abs(r["stint_pm"] - r["box_pm"]))
        self._write_csv(out_dir / f"b7_stint_plus_minus_off_{season}.csv", off[:200])
        # Every game with a miss larger than 1 point (games_off_gt1 in full).
        by_game: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            if abs(r["stint_pm"] - r["box_pm"]) > 1:
                by_game[r["game_id"]].append(r)
        self._write_csv(out_dir / f"b7_games_off_gt1_{season}.csv", [
            {"game_id": gid, "source": rs[0]["source"], "flagged": rs[0]["flagged"],
             "n_player_games_off_gt1": len(rs),
             "max_miss": max(abs(r["stint_pm"] - r["box_pm"]) for r in rs)}
            for gid, rs in sorted(by_game.items())
        ])
        return self._headline_and_flagged("B7", season, rows, self._measure_b7)
