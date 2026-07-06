"""
Management command: dump_bpr_ratings

Runs the NCAA BPR pipeline fully IN MEMORY (persist=False) for one season and
dumps {player_id: bpr} JSON — the experiment-arm format consumed by
`backtest_bpr_suite --extra-ratings-json`.

This is how model variants (truthful targets, alternate configs) enter the
leak-free backtest without touching stored production ratings.

Usage:
  python manage.py dump_bpr_ratings --season 2025 --truthful-targets \\
      --out backtest_output/bpr_suite/ratings_2025_truthful.json
  python manage.py dump_bpr_ratings --season 2025 --rapm-window 4 \\
      --out backtest_output/bpr_suite/ratings_2025_current.json
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "In-memory BPR run → {player_id: bpr} JSON for suite experiment arms."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument("--out", type=str, required=True)
        parser.add_argument("--truthful-targets", action="store_true", default=False)
        parser.add_argument("--rapm-window", type=int, default=4)
        parser.add_argument("--no-em-calibrate", action="store_true", default=False)
        parser.add_argument("--sd-scale-off", type=float, default=None,
                            help="Override prior SD scale (off) — skips CV tuning "
                                 "(experiment N-B)")
        parser.add_argument("--sd-scale-def", type=float, default=None,
                            help="Override prior SD scale (def)")
        parser.add_argument("--garbage-weight", type=float, default=1.0,
                            help="Downweight blowout late-2nd-half segments "
                                 "(experiment N-C; 1.0 = off)")

    def handle(self, *args, **opts):
        from ncaa.analytics.player_value.bpr.pipeline import run_bpr_season

        summary = run_bpr_season(
            opts["season"],
            persist=False,
            verbose=False,
            rapm_window_size=opts["rapm_window"],
            em_calibrate=not opts["no_em_calibrate"],
            truthful_targets=opts["truthful_targets"],
            sd_scale_off_override=opts["sd_scale_off"],
            sd_scale_def_override=opts["sd_scale_def"],
            garbage_time_weight=opts["garbage_weight"],
        )
        bpr_map = summary.get("player_bpr_map") or {}
        out = {
            str(pid): round(v["bpr"], 4)
            for pid, v in bpr_map.items()
            if v.get("bpr") is not None
        }
        path = Path(opts["out"])
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(out, f)
        tt = summary.get("truthful_targets", {})
        self.stdout.write(self.style.SUCCESS(
            f"{len(out)} ratings → {path}"
            + (f"  (truthful: pool={tt.get('rapm_years')}, "
               f"dropped={tt.get('dropped_years')})" if tt else "")))
