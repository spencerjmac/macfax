"""
derive_rookie_priors — empirical rookie-season BPR/MPG priors by draft slot.

Phase 4 Stage 1 (REPORT ONLY — commits nothing).

WHY PICK-BASED, NOT MPS-BASED (Step 0 census verdict):
  mps_score exists ONLY on the current unplayed draft class (60 drafted
  TeamOutseasonMove rows, 2026 draft → 2026-27, no rookie outcomes yet).
  ZERO rookies-with-outcomes carry an MPS score. A direct MPS→BPR fit is
  therefore impossible; the predictor is overall_pick. MPS re-enters in a
  later phase once the 2026 class plays and its outcomes land.

PREDICTOR JOIN (clean, no name matching):
  NBA.com DraftHistory(year=D).PERSON_ID  →  NBAPlayer.player_id  →
  NBAPlayerSeasonStats(season=D+1, season_type='regular').
  Draft year D drafts into season year D+1 (June draft → that fall's season,
  which our season-year convention labels D+1).

ONE-ROW DISCIPLINE (Phase 2/3 lesson, adapted):
  NBAPlayerSeasonStats is unique per (player, season, team, season_type) —
  a rookie traded mid-season has multiple rows. We COLLAPSE each rookie's
  team splits into one minutes-weighted season line, then ASSERT one row per
  player per class. Outcome BPR is minutes-weighted; MPG is total-min / total-gp.

LINEAGE CAVEAT (reported, not silently trusted):
  Outcome-season BPR must be lineage-clean. 2022-2024 seasons were batch-
  updated 2026-05-22; 2025-2026 re-solved 2026-07-05. Phase 2 flagged 2025
  stored BPR as having drifted from a fresh 3-yr-window solve (Amen Thompson
  fresh 9.43 vs stored). The 2024→2025 class's outcomes are the weakest link;
  LOYO-by-class surfaces contamination as a held-out MAE outlier for that class.

Usage:
    python manage.py derive_rookie_priors
    python manage.py derive_rookie_priors --draft-years 2021,2022,2023,2024 --min-mpg 5.0
"""

from __future__ import annotations

import statistics
import time

from django.core.management.base import BaseCommand, CommandError

from nba.models import NBAPlayer, NBAPlayerSeasonStats

# Pick bins (overall_pick). Coarse by design: ~45 rookies/class over 4 classes
# cannot support a flexible curve. Lottery / mid-first / late-first / second.
PICK_BINS = [(1, 5), (6, 14), (15, 30), (31, 60)]

# Current hardcoded rookie prior in compute_nba_team_outlooks._assemble_roster
# (baseline (a) for LOYO): drafted → obpr 0.0, dbpr 0.0, mpg 12.0.
HARDCODED_OBPR = 0.0
HARDCODED_DBPR = 0.0
HARDCODED_MPG = 12.0


def _bin_label(pick: int) -> str | None:
    for lo, hi in PICK_BINS:
        if lo <= pick <= hi:
            return f"{lo}-{hi}"
    return None


