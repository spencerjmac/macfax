"""
Task 6d step 2: recompute ratings and every downstream team field, 2005-2026 (local macfax DB).

  python data_fixes/2026-11-13_task6d_recompute_all.py --log-dir DIR [--seasons 2005-2026] [--resume]

Per season, Task 7b's sequence: the post-tournament chain, then the pre-tournament chain (which uses that
season's NationalAverages). Skipped: seed_conferences (frozen 2025-26 map; never rerun for past seasons),
fetch_net_rankings (network), compute_sor.
Each command commits on its own (as the pipeline does). DIR/timing.csv: season, phase, command, seconds, status,
warnings; DIR/warnings.log: every warning line (command output and the membership-fallback / zero-valid-rating-
games loggers); DIR/out/<season>_<phase>_<command>.txt: full output. --resume skips seasons already complete.
"""

import argparse
import csv
import io
import logging
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402

POST = ["compute_team_metrics", "compute_national_averages", "compute_adjusted_ratings", "compute_hca", "compute_sigma",
        "compute_adjusted_four_factors", "compute_four_factor_index", "train_four_factor_regression", "compute_game_value",
        "compute_sos", "compute_wab"]
PRE = ["compute_team_metrics", "compute_adjusted_ratings", "compute_adjusted_four_factors", "compute_four_factor_index",
       "compute_sos", "compute_wab"]
WARN_RE = re.compile(r"⚠|WARNING|warning|fell back|falling back|Falling back|not found|No game stats", re.I)


class Collector(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING); self.records = []

    def emit(self, record):
        self.records.append(f"{record.name}: {record.getMessage()}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log-dir", required=True)
    ap.add_argument("--seasons", default="2005-2026")
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()
    lo, hi = (int(x) for x in a.seasons.split("-"))
    log = Path(a.log_dir); (log / "out").mkdir(parents=True, exist_ok=True)
    timing_path = log / "timing.csv"
    done = set()
    if a.resume and timing_path.exists():
        rows = list(csv.DictReader(open(timing_path)))
        for y in {r["season"] for r in rows}:
            if sum(1 for r in rows if r["season"] == y and r["status"] == "ok") == len(POST) + len(PRE):
                done.add(int(y))
    new_file = not timing_path.exists()
    tf = open(timing_path, "a", newline=""); tw = csv.writer(tf)
    if new_file:
        tw.writerow(["season", "phase", "command", "seconds", "status", "warnings"])
    wf = open(log / "warnings.log", "a")
    handler = Collector(); logging.getLogger().addHandler(handler)
    for y in range(lo, hi + 1):
        if y in done:
            print(f"{y}: already done", flush=True); continue
        for phase, cmds in (("post", POST), ("pre", PRE)):
            for cmd in cmds:
                handler.records.clear()
                buf = io.StringIO(); t = time.time(); status = "ok"
                kw = {"season": y}
                if phase == "pre":
                    kw["pre_tournament"] = True
                try:
                    call_command(cmd, stdout=buf, stderr=buf, **kw)
                except BaseException as e:  # noqa: BLE001
                    status = f"ERROR {type(e).__name__}: {e}"
                secs = time.time() - t
                text = buf.getvalue()
                (log / "out" / f"{y}_{phase}_{cmd}.txt").write_text(text + ("\n" + status if status != "ok" else ""))
                warns = [ln.strip() for ln in text.splitlines() if WARN_RE.search(ln)] + handler.records
                for w in warns:
                    wf.write(f"{y}\t{phase}\t{cmd}\t{w}\n")
                wf.flush()
                tw.writerow([y, phase, cmd, f"{secs:.1f}", status, len(warns)]); tf.flush()
                print(f"{y} {phase} {cmd} {secs:.0f}s {status} warnings={len(warns)}", flush=True)
                if status != "ok":
                    print("STOPPING on error", flush=True); sys.exit(1)
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
