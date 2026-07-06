"""
Management command: nba_experiment_box_chain

Full-chain NBA experiment harness (mission items B-A / B-B): retrains Box BPR
IN MEMORY under variant settings, feeds the variant box priors through the
final prior-informed RAPM, and forward-evaluates — no DB writes anywhere.

Variants supported:
  --lebron-blend-w W     Box BPR target blend: (1-W)*baseline_RAPM + W*LEBRON
                         (production 0.7). Experiment B-B.
  --drop-features f1 f2  Remove named features from OFF/DEF sets before
                         training/prediction (e.g. d_mpir on_court_adj_d).
                         Experiment B-A.
  --lebron-prior-w       Final-stage prior blend (production 0.75).

Evaluation per source season Y (mirrors nba_experiment_final_bpr):
  player-forward  variant BPR(Y) vs stored baseline RAPM(Y+1) r/rho
  team-forward    minutes-weighted aggregate → adj_net(Y+1) r / RMSE
  references      stored production BPR and persistence

Usage:
  python manage.py nba_experiment_box_chain --source-seasons 2022 2023 2024 \\
      --lebron-blend-w 0.3 --run-name blendw_030
  python manage.py nba_experiment_box_chain --source-seasons 2022 2023 2024 \\
      --drop-features d_mpir --run-name ablate_dmpir
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
import scipy.stats
from django.core.management.base import BaseCommand
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from nba.analytics.box_bpr import (
    OFF_FEATURES, DEF_FEATURES,
    extract_nba_box_features,
    compute_opp_quality_map, compute_team_adj_em_map,
)
from nba.analytics.career_stats import build_career_stats_map
from nba.analytics.rapm import fit_prior_informed_rapm
from nba.management.commands.nba_compute_final_bpr import (
    Command as FinalBprCommand,
    LAMBDA_TIERS, LEBRON_LAMBDA_CAP,
    _build_lambda_array, _load_lebron_priors,
)
from nba.management.commands.nba_experiment_final_bpr import (
    Command as ExpCommand,
)

BOX_ALPHA_OFF = 5.0   # pinned, matches production nba box_bpr
BOX_ALPHA_DEF = 10.0


def _fit_ridge(X: np.ndarray, y: np.ndarray, alpha: float):
    scaler = StandardScaler().fit(X)
    model = Ridge(alpha=alpha).fit(scaler.transform(X), y)
    return scaler, model


class Command(BaseCommand):
    help = "In-memory NBA box+final chain variants (ablation / target-blend sweeps)."

    def add_arguments(self, parser):
        parser.add_argument("--source-seasons", nargs="+", type=int, required=True)
        parser.add_argument("--lebron-blend-w", type=float, default=0.7,
                            help="Box target blend weight on LEBRON (prod 0.7)")
        parser.add_argument("--drop-features", nargs="+", default=[],
                            help="Feature names to ablate from OFF/DEF sets")
        parser.add_argument("--lebron-prior-w", type=float, default=0.75)
        parser.add_argument("--lebron-lambda-scale", type=float, default=0.7)
        parser.add_argument("--rapm-window", type=int, default=3)
        parser.add_argument("--run-name", type=str, required=True)
        parser.add_argument("--out-dir", type=str,
                            default="backtest_output/bpr_suite/nba")

    # ── box stage ─────────────────────────────────────────────────────────────

    def _load_stats(self, season: int) -> list[dict]:
        from nba.models import NBAPlayerSeasonStats

        return list(NBAPlayerSeasonStats.objects.filter(
            season__year=season, season_type="regular",
        ).values(
            "player__player_id", "team_id", "gp", "mpg", "on_court_poss",
            "pts", "ast", "tov", "stl", "blk", "oreb_pg", "dreb_pg",
            "fga_pg", "fg3a_pg", "fta_pg",
            "efg_pct", "ts_pct", "usg_pct", "ast_pct",
            "stl_pct", "blk_pct", "oreb_pct",
            "ast_to", "d_mpir", "o_mpir",
            "on_court_adj_o", "on_court_adj_d", "on_court_adj_em",
            "baseline_obpr", "baseline_dbpr",
        ))

    def _variant_box(self, season: int, stats: list[dict],
                     blend_w: float, drop: set[str]) -> dict[int, dict]:
        """Train variant box model, return {nba_id: {box_obpr, box_dbpr}}."""
        for r in stats:
            r["player_id"] = r["player__player_id"]

        opp_q = compute_opp_quality_map(season)
        team_em = compute_team_adj_em_map(season)
        career = build_career_stats_map(
            target_season_year=season, min_season_year=2016)
        feats = extract_nba_box_features(stats, opp_q, team_em, career)

        off_idx = [i for i, f in enumerate(OFF_FEATURES) if f not in drop]
        def_idx = [i for i, f in enumerate(DEF_FEATURES) if f not in drop]

        # targets: blend stored baseline RAPM with LEBRON (name→pk match not
        # needed — LEBRON csv keys by nba_id which IS our player key here)
        lebron = _load_lebron_priors(season, list(feats.keys()))
        t_off, t_def = {}, {}
        for r in stats:
            pid = r["player_id"]
            if r["baseline_obpr"] is None or r["baseline_dbpr"] is None:
                continue
            o, d = float(r["baseline_obpr"]), float(r["baseline_dbpr"])
            if pid in lebron and blend_w > 0:
                lo, ld = lebron[pid]
                o = (1 - blend_w) * o + blend_w * lo
                d = (1 - blend_w) * d + blend_w * ld
            t_off[pid], t_def[pid] = o, d

        Xo, yo, Xd, yd = [], [], [], []
        for pid, fv in feats.items():
            if pid in t_off:
                Xo.append([fv["off"][i] for i in off_idx])
                yo.append(t_off[pid])
                Xd.append([fv["def"][i] for i in def_idx])
                yd.append(t_def[pid])
        if len(Xo) < 50:
            raise RuntimeError(f"too few training rows ({len(Xo)}) for {season}")

        so, mo = _fit_ridge(np.array(Xo), np.array(yo), BOX_ALPHA_OFF)
        sd_, md = _fit_ridge(np.array(Xd), np.array(yd), BOX_ALPHA_DEF)

        out = {}
        for pid, fv in feats.items():
            xo = np.array([[fv["off"][i] for i in off_idx]])
            xd = np.array([[fv["def"][i] for i in def_idx]])
            out[pid] = {
                "box_obpr": float(mo.predict(so.transform(xo))[0]),
                "box_dbpr": float(md.predict(sd_.transform(xd))[0]),
            }
        return out

    # ── main ──────────────────────────────────────────────────────────────────

    def handle(self, *args, **opts):
        out_dir = Path(opts["out_dir"]) / opts["run_name"]
        out_dir.mkdir(parents=True, exist_ok=True)
        drop = set(opts["drop_features"])
        unknown = drop - set(OFF_FEATURES) - set(DEF_FEATURES)
        if unknown:
            self.stderr.write(f"WARNING: unknown feature names ignored: {unknown}")

        loader = FinalBprCommand()
        loader.stdout, loader.stderr = self.stdout, self.stderr

        rows_out = []
        for src in sorted(opts["source_seasons"]):
            tgt = src + 1
            self.stdout.write(
                f"\n=== box-chain variant @ {src} → eval {tgt} "
                f"(blend_w={opts['lebron_blend_w']}, drop={sorted(drop) or '-'}) ===")

            stats = self._load_stats(src)
            box = self._variant_box(src, stats, opts["lebron_blend_w"], drop)
            self.stdout.write(f"  variant box preds: {len(box)} players")

            # final stage — variant box as prior base
            minutes = {r["player__player_id"]: (r["mpg"] or 0) * (r["gp"] or 0)
                       for r in stats}
            prior_obpr = {p: v["box_obpr"] for p, v in box.items()}
            prior_dbpr = {p: v["box_dbpr"] for p, v in box.items()}
            lebron_map = _load_lebron_priors(src, list(prior_obpr.keys()))
            w = opts["lebron_prior_w"]
            if w > 0 and lebron_map:
                for pid, (lo, ld) in lebron_map.items():
                    if pid in prior_obpr:
                        prior_obpr[pid] = w * lo + (1 - w) * prior_obpr[pid]
                        prior_dbpr[pid] = w * ld + (1 - w) * prior_dbpr[pid]

            observations, ps_index, n_ps = loader._load_stints(
                src, opts["rapm_window"])
            keys = sorted(ps_index, key=ps_index.get)
            lam = _build_lambda_array(
                keys, minutes, LAMBDA_TIERS["A_conservative"],
                lebron_map=lebron_map if opts["lebron_lambda_scale"] > 0 else None,
                lebron_scale=opts["lebron_lambda_scale"],
                lebron_cap=LEBRON_LAMBDA_CAP)
            lam_by_id = {pid: float(lam[i]) for i, (pid, _y) in enumerate(keys)}

            result = fit_prior_informed_rapm(
                observations=observations, player_season_index=ps_index,
                n_player_seasons=n_ps,
                prior_obpr=prior_obpr, prior_dbpr=prior_dbpr,
                lambda_val=1000.0, lambda_by_nba_id=lam_by_id,
                target_season_year=src, cross_season_decay=1.0,
                within_season_half_life=90.0)
            variant = {pid: result["obpr"][(pid, y)] + result["dbpr"][(pid, y)]
                       for (pid, y) in result["obpr"] if y == src}

            stored = ExpCommand._load_stored(src)
            nxt = ExpCommand._load_stored(tgt)
            team_ratings = ExpCommand._load_team_ratings((src, tgt))

            row = {"run": opts["run_name"], "source": src, "target": tgt,
                   "blend_w": opts["lebron_blend_w"],
                   "dropped": ",".join(sorted(drop)) or "-"}
            for name, ratings in (
                ("variant", variant),
                ("stored", {p: v["bpr"] for p, v in stored.items()
                            if v["bpr"] is not None}),
            ):
                pairs = [(ratings[p], nxt[p]["baseline"]) for p in ratings
                         if p in nxt and nxt[p]["baseline"] is not None
                         and nxt[p]["minutes"] >= 1000]
                if len(pairs) >= 30:
                    a, b = zip(*pairs)
                    r, _ = scipy.stats.pearsonr(a, b)
                    row[f"{name}_next_baseline_r"] = round(float(r), 4)
                m = ExpCommand._team_forward(ratings, stored, team_ratings, src, tgt)
                if m:
                    row[f"{name}_team_r"] = m["r"]
                    row[f"{name}_team_rmse"] = m["rmse"]
            rows_out.append(row)
            self.stdout.write("  " + "  ".join(
                f"{k}={v}" for k, v in row.items()
                if k.endswith(("_r", "_rmse"))))

        with open(out_dir / "results.csv", "w", newline="") as f:
            keys_ = []
            for r in rows_out:
                for k in r:
                    if k not in keys_:
                        keys_.append(k)
            w_ = csv.DictWriter(f, fieldnames=keys_)
            w_.writeheader()
            w_.writerows(rows_out)
        with open(out_dir / "manifest.json", "w") as f:
            json.dump({k: v for k, v in opts.items()
                       if k not in ("stdout", "stderr")}, f, indent=2, default=str)
        self.stdout.write(self.style.SUCCESS(f"\nResults → {out_dir}/results.csv"))
