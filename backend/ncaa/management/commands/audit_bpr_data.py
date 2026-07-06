"""
Management command: audit_bpr_data

Read-only data-integrity audit for the NCAA BPR pipeline (mission Phase 2).
Runs a battery of checks (A1-A12) over stint, box-score, recruiting, and
Evan Miya reference data, and writes per-check CSVs plus a summary JSON.

Never writes to any model. Safe to run against production data.

Usage:
  python manage.py audit_bpr_data --seasons 2021 2022 2023 2024 2025 2026
  python manage.py audit_bpr_data --seasons 2026 --check A2
  python manage.py audit_bpr_data --seasons 2024 --out-dir backtest_output/bpr_audit

Checks:
  A1  Stint minute coverage vs game clock and vs box-score minutes
  A2  Duplicate / overlapping stints (the NBA update_conflicts bug class)
  A3  Lineup-size sweep: % of game-seconds with exactly 5v5 on court
  A4  Stint-derived possessions vs box-score possessions per game-team
  A5  FGA coverage per season (datasets.py 50% gate)
  A6  build_rapm_dataset == build_rapm_dataset_through_date(season-end)
  A7  Mid-season transfers: multi-team players, stint team attribution
  A8  OT / neutral-site handling counts
  A9  Freshman recruiting-profile coverage
  A10 Evan Miya fuzzy-match audit (rate + worst accepted matches)
  A11 BPR distribution / provenance by possession bucket
  A12 Garbage-time share proxy (2nd-half stint-secs in 25+ blowouts)
"""

from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand

ALL_CHECKS = [
    "A1", "A2", "A3", "A4", "A5", "A6",
    "A7", "A8", "A9", "A10", "A11", "A12",
]

REGULATION_SECS_PER_PERIOD = 1200   # 20-minute halves
OT_SECS_PER_PERIOD = 300