class Command(BaseCommand):
    help = "Derive rookie-season obpr/dbpr/mpg priors by draft-pick bin (report only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--draft-years", type=str, default="2021,2022,2023,2024",
            help="Comma-separated draft years. Draft year D → rookie season D+1.",
        )
        parser.add_argument(
            "--min-mpg", type=float, default=5.0,
            help="Minimum rookie MPG to count as a real rookie outcome (default 5.0).",
        )

    def handle(self, *args, **options):
        draft_years = [int(y) for y in options["draft_years"].split(",")]
        min_mpg = options["min_mpg"]

        # rookie identification: a player's FIRST regular season in our DB
        from django.db.models import Min
        first_season = {
            r["player_id"]: r["first_yr"]
            for r in NBAPlayerSeasonStats.objects.filter(season_type="regular")
            .values("player_id")
            .annotate(first_yr=Min("season__year"))
        }
        dbid_by_nbaid = {p.player_id: p.id for p in NBAPlayer.objects.all()}

        # rows[class_year] = list of dicts {pick, obpr, dbpr, mpg, name}
        classes: dict[int, list[dict]] = {}
        for draft_yr in draft_years:
            season_yr = draft_yr + 1
            rows = self._collect_class(
                draft_yr, season_yr, dbid_by_nbaid, first_season, min_mpg
            )
            classes[draft_yr] = rows
            time.sleep(0.6)  # be gentle to NBA.com

        if not any(classes.values()):
            raise CommandError("No rookie outcomes joined — check network / DB.")

        self._report_census(classes, min_mpg)
        self._report_bins(classes)
        self._report_loyo(classes)

        self.stdout.write(self.style.WARNING(
            "\nHUMAN REVIEW GATE — no constants written. Approve pick→prior "
            "table before Stage 2 wires it into _assemble_roster."
        ))

    # ── Collection ─────────────────────────────────────────────────────────────

    def _collect_class(self, draft_yr, season_yr, dbid_by_nbaid, first_season, min_mpg):
        from nba_api.stats.endpoints import drafthistory

        try:
            df = drafthistory.DraftHistory(
                league_id="00", season_year_nullable=str(draft_yr), timeout=25
            ).draft_history.get_data_frame()
        except Exception as exc:
            self.stderr.write(f"  draft {draft_yr}: NBA.com fetch failed ({exc}) — skipped")
            return []

        pick_by_dbid: dict[int, int] = {}
        for _, r in df.iterrows():
            nbaid = int(r["PERSON_ID"])
            pick = int(r["OVERALL_PICK"])
            dbid = dbid_by_nbaid.get(nbaid)
            if dbid is not None:
                pick_by_dbid[dbid] = pick

        rows = []
        seen_players = set()
        for dbid, pick in pick_by_dbid.items():
            # rookie gate: this season must be the player's first in our DB
            if first_season.get(dbid) != season_yr:
                continue
            # collapse multi-team splits → one minutes-weighted line
            splits = list(
                NBAPlayerSeasonStats.objects.filter(
                    player_id=dbid, season__year=season_yr, season_type="regular",
                    bpr__isnull=False, obpr__isnull=False, dbpr__isnull=False,
                    mpg__isnull=False, gp__isnull=False,
                ).values("obpr", "dbpr", "mpg", "gp", "player__name")
            )
            if not splits:
                continue
            total_min = sum((s["mpg"] or 0.0) * (s["gp"] or 0) for s in splits)
            total_gp = sum(s["gp"] or 0 for s in splits)
            if total_min <= 0 or total_gp <= 0:
                continue
            combined_mpg = total_min / total_gp
            if combined_mpg < min_mpg:
                continue
            w_obpr = sum(s["obpr"] * (s["mpg"] or 0.0) * (s["gp"] or 0) for s in splits) / total_min
            w_dbpr = sum(s["dbpr"] * (s["mpg"] or 0.0) * (s["gp"] or 0) for s in splits) / total_min
            # one-row assertion
            if dbid in seen_players:
                raise CommandError(
                    f"one-row violation: player_id {dbid} collapsed twice in {season_yr}"
                )
            seen_players.add(dbid)
            rows.append({
                "pick": pick, "obpr": w_obpr, "dbpr": w_dbpr, "mpg": combined_mpg,
                "name": splits[0]["player__name"], "n_teams": len(splits),
            })
        return rows

    # ── Reports ────────────────────────────────────────────────────────────────

    def _report_census(self, classes, min_mpg):
        self.stdout.write(f"\n{'='*66}\nSTEP 0 CENSUS (min_mpg={min_mpg}, predictor=overall_pick)")
        self.stdout.write("MPS coverage for rookies-with-outcomes: 0 → pick-based fallback.\n")
        self.stdout.write(f"  {'class':>7} {'rookie outcomes':>16} {'multi-team collapses':>21}")
        for dyr, rows in classes.items():
            multi = sum(1 for r in rows if r["n_teams"] > 1)
            self.stdout.write(f"  {dyr}→{dyr+1:<4} {len(rows):>16} {multi:>21}")
        self.stdout.write(f"  TOTAL rookie outcomes: {sum(len(r) for r in classes.values())}")

    def _bin_rows(self, rows):
        bins: dict[str, list[dict]] = {f"{lo}-{hi}": [] for lo, hi in PICK_BINS}
        for r in rows:
            lbl = _bin_label(r["pick"])
            if lbl:
                bins[lbl].append(r)
        return bins

    def _report_bins(self, classes):
        all_rows = [r for rows in classes.values() for r in rows]
        bins = self._bin_rows(all_rows)
        self.stdout.write(f"\n{'='*66}\nPICK→PRIOR TABLE (pooled all classes)")
        self.stdout.write(
            f"  {'bin':>7} {'N':>4} "
            f"{'obpr μ':>8} {'σ':>6} {'dbpr μ':>8} {'σ':>6} {'mpg μ':>7} {'σ':>6}"
        )
        for lbl, rs in bins.items():
            if not rs:
                self.stdout.write(f"  {lbl:>7} {0:>4}  (empty)")
                continue
            o = [r["obpr"] for r in rs]; d = [r["dbpr"] for r in rs]; m = [r["mpg"] for r in rs]
            self.stdout.write(
                f"  {lbl:>7} {len(rs):>4} "
                f"{statistics.mean(o):>8.2f} {(statistics.pstdev(o) if len(o)>1 else 0):>6.2f} "
                f"{statistics.mean(d):>8.2f} {(statistics.pstdev(d) if len(d)>1 else 0):>6.2f} "
                f"{statistics.mean(m):>7.1f} {(statistics.pstdev(m) if len(m)>1 else 0):>6.1f}"
            )
        # monotonicity note (total bpr = obpr+dbpr by bin)
        means = [
            (lbl, statistics.mean([r["obpr"] + r["dbpr"] for r in rs]))
            for lbl, rs in bins.items() if rs
        ]
        mono = all(means[i][1] >= means[i+1][1] for i in range(len(means)-1))
        self.stdout.write(
            f"  bin BPR means: {', '.join(f'{l}={v:+.2f}' for l,v in means)}  "
            f"→ monotone decreasing in pick: {mono}"
        )

    def _predict_from_bins(self, bins_means, pick):
        lbl = _bin_label(pick)
        return bins_means.get(lbl)

    def _report_loyo(self, classes):
        self.stdout.write(f"\n{'='*66}\nLOYO (leave-one-CLASS-out) held-out MAE vs baselines")
        self.stdout.write(
            "  baseline (a) = current hardcoded 0.0 obpr / 0.0 dbpr / 12.0 mpg\n"
            "  baseline (b) = predict training-classes global rookie mean"
        )
        self.stdout.write(
            f"\n  {'held-out':>9} {'N':>4}  "
            f"{'MAE_bpr map':>11} {'(a)hard':>8} {'(b)mean':>8}   {'MAE_mpg map':>11} {'(a)':>6} {'(b)':>6}"
        )
        agg = {"map_bpr": [], "a_bpr": [], "b_bpr": [], "map_mpg": [], "a_mpg": [], "b_mpg": []}
        for held in classes:
            test = classes[held]
            train = [r for dyr, rows in classes.items() if dyr != held for r in rows]
            if not test or not train:
                continue
            train_bins = self._bin_rows(train)
            bin_obpr = {l: statistics.mean([r["obpr"] for r in rs]) for l, rs in train_bins.items() if rs}
            bin_dbpr = {l: statistics.mean([r["dbpr"] for r in rs]) for l, rs in train_bins.items() if rs}
            bin_mpg = {l: statistics.mean([r["mpg"] for r in rs]) for l, rs in train_bins.items() if rs}
            g_obpr = statistics.mean([r["obpr"] for r in train])
            g_dbpr = statistics.mean([r["dbpr"] for r in train])
            g_mpg = statistics.mean([r["mpg"] for r in train])

            e_map, e_a, e_b, em_map, em_a, em_b = [], [], [], [], [], []
            for r in test:
                lbl = _bin_label(r["pick"])
                actual_bpr = r["obpr"] + r["dbpr"]
                pred_bpr = bin_obpr.get(lbl, g_obpr) + bin_dbpr.get(lbl, g_dbpr)
                e_map.append(abs(pred_bpr - actual_bpr))
                e_a.append(abs((HARDCODED_OBPR + HARDCODED_DBPR) - actual_bpr))
                e_b.append(abs((g_obpr + g_dbpr) - actual_bpr))
                pred_mpg = bin_mpg.get(lbl, g_mpg)
                em_map.append(abs(pred_mpg - r["mpg"]))
                em_a.append(abs(HARDCODED_MPG - r["mpg"]))
                em_b.append(abs(g_mpg - r["mpg"]))
            self.stdout.write(
                f"  {held}→{held+1:<3} {len(test):>4}  "
                f"{statistics.mean(e_map):>11.2f} {statistics.mean(e_a):>8.2f} {statistics.mean(e_b):>8.2f}   "
                f"{statistics.mean(em_map):>11.2f} {statistics.mean(em_a):>6.1f} {statistics.mean(em_b):>6.1f}"
            )
            agg["map_bpr"] += e_map; agg["a_bpr"] += e_a; agg["b_bpr"] += e_b
            agg["map_mpg"] += em_map; agg["a_mpg"] += em_a; agg["b_mpg"] += em_b

        self.stdout.write(
            f"  {'POOLED':>9} {len(agg['map_bpr']):>4}  "
            f"{statistics.mean(agg['map_bpr']):>11.2f} {statistics.mean(agg['a_bpr']):>8.2f} {statistics.mean(agg['b_bpr']):>8.2f}   "
            f"{statistics.mean(agg['map_mpg']):>11.2f} {statistics.mean(agg['a_mpg']):>6.1f} {statistics.mean(agg['b_mpg']):>6.1f}"
        )
        beats_a = statistics.mean(agg["map_bpr"]) < statistics.mean(agg["a_bpr"])
        beats_b = statistics.mean(agg["map_bpr"]) < statistics.mean(agg["b_bpr"])
        self.stdout.write(
            f"\n  VERDICT (BPR): map beats (a) hardcoded: {beats_a}  |  "
            f"map beats (b) global-mean: {beats_b}"
        )
