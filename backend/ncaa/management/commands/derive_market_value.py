"""
derive_market_value — Macfax Player Market Value chain derivation.

Phase 6 Stage 1 (REPORT ONLY — commits nothing, writes nothing).

Chain: BPR → marginal team EM → marginal wins → dollars.
Valuation basis: current-season ACTUALS (PlayerSeasonStats-side BPR +
minutes for the most recent complete season), not projections.

STEP 1 — WINS_PER_EM_NCAA
  D1-vs-D1 wins per team from Game results (both teams D1, final scores),
  joined to final post-tournament TeamSeasonRatings (explicit
  is_pre_tournament=False on all_objects — the Phase 3 trap — with a
  one-row-per-team assertion). Two candidate conventions:
    A) OLS actual D1 wins ~ AdjEM (schedule-blind), with residuals reported
       by conference tier (power vs mid, ncaa/conf_utils) and vs mean
       opponent EM — quantifying the schedule bias, not assuming it.
    B) Common-schedule: logistic P(win) ~ ΔEM (+HCA) fit on pooled D1vD1
       game outcomes; expected wins on a 30-game league-average schedule =
       30·σ(k·EM). Marginal wins/EM at the roster's EM is 30·k·σ(1−σ).
       (Comparative product → schedule-neutral convention, same logic as
       Phase 3's D1 demeaning ruling.)

STEP 2 — Player marginal wins
  Actuals-side replacement constants derived analogously to Phase 1's
  projection-side method: per team, rank players by actual mpg; the
  rank>8 pool's minutes-weighted mean obpr/dbpr = replacement. (Derived
  fresh; compared against — never assumed equal to — the projection-side
  REPLACEMENT_FILL constants.)
    marginal_EM  = SLOPE_OFF·share·(obpr−repl_o) + SLOPE_DEF·share·(dbpr−repl_d)
    share        = mpg/40 (the codebase's 5.0-pool convention)
    marginal_wins = marginal_EM × wins_per_EM (Step 1 convention)
  Slopes reused from committed team_projection constants — never re-derived
  here.

STEP 3 — Dollar anchor (rev-share, carried as a RANGE)
  2026-27 school rev-share cap ≈ $21.3M; public reporting puts typical
  power-conference MBB allocations at ~15–25% of pool → effective MBB pool
  ≈ $3.2–5.3M. $/marginal-win = pool / (median power-conference roster's
  total marginal wins). No repo doc supplies a sharper share; the range IS
  the honest anchor.

STEP 4 — CLOSURE (house doctrine)
  Implied roster value for named programs across tiers vs publicly
  reported top-roster spend ($5–10M+). Note the built-in calibration:
  $/win is anchored to the MEDIAN power roster, so closure tests the
  SPREAD (do top rosters imply top-market totals), not the center.

Usage:
    python manage.py derive_market_value --season 2026 --wins-seasons 2022,2023,2024,2025,2026
"""

from __future__ import annotations

import math
import statistics

from django.core.management.base import BaseCommand, CommandError

from ncaa.conf_utils import get_conf_group
from ncaa.models import Game, PlayerSeasonStats, Season, TeamSeasonRatings
from ncaa.analytics.player_value.team_projection.constants import (
    REPLACEMENT_FILL_DBPR,
    REPLACEMENT_FILL_OBPR,
    SLOPE_DEF,
    SLOPE_OFF,
)

CAP_TOTAL = 21_300_000          # 2026-27 school rev-share cap (public reporting)
MBB_SHARE_RANGE = (0.15, 0.25)  # typical power-conference MBB allocation share
COMMON_SCHEDULE_GAMES = 30      # league-average D1 schedule length for convention B


def _sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


