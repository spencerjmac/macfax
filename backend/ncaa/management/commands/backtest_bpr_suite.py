"""
Management command: backtest_bpr_suite

Unified, leak-free NCAA BPR backtesting (mission Phase 4 deliverable).
Supersedes backtest_bpr_walkforward for within-season claims — that command
leaks full-season box features and team ratings (see
docs/bpr_audit/03_weakness_report.md items 3.1/3.2).

Modes:
  cross-season  Season Y ratings → season Y+1 game margins.
                OLS calibration fit on season Y games only (fully pre-Y+1).
  rolling       Within-season, rolling-origin. Per cutoff: recompute BPR
                in-memory with date-bounded RAPM data AND date-bounded
                box/team features (through_date.py overrides), fit OLS on
                games <= cutoff, predict the next window.
  player        Player-level validation: YoY stability by possession bucket,
                current BPR → next-season on-court net, preseason prior
                calibration by recruitment type.

Arms: bpr, box_bpr, baseline (RAPM-only), adj_em, home_only, plus an
optional experiment arm via --extra-ratings-json {player_id: bpr}.

All outputs land in backtest_output/bpr_suite/ncaa/<run-name>/ ;
nothing is written to the database (all pipeline runs use persist=False).

Usage:
  python manage.py backtest_bpr_suite --mode cross-season --seasons 2022 2023 2024
  python manage.py backtest_bpr_suite --mode rolling --seasons 2026 \\
      --cutoffs 12-01 01-15 02-15 --run-name rolling_2026_v16
  python manage.py backtest_bpr_suite --mode player --seasons 2022 2023 2024 2026
"""

from __future__ import annotations

import csv
import datetime
import json
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np
from django.core.management.base import BaseCommand, CommandError

from ncaa.analytics.player_value.bpr.constants import BPR_MODEL_VERSION
from ncaa.analytics.player_value.bpr import backtest_lib as lib

ARMS = ["bpr", "box_bpr", "baseline", "adj_em", "home_only"]


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:
        return "unknown"


def _parse_cutoff(mmdd: str, season_year: int) -> datetime.date:
    """'12-01' in season 2026 → 2025-12-01; '01-15' → 2026-01-15."""
    month, day = (int(x) for x in mmdd.split("-"))
    year = season_year - 1 if month >= 8 else season_year
    return datetime.date(year, month, day)


