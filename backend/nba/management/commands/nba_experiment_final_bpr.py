"""
Management command: nba_experiment_final_bpr

Non-destructive NBA final-BPR experiment harness (mission Step 7).
Recomputes final prior-informed RAPM IN MEMORY for one or more source
seasons under variant parameters, then forward-evaluates each variant —
nothing is written to the database.

Per variant × source season Y:
  player-forward  variant BPR(Y) vs stored baseline RAPM(Y+1)
                  (pure lineup on-court impact next season) and vs stored
                  final BPR(Y+1) as a secondary reference
  team-forward    minutes-weighted team aggregate of variant BPR(Y)
                  vs actual adj_net(Y+1): OLS slope, r, RMSE
  references      persistence (adj_net Y → Y+1) and the STORED production
                  BPR(Y) evaluated identically

Notes:
  - Uses stored box_bpr as the prior base (fixed input) — this harness
    isolates the final-stage knobs: LEBRON prior weight, LEBRON-adjusted
    lambda scale, lambda tier, recency half-life.
  - LEBRON_BLEND_W (Box BPR target blend) is NOT sweepable here; it needs a
    box_bpr recompute chain. Tracked separately.
  - Same-season LEBRON in the prior is legitimate for forward evaluation
    (all inputs predate the target season).

Usage:
  python manage.py nba_experiment_final_bpr --source-seasons 2022 2023 2024 2025 \\
      --lebron-prior-w 0.5 --lebron-lambda-scale 0.7 --tier A_conservative \\
      --run-name prior_w_050
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
import scipy.stats
from django.core.management.base import BaseCommand

from nba.analytics.rapm import fit_prior_informed_rapm
from nba.management.commands.nba_compute_final_bpr import (
    Command as FinalBprCommand,
    LAMBDA_TIERS,
    LEBRON_LAMBDA_CAP,
    _build_lambda_array,
    _load_lebron_priors,
)


class Command(BaseCommand):
    help = "In-memory NBA final-BPR variant experiments with forward evaluation (no DB writes)."

    def add_arguments(self, parser):
        parser.add_argument("--source-seasons", nargs="+", type=int, required=True,
                            help="Source seasons Y; each is evaluated against Y+1")
        parser.add_argument("--lebron-prior-w", type=float, default=0.5)
        parser.add_argument("--lebron-prior-def-w", type=float, default=None,
                            help="Defaults to --lebron-prior-w when omitted")
        parser.add_argument("--lebron-lambda-scale", type=float, default=0.7)
        parser.add_argument("--tier", choices=list(LAMBDA_TIERS), default="A_conservative")
        parser.add_argument("--within-season-half-life", type=float, default=90.0,
                            help="0 disables")
        parser.add_argument("--rapm-window", type=int, default=3)
        parser.add_argument("--native-lambda", action="store_true", default=False,
                            help="Candidate E (doc 10): anchor role-player lambda "
                                 "on the player's own box_bpr instead of LEBRON — "
                                 "same anchoring idea, zero external dependency. "
                                 "Overrides --lebron-lambda-scale's map source.")
        parser.add_argument("--native-lambda-cap", type=float, default=4.0,
                            help="box_bpr total above which no extra lambda "
                                 "(box scale ~ +/-6 vs LEBRON cap 7)")
        parser.add_argument("--dump-ratings", action="store_true", default=False,
                            help="Write per-season variant ratings JSON "
                                 "({nba_id: bpr}) into the run dir — enables "
                                 "YoY stability and independence analysis.")
        parser.add_argument("--run-name", type=str, required=True)
        parser.add_argument("--out-dir", type=str,
                            default="backtest_output/bpr_suite/nba")

    def handle(self, *args, **opts):
        out_dir = Path(opts["out_dir"]) / opts["run_name"]
        out_dir.mkdir(parents=True, exist_ok=True)

        prior_w = opts["lebron_prior_w"]
        prior_def_w = (opts["lebron_prior_def_w"]
                       if opts["lebron_prior_def_w"] is not None else prior_w)
        lam_scale = opts["lebron_lambda_scale"]
        tier = opts["tier"]
        whl = opts["within_season_half_life"] or None
        window = opts["rapm_window"]

        # Borrow the production command's loaders (read-only methods).
        loader = FinalBprCommand()
        loader.stdout, loader.stderr = self.stdout, self.stderr

        rows_out: list[dict] = []
        for src in sorted(opts["source_seasons"]):
            tgt = src + 1
            self.stdout.write(f"\n=== variant @ {src} → eval {tgt} ===")

            # ── compute variant ratings in memory ────────────────────────────
            prior_obpr, prior_dbpr, minutes = loader._load_priors(src)
            prior_obpr_box = dict(prior_obpr)   # pre-blend box priors (candidate E anchor)
            prior_dbpr_box = dict(prior_dbpr)
            lebron_map = _load_lebron_priors(src, list(prior_obpr.keys()))
            if prior_w > 0 and lebron_map:
                prior_obpr, prior_dbpr = loader._blend_lebron_priors(
                    src, prior_obpr, prior_dbpr, prior_w,
                    def_weight=prior_def_w, lebron_map=lebron_map)

            observations, ps_index, n_ps = loader._load_stints(src, window)
            keys = sorted(ps_index, key=ps_index.get)
            if opts.get("native_lambda"):
                # Candidate E: anchor map from the player's own box prior —
                # (o, d) tuple so total = box_bpr; cap rescaled to box units.
                anchor_map = {
                    pid: (prior_obpr_box.get(pid, 0.0), prior_dbpr_box.get(pid, 0.0))
                    for pid in prior_obpr_box
                }
                lam_arr = _build_lambda_array(
                    keys, minutes, LAMBDA_TIERS[tier],
                    lebron_map=anchor_map if lam_scale > 0 else None,
                    lebron_scale=lam_scale,
                    lebron_cap=opts["native_lambda_cap"])
            else:
                lam_arr = _build_lambda_array(
                    keys, minutes, LAMBDA_TIERS[tier],
                    lebron_map=lebron_map if lam_scale > 0 else None,
                    lebron_scale=lam_scale, lebron_cap=LEBRON_LAMBDA_CAP)
            lambda_by_id = {pid: float(lam_arr[i])
                            for i, (pid, _yr) in enumerate(keys)}

            result = fit_prior_informed_rapm(
                observations=observations,
                player_season_index=ps_index,
                n_player_seasons=n_ps,
                prior_obpr=prior_obpr,
                prior_dbpr=prior_dbpr,
                lambda_val=1000.0,
                lambda_by_nba_id=lambda_by_id,
                target_season_year=src,
                cross_season_decay=1.0,
                within_season_half_life=whl,
            )
            variant = {
                pid: result["obpr"][(pid, yr)] + result["dbpr"][(pid, yr)]
                for (pid, yr) in result["obpr"] if yr == src
            }
            self.stdout.write(f"  variant ratings: {len(variant)} players")

            # ── forward references from DB (read-only) ────────────────────────
            if opts.get("dump_ratings"):
                with open(out_dir / f"ratings_{src}.json", "w") as f:
                    json.dump({str(p): round(v, 4) for p, v in variant.items()}, f)

            stored = self._load_stored(src)
            nxt = self._load_stored(tgt)
            team_ratings = self._load_team_ratings((src, tgt))

            row = {"run": opts["run_name"], "source": src, "target": tgt,
                   "prior_w": prior_w, "prior_def_w": prior_def_w,
                   "lambda_scale": lam_scale, "tier": tier,
                   "half_life": whl or 0, "n_variant": len(variant)}

            # (a) player-forward: variant(Y) vs baseline RAPM(Y+1) and BPR(Y+1)
            for label, target_key in (("next_baseline", "baseline"),
                                      ("next_bpr", "bpr")):
                for name, ratings in (("variant", variant),
                                      ("stored", {p: v["bpr"] for p, v in stored.items()
                                                  if v["bpr"] is not None})):
                    pairs = [(ratings[p], nxt[p][target_key])
                             for p in ratings
                             if p in nxt and nxt[p][target_key] is not None
                             and nxt[p]["minutes"] >= 1000]
                    if len(pairs) >= 30:
                        a, b = zip(*pairs)
                        r, _ = scipy.stats.pearsonr(a, b)
                        rho, _ = scipy.stats.spearmanr(a, b)
                        row[f"{name}_{label}_r"] = round(float(r), 4)
                        row[f"{name}_{label}_rho"] = round(float(rho), 4)
                        row[f"{name}_{label}_n"] = len(pairs)

            # (b) team-forward: minutes-weighted aggregate → adj_net(Y+1)
            for name, ratings in (("variant", variant),
                                  ("stored", {p: v["bpr"] for p, v in stored.items()
                                              if v["bpr"] is not None})):
                m = self._team_forward(ratings, stored, team_ratings, src, tgt)
                if m:
                    row[f"{name}_team_r"] = m["r"]
                    row[f"{name}_team_rmse"] = m["rmse"]
                    row[f"{name}_team_slope"] = m["slope"]

            # persistence reference
            pers = [(em_src, em_tgt)
                    for tid, em_src in team_ratings.get(src, {}).items()
                    if (em_tgt := team_ratings.get(tgt, {}).get(tid)) is not None]
            if len(pers) >= 10:
                a, b = zip(*pers)
                r, _ = scipy.stats.pearsonr(a, b)
                rmse = math.sqrt(float(np.mean((np.array(a) - np.array(b)) ** 2)))
                row["persistence_team_r"] = round(float(r), 4)
                row["persistence_team_rmse"] = round(rmse, 3)

            rows_out.append(row)
            self.stdout.write("  " + "  ".join(
                f"{k}={v}" for k, v in row.items()
                if k.endswith(("_r", "_rmse", "_rho")) and v is not None))

        with open(out_dir / "results.csv", "w", newline="") as f:
            keys = []
            for r in rows_out:
                for k in r:
                    if k not in keys:
                        keys.append(k)
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows_out)
        with open(out_dir / "manifest.json", "w") as f:
            json.dump({k: v for k, v in opts.items()
                       if k not in ("stdout", "stderr")}, f, indent=2, default=str)
        self.stdout.write(self.style.SUCCESS(f"\nResults → {out_dir}/results.csv"))

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _load_stored(season: int) -> dict[int, dict]:
        from nba.models import NBAPlayerSeasonStats

        out: dict[int, dict] = {}
        for r in NBAPlayerSeasonStats.objects.filter(
            season__year=season, season_type="regular",
        ).values("player__player_id", "team_id", "bpr",
                 "baseline_obpr", "baseline_dbpr", "mpg", "gp"):
            pid = r["player__player_id"]
            minutes = (r["mpg"] or 0.0) * (r["gp"] or 0)
            prev = out.get(pid)
            if prev is not None and prev["minutes"] >= minutes:
                continue   # traded players: keep the highest-minutes row
            base = (r["baseline_obpr"] + r["baseline_dbpr"]
                    if r["baseline_obpr"] is not None
                    and r["baseline_dbpr"] is not None else None)
            out[pid] = {"bpr": r["bpr"], "baseline": base,
                        "minutes": minutes, "team_id": r["team_id"]}
        return out

    @staticmethod
    def _load_team_ratings(seasons: tuple[int, ...]) -> dict[int, dict[int, float]]:
        from nba.models import NBATeamSeasonRatings

        out: dict[int, dict[int, float]] = {}
        for r in NBATeamSeasonRatings.objects.filter(
            season__year__in=seasons, adj_net__isnull=False,
        ).values("season__year", "team_id", "adj_net"):
            out.setdefault(r["season__year"], {})[r["team_id"]] = float(r["adj_net"])
        return out

    @staticmethod
    def _team_forward(ratings: dict[int, float], stored_meta: dict,
                      team_ratings: dict, src: int, tgt: int) -> dict | None:
        """Minutes-weighted team mean of ratings(Y) → adj_net(Y+1)."""
        team_num: dict[int, float] = {}
        team_den: dict[int, float] = {}
        for pid, val in ratings.items():
            meta = stored_meta.get(pid)
            if meta is None or meta["team_id"] is None or meta["minutes"] < 500:
                continue
            team_num[meta["team_id"]] = team_num.get(meta["team_id"], 0.0) \
                + val * meta["minutes"]
            team_den[meta["team_id"]] = team_den.get(meta["team_id"], 0.0) \
                + meta["minutes"]

        pairs = []
        for tid, den in team_den.items():
            tgt_em = team_ratings.get(tgt, {}).get(tid)
            if den > 0 and tgt_em is not None:
                pairs.append((team_num[tid] / den, tgt_em))
        if len(pairs) < 10:
            return None
        x = np.array([p[0] for p in pairs])
        y = np.array([p[1] for p in pairs])
        r, _ = scipy.stats.pearsonr(x, y)
        slope, intercept = np.polyfit(x, y, 1)
        pred = slope * x + intercept
        rmse = math.sqrt(float(np.mean((pred - y) ** 2)))
        return {"r": round(float(r), 4), "rmse": round(rmse, 3),
                "slope": round(float(slope), 3)}