class Command(BaseCommand):
    help = "Read-only data integrity audit for the NCAA BPR pipeline (checks A1-A12)."

    def add_arguments(self, parser):
        parser.add_argument("--seasons", nargs="+", type=int, required=True)
        parser.add_argument("--check", type=str, default=None,
                            help="Run a single check (e.g. A2). Default: all.")
        parser.add_argument("--out-dir", type=str,
                            default="backtest_output/bpr_audit",
                            help="Output dir relative to backend/ (CSVs + summary JSON)")

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
                except Exception as exc:  # keep the battery running
                    res = {"check": check, "season": season,
                           "status": "ERROR", "metrics": {"error": str(exc)}}
                if res is None:
                    continue
                results.append(res)
                self.stdout.write(
                    f"  {season}: {res['status']}  "
                    + "  ".join(f"{k}={v}" for k, v in list(res["metrics"].items())[:6])
                )

        summary_path = out_dir / "audit_summary.json"
        with open(summary_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        self.stdout.write(self.style.SUCCESS(f"\nSummary written to {summary_path}"))

        n_fail = sum(1 for r in results if r["status"] == "FAIL")
        n_warn = sum(1 for r in results if r["status"] == "WARN")
        n_err = sum(1 for r in results if r["status"] == "ERROR")
        self.stdout.write(
            f"Totals: {len(results)} results — "
            f"{n_fail} FAIL, {n_warn} WARN, {n_err} ERROR"
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _game_clock_secs(period_count: int) -> int:
        ot = max(0, (period_count or 2) - 2)
        return 2 * REGULATION_SECS_PER_PERIOD + ot * OT_SECS_PER_PERIOD

    @staticmethod
    def _write_csv(path: Path, rows: list[dict]) -> None:
        if not rows:
            return
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    @staticmethod
    def _load_game_meta(season: int) -> dict[int, dict]:
        from ncaa.models import Game
        return {
            g["id"]: g
            for g in Game.objects.filter(
                season_year=season, status="final"
            ).values("id", "period_count", "went_to_ot", "neutral_site",
                     "home_team_id", "away_team_id", "home_score", "away_score",
                     "game_date")
        }

    # ── A1: stint minute coverage ─────────────────────────────────────────────

    def check_a1(self, season: int, out_dir: Path) -> dict:
        from ncaa.models import PlayerGameStint, PlayerGameStats

        games = self._load_game_meta(season)
        if not games:
            return {"check": "A1", "season": season, "status": "WARN",
                    "metrics": {"note": "no final games"}}

        stint_secs: dict[int, int] = defaultdict(int)
        for row in (PlayerGameStint.objects
                    .filter(game__season_year=season)
                    .values_list("game_id", "secs_on")):
            stint_secs[row[0]] += row[1]

        box_secs: dict[int, float] = defaultdict(float)
        for row in (PlayerGameStats.objects
                    .filter(game__season_year=season, did_not_play=False)
                    .values_list("game_id", "minutes")):
            box_secs[row[0]] += (row[1] or 0.0) * 60.0

        rows, stint_ratios, box_ratios = [], [], []
        for gid, g in games.items():
            expected = 10 * self._game_clock_secs(g["period_count"])
            s_ratio = stint_secs.get(gid, 0) / expected if expected else 0.0
            b_ratio = box_secs.get(gid, 0.0) / expected if expected else 0.0
            if gid in stint_secs:
                stint_ratios.append(s_ratio)
            if gid in box_secs:
                box_ratios.append(b_ratio)
            rows.append({"game_id": gid, "date": g["game_date"],
                         "expected_secs": expected,
                         "stint_secs": stint_secs.get(gid, 0),
                         "stint_ratio": round(s_ratio, 4),
                         "box_secs": round(box_secs.get(gid, 0.0)),
                         "box_ratio": round(b_ratio, 4)})

        self._write_csv(out_dir / f"a1_stint_coverage_{season}.csv", rows)

        med = statistics.median(stint_ratios) if stint_ratios else 0.0
        pct_with_stints = len(stint_ratios) / len(games)
        status = "PASS" if med >= 0.95 else ("WARN" if med >= 0.85 else "FAIL")
        # Coverage of the schedule matters too: many games with zero stints
        # is its own failure mode even if covered games look perfect.
        if pct_with_stints < 0.80 and status == "PASS":
            status = "WARN"
        return {"check": "A1", "season": season, "status": status,
                "metrics": {
                    "n_games": len(games),
                    "pct_games_with_stints": round(pct_with_stints, 3),
                    "median_stint_ratio": round(med, 3),
                    "median_box_ratio": round(statistics.median(box_ratios), 3) if box_ratios else None,
                }}

    # ── A2: duplicate / overlapping stints ────────────────────────────────────

    def check_a2(self, season: int, out_dir: Path) -> dict:
        from ncaa.models import PlayerGameStint

        qs = (PlayerGameStint.objects
              .filter(game__season_year=season)
              .values_list("player_id", "game_id", "period",
                           "clock_start_secs", "clock_end_secs", "secs_on"))

        by_player_game: dict[tuple, list] = defaultdict(list)
        exact_seen: set = set()
        n_exact_dupes = 0
        total_secs = 0
        for pid, gid, period, cs, ce, secs in qs.iterator(chunk_size=50000):
            key = (pid, gid, period, cs, ce)
            if key in exact_seen:
                n_exact_dupes += 1
            else:
                exact_seen.add(key)
            by_player_game[(pid, gid, period)].append((cs, ce))
            total_secs += secs

        # Interval-overlap sweep per (player, game, period).
        # Clock counts DOWN: start > end. Overlap between two stints
        # [e1,s1], [e2,s2] = max(0, min(s1,s2) - max(e1,e2)).
        overlap_secs = 0
        overlap_examples = []
        for key, intervals in by_player_game.items():
            if len(intervals) < 2:
                continue
            intervals.sort(key=lambda t: -t[0])
            for i in range(len(intervals) - 1):
                s1, e1 = intervals[i]
                s2, e2 = intervals[i + 1]
                ov = min(s1, s2) - max(e1, e2)
                if ov > 0:
                    overlap_secs += ov
                    if len(overlap_examples) < 200:
                        overlap_examples.append({
                            "player_id": key[0], "game_id": key[1],
                            "period": key[2],
                            "stint_a": f"{s1}-{e1}", "stint_b": f"{s2}-{e2}",
                            "overlap_secs": ov,
                        })

        self._write_csv(out_dir / f"a2_overlaps_{season}.csv", overlap_examples)
        overlap_frac = overlap_secs / total_secs if total_secs else 0.0
        status = "PASS" if (n_exact_dupes == 0 and overlap_frac < 0.001) else "FAIL"
        return {"check": "A2", "season": season, "status": status,
                "metrics": {
                    "n_stints": len(exact_seen) + n_exact_dupes,
                    "n_exact_dupes": n_exact_dupes,
                    "overlap_secs": overlap_secs,
                    "overlap_frac": round(overlap_frac, 6),
                }}

    # ── A3: lineup-size sweep ─────────────────────────────────────────────────

    def check_a3(self, season: int, out_dir: Path) -> dict:
        from ncaa.models import PlayerGameStint

        games = self._load_game_meta(season)

        # stints grouped per game: {game_id: {team_id: [(start, end)]}}
        game_stints: dict[int, dict[int, list]] = defaultdict(lambda: defaultdict(list))
        for gid, tid, period, cs, ce in (
            PlayerGameStint.objects
            .filter(game__season_year=season)
            .values_list("game_id", "team_id", "period",
                         "clock_start_secs", "clock_end_secs")
            .iterator(chunk_size=50000)
        ):
            game_stints[gid][tid].append((period, cs, ce))

        total_secs = 0
        clean_secs = 0
        per_game_rows = []
        for gid, teams in game_stints.items():
            g = games.get(gid)
            if g is None or len(teams) != 2:
                continue
            home_id, away_id = g["home_team_id"], g["away_team_id"]
            if home_id not in teams or away_id not in teams:
                continue
            periods = {p for t in teams.values() for (p, _, _) in t}
            g_total = 0
            g_clean = 0
            for period in periods:
                # breakpoints from both teams' stints in this period
                bps = set()
                for tid in (home_id, away_id):
                    for (p, cs, ce) in teams[tid]:
                        if p == period:
                            bps.add(cs)
                            bps.add(ce)
                bps = sorted(bps, reverse=True)
                for i in range(len(bps) - 1):
                    seg_s, seg_e = bps[i], bps[i + 1]
                    seg_len = seg_s - seg_e
                    if seg_len <= 0:
                        continue
                    counts = {}
                    for tid in (home_id, away_id):
                        counts[tid] = sum(
                            1 for (p, cs, ce) in teams[tid]
                            if p == period and cs >= seg_s and ce <= seg_e
                        )
                    g_total += seg_len
                    if counts[home_id] == 5 and counts[away_id] == 5:
                        g_clean += seg_len
            total_secs += g_total
            clean_secs += g_clean
            per_game_rows.append({
                "game_id": gid, "date": g["game_date"],
                "covered_secs": g_total, "clean_5v5_secs": g_clean,
                "clean_frac": round(g_clean / g_total, 4) if g_total else 0.0,
            })

        self._write_csv(out_dir / f"a3_lineup_sweep_{season}.csv", per_game_rows)
        clean_frac = clean_secs / total_secs if total_secs else 0.0
        status = "PASS" if clean_frac >= 0.70 else "WARN"
        return {"check": "A3", "season": season, "status": status,
                "metrics": {"n_games_swept": len(per_game_rows),
                            "clean_5v5_frac": round(clean_frac, 4)}}

    # ── A4: possession sanity ─────────────────────────────────────────────────

    def check_a4(self, season: int, out_dir: Path) -> dict:
        from django.db.models import Sum
        from ncaa.models import PlayerGameStint, PlayerGameStats

        # Stint side: each team box event is recorded once per on-court player
        # (5 with a clean lineup), so /5 approximates the team total.
        stint_agg = (PlayerGameStint.objects
                     .filter(game__season_year=season)
                     .values("game_id", "team_id")
                     .annotate(fga=Sum("team_fga"), fta=Sum("team_fta"),
                               tov=Sum("team_tov"), oreb=Sum("team_oreb")))
        stint_poss = {}
        for r in stint_agg:
            poss = (r["fga"] + 0.44 * r["fta"] + r["tov"] - r["oreb"]) / 5.0
            stint_poss[(r["game_id"], r["team_id"])] = poss

        box_agg = (PlayerGameStats.objects
                   .filter(game__season_year=season)
                   .values("game_id", "team_id")
                   .annotate(fga=Sum("fg_attempted"), fta=Sum("ft_attempted"),
                             tov=Sum("turnovers"), oreb=Sum("offensive_rebounds")))
        rows, ratios = [], []
        n_flagged = 0
        for r in box_agg:
            key = (r["game_id"], r["team_id"])
            box_poss = r["fga"] + 0.44 * r["fta"] + r["tov"] - r["oreb"]
            sp = stint_poss.get(key)
            if sp is None or box_poss <= 10:
                continue
            ratio = sp / box_poss
            ratios.append(ratio)
            flagged = abs(ratio - 1.0) > 0.10
            n_flagged += flagged
            if flagged and len(rows) < 500:
                rows.append({"game_id": key[0], "team_id": key[1],
                             "stint_poss": round(sp, 1),
                             "box_poss": round(box_poss, 1),
                             "ratio": round(ratio, 3)})

        self._write_csv(out_dir / f"a4_poss_flagged_{season}.csv", rows)
        med = statistics.median(ratios) if ratios else 0.0
        status = "PASS" if 0.95 <= med <= 1.05 else ("WARN" if 0.85 <= med <= 1.15 else "FAIL")
        return {"check": "A4", "season": season, "status": status,
                "metrics": {"n_game_teams": len(ratios),
                            "median_ratio": round(med, 3),
                            "pct_flagged": round(n_flagged / len(ratios), 3) if ratios else None}}

    # ── A5: FGA coverage ──────────────────────────────────────────────────────

    def check_a5(self, season: int, out_dir: Path) -> dict:
        from ncaa.models import PlayerGameStint

        total = PlayerGameStint.objects.filter(game__season_year=season).count()
        if total == 0:
            return {"check": "A5", "season": season, "status": "WARN",
                    "metrics": {"n_stints": 0}}
        with_fga = PlayerGameStint.objects.filter(
            game__season_year=season, team_fga__gt=0).count()
        cov = with_fga / total
        passes_gate = cov >= 0.50
        return {"check": "A5", "season": season,
                "status": "PASS" if passes_gate else "WARN",
                "metrics": {"n_stints": total,
                            "fga_coverage": round(cov, 3),
                            "passes_datasets_gate": passes_gate}}

    # ── A6: through-date builder consistency ─────────────────────────────────

    def check_a6(self, season: int, out_dir: Path) -> dict:
        import datetime
        from ncaa.analytics.player_value.bpr.datasets import (
            build_rapm_dataset, build_rapm_dataset_through_date,
        )

        full = build_rapm_dataset([season], verbose=False)
        cutoff = datetime.date(season, 6, 30)  # after any season-Y game
        bounded = build_rapm_dataset_through_date(season, cutoff, verbose=False)

        full_n = full["n_observations"]
        bnd_n = bounded["n_observations"]
        full_poss = sum(o["home_poss"] + o["away_poss"] for o in full["observations"])
        bnd_poss = sum(o["home_poss"] + o["away_poss"] for o in bounded["observations"])
        full_players = set(full["player_season_index"].keys())
        bnd_players = set(bounded["player_season_index"].keys())

        match = (full_n == bnd_n
                 and abs(full_poss - bnd_poss) < 1.0
                 and full_players == bnd_players)
        return {"check": "A6", "season": season,
                "status": "PASS" if match else "FAIL",
                "metrics": {
                    "full_obs": full_n, "bounded_obs": bnd_n,
                    "full_poss": round(full_poss), "bounded_poss": round(bnd_poss),
                    "player_cols_match": full_players == bnd_players,
                }}

    # ── A7: mid-season transfers ──────────────────────────────────────────────

    def check_a7(self, season: int, out_dir: Path) -> dict:
        from ncaa.models import PlayerGameStats, PlayerGameStint

        team_by_pg: dict[int, set] = defaultdict(set)
        for pid, tid in (PlayerGameStats.objects
                         .filter(game__season_year=season, did_not_play=False,
                                 team__isnull=False)
                         .values_list("player_id", "team_id")):
            team_by_pg[pid].add(tid)
        multi = {pid: tids for pid, tids in team_by_pg.items() if len(tids) > 1}

        # For multi-team players, verify each stint's team matches a team the
        # player actually logged box-score games for.
        n_bad_stints = 0
        rows = []
        if multi:
            for pid, gid, tid in (PlayerGameStint.objects
                                  .filter(game__season_year=season,
                                          player_id__in=list(multi))
                                  .values_list("player_id", "game_id", "team_id")):
                if tid is not None and tid not in multi[pid]:
                    n_bad_stints += 1
                    if len(rows) < 200:
                        rows.append({"player_id": pid, "game_id": gid,
                                     "stint_team_id": tid,
                                     "valid_team_ids": sorted(multi[pid])})
        self._write_csv(out_dir / f"a7_transfer_stints_{season}.csv", rows)
        return {"check": "A7", "season": season,
                "status": "FAIL" if n_bad_stints else "PASS",
                "metrics": {"n_multi_team_players": len(multi),
                            "n_misattributed_stints": n_bad_stints}}

    # ── A8: OT / neutral handling ─────────────────────────────────────────────

    def check_a8(self, season: int, out_dir: Path) -> dict:
        from ncaa.models import Game

        qs = Game.objects.filter(season_year=season, status="final")
        n = qs.count()
        n_ot = qs.filter(went_to_ot=True).count()
        n_neutral = qs.filter(neutral_site=True).count()
        n_ot_mismatch = qs.filter(went_to_ot=True, period_count__lte=2).count()
        return {"check": "A8", "season": season,
                "status": "PASS" if n_ot_mismatch == 0 else "WARN",
                "metrics": {"n_final_games": n, "n_ot": n_ot,
                            "n_neutral": n_neutral,
                            "ot_flag_period_mismatch": n_ot_mismatch}}

    # ── A9: freshman recruiting coverage ──────────────────────────────────────

    def check_a9(self, season: int, out_dir: Path) -> dict:
        from ncaa.models import PlayerSeasonProjection, PlayerRecruitingProfile

        newcomers = set(
            PlayerSeasonProjection.objects
            .filter(projected_season_year=season, recruitment_type="newcomer")
            .values_list("player_id", flat=True)
        )
        if not newcomers:
            return {"check": "A9", "season": season, "status": "WARN",
                    "metrics": {"n_newcomers": 0, "note": "no projections"}}
        with_profile = set(
            PlayerRecruitingProfile.objects
            .filter(class_year=season, player_id__in=newcomers)
            .values_list("player_id", flat=True)
        )
        cov = len(with_profile) / len(newcomers)
        return {"check": "A9", "season": season,
                "status": "PASS" if cov >= 0.60 else "WARN",
                "metrics": {"n_newcomers": len(newcomers),
                            "n_with_profile": len(with_profile),
                            "coverage": round(cov, 3)}}

    # ── A10: Evan Miya fuzzy-match audit ──────────────────────────────────────

    def check_a10(self, season: int, out_dir: Path) -> dict:
        import difflib
        import re
        import unicodedata
        from ncaa.models import PlayerSeasonStats
        from ncaa.analytics.player_value.bpr.evan_miya_reference import (
            RAW_DATA, parse_em_text, normalize_team_name,
        )

        if season not in RAW_DATA:
            return {"check": "A10", "season": season, "status": "WARN",
                    "metrics": {"note": "no EM data for season"}}

        def _norm(s: str) -> str:
            s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
            return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()

        em_records = parse_em_text(RAW_DATA[season])
        db = list(PlayerSeasonStats.objects
                  .filter(season__year=season, mpg__gte=8.0, gp__gte=5)
                  .values("player_id", "player__display_name", "team__name"))
        name_lookup: dict[str, list] = defaultdict(list)
        for r in db:
            name_lookup[_norm(r["player__display_name"])].append(r)
        name_keys = list(name_lookup.keys())

        n_matched = 0
        accepted = []
        for em in em_records:
            em_n = _norm(em["name"])
            cands = difflib.get_close_matches(em_n, name_keys, n=3, cutoff=0.65)
            best, best_score = None, 0.0
            for ck in cands:
                for rec in name_lookup[ck]:
                    ns = difflib.SequenceMatcher(None, em_n, ck).ratio()
                    ts = difflib.SequenceMatcher(
                        None, _norm(normalize_team_name(em["team"])),
                        _norm(rec["team__name"] or "")).ratio()
                    score = ns * 0.65 + ts * 0.35
                    if score > best_score:
                        best_score, best = score, rec
            if best is not None and best_score >= 0.58:
                n_matched += 1
                accepted.append({"em_name": em["name"], "em_team": em["team"],
                                 "db_name": best["player__display_name"],
                                 "db_team": best["team__name"],
                                 "score": round(best_score, 3)})

        accepted.sort(key=lambda r: r["score"])
        self._write_csv(out_dir / f"a10_em_worst_matches_{season}.csv", accepted[:50])
        rate = n_matched / len(em_records) if em_records else 0.0
        return {"check": "A10", "season": season,
                "status": "PASS" if rate >= 0.85 else "WARN",
                "metrics": {"n_em_records": len(em_records),
                            "n_matched": n_matched,
                            "match_rate": round(rate, 3),
                            "worst_accepted_score": accepted[0]["score"] if accepted else None}}

    # ── A11: BPR distribution / provenance by poss bucket ────────────────────

    def check_a11(self, season: int, out_dir: Path) -> dict:
        from ncaa.models import PlayerSeasonStats

        qs = (PlayerSeasonStats.objects
              .filter(season__year=season, bpr__isnull=False)
              .values("bpr", "off_poss", "bpr_source"))
        buckets = {"lt200": [], "200_400": [], "400_800": [], "800plus": []}
        src_by_bucket: dict[str, dict] = defaultdict(lambda: defaultdict(int))
        for r in qs:
            p = r["off_poss"] or 0.0
            b = ("lt200" if p < 200 else
                 "200_400" if p < 400 else
                 "400_800" if p < 800 else "800plus")
            buckets[b].append(r["bpr"])
            src_by_bucket[b][r["bpr_source"] or "null"] += 1

        all_sources = sorted({s for d in src_by_bucket.values() for s in d})
        rows = []
        for b, vals in buckets.items():
            if not vals:
                continue
            rows.append({
                "bucket": b, "n": len(vals),
                "mean": round(statistics.mean(vals), 3),
                "std": round(statistics.pstdev(vals), 3),
                "n_extreme_abs8": sum(1 for v in vals if abs(v) > 8),
                **{f"src_{s}": src_by_bucket[b].get(s, 0) for s in all_sources},
            })
        self._write_csv(out_dir / f"a11_bpr_buckets_{season}.csv", rows)
        low = buckets["200_400"]
        n_extreme_low = sum(1 for v in low if abs(v) > 8)
        return {"check": "A11", "season": season, "status": "PASS",
                "metrics": {"n_with_bpr": sum(len(v) for v in buckets.values()),
                            "extreme_in_200_400": n_extreme_low,
                            "extreme_frac_200_400": round(n_extreme_low / len(low), 4) if low else None}}

    # ── A12: garbage-time share proxy ─────────────────────────────────────────

    def check_a12(self, season: int, out_dir: Path) -> dict:
        from ncaa.models import PlayerGameStint

        games = self._load_game_meta(season)
        blowouts = {gid for gid, g in games.items()
                    if g["home_score"] is not None and g["away_score"] is not None
                    and abs(g["home_score"] - g["away_score"]) >= 25}

        total_secs = 0
        gt_secs = 0
        for gid, period, secs in (PlayerGameStint.objects
                                  .filter(game__season_year=season)
                                  .values_list("game_id", "period", "secs_on")
                                  .iterator(chunk_size=50000)):
            total_secs += secs
            if gid in blowouts and period >= 2:
                gt_secs += secs

        frac = gt_secs / total_secs if total_secs else 0.0
        return {"check": "A12", "season": season, "status": "PASS",
                "metrics": {"n_blowout_games": len(blowouts),
                            "blowout_2h_stint_frac": round(frac, 4)}}