class Command(BaseCommand):
    help = "Unified leak-free NCAA BPR backtest suite (cross-season / rolling / player)."

    def add_arguments(self, parser):
        parser.add_argument("--mode", choices=["cross-season", "rolling", "player"],
                            required=True)
        parser.add_argument("--seasons", nargs="+", type=int, required=True,
                            help="cross-season: source seasons Y (predicts Y+1). "
                                 "rolling/player: target seasons.")
        parser.add_argument("--cutoffs", nargs="+", type=str,
                            default=["12-01", "01-15", "02-15"],
                            help="MM-DD cutoffs for rolling mode")
        parser.add_argument("--horizon", choices=["window", "full"], default="window",
                            help="rolling: predict to next cutoff (window) or season end (full)")
        parser.add_argument("--min-poss", type=int, default=150)
        parser.add_argument("--run-name", type=str, default=None)
        parser.add_argument("--extra-ratings-json", type=str, default=None,
                            help="JSON {player_id: bpr} or {player_id: {bpr, box_bpr}} "
                                 "added as arm 'extra' (experiment hook)")
        parser.add_argument("--rapm-window", type=int, default=1,
                            help="rolling: RAPM season pool size (cutoff mode is "
                                 "single-season; kept for cross-season recompute experiments)")
        parser.add_argument("--truthful-targets", action="store_true", default=False,
                            help="rolling: pass truthful_targets=True to the pipeline "
                                 "(exclude pre-2025 placeholder RAPM from targets/priors)")
        parser.add_argument("--smooth-k", type=float, default=None,
                            help="rolling: add a smooth-reliability arm blending "
                                 "rel*RAPM+(1-rel)*box with rel=poss/(poss+k), "
                                 "computed per-cutoff from in-memory components "
                                 "(experiment N-A)")

    # ── entry ────────────────────────────────────────────────────────────────

    def handle(self, *args, **opts):
        mode = opts["mode"]
        run_name = opts["run_name"] or (
            f"{mode}_{datetime.datetime.now():%Y%m%d_%H%M%S}")
        out_dir = Path("backtest_output/bpr_suite/ncaa") / run_name
        out_dir.mkdir(parents=True, exist_ok=True)

        extra_ratings = None
        if opts["extra_ratings_json"]:
            with open(opts["extra_ratings_json"]) as f:
                raw = json.load(f)
            extra_ratings = {
                int(pid): (v["bpr"] if isinstance(v, dict) else float(v))
                for pid, v in raw.items()
            }

        manifest = {
            "mode": mode, "args": {k: v for k, v in opts.items()
                                   if k not in ("stdout", "stderr")},
            "bpr_model_version": BPR_MODEL_VERSION,
            "git_sha": _git_sha(),
            "started": datetime.datetime.now().isoformat(),
            "notes": [],
        }

        if mode == "cross-season":
            self._run_cross_season(opts, out_dir, manifest, extra_ratings)
        elif mode == "rolling":
            self._run_rolling(opts, out_dir, manifest, extra_ratings)
        else:
            self._run_player(opts, out_dir, manifest)

        manifest["finished"] = datetime.datetime.now().isoformat()
        with open(out_dir / "manifest.json", "w") as f:
            json.dump(manifest, f, indent=2, default=str)
        self.stdout.write(self.style.SUCCESS(f"\nOutputs in {out_dir}"))

    # ── shared output helpers ────────────────────────────────────────────────

    @staticmethod
    def _write_csv(path: Path, rows: list[dict]) -> None:
        if not rows:
            return
        keys: list[str] = []
        for r in rows:
            for k in r:
                if k not in keys:
                    keys.append(k)
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)

    def _summarize(self, results_by_arm: dict, games_meta: dict,
                   context: dict, summary_rows: list, calib_rows: list,
                   game_rows: list, conf_by_team: dict, high_major: set) -> None:
        """Compute overall + split metrics for each arm and append output rows."""
        for arm, results in results_by_arm.items():
            if not results:
                continue
            # per-game rows
            for r in results:
                g = games_meta[r["game_id"]]
                splits = lib.tag_game_splits(g, conf_by_team, high_major)
                game_rows.append({**context, "arm": arm, **r, **splits})

            groups: dict[str, list] = {"all": results}
            for r in results:
                g = games_meta[r["game_id"]]
                s = lib.tag_game_splits(g, conf_by_team, high_major)
                for label in (s["site"], s["conf"], s["tier"]):
                    groups.setdefault(label, []).append(r)

            for split, rs in groups.items():
                m = lib.compute_metrics(rs)
                if m:
                    summary_rows.append({**context, "arm": arm, "split": split, **m})

            for row in lib.calibration_table(results):
                calib_rows.append({**context, "arm": arm, **row})

    # ── cross-season mode ────────────────────────────────────────────────────

    def _run_cross_season(self, opts, out_dir, manifest, extra_ratings):
        seasons = sorted(opts["seasons"])
        min_poss = opts["min_poss"]
        all_years = sorted(set(seasons) | {y + 1 for y in seasons})

        player_ratings, team_roster = lib.load_stored_player_ratings(all_years)
        adj_em_map = lib.load_stored_adj_em(all_years)
        games_by_year = lib.load_games(all_years)

        if extra_ratings:
            for (pid, yr), pr in player_ratings.items():
                pr["extra"] = extra_ratings.get(pid)

        summary_rows, calib_rows, game_rows = [], [], []

        for y in seasons:
            test_year = y + 1
            train_games = games_by_year.get(y, [])
            test_games = games_by_year.get(test_year, [])
            if not train_games or not test_games:
                manifest["notes"].append(
                    f"skip {y}->{test_year}: {len(train_games)} train / "
                    f"{len(test_games)} test games")
                continue
            n_rated = sum(1 for (pid, yr), pr in player_ratings.items()
                          if yr == y and pr["bpr"] is not None)
            if n_rated < 500:
                manifest["notes"].append(
                    f"skip {y}->{test_year}: only {n_rated} rated players in {y} "
                    f"(2025 BPR gap — see data integrity report)")
                continue

            conf_by_team, high_major = lib.load_conference_maps(test_year)
            games_meta = {g["id"]: g for g in test_games}
            self.stdout.write(f"\n=== {y} ratings → {test_year} games "
                              f"({len(test_games)} games) ===")

            arms = list(ARMS) + (["extra"] if extra_ratings else [])
            results_by_arm = {}
            for arm in arms:
                predictor = "bpr" if arm == "extra" else arm
                ratings = player_ratings
                if arm == "extra":
                    ratings = {
                        k: {**v, "bpr": v.get("extra")}
                        for k, v in player_ratings.items()
                    }
                # OLS fit on season-Y games with season-Y ratings/rosters:
                # every input predates the evaluated season.
                betas = lib._fit_ols(train_games, predictor, y,
                                     ratings, team_roster, adj_em_map, min_poss)
                results = lib.evaluate_arm(
                    test_games, predictor, y, test_year,
                    ratings, team_roster, adj_em_map, min_poss, betas)
                results_by_arm[arm] = results
                m = lib.compute_metrics(results)
                self.stdout.write(
                    f"  {arm:16s} rmse={m['rmse']:.2f} mae={m['mae']:.2f} "
                    f"acc={m['win_acc']:.3f} brier={m['brier']:.3f} "
                    f"logloss={m['log_loss']:.3f} auc={m['auc']:.3f} "
                    f"cov={m['mean_cov']:.2f}")

            combo_betas = lib.fit_ols_combo(
                train_games, y, player_ratings, team_roster, adj_em_map, min_poss)
            results_by_arm["adj_em_plus_bpr"] = lib.evaluate_combo_arm(
                test_games, y, test_year, player_ratings, team_roster,
                adj_em_map, min_poss, combo_betas)
            m = lib.compute_metrics(results_by_arm["adj_em_plus_bpr"])
            self.stdout.write(
                f"  {'adj_em_plus_bpr':16s} rmse={m['rmse']:.2f} mae={m['mae']:.2f} "
                f"acc={m['win_acc']:.3f} brier={m['brier']:.3f} "
                f"logloss={m['log_loss']:.3f} auc={m['auc']:.3f} "
                f"| beta_em={combo_betas[1]:.3f} beta_bpr={combo_betas[2]:.3f}")

            self._summarize(results_by_arm, games_meta,
                            {"mode": "cross-season", "source_season": y,
                             "target_season": test_year, "cutoff": ""},
                            summary_rows, calib_rows, game_rows,
                            conf_by_team, high_major)

        self._write_csv(out_dir / "summary.csv", summary_rows)
        self._write_csv(out_dir / "calibration.csv", calib_rows)
        self._write_csv(out_dir / "games.csv", game_rows)

    # ── rolling mode ─────────────────────────────────────────────────────────

    def _run_rolling(self, opts, out_dir, manifest, extra_ratings):
        from ncaa.analytics.player_value.bpr.pipeline import run_bpr_season
        from ncaa.analytics.player_value.bpr.through_date import (
            build_team_adj_em_through_date,
            build_opp_quality_map_through_date,
            build_pss_features_through_date,
            build_rosters_through_date,
        )

        seasons = sorted(opts["seasons"])
        min_poss = opts["min_poss"]
        horizon = opts["horizon"]
        games_by_year = lib.load_games(seasons)

        summary_rows, calib_rows, game_rows = [], [], []

        for season in seasons:
            season_games = games_by_year.get(season, [])
            if not season_games:
                manifest["notes"].append(f"skip {season}: no games")
                continue
            cutoffs = sorted(_parse_cutoff(c, season) for c in opts["cutoffs"])
            season_end = max(g["game_date"] for g in season_games)
            conf_by_team, high_major = lib.load_conference_maps(season)
            games_meta = {g["id"]: g for g in season_games}

            for i, cutoff in enumerate(cutoffs):
                window_end = (cutoffs[i + 1] if (horizon == "window"
                                                 and i + 1 < len(cutoffs))
                              else season_end)
                train_games = [g for g in season_games if g["game_date"] <= cutoff]
                test_games = [g for g in season_games
                              if cutoff < g["game_date"] <= window_end]
                if len(train_games) < 300 or len(test_games) < 100:
                    manifest["notes"].append(
                        f"skip {season}@{cutoff}: {len(train_games)} train / "
                        f"{len(test_games)} test")
                    continue

                self.stdout.write(
                    f"\n=== {season} @ cutoff {cutoff} "
                    f"(train {len(train_games)}, test {len(test_games)} "
                    f"through {window_end}) ===")

                # Leak-free through-date inputs
                team_maps = build_team_adj_em_through_date(season, cutoff)
                adj_em_td = team_maps[0]
                opp_q = build_opp_quality_map_through_date(
                    season, cutoff, adj_em_map=adj_em_td)
                pss_td = build_pss_features_through_date(
                    season, cutoff, team_maps=team_maps)

                self.stdout.write("  running BPR pipeline (persist=False, "
                                  "date-bounded RAPM + features)...")
                summary = run_bpr_season(
                    season,
                    cutoff_date=cutoff,
                    persist=False,
                    verbose=False,
                    player_season_stats_override=pss_td,
                    opp_quality_map_override=opp_q,
                    team_adj_em_map_override=adj_em_td,
                    truthful_targets=opts.get("truthful_targets", False),
                )
                bpr_map = summary.get("player_bpr_map") or {}
                self.stdout.write(f"  in-memory ratings: {len(bpr_map)} players")

                player_ratings = {
                    (pid, season): {
                        "bpr": v["bpr"],
                        "box_bpr": v["box_bpr"],
                        # _team_strength 'baseline' arm reads obpr+dbpr parts:
                        "baseline_obpr": v.get("baseline_bpr"),
                        "baseline_dbpr": 0.0 if v.get("baseline_bpr") is not None else None,
                        "off_poss": v["off_poss"] or 0.0,
                        "extra": (extra_ratings or {}).get(pid),
                    }
                    for pid, v in bpr_map.items()
                }
                rosters_td = build_rosters_through_date(season, cutoff)
                team_roster = {
                    (tid, season): players for tid, players in rosters_td.items()
                }
                adj_em_keyed = {(tid, season): em for tid, em in adj_em_td.items()}

                arms = list(ARMS) + (["extra"] if extra_ratings else [])
                results_by_arm = {}
                for arm in arms:
                    predictor = "bpr" if arm == "extra" else arm
                    ratings = player_ratings
                    if arm == "extra":
                        ratings = {k: {**v, "bpr": v.get("extra")}
                                   for k, v in player_ratings.items()}
                    betas = lib._fit_ols(train_games, predictor, season,
                                         ratings, team_roster, adj_em_keyed,
                                         min_poss)
                    results = lib.evaluate_arm(
                        test_games, predictor, season, season,
                        ratings, team_roster, adj_em_keyed, min_poss, betas)
                    results_by_arm[arm] = results
                    m = lib.compute_metrics(results)
                    self.stdout.write(
                        f"  {arm:16s} rmse={m['rmse']:.2f} mae={m['mae']:.2f} "
                        f"acc={m['win_acc']:.3f} brier={m['brier']:.3f} "
                        f"logloss={m['log_loss']:.3f} auc={m['auc']:.3f} "
                        f"cov={m['mean_cov']:.2f}")

                if opts.get("smooth_k"):
                    k = opts["smooth_k"]
                    smooth_ratings = {}
                    for key, v in player_ratings.items():
                        rapm, box = v["bpr"], v["box_bpr"]
                        poss = v["off_poss"] or 0.0
                        if rapm is None and box is None:
                            val = None
                        elif rapm is None:
                            val = box
                        elif box is None:
                            val = rapm
                        else:
                            rel = poss / (poss + k)
                            val = rel * rapm + (1 - rel) * box
                        smooth_ratings[key] = {**v, "bpr": val}
                    betas = lib._fit_ols(train_games, "bpr", season,
                                         smooth_ratings, team_roster,
                                         adj_em_keyed, min_poss)
                    results = lib.evaluate_arm(
                        test_games, "bpr", season, season,
                        smooth_ratings, team_roster, adj_em_keyed,
                        min_poss, betas)
                    results_by_arm[f"smooth_k{int(k)}"] = results
                    m = lib.compute_metrics(results)
                    self.stdout.write(
                        f"  {f'smooth_k{int(k)}':16s} rmse={m['rmse']:.2f} "
                        f"mae={m['mae']:.2f} acc={m['win_acc']:.3f} "
                        f"brier={m['brier']:.3f} logloss={m['log_loss']:.3f} "
                        f"auc={m['auc']:.3f} cov={m['mean_cov']:.2f}")

                combo_betas = lib.fit_ols_combo(
                    train_games, season, player_ratings, team_roster,
                    adj_em_keyed, min_poss)
                results_by_arm["adj_em_plus_bpr"] = lib.evaluate_combo_arm(
                    test_games, season, season, player_ratings, team_roster,
                    adj_em_keyed, min_poss, combo_betas)
                m = lib.compute_metrics(results_by_arm["adj_em_plus_bpr"])
                self.stdout.write(
                    f"  {'adj_em_plus_bpr':16s} rmse={m['rmse']:.2f} "
                    f"mae={m['mae']:.2f} acc={m['win_acc']:.3f} "
                    f"brier={m['brier']:.3f} logloss={m['log_loss']:.3f} "
                    f"auc={m['auc']:.3f} | beta_em={combo_betas[1]:.3f} "
                    f"beta_bpr={combo_betas[2]:.3f}")

                self._summarize(results_by_arm, games_meta,
                                {"mode": "rolling", "source_season": season,
                                 "target_season": season,
                                 "cutoff": cutoff.isoformat()},
                                summary_rows, calib_rows, game_rows,
                                conf_by_team, high_major)

        self._write_csv(out_dir / "summary.csv", summary_rows)
        self._write_csv(out_dir / "calibration.csv", calib_rows)
        self._write_csv(out_dir / "games.csv", game_rows)

    # ── player mode ──────────────────────────────────────────────────────────

    def _run_player(self, opts, out_dir, manifest):
        from ncaa.models import PlayerSeasonStats, PlayerSeasonProjection

        seasons = sorted(opts["seasons"])
        rows_out: list[dict] = []

        pss = defaultdict(dict)   # year -> pid -> row
        for r in PlayerSeasonStats.objects.filter(
            season__year__in=sorted(set(seasons) | {y + 1 for y in seasons}),
        ).values("player_id", "season__year", "bpr", "box_bpr", "off_poss",
                 "on_court_adj_em", "preseason_obpr", "preseason_dbpr", "mpg"):
            pss[r["season__year"]][r["player_id"]] = r

        def _pearson(pairs):
            if len(pairs) < 10:
                return None
            a = np.array([p[0] for p in pairs], dtype=float)
            b = np.array([p[1] for p in pairs], dtype=float)
            if a.std() == 0 or b.std() == 0:
                return None
            return float(np.corrcoef(a, b)[0, 1])

        POSS_BUCKETS = [(200, 400), (400, 800), (800, 10 ** 9)]

        for y in seasons:
            cur, nxt = pss.get(y, {}), pss.get(y + 1, {})
            if not cur or not nxt:
                manifest["notes"].append(f"player mode: skip {y}->{y+1} (missing data)")
                continue

            # (a) YoY BPR stability by possession bucket
            for lo, hi in POSS_BUCKETS:
                pairs = [(c["bpr"], nxt[pid]["bpr"])
                         for pid, c in cur.items()
                         if c["bpr"] is not None and lo <= (c["off_poss"] or 0) < hi
                         and pid in nxt and nxt[pid]["bpr"] is not None]
                r = _pearson(pairs)
                rows_out.append({"check": "yoy_bpr_r", "season": y,
                                 "group": f"poss_{lo}_{hi if hi < 10**9 else 'plus'}",
                                 "n": len(pairs), "value": round(r, 4) if r else None})

            # (b) BPR(Y) → next-season on-court adjusted net
            pairs = [(c["bpr"], nxt[pid]["on_court_adj_em"])
                     for pid, c in cur.items()
                     if c["bpr"] is not None and (c["off_poss"] or 0) >= 200
                     and pid in nxt and nxt[pid]["on_court_adj_em"] is not None]
            r = _pearson(pairs)
            rows_out.append({"check": "bpr_to_next_oncourt_r", "season": y,
                             "group": "poss_200_plus", "n": len(pairs),
                             "value": round(r, 4) if r else None})

            # (c) preseason prior calibration by recruitment type (season y+1)
            rec_type = dict(PlayerSeasonProjection.objects.filter(
                projected_season_year=y + 1,
            ).values_list("player_id", "recruitment_type"))
            for rtype in ("returner", "transfer", "newcomer"):
                diffs, pairs = [], []
                for pid, row in nxt.items():
                    if rec_type.get(pid) != rtype:
                        continue
                    if row["preseason_obpr"] is None or row["bpr"] is None:
                        continue
                    prior = (row["preseason_obpr"] or 0) + (row["preseason_dbpr"] or 0)
                    diffs.append(prior - row["bpr"])
                    pairs.append((prior, row["bpr"]))
                r = _pearson(pairs)
                rows_out.append({
                    "check": "preseason_prior_calibration",
                    "season": y + 1, "group": rtype, "n": len(diffs),
                    "value": round(r, 4) if r else None,
                    "bias": round(float(np.mean(diffs)), 3) if diffs else None,
                    "mae": round(float(np.mean(np.abs(diffs))), 3) if diffs else None,
                })

        for row in rows_out:
            self.stdout.write(str(row))
        self._write_csv(out_dir / "player_validation.csv", rows_out)