class Command(BaseCommand):
    help = "Market-value chain derivation (report only)."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, default=2026,
                            help="Valuation season (actuals side).")
        parser.add_argument("--wins-seasons", type=str, default="2022,2023,2024,2025,2026",
                            help="Seasons pooled for the wins~EM fit.")

    def handle(self, *args, **options):
        season_year = options["season"]
        wins_years = [int(y) for y in options["wins_seasons"].split(",")]

        wpe_a, wpe_b, k_logit = self._step1_wins_per_em(wins_years)
        repl_o, repl_d, pool_n = self._step2_replacement(season_year)
        players = self._step2_marginal_wins(season_year, repl_o, repl_d, wpe_b)
        dollars_lo, dollars_hi = self._step3_dollars(players)
        self._step4_closure(players, dollars_lo, dollars_hi)

        self.stdout.write(self.style.WARNING(
            "\nHUMAN REVIEW GATE — report only; nothing committed, nothing "
            "written. Methodology draft is a separate deliverable."
        ))

    # ── STEP 1 ────────────────────────────────────────────────────────────────

    def _d1_wins(self, year: int) -> dict[int, tuple[int, int]]:
        """team_id → (d1_wins, d1_games) from final-scored D1-vs-D1 games."""
        rec: dict[int, list[int]] = {}
        qs = Game.objects.filter(
            season_year=year,
            home_team__is_d1=True, away_team__is_d1=True,
        ).exclude(home_score=0, away_score=0).only(
            "home_team_id", "away_team_id", "home_score", "away_score"
        )
        for g in qs:
            if g.home_score is None or g.away_score is None:
                continue
            if g.home_score == g.away_score:
                continue
            hw = g.home_score > g.away_score
            for tid, won in ((g.home_team_id, hw), (g.away_team_id, not hw)):
                w, n = rec.get(tid, (0, 0))
                rec[tid] = (w + (1 if won else 0), n + 1)
        return rec

    def _final_ratings(self, year: int) -> dict[int, float]:
        """team_id → adj_em, final snapshot, EXPLICIT filter + one-row assert."""
        rows = list(
            TeamSeasonRatings.all_objects.filter(
                season__year=year, is_pre_tournament=False, team__is_d1=True,
            ).values("team_id", "adj_em")
        )
        seen: dict[int, int] = {}
        for r in rows:
            seen[r["team_id"]] = seen.get(r["team_id"], 0) + 1
        dupes = [t for t, c in seen.items() if c > 1]
        if dupes:
            raise CommandError(
                f"{year}: {len(dupes)} teams with >1 final ratings row — aborting."
            )
        return {r["team_id"]: float(r["adj_em"]) for r in rows}

    def _step1_wins_per_em(self, years):
        self.stdout.write(f"\n{'='*70}\nSTEP 1 — WINS_PER_EM_NCAA (D1-vs-D1 only)")
        pooled = []           # (em, wins, games, conf_group, team_id, year)
        game_pairs = []       # (em_diff signed toward home, home_won, neutral)
        slug_by_id = {}
        from ncaa.models import Team
        for t in Team.objects.filter(is_d1=True).only("id", "slug"):
            slug_by_id[t.id] = t.slug

        for yr in years:
            ems = self._final_ratings(yr)
            recs = self._d1_wins(yr)
            n = 0
            for tid, (w, g) in recs.items():
                if tid not in ems or g < 15:
                    continue
                pooled.append((ems[tid], w, g, get_conf_group(slug_by_id.get(tid, "")), tid, yr))
                n += 1
            # game-level pairs for convention B
            for gobj in Game.objects.filter(
                season_year=yr, home_team__is_d1=True, away_team__is_d1=True,
            ).exclude(home_score=0, away_score=0).only(
                "home_team_id", "away_team_id", "home_score", "away_score", "neutral_site"
            ):
                if gobj.home_score is None or gobj.away_score is None or gobj.home_score == gobj.away_score:
                    continue
                if gobj.home_team_id in ems and gobj.away_team_id in ems:
                    game_pairs.append((
                        ems[gobj.home_team_id] - ems[gobj.away_team_id],
                        1.0 if gobj.home_score > gobj.away_score else 0.0,
                        bool(gobj.neutral_site),
                    ))
            self.stdout.write(f"  {yr}: {n} teams joined (>=15 D1 games)")

        # Convention A: OLS wins ~ EM (per-30-game normalized)
        xs = [p[0] for p in pooled]
        ys = [p[1] * 30.0 / p[2] for p in pooled]   # wins per 30 games
        mx, my = statistics.mean(xs), statistics.mean(ys)
        b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
        a = my - b * mx
        resid = [y - (a + b * x) for x, y in zip(xs, ys)]
        r = 1 - sum(e * e for e in resid) / sum((y - my) ** 2 for y in ys)
        self.stdout.write(
            f"\n  Convention A (OLS, wins/30 ~ EM): wins30 = {a:.2f} + {b:.3f}·EM"
            f"   R²={r:.3f}  N={len(pooled)}"
        )
        # residuals by conference tier
        for grp in ("power", "mid_major"):
            rs = [e for e, p in zip(resid, pooled) if p[3] == grp]
            self.stdout.write(
                f"    residual, {grp:9}: mean {statistics.mean(rs):+.2f} wins/30 (n={len(rs)})"
            )
        # residual vs EM curvature check (tails)
        hi = [e for e, p in zip(resid, pooled) if p[0] > 15]
        lo = [e for e, p in zip(resid, pooled) if p[0] < -10]
        self.stdout.write(
            f"    residual, EM>+15: {statistics.mean(hi):+.2f} (n={len(hi)})   "
            f"EM<-10: {statistics.mean(lo):+.2f} (n={len(lo)}) — linearity check"
        )

        # Convention B: logistic P(home win) ~ k·ΔEM + hca (neutral games get no hca)
        k, hca = self._fit_logistic(game_pairs)
        wpe_b = COMMON_SCHEDULE_GAMES * k * 0.25  # dσ/dx at 0 = 1/4
        self.stdout.write(
            f"\n  Convention B (game-level logistic): P(win) = σ({k:.4f}·ΔEM"
            f" + {hca:.3f}·home)   N={len(game_pairs)} games"
        )
        self.stdout.write(
            f"    marginal wins/EM at EM=0 on a {COMMON_SCHEDULE_GAMES}-game common "
            f"schedule: {wpe_b:.3f}"
        )
        self.stdout.write(
            f"    (curve: EM+10 → {COMMON_SCHEDULE_GAMES*_sigmoid(k*10):.1f} wins; "
            f"EM+20 → {COMMON_SCHEDULE_GAMES*_sigmoid(k*20):.1f}; flattens at the top — "
            f"marginal wins/EM at EM=20: {COMMON_SCHEDULE_GAMES*k*_sigmoid(k*20)*(1-_sigmoid(k*20)):.3f})"
        )
        return b, wpe_b, k

    def _fit_logistic(self, pairs):
        """2-param logistic (k on ΔEM, hca intercept for non-neutral) via scipy MLE."""
        import numpy as np
        from scipy.optimize import minimize

        d = np.array([p[0] for p in pairs])
        y = np.array([p[1] for p in pairs])
        h = np.array([0.0 if p[2] else 1.0 for p in pairs])

        def nll(theta):
            z = theta[0] * d + theta[1] * h
            # numerically stable log-loss
            return float(np.mean(np.logaddexp(0.0, z) - y * z))

        res = minimize(nll, x0=[0.1, 0.4], method="Nelder-Mead",
                       options={"xatol": 1e-6, "fatol": 1e-9, "maxiter": 2000})
        k, hca = float(res.x[0]), float(res.x[1])
        if not (0.01 < k < 0.5):
            raise CommandError(
                f"logistic fit implausible (k={k:.4f}); expected ~0.10-0.20 per "
                "EM point — refusing to propagate a broken wins/EM downstream."
            )
        return k, hca

    # ── STEP 2 ────────────────────────────────────────────────────────────────

    def _step2_replacement(self, year):
        self.stdout.write(f"\n{'='*70}\nSTEP 2 — actuals-side replacement level ({year})")
        rows = list(
            PlayerSeasonStats.objects.filter(
                season__year=year, team__is_d1=True,
                mpg__isnull=False, gp__isnull=False,
                obpr__isnull=False, dbpr__isnull=False,
            ).values("team_id", "player_id", "mpg", "gp", "obpr", "dbpr")
        )
        by_team: dict[int, list] = {}
        for r in rows:
            by_team.setdefault(r["team_id"], []).append(r)
        pool = []
        for tid, rs in by_team.items():
            rs.sort(key=lambda r: -(r["mpg"] or 0))
            pool.extend(rs[8:])   # rotation_rank > 8 analogue on actual minutes
        tot_min = sum((r["mpg"] or 0) * (r["gp"] or 0) for r in pool)
        repl_o = sum(r["obpr"] * (r["mpg"] or 0) * (r["gp"] or 0) for r in pool) / tot_min
        repl_d = sum(r["dbpr"] * (r["mpg"] or 0) * (r["gp"] or 0) for r in pool) / tot_min
        self.stdout.write(
            f"  actuals replacement (rank>8 by mpg, minutes-weighted, N={len(pool)}):"
            f"  obpr={repl_o:+.4f}  dbpr={repl_d:+.4f}"
        )
        self.stdout.write(
            f"  projection-side constants (Phase 1, for comparison, NOT reused):"
            f"  obpr={REPLACEMENT_FILL_OBPR:+.4f}  dbpr={REPLACEMENT_FILL_DBPR:+.4f}"
        )
        return repl_o, repl_d, len(pool)

    def _step2_marginal_wins(self, year, repl_o, repl_d, wpe):
        rows = list(
            PlayerSeasonStats.objects.filter(
                season__year=year, team__is_d1=True,
                mpg__isnull=False, obpr__isnull=False, dbpr__isnull=False,
            ).select_related("player", "team")
        )
        players = []
        for r in rows:
            share = (r.mpg or 0) / 40.0
            mem = (SLOPE_OFF * share * (r.obpr - repl_o)
                   + SLOPE_DEF * share * (r.dbpr - repl_d))
            players.append({
                "name": r.player.display_name,
                "team": r.team.name, "slug": r.team.slug,
                "conf_group": get_conf_group(r.team.slug),
                "mpg": r.mpg, "bpr": (r.obpr + r.dbpr),
                "m_em": mem, "m_wins": mem * wpe,
                "team_id": r.team_id,
            })
        players.sort(key=lambda p: -p["m_wins"])
        self.stdout.write(f"\n  Top 10 nationally by marginal wins ({year} actuals):")
        for p in players[:10]:
            self.stdout.write(
                f"    {p['name']:26} {p['team']:16} mpg={p['mpg']:.1f} "
                f"bpr={p['bpr']:+.2f}  mEM={p['m_em']:+.2f}  mWins={p['m_wins']:+.2f}"
            )
        # medians by role
        by_team: dict[int, list] = {}
        for p in players:
            by_team.setdefault(p["team_id"], []).append(p)
        power_starters, rotations, bench = [], [], []
        for tid, ps in by_team.items():
            ps.sort(key=lambda p: -p["mpg"])
            if ps and ps[0]["conf_group"] == "power":
                power_starters.extend(ps[:5])
            rotations.extend(ps[:8])
            bench.extend(ps[10:])
        self.stdout.write(
            f"  median power-conference starter mWins: "
            f"{statistics.median([p['m_wins'] for p in power_starters]):+.3f} "
            f"(n={len(power_starters)})"
        )
        self.stdout.write(
            f"  median rotation player (top-8) mWins: "
            f"{statistics.median([p['m_wins'] for p in rotations]):+.3f} (n={len(rotations)})"
        )
        self.stdout.write(
            f"  median bench (rank>10) mWins: "
            f"{statistics.median([p['m_wins'] for p in bench]):+.3f} (n={len(bench)}) "
            f"— plausibility: should sit ≈ 0"
        )
        return players

    # ── STEP 3 ────────────────────────────────────────────────────────────────

    def _step3_dollars(self, players):
        self.stdout.write(f"\n{'='*70}\nSTEP 3 — dollar anchor (rev-share range)")
        by_team: dict[int, dict] = {}
        for p in players:
            t = by_team.setdefault(p["team_id"], {"conf": p["conf_group"], "tot": 0.0})
            t["tot"] += max(p["m_wins"], 0.0)   # negative-marginal players don't refund the pool
        power_totals = sorted(t["tot"] for t in by_team.values() if t["conf"] == "power")
        med_power = statistics.median(power_totals)
        pool_lo = CAP_TOTAL * MBB_SHARE_RANGE[0]
        pool_hi = CAP_TOTAL * MBB_SHARE_RANGE[1]
        dol_lo, dol_hi = pool_lo / med_power, pool_hi / med_power
        self.stdout.write(
            f"  cap ${CAP_TOTAL/1e6:.1f}M × MBB share {MBB_SHARE_RANGE[0]:.0%}–"
            f"{MBB_SHARE_RANGE[1]:.0%} → pool ${pool_lo/1e6:.1f}M–${pool_hi/1e6:.1f}M"
        )
        self.stdout.write(
            f"  median power roster Σ positive mWins: {med_power:.2f} "
            f"(n={len(power_totals)} power rosters)"
        )
        self.stdout.write(
            f"  $/marginal-win: ${dol_lo/1e3:,.0f}k – ${dol_hi/1e3:,.0f}k"
        )
        self.stdout.write(
            "  Anchor B (third-party NIL multiplier): DECLINED — no defensible "
            "public multiplier exists (On3 figures are model estimates, not "
            "payments; CSC-cleared deals are a non-representative fraction). "
            "Documented decline per Phase 3 D3 pattern; revisit only if a "
            "sourced multiplier appears."
        )
        return dol_lo, dol_hi

    # ── STEP 4 ────────────────────────────────────────────────────────────────

    def _step4_closure(self, players, dol_lo, dol_hi):
        self.stdout.write(f"\n{'='*70}\nSTEP 4 — CLOSURE vs reported roster spend")
        self.stdout.write(
            "  (note: $/win is anchored to the MEDIAN power roster, so the median "
            "closes by construction — this table tests the SPREAD.)"
        )
        by_slug: dict[str, float] = {}
        for p in players:
            by_slug[p["slug"]] = by_slug.get(p["slug"], 0.0) + max(p["m_wins"], 0.0)
        programs = ["duke", "florida", "kansas", "gonzaga", "vermont"]
        self.stdout.write(f"  {'program':12} {'Σ mWins':>8} {'implied value range':>28}")
        for slug in programs:
            tot = by_slug.get(slug)
            if tot is None:
                self.stdout.write(f"  {slug:12} — no data")
                continue
            self.stdout.write(
                f"  {slug:12} {tot:8.2f}   ${tot*dol_lo/1e6:5.2f}M – ${tot*dol_hi/1e6:5.2f}M"
            )
        self.stdout.write(
            "  public reference: top-tier MBB roster spend reported in the "
            "$5–10M+ region (2025-26 reporting)."
        )
