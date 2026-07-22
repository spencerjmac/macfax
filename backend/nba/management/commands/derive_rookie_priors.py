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
        parser.add_argument(
            "--v2", action="store_true",
            help=(
                "Phase 4.6 re-derivation: FULL pick universe (zero-minute picks "
                "included — survivor correction) + team-context conditioning "
                "(drafting team's prior-season actual wins), LOYO vs 3 baselines, "
                "league-share closure check. Report only."
            ),
        )

    def handle(self, *args, **options):
        if options["v2"]:
            self._handle_v2(options)
            return
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

    # ══ Phase 4.6 Stage A: v2 re-derivation ══════════════════════════════════
    #
    # Fixes the two proven biases of the 4.5 pin:
    #   SURVIVOR: universe = ALL rounds-1-2 picks per class; a pick with no
    #     rookie-season row contributes mpg 0.0 (the pin is an EXPECTATION).
    #   TEAM CONTEXT: conditioned on the drafting team's prior-season actual
    #     wins (season D — ex-ante, no circularity with our projection).
    #     Caveat: draft-night trades mean the drafting team occasionally isn't
    #     the playing team; conditioning uses the drafting team uniformly
    #     because that is the team a production pin would be applied to.

    def _team_wins(self, season_year: int) -> dict[str, int]:
        """Actual regular-season wins per team abbreviation for a season."""
        from nba.models import NBAGame
        wins: dict[str, int] = {}
        qs = NBAGame.objects.filter(
            season__year=season_year, season_type="regular",
        ).select_related("home_team", "away_team").only(
            "home_score", "away_score", "home_team__abbreviation",
            "away_team__abbreviation",
        )
        for g in qs:
            if g.home_score is None or g.away_score is None:
                continue
            w = (g.home_team.abbreviation if g.home_score > g.away_score
                 else g.away_team.abbreviation)
            wins[w] = wins.get(w, 0) + 1
        return wins

    def _collect_class_v2(self, draft_yr: int, dbid_by_nbaid: dict) -> list[dict]:
        """Full-universe rows: every rounds-1-2 pick, zero-minute picks included."""
        from nba_api.stats.endpoints import drafthistory

        season_yr = draft_yr + 1
        df = drafthistory.DraftHistory(
            league_id="00", season_year_nullable=str(draft_yr), timeout=25
        ).draft_history.get_data_frame()

        prior_wins = self._team_wins(draft_yr)  # season D = year the draft follows
        rows = []
        for _, r in df.iterrows():
            pick = int(r["OVERALL_PICK"])
            if pick > 60 or int(r["ROUND_NUMBER"]) > 2:
                continue
            abbr = str(r["TEAM_ABBREVIATION"])
            dbid = dbid_by_nbaid.get(int(r["PERSON_ID"]))
            total_min = total_gp = 0.0
            if dbid is not None:
                splits = NBAPlayerSeasonStats.objects.filter(
                    player_id=dbid, season__year=season_yr, season_type="regular",
                    mpg__isnull=False, gp__isnull=False,
                ).values_list("mpg", "gp")
                for mpg, gp in splits:
                    total_min += (mpg or 0.0) * (gp or 0)
                    total_gp += gp or 0
            rows.append({
                "pick": pick,
                "name": str(r["PLAYER_NAME"]),
                "mpg": (total_min / total_gp) if total_gp > 0 else 0.0,
                "total_min": total_min,
                "prior_wins": prior_wins.get(abbr),
                "in_db": dbid is not None,
            })
        return rows

    @staticmethod
    def _tier(prior_wins, median_wins) -> str:
        return "good" if (prior_wins is not None and prior_wins > median_wins) else "bad"

    def _fit_cells(self, rows):
        """(bin_label, tier) → mean mpg. Returns (cell_means, bin_means, global)."""
        cells: dict[tuple, list] = {}
        bins: dict[str, list] = {}
        for r in rows:
            lbl = _bin_label(r["pick"])
            if lbl is None:
                continue
            cells.setdefault((lbl, r["tier"]), []).append(r["mpg"])
            bins.setdefault(lbl, []).append(r["mpg"])
        cell_means = {k: statistics.mean(v) for k, v in cells.items()}
        bin_means = {k: statistics.mean(v) for k, v in bins.items()}
        g = statistics.mean([r["mpg"] for r in rows])
        return cell_means, bin_means, g, cells

    def _fit_additive(self, rows):
        """mpg = bin_effect[label] + b·(prior_wins − 41). Returns (effects, b, r2)."""
        labels = [f"{lo}-{hi}" for lo, hi in PICK_BINS]
        data = [r for r in rows if _bin_label(r["pick"]) and r["prior_wins"] is not None]
        n = len(data)
        # normal equations for 4 bin dummies + centered wins slope
        import itertools
        k = len(labels) + 1
        X = []
        y = []
        for r in data:
            xi = [1.0 if _bin_label(r["pick"]) == l else 0.0 for l in labels]
            xi.append(r["prior_wins"] - 41.0)
            X.append(xi)
            y.append(r["mpg"])
        # solve (X'X) beta = X'y  via Gaussian elimination (k=5, trivial)
        XtX = [[sum(X[i][a] * X[i][b] for i in range(n)) for b in range(k)] for a in range(k)]
        Xty = [sum(X[i][a] * y[i] for i in range(n)) for a in range(k)]
        M = [row[:] + [Xty[a]] for a, row in enumerate(XtX)]
        for col in range(k):
            piv = max(range(col, k), key=lambda r_: abs(M[r_][col]))
            M[col], M[piv] = M[piv], M[col]
            if abs(M[col][col]) < 1e-12:
                continue
            for r_ in range(k):
                if r_ != col and abs(M[r_][col]) > 1e-15:
                    f = M[r_][col] / M[col][col]
                    for c_ in range(col, k + 1):
                        M[r_][c_] -= f * M[col][c_]
        beta = [M[i][k] / M[i][i] if abs(M[i][i]) > 1e-12 else 0.0 for i in range(k)]
        effects = dict(zip(labels, beta[:-1]))
        b = beta[-1]
        yhat = [sum(X[i][j] * beta[j] for j in range(k)) for i in range(n)]
        ybar = statistics.mean(y)
        ss_res = sum((y[i] - yhat[i]) ** 2 for i in range(n))
        ss_tot = sum((yi - ybar) ** 2 for yi in y) or 1.0
        return effects, b, 1.0 - ss_res / ss_tot

    def _handle_v2(self, options):
        from django.db.models import Sum, F, FloatField
        from django.db.models.functions import Cast
        from nba.models import NBATeam, TeamOutseasonMove

        draft_years = [int(y) for y in options["draft_years"].split(",")]
        dbid_by_nbaid = {p.player_id: p.id for p in NBAPlayer.objects.all()}

        classes: dict[int, list[dict]] = {}
        league_minutes: dict[int, float] = {}
        for dy in draft_years:
            rows = self._collect_class_v2(dy, dbid_by_nbaid)
            # tier within class (median of that prior season's win table)
            wins_vals = sorted(set(r["prior_wins"] for r in rows if r["prior_wins"] is not None))
            med = statistics.median(wins_vals) if wins_vals else 41
            for r in rows:
                r["tier"] = self._tier(r["prior_wins"], med)
                # THE FITTED / PIN-ABLE QUANTITY IS EFFECTIVE MPG = total_min/82
                # (minutes per TEAM game). Per-game MPG ignores games played —
                # a 14-mpg-over-45-games rookie is not a 14-mpg-over-82-games
                # player. Fitting per-game MPG fails league closure by 3-4x
                # (the third bias, caught by this command's own closure check);
                # effective MPG closes within the historical band.
                r["mpg_pergame"] = r["mpg"]
                r["mpg"] = r["total_min"] / 82.0
            classes[dy] = rows
            # league total minutes for rookie season D+1 (closure denominator)
            agg = NBAPlayerSeasonStats.objects.filter(
                season__year=dy + 1, season_type="regular",
                mpg__isnull=False, gp__isnull=False,
            ).aggregate(t=Sum(Cast(F("mpg"), FloatField()) * Cast(F("gp"), FloatField())))
            league_minutes[dy] = float(agg["t"] or 0.0)
            time.sleep(0.6)

        # ── Census ──────────────────────────────────────────────────────────
        self.stdout.write(f"\n{'='*70}\nV2 CENSUS — full rounds-1-2 universe (survivor-corrected)")
        self.stdout.write(
            f"  {'class':>7} {'picks':>6} {'in DB':>6} {'zero-min':>9} "
            f"{'mean eff-mpg':>13} {'mean pergame':>13}"
        )
        for dy, rows in classes.items():
            zero = sum(1 for r in rows if r["mpg"] == 0.0)
            self.stdout.write(
                f"  {dy}→{dy+1:<4} {len(rows):>6} {sum(1 for r in rows if r['in_db']):>6} "
                f"{zero:>9} {statistics.mean([r['mpg'] for r in rows]):>13.1f} "
                f"{statistics.mean([r['mpg_pergame'] for r in rows]):>13.1f}"
            )

        all_rows = [r for rows in classes.values() for r in rows]

        # ── Model (a): 4 pick bins × 2 tiers ───────────────────────────────
        cell_means, bin_means, global_mean, cells = self._fit_cells(all_rows)
        self.stdout.write(f"\nMODEL (a) — pick bin × prior-wins tier cells (pooled):")
        self.stdout.write(f"  {'bin':>7} {'tier':>5} {'N':>5} {'mean':>7} {'σ':>6}")
        for (lbl, tier), vals in sorted(cells.items()):
            warn = "  ← N < 12" if len(vals) < 12 else ""
            self.stdout.write(
                f"  {lbl:>7} {tier:>5} {len(vals):>5} {statistics.mean(vals):>7.1f} "
                f"{(statistics.pstdev(vals) if len(vals)>1 else 0):>6.1f}{warn}"
            )

        # ── Model (b): additive ─────────────────────────────────────────────
        effects, b_wins, r2 = self._fit_additive(all_rows)
        self.stdout.write(f"\nMODEL (b) — additive: mpg = bin_effect + b·(prior_wins − 41)")
        for lbl, e in effects.items():
            self.stdout.write(f"  bin {lbl}: {e:+.2f}")
        self.stdout.write(f"  b (per prior win): {b_wins:+.3f}   R²={r2:.3f}")

        # ── LOYO ────────────────────────────────────────────────────────────
        self.stdout.write(f"\nLOYO (held-out class MAE on MPG, FULL universe incl. zeros):")
        self.stdout.write(
            f"  {'held-out':>9} {'N':>4} {'cells(a)':>9} {'additive(b)':>12} "
            f"{'12.0-hard':>10} {'4.5-bins':>9} {'global-mean':>12}"
        )
        agg = {k: [] for k in ("a", "b", "hard", "v45", "gmean")}
        for held in classes:
            test = classes[held]
            train = [r for dy, rows in classes.items() if dy != held for r in rows]
            c_m, b_m, g_m, _ = self._fit_cells(train)
            eff, bw, _ = self._fit_additive(train)
            # 4.5-bins baseline = the SHIPPED 4.5 model's claim: its qualifier-
            # conditional per-game bin means pinned as if they were effective
            # (that conflation was exactly its bias — score it as shipped).
            q_means = {"1-5": 27.9, "6-14": 20.9, "15-30": 16.4, "31-60": 13.0}
            errs = {k: [] for k in agg}
            for r in test:
                lbl = _bin_label(r["pick"])
                if lbl is None:
                    continue
                actual = r["mpg"]
                errs["a"].append(abs(c_m.get((lbl, r["tier"]), b_m.get(lbl, g_m)) - actual))
                pw = (r["prior_wins"] - 41.0) if r["prior_wins"] is not None else 0.0
                errs["b"].append(abs(eff.get(lbl, g_m) + bw * pw - actual))
                errs["hard"].append(abs(12.0 - actual))
                errs["v45"].append(abs(q_means.get(lbl, g_m) - actual))
                errs["gmean"].append(abs(g_m - actual))
            self.stdout.write(
                f"  {held}→{held+1:<3} {len(errs['a']):>4} "
                f"{statistics.mean(errs['a']):>9.2f} {statistics.mean(errs['b']):>12.2f} "
                f"{statistics.mean(errs['hard']):>10.2f} {statistics.mean(errs['v45']):>9.2f} "
                f"{statistics.mean(errs['gmean']):>12.2f}"
            )
            for k in agg:
                agg[k] += errs[k]
        self.stdout.write(
            f"  {'POOLED':>9} {len(agg['a']):>4} "
            f"{statistics.mean(agg['a']):>9.2f} {statistics.mean(agg['b']):>12.2f} "
            f"{statistics.mean(agg['hard']):>10.2f} {statistics.mean(agg['v45']):>9.2f} "
            f"{statistics.mean(agg['gmean']):>12.2f}"
        )

        # ── Closure check (all quantities in Σ effective-MPG units) ──────────
        # Actual class Σeff = class total minutes / 82; a candidate passes if
        # its implied Σeff for the CURRENT 60-pick class sits inside the
        # historical actual band. (Real-minutes share ≈ Σeff·82/league_min is
        # printed for context — this is the ~8% number; the pool-share number
        # is Σeff/3000 because the 5.0-share pool ≈ 100 'MPG' by convention.)
        self.stdout.write(f"\nCLOSURE — class Σ effective-MPG (total_min/82):")
        eff_totals = []
        for dy, rows in classes.items():
            cls_min = sum(r["total_min"] for r in rows)
            eff_tot = cls_min / 82.0
            eff_totals.append(eff_tot)
            lg = league_minutes[dy]
            self.stdout.write(
                f"  actual {dy+1}: Σeff = {eff_tot:,.0f}   "
                f"(real-minutes share {cls_min/lg*100 if lg else float('nan'):.1f}%)"
            )
        lo_band, hi_band = min(eff_totals), max(eff_totals)
        self.stdout.write(f"  historical Σeff band: {lo_band:.0f}–{hi_band:.0f}")

        # candidate implied Σeff for the CURRENT 60-pick class
        cur_wins = self._team_wins(2026)
        wins_vals = sorted(cur_wins.values())
        med_cur = statistics.median(wins_vals) if wins_vals else 41
        moves = list(
            TeamOutseasonMove.objects.filter(move_type="drafted")
            .select_related("team")
        )
        tot = {"a": 0.0, "b": 0.0, "v45": 0.0}
        for m in moves:
            lbl = _bin_label(m.overall_pick or 45) or "31-60"
            w = cur_wins.get(m.team.team_abbr)
            tier = self._tier(w, med_cur)
            tot["a"] += cell_means.get((lbl, tier), bin_means.get(lbl, global_mean))
            pw = (w - 41.0) if w is not None else 0.0
            tot["b"] += effects.get(lbl, global_mean) + b_wins * pw
            tot["v45"] += {"1-5": 27.9, "6-14": 20.9, "15-30": 16.4, "31-60": 13.0}[lbl]
        for k, label in (("a", "cells (a)"), ("b", "additive (b)"), ("v45", "4.5 bins")):
            verdict = "PASS" if lo_band <= tot[k] <= hi_band else "FAIL"
            self.stdout.write(
                f"  implied current-class Σeff, {label:12}: {tot[k]:.0f}  → {verdict}"
            )

        self.stdout.write(self.style.WARNING(
            "\nHUMAN REVIEW GATE — v2 report only, nothing committed. "
            "Production remains pin-OFF (2.2-nopin)."
        ))
