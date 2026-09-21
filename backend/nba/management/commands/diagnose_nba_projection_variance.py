"""
diagnose_nba_projection_variance — READ-ONLY diagnostic on the NBA team
outlook projection variance. WRITES NOTHING (no DB rows, no constants).

Four sections:
  D1  Persistence baseline: adj_net(Y+1) ~ adj_net(Y), pooled over the same
      pairs + season_type filter derive_nba_slope uses (2025→2026 excluded).
  D2  Current projection spread: mean/SD/min/max of projected_adj_net,
      projected_wins (stored) and team_pv (recomputed in-memory).
  D3  PV source composition: per-team minutes-weighted bpr_fallback share,
      plus pooled SD of pv_effective for stored vs fallback slots.
  D4  Ceiling binding: per-team count of slots at MINUTES_CEIL vs
      projected_adj_net.

The team_pv / pv_source / minutes_share numbers are recomputed by driving the
production compute_nba_team_outlooks pass-1 methods (same allocator, same
shrinkage, same PV fallback) so the diagnostic reflects production exactly.
No instance of this command persists anything.

Usage:
    python manage.py diagnose_nba_projection_variance
    python manage.py diagnose_nba_projection_variance --source-season 2026
"""

import math
import statistics

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Avg, StdDev

from nba.models import (
    NBASeason,
    NBATeam,
    NBAPlayerSeasonStats,
    NBATeamSeasonRatings,
    TeamSeasonOutlook,
)

# Production allocator / shrinkage constants and the pass-1 compute methods.
from nba.management.commands import compute_nba_team_outlooks as cto
from nba.management.commands.compute_nba_team_outlooks import (
    Command as ComputeCommand,
    MIN_MPG,
    MINUTES_FLOOR,
    MINUTES_CEIL,
    SHRINKAGE_RETURNER,
    SHRINKAGE_ACQUISITION,
    REPLACEMENT_LEVEL,
    POWER_EXPONENT,
    PV_SLOPE,
    ROOKIE_PRIOR_OBPR,
    ROOKIE_PRIOR_DBPR,
    rookie_eff_mpg,
)

ROOKIE_PRIOR_BPR = ROOKIE_PRIOR_OBPR + ROOKIE_PRIOR_DBPR
# Returner-roster minutes allocator used by the SLOPE derivation — reused here
# for the historical PV predictor. `dns` (module handle) is patched in-memory by
# J1/J2 to sweep TOTAL_SHARES / MINUTES_CEIL, then restored.
from nba.management.commands import derive_nba_slope as dns
from nba.management.commands.derive_nba_slope import (
    _allocate_minutes as _ds_allocate,
    _through_origin_fit,
)

# Same pairs + exclusion as derive_nba_slope (2025→2026 is stale-lineage).
PERSISTENCE_PAIRS = [(2022, 2023), (2023, 2024), (2024, 2025)]
# D1 pooled through-origin persistence slope (adj_net(Y+1) ~ adj_net(Y)).
PERSISTENCE_SLOPE = 0.598
# Z4-fitted pool-12 wins-added scalar: Σ(share×bpr)@pool12 → (wins − 20).
WINS_ADDED_SCALAR_P12 = 1.1287


def _pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx <= 0 or syy <= 0:
        return float("nan")
    return sxy / math.sqrt(sxx * syy)


def _ols_with_intercept(xs, ys):
    """Return (slope, intercept, r, rmse) for y = a + b·x."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx > 0 else float("nan")
    intercept = my - slope * mx
    r = _pearson(xs, ys)
    resid_sq = [(y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys)]
    rmse = math.sqrt(sum(resid_sq) / n)
    return slope, intercept, r, rmse


class Command(BaseCommand):
    help = (
        "Read-only diagnostic on NBA outlook projection variance (D1–D4). "
        "Writes nothing — report only."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-season", type=int, default=None,
            help="Source season year (default: current season). E.g. 2026 for 2025-26.",
        )
        parser.add_argument(
            "--z0-only", action="store_true",
            help="Run ONLY the Z0 2026-BPR lineage gate (blocking check) and stop. "
                 "Cheapest path to the go/no-go before spending compute on the batch.",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING(
            "READ-ONLY DIAGNOSTIC — no DB writes, no constant changes.\n"
        ))

        if options["z0_only"]:
            self._z0_bpr_lineage(options["source_season"] or 2026)
            return

        self._d1_persistence_baseline()
        source_season = self._resolve_source_season(options["source_season"])
        team_data, league_pv_mean, league_bpr = self._recompute_team_pv(source_season)
        self._d2_current_spread(team_data, league_pv_mean)
        flagged = self._d3_pv_source_composition(team_data)
        self._d4_ceiling_binding(team_data)

        # ── Phase 2 ──
        self._e1_fallback_root_cause(team_data, flagged)
        self._e2_resolvable_share(team_data)
        self._e3_fallback_constant(team_data, league_bpr)
        self._e4_prediction_correlation(team_data, source_season)
        self._e5_utah(team_data)

        # ── Phase 3 ──  (G3 mutates team_data minutes_share — run G1/G2 first)
        self._g1_unit_audit(team_data)
        self._g2_closure_share_space(team_data)
        self._g3_counterfactual_pool(team_data)
        self._h_delta_signal()

        # ── Phase 4 ──
        self._j1_pool12_skill()
        self._j2_ceiling_sensitivity()
        self._k_persistence_allocator()

        # ── Phase 5 ── Z0 is the blocking gate: FAIL voids T1/T2/Z1–Z4.
        if self._z0_bpr_lineage(source_season.year):
            best_n = self._t1_tanking()
            self._t2_asymmetry()
            self._z1_joint_fit(best_n)
            self._z2_loyo()
            self._z3_delta_metric()
            self._z4_wins_added()
            self._z5_loyo_pv_delta()
            self._z6_wins_closure()
        else:
            self.stdout.write(self.style.ERROR(
                "Z0 FAILED — T1/T2/Z1–Z4 skipped (void per gate)."))

        self.stdout.write(self.style.WARNING(
            "\nGATE: report only — no fixes proposed or applied."
        ))

    # ── D1 ──────────────────────────────────────────────────────────────────────

    def _d1_persistence_baseline(self):
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            "D1 — PERSISTENCE BASELINE  adj_net(Y+1) ~ adj_net(Y)"))
        self.stdout.write(self.style.SUCCESS("=" * 72))

        pooled_x, pooled_y = [], []
        for src_year, tgt_year in PERSISTENCE_PAIRS:
            try:
                src = NBASeason.objects.get(year=src_year)
                tgt = NBASeason.objects.get(year=tgt_year)
            except NBASeason.DoesNotExist:
                self.stdout.write(self.style.ERROR(
                    f"  pair {src_year}→{tgt_year}: season row missing — skipped"))
                continue

            src_net = self._adj_net_by_team(src)
            tgt_net = self._adj_net_by_team(tgt)
            common = sorted(set(src_net) & set(tgt_net))
            xs = [src_net[t] for t in common]
            ys = [tgt_net[t] for t in common]
            pooled_x += xs
            pooled_y += ys

            if len(xs) >= 2:
                slope, intercept, r, rmse = _ols_with_intercept(xs, ys)
                self.stdout.write(
                    f"  {src_year}→{tgt_year}: n={len(xs)}  r={r:+.3f}  "
                    f"slope={slope:+.3f}  intercept={intercept:+.2f}  RMSE={rmse:.2f}  "
                    f"SD(Y)={statistics.stdev(xs):.2f} SD(Y+1)={statistics.stdev(ys):.2f}"
                )
            else:
                self.stdout.write(f"  {src_year}→{tgt_year}: n={len(xs)} — too few to fit")

        self.stdout.write("")
        if len(pooled_x) >= 2:
            slope, intercept, r, rmse = _ols_with_intercept(pooled_x, pooled_y)
            self.stdout.write(self.style.SUCCESS(
                f"  POOLED N={len(pooled_x)}:  r={r:+.3f}  slope={slope:+.3f}  "
                f"intercept={intercept:+.2f}  RMSE={rmse:.2f}"))
            self.stdout.write(
                f"    SD(adj_net Y)   = {statistics.stdev(pooled_x):.3f}\n"
                f"    SD(adj_net Y+1) = {statistics.stdev(pooled_y):.3f}"
            )
        else:
            self.stdout.write(self.style.ERROR("  POOLED: insufficient data"))
        self.stdout.write("")

    def _adj_net_by_team(self, season):
        """{team_id: adj_off - adj_def} for regular-season rows (derive_nba_slope parity)."""
        return {
            r.team_id: float(r.adj_off - r.adj_def)
            for r in NBATeamSeasonRatings.objects.filter(
                season=season, season_type="regular"
            )
            if r.adj_off is not None and r.adj_def is not None
        }

    # ── shared recompute (drives production pass-1) ─────────────────────────────

    def _resolve_source_season(self, source_year):
        if source_year is None:
            try:
                return NBASeason.objects.get(is_current=True)
            except NBASeason.DoesNotExist:
                raise CommandError("No current season flagged. Use --source-season YYYY.")
        try:
            return NBASeason.objects.get(year=source_year)
        except NBASeason.DoesNotExist:
            raise CommandError(f"Season {source_year} not found in DB.")

    def _recompute_team_pv(self, source_season):
        """
        Replicate compute_nba_team_outlooks pass 1 (roster assembly → BPR
        projection → PV fallback → minutes allocation) IN MEMORY, returning
        {outlook.pk: {"outlook", "slots"}} and league_pv_mean. Nothing persisted.
        """
        cmd = ComputeCommand()
        cmd.stdout = self.stdout
        cmd.stderr = self.stderr
        cmd.rookie_pin = True  # production default

        # League BPR shrinkage targets (mirror handle()).
        bpr_qs = NBAPlayerSeasonStats.objects.filter(
            season=source_season, season_type="regular", mpg__gte=MIN_MPG,
        )
        league_obpr_avg = bpr_qs.filter(obpr__isnull=False).aggregate(v=Avg("obpr"))["v"] or 0.0
        league_dbpr_avg = bpr_qs.filter(dbpr__isnull=False).aggregate(v=Avg("dbpr"))["v"] or 0.0
        league_bpr_avg  = bpr_qs.filter(bpr__isnull=False).aggregate(v=Avg("bpr"))["v"] or 0.0
        league_bpr_sd   = bpr_qs.filter(bpr__isnull=False).aggregate(v=StdDev("bpr"))["v"] or 1.0

        cmd.rapm_gap_sigma = cmd._compute_rapm_gap_sigma(source_season)
        self._cmd = cmd  # reused by E2 for name resolution

        team_data = {}
        for outlook in TeamSeasonOutlook.objects.all().order_by("team_abbr"):
            nba_team = (
                NBATeam.objects.filter(slug=outlook.team_slug).first()
                or NBATeam.objects.filter(abbreviation=outlook.team_abbr).first()
            )
            slots = cmd._assemble_roster(outlook, nba_team, source_season)
            if not slots:
                team_data[outlook.pk] = {"outlook": outlook, "slots": [], "nba_team": nba_team}
                continue
            for slot in slots:
                slot["projected_obpr"], slot["projected_dbpr"], slot["projected_bpr"] = (
                    cmd._project_bpr(slot, league_obpr_avg, league_dbpr_avg, league_bpr_avg)
                )
                lam = (SHRINKAGE_RETURNER
                       if slot.get("acquisition_type") in ("returner", "extended")
                       else SHRINKAGE_ACQUISITION)
                pv = slot.get("projection_value")
                if pv is None:
                    pv = ((slot.get("projected_bpr") or 0.0) - league_bpr_avg) / league_bpr_sd
                    slot["pv_source"] = "bpr_fallback"
                else:
                    pv = pv * (1.0 - lam)
                    slot["pv_source"] = "stored"
                slot["pv_effective"] = pv
            slots = cmd._allocate_minutes(slots)
            team_data[outlook.pk] = {"outlook": outlook, "slots": slots, "nba_team": nba_team}

        # League mean team_pv (minutes-weighted team mean, averaged across teams).
        team_pvs = []
        for td in team_data.values():
            slots = td["slots"]
            tot = sum(s.get("minutes_share", 0.0) for s in slots)
            if tot > 0:
                tpv = sum(s.get("minutes_share", 0.0) * s.get("pv_effective", 0.0)
                          for s in slots) / tot
                td["team_pv"] = tpv
                team_pvs.append(tpv)
            else:
                td["team_pv"] = None
        league_pv_mean = sum(team_pvs) / len(team_pvs) if team_pvs else 0.0
        return team_data, league_pv_mean, (league_bpr_avg, league_bpr_sd)

    # ── D2 ──────────────────────────────────────────────────────────────────────

    def _d2_current_spread(self, team_data, league_pv_mean):
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS("D2 — CURRENT PROJECTION SPREAD (30 TeamSeasonOutlook rows)"))
        self.stdout.write(self.style.SUCCESS("=" * 72))

        adj_net = [o.projected_adj_net for o in TeamSeasonOutlook.objects.all()
                   if o.projected_adj_net is not None]
        wins = [o.projected_wins for o in TeamSeasonOutlook.objects.all()
                if o.projected_wins is not None]
        team_pv = [td["team_pv"] for td in team_data.values() if td.get("team_pv") is not None]

        self._print_stats("projected_adj_net (stored)", adj_net)
        self._print_stats("projected_wins    (stored)", wins)
        self._print_stats("team_pv           (recomputed)", team_pv)
        self.stdout.write(f"  league_pv_mean (recomputed) = {league_pv_mean:+.4f}")
        self.stdout.write("")

    def _print_stats(self, label, vals):
        if not vals:
            self.stdout.write(f"  {label:32s}: no data")
            return
        sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
        self.stdout.write(
            f"  {label:32s}: n={len(vals):2d}  mean={statistics.mean(vals):+7.3f}  "
            f"SD={sd:6.3f}  min={min(vals):+7.3f}  max={max(vals):+7.3f}"
        )

    # ── D3 ──────────────────────────────────────────────────────────────────────

    def _d3_pv_source_composition(self, team_data):
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS("D3 — PV SOURCE COMPOSITION (minutes-weighted bpr_fallback share)"))
        self.stdout.write(self.style.SUCCESS("=" * 72))

        rows = []
        pooled_stored, pooled_fallback = [], []
        for td in team_data.values():
            slots = td["slots"]
            if not slots:
                continue
            tot = sum(s.get("minutes_share", 0.0) for s in slots)
            fb = sum(s.get("minutes_share", 0.0) for s in slots
                     if s.get("pv_source") == "bpr_fallback")
            frac = fb / tot if tot > 0 else 0.0
            rows.append((td["outlook"].team_abbr, frac))
            for s in slots:
                if s.get("pv_source") == "bpr_fallback":
                    pooled_fallback.append(s.get("pv_effective", 0.0))
                else:
                    pooled_stored.append(s.get("pv_effective", 0.0))

        fracs = [f for _, f in rows]
        mean = statistics.mean(fracs) if fracs else 0.0
        sd = statistics.stdev(fracs) if len(fracs) > 1 else 0.0
        flag_threshold = mean + sd

        rows.sort(key=lambda r: r[1], reverse=True)
        for abbr, frac in rows:
            flag = "  <<< FLAG (> mean+1SD)" if frac > flag_threshold else ""
            self.stdout.write(f"  {abbr:4s}  fallback share = {frac*100:5.1f}%{flag}")

        self.stdout.write("")
        self.stdout.write(
            f"  league fallback-share  mean={mean*100:.1f}%  SD={sd*100:.1f}%  "
            f"flag threshold={flag_threshold*100:.1f}%"
        )
        self.stdout.write(
            f"  pooled pv_effective SD — stored slots  : {self._sd(pooled_stored):.3f} "
            f"(n={len(pooled_stored)})"
        )
        self.stdout.write(
            f"  pooled pv_effective SD — fallback slots: {self._sd(pooled_fallback):.3f} "
            f"(n={len(pooled_fallback)})"
        )
        self.stdout.write("")
        return {abbr for abbr, frac in rows if frac > flag_threshold}

    @staticmethod
    def _sd(vals):
        return statistics.stdev(vals) if len(vals) > 1 else float("nan")

    # ── D4 ──────────────────────────────────────────────────────────────────────

    def _d4_ceiling_binding(self, team_data):
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS("D4 — CEILING BINDING (slots at MINUTES_CEIL vs projected_adj_net)"))
        self.stdout.write(self.style.SUCCESS("=" * 72))

        counts, nets = [], []
        detail = []
        for td in team_data.values():
            slots = td["slots"]
            if not slots:
                continue
            outlook = td["outlook"]
            net = outlook.projected_adj_net
            if net is None:
                continue
            n_ceil = sum(1 for s in slots
                         if s.get("minutes_share", 0.0) >= MINUTES_CEIL - 1e-6)
            counts.append(n_ceil)
            nets.append(net)
            detail.append((outlook.team_abbr, n_ceil, net))

        detail.sort(key=lambda d: (-d[1], -d[2]))
        for abbr, n_ceil, net in detail:
            self.stdout.write(f"  {abbr:4s}  ceil_slots={n_ceil}  projected_adj_net={net:+.2f}")

        r = _pearson(counts, nets) if len(counts) >= 2 else float("nan")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"  corr(ceiling_count, projected_adj_net) = {r:+.3f}  "
            f"(n={len(counts)}, MINUTES_CEIL={MINUTES_CEIL})"))
        self.stdout.write("")

    # ── E1 ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _classify_fallback(slot):
        """Why was projection_value None on this fallback slot?"""
        if slot.get("acquisition_type") == "drafted":
            return "a"  # legitimate rookie, no NBA history
        if slot.get("player_obj") is None:
            return "b"  # name resolution failed
        if slot.get("stats_obj") is None:
            return "c"  # player resolved, no prior_stats row
        if getattr(slot.get("stats_obj"), "projection_value", None) is None:
            return "d"  # prior_stats exists but its projection_value is NULL
        return "e"

    _CAT_LABEL = {
        "a": "drafted rookie (no NBA history)",
        "b": "player FK NULL (name resolution failed)",
        "c": "player FK ok, prior_stats FK NULL",
        "d": "prior_stats ok, projection_value NULL",
        "e": "other",
    }

    def _e1_fallback_root_cause(self, team_data, flagged):
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS("E1 — FALLBACK ROOT CAUSE (why projection_value was None)"))
        self.stdout.write(self.style.SUCCESS("=" * 72))

        league_total_min = 0.0
        cat_count = {k: 0 for k in self._CAT_LABEL}
        cat_min = {k: 0.0 for k in self._CAT_LABEL}
        per_team_cat_min = {}  # abbr -> {cat: minutes}
        per_team_total = {}    # abbr -> total minutes

        for td in team_data.values():
            slots = td["slots"]
            if not slots:
                continue
            abbr = td["outlook"].team_abbr
            tot = sum(s.get("minutes_share", 0.0) for s in slots)
            league_total_min += tot
            per_team_total[abbr] = tot
            per_team_cat_min.setdefault(abbr, {k: 0.0 for k in self._CAT_LABEL})
            for s in slots:
                if s.get("pv_source") != "bpr_fallback":
                    continue
                cat = self._classify_fallback(s)
                m = s.get("minutes_share", 0.0)
                cat_count[cat] += 1
                cat_min[cat] += m
                per_team_cat_min[abbr][cat] += m
                if cat == "e":
                    self.stdout.write(self.style.WARNING(
                        f"    [cat e] {abbr} {s.get('player_name')} "
                        f"acq={s.get('acquisition_type')} share={m:.3f}"))

        self.stdout.write("  LEAGUE-WIDE (share = fraction of all projected league minutes):")
        for k in self._CAT_LABEL:
            self.stdout.write(
                f"    ({k}) {self._CAT_LABEL[k]:44s} n={cat_count[k]:3d}  "
                f"min={cat_min[k]:6.2f}  share={cat_min[k]/league_total_min*100 if league_total_min else 0:5.1f}%"
            )

        self.stdout.write("\n  SEVEN FLAGGED TEAMS (share = fraction of that team's minutes):")
        for abbr in sorted(flagged):
            tot = per_team_total.get(abbr, 0.0) or 1.0
            parts = " ".join(
                f"{k}={per_team_cat_min[abbr][k]/tot*100:4.1f}%"
                for k in self._CAT_LABEL if per_team_cat_min[abbr][k] > 0
            )
            self.stdout.write(f"    {abbr:4s}  {parts}")
        self.stdout.write("")

    # ── E2 ──────────────────────────────────────────────────────────────────────

    def _e2_resolvable_share(self, team_data):
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            "E2 — RESOLVABLE SHARE (cats b/c/d that DO have a stored PV somewhere)"))
        self.stdout.write(self.style.SUCCESS("=" * 72))

        recoverable = []  # (share, name, abbr, cat)
        n_recoverable = 0
        min_recoverable = 0.0
        for td in team_data.values():
            slots = td["slots"]
            if not slots:
                continue
            abbr = td["outlook"].team_abbr
            for s in slots:
                if s.get("pv_source") != "bpr_fallback":
                    continue
                cat = self._classify_fallback(s)
                if cat not in ("b", "c", "d"):
                    continue
                player = s.get("player_obj")
                if player is None:
                    player = self._cmd._resolve_player_by_name(s.get("player_name", ""))
                if player is None:
                    continue
                has_pv = NBAPlayerSeasonStats.objects.filter(
                    player=player, projection_value__isnull=False
                ).exists()
                if has_pv:
                    n_recoverable += 1
                    m = s.get("minutes_share", 0.0)
                    min_recoverable += m
                    recoverable.append((m, s.get("player_name"), abbr, cat))

        self.stdout.write(
            f"  recoverable fallback slots: n={n_recoverable}  "
            f"total minutes-share={min_recoverable:.2f}  "
            f"(= {min_recoverable/(5.0*30)*100:.1f}% of league minutes)"
        )
        recoverable.sort(reverse=True)
        self.stdout.write("  top 30 by minutes share:")
        for m, name, abbr, cat in recoverable[:30]:
            self.stdout.write(f"    {abbr:4s}  ({cat})  share={m:.3f}  {name}")
        self.stdout.write("")

    # ── E3 ──────────────────────────────────────────────────────────────────────

    def _e3_fallback_constant(self, team_data, league_bpr):
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS("E3 — FALLBACK CONSTANT (pv_effective, fallback vs stored)"))
        self.stdout.write(self.style.SUCCESS("=" * 72))

        fb, st = [], []
        for td in team_data.values():
            for s in td["slots"]:
                (fb if s.get("pv_source") == "bpr_fallback" else st).append(
                    s.get("pv_effective", 0.0))

        def line(label, v):
            if not v:
                self.stdout.write(f"  {label:16s}: no data")
                return
            self.stdout.write(
                f"  {label:16s}: n={len(v):3d}  mean={statistics.mean(v):+.4f}  "
                f"SD={self._sd(v):.4f}  min={min(v):+.4f}  max={max(v):+.4f}")

        line("fallback slots", fb)
        line("stored slots", st)
        if fb and st:
            self.stdout.write(
                f"  Δ mean (fallback − stored) = "
                f"{statistics.mean(fb) - statistics.mean(st):+.4f}")
        league_bpr_avg, league_bpr_sd = league_bpr
        self.stdout.write(
            f"  line-325 inputs: league_bpr_avg={league_bpr_avg:+.4f}  "
            f"league_bpr_sd={league_bpr_sd:.4f}")
        self.stdout.write("")

    # ── E4 ──────────────────────────────────────────────────────────────────────

    def _e4_prediction_correlation(self, team_data, source_season):
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            "E4 — PREDICTION CORRELATION  ρ(PV predictor, persistence predictor)"))
        self.stdout.write(self.style.SUCCESS("=" * 72))

        # Current season: PV predictor = recomputed team_pv, persistence = adj_net(Y)×slope.
        src_net = self._adj_net_by_team(source_season)
        pv_vec, pers_vec = [], []
        for td in team_data.values():
            nba_team = td.get("nba_team")
            tpv = td.get("team_pv")
            if nba_team is None or tpv is None or nba_team.id not in src_net:
                continue
            pv_vec.append(tpv)
            pers_vec.append(src_net[nba_team.id] * PERSISTENCE_SLOPE)
        rho_now = _pearson(pv_vec, pers_vec) if len(pv_vec) >= 2 else float("nan")
        self.stdout.write(
            f"  CURRENT ({source_season.year}): ρ={rho_now:+.3f}  n={len(pv_vec)}")

        # Historical pairs: PV predictor = returner-roster team_pv for season Y.
        self.stdout.write("  HISTORICAL (returner-roster PV predictor vs persistence, season Y):")
        for src_year, _tgt in PERSISTENCE_PAIRS:
            try:
                src = NBASeason.objects.get(year=src_year)
            except NBASeason.DoesNotExist:
                continue
            hist_pv = self._historical_team_pv(src)
            hist_net = self._adj_net_by_team(src)
            common = sorted(set(hist_pv) & set(hist_net))
            a = [hist_pv[t] for t in common]
            b = [hist_net[t] * PERSISTENCE_SLOPE for t in common]
            rho = _pearson(a, b) if len(a) >= 2 else float("nan")
            self.stdout.write(f"    {src_year}: ρ={rho:+.3f}  n={len(a)}")
        self.stdout.write("")

    def _historical_team_pv(self, src):
        """{team_id: minutes-weighted team_pv} — wrapper over _historical_team_players."""
        team_players = self._historical_team_players(src)
        return {
            t: (sum(p["minutes_share"] * p["pv_effective"] for p in ps)
                / (sum(p["minutes_share"] for p in ps) or 1.0))
            for t, ps in team_players.items()
        }

    def _historical_team_players(self, src):
        """
        {team_id: [player dicts with minutes_share + pv_effective]} for a source
        season's returner rosters — mirrors derive_nba_slope._run_pair (same
        shrinkage, RAPM cap, allocator, PV-fallback). No offseason moves (none
        exist historically). Allocates via dns._allocate_minutes, which reads the
        dns module globals TOTAL_SHARES / MINUTES_CEIL — patched by J1/J2.
        """
        bpr_qs = NBAPlayerSeasonStats.objects.filter(
            season=src, season_type="regular", mpg__gte=MIN_MPG,
        )
        lg_obpr = bpr_qs.filter(obpr__isnull=False).aggregate(v=Avg("obpr"))["v"] or 0.0
        lg_dbpr = bpr_qs.filter(dbpr__isnull=False).aggregate(v=Avg("dbpr"))["v"] or 0.0
        lg_bpr  = bpr_qs.filter(bpr__isnull=False).aggregate(v=Avg("bpr"))["v"] or 0.0
        lg_bpr_sd = bpr_qs.filter(bpr__isnull=False).aggregate(v=StdDev("bpr"))["v"] or 1.0

        gap_qs = NBAPlayerSeasonStats.objects.filter(
            season=src, season_type="regular", gp__gte=20, mpg__gte=12,
            bpr__isnull=False, box_obpr__isnull=False, box_dbpr__isnull=False,
        ).only("bpr", "box_obpr", "box_dbpr")
        gaps = [float(r.bpr) - (float(r.box_obpr) + float(r.box_dbpr)) for r in gap_qs]
        cap_threshold = 1.6 * (statistics.stdev(gaps) if len(gaps) >= 20 else 3.5)

        rows = NBAPlayerSeasonStats.objects.filter(
            season=src, season_type="regular", mpg__gte=MIN_MPG, bpr__isnull=False,
        ).only("team_id", "mpg", "obpr", "dbpr", "bpr", "box_obpr", "box_dbpr",
               "projection_value")

        lam = SHRINKAGE_RETURNER
        team_players = {}
        for row in rows:
            if row.team_id is None:
                continue
            p = {
                "mpg": row.mpg or 15.0,
                "proj_obpr": (row.obpr or 0.0) * (1 - lam) + lg_obpr * lam,
                "proj_dbpr": (row.dbpr or 0.0) * (1 - lam) + lg_dbpr * lam,
                "proj_bpr":  (row.bpr  or 0.0) * (1 - lam) + lg_bpr  * lam,
                "projection_value": row.projection_value,
            }
            if row.box_obpr is not None and row.box_dbpr is not None:
                box_bpr = float(row.box_obpr) + float(row.box_dbpr)
                gap = p["proj_bpr"] - box_bpr
                if gap > cap_threshold:
                    excess = gap - cap_threshold
                    if abs(gap) > 0:
                        p["proj_obpr"] -= excess * (p["proj_obpr"] - float(row.box_obpr)) / gap
                        p["proj_dbpr"] -= excess * (p["proj_dbpr"] - float(row.box_dbpr)) / gap
                    p["proj_bpr"] -= excess
            if p["projection_value"] is None:
                p["pv_effective"] = (p["proj_bpr"] - lg_bpr) / lg_bpr_sd
            else:
                p["pv_effective"] = p["projection_value"] * (1.0 - lam)
            team_players.setdefault(row.team_id, []).append(p)

        for players in team_players.values():
            _ds_allocate(players)

        return team_players

    # ── E5 ──────────────────────────────────────────────────────────────────────

    def _e5_utah(self, team_data):
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS("E5 — UTAH JAZZ projected slot list"))
        self.stdout.write(self.style.SUCCESS("=" * 72))

        td = next((d for d in team_data.values()
                   if d["outlook"].team_slug == "utah-jazz"), None)
        if td is None:
            self.stdout.write(self.style.ERROR("  utah-jazz outlook not found"))
            self.stdout.write("")
            return
        slots = sorted(td["slots"], key=lambda s: s.get("minutes_share", 0.0), reverse=True)
        self.stdout.write(
            f"  {'player':26s} {'age':>3s} {'acq':>10s} {'pv_src':>12s} "
            f"{'proj_bpr':>9s} {'pv_eff':>8s} {'min_sh':>7s}")
        for s in slots:
            age = s.get("age")
            self.stdout.write(
                f"  {(s.get('player_name') or '?')[:26]:26s} "
                f"{(str(age) if age is not None else '-'):>3s} "
                f"{s.get('acquisition_type', '?'):>10s} "
                f"{s.get('pv_source', '?'):>12s} "
                f"{s.get('projected_bpr', 0.0):+9.2f} "
                f"{s.get('pv_effective', 0.0):+8.3f} "
                f"{s.get('minutes_share', 0.0):7.3f}")
        self.stdout.write("")

    # ── G1 ──────────────────────────────────────────────────────────────────────

    def _g1_unit_audit(self, team_data):
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            "G1 — UNIT AUDIT (share sums, implied MPG, pinned-rookie share)"))
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(
            f"  {'TM':4s} {'Σshare':>7s} {'max':>6s} {'MPG(×20)':>9s} "
            f"{'MPG(×48/5)':>11s} {'pinShr':>7s} {'pin%':>6s}")

        league_pin = 0.0
        league_share = 0.0
        for td in sorted(team_data.values(), key=lambda d: d["outlook"].team_abbr):
            slots = td["slots"]
            if not slots:
                continue
            abbr = td["outlook"].team_abbr
            tot = sum(s.get("minutes_share", 0.0) for s in slots)
            mx = max(s.get("minutes_share", 0.0) for s in slots)
            pin = sum(s.get("minutes_share", 0.0) for s in slots if s.get("is_rookie_prior"))
            league_pin += pin
            league_share += tot
            from nba.management.commands.compute_nba_team_outlooks import TOTAL_SHARES
            self.stdout.write(
                f"  {abbr:4s} {tot:7.3f} {mx:6.3f} {mx*20:9.1f} {mx*48/5:11.1f} "
                f"{pin:7.3f} {pin/TOTAL_SHARES*100:5.1f}%")
        self.stdout.write("")
        self.stdout.write(
            f"  LEAGUE pinned share = {league_pin:.2f} / {league_share:.2f} "
            f"= {league_pin/league_share*100 if league_share else 0:.1f}% of all shares")
        self.stdout.write("")

    # ── G2 ──────────────────────────────────────────────────────────────────────

    def _g2_closure_share_space(self, team_data):
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            "G2 — CLOSURE IN SHARE SPACE (implied season minutes vs 240×82)"))
        self.stdout.write(self.style.SUCCESS("=" * 72))
        ACTUAL_TEAM_MIN = 240 * 82  # 19,680
        ratios = []
        for td in sorted(team_data.values(), key=lambda d: d["outlook"].team_abbr):
            slots = td["slots"]
            if not slots:
                continue
            implied = sum(s.get("minutes_share", 0.0) * 20 * 82 for s in slots)
            ratio = implied / ACTUAL_TEAM_MIN
            ratios.append(ratio)
            self.stdout.write(
                f"  {td['outlook'].team_abbr:4s} implied_min={implied:8.0f}  "
                f"actual={ACTUAL_TEAM_MIN}  ratio={ratio:.3f}")
        mean_ratio = sum(ratios) / len(ratios) if ratios else 0.0
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"  LEAGUE MEAN ratio = {mean_ratio:.3f}  (1.000 = closed; "
            f"1/ratio = {1/mean_ratio if mean_ratio else 0:.2f}x under-sized pool)"))
        self.stdout.write("")

    # ── G3 ──────────────────────────────────────────────────────────────────────

    def _g3_counterfactual_pool(self, team_data):
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            "G3 — COUNTERFACTUAL POOL (TOTAL_SHARES 5.0 → 12.0, in-memory only)"))
        self.stdout.write(self.style.SUCCESS("=" * 72))

        # Capture BEFORE (already computed at TOTAL_SHARES=5.0).
        before = {}
        before_pin = {}
        for td in team_data.values():
            if not td["slots"]:
                continue
            before[td["outlook"].team_abbr] = td.get("team_pv")
            before_pin[td["outlook"].team_abbr] = sum(
                s.get("minutes_share", 0.0) for s in td["slots"] if s.get("is_rookie_prior"))

        # Re-allocate every roster with TOTAL_SHARES=12.0 (monkeypatch module global;
        # pv_effective is unchanged — only minutes_share weights shift).
        original = cto.TOTAL_SHARES
        after, after_pin = {}, {}
        try:
            cto.TOTAL_SHARES = 12.0
            for td in team_data.values():
                slots = td["slots"]
                if not slots:
                    continue
                self._cmd._allocate_minutes(slots)
                tot = sum(s.get("minutes_share", 0.0) for s in slots)
                tpv = (sum(s.get("minutes_share", 0.0) * s.get("pv_effective", 0.0)
                           for s in slots) / tot) if tot > 0 else 0.0
                abbr = td["outlook"].team_abbr
                after[abbr] = tpv
                after_pin[abbr] = sum(
                    s.get("minutes_share", 0.0) for s in slots if s.get("is_rookie_prior"))
        finally:
            cto.TOTAL_SHARES = original

        before_vals = [v for v in before.values() if v is not None]
        after_vals = [after[a] for a in before if a in after]
        self.stdout.write(
            f"  {'TM':4s} {'pv_before':>10s} {'pv_after':>9s} {'Δpv':>8s} "
            f"{'pin%_before':>11s} {'pin%_after':>11s}")
        for abbr in sorted(before):
            b, a = before[abbr], after.get(abbr)
            if b is None or a is None:
                continue
            pb = before_pin[abbr] / 5.0 * 100
            pa = after_pin[abbr] / 12.0 * 100
            self.stdout.write(
                f"  {abbr:4s} {b:+10.3f} {a:+9.3f} {a-b:+8.3f} "
                f"{pb:10.1f}% {pa:10.1f}%")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"  SD(team_pv) before = {self._sd(before_vals):.3f}  →  "
            f"after = {self._sd(after_vals):.3f}"))
        lp_b = sum(before_pin.values())
        lp_a = sum(after_pin.values())
        self.stdout.write(
            f"  league pinned share: {lp_b/(5.0*len(before))*100:.1f}% (pool 5.0) → "
            f"{lp_a/(12.0*len(after))*100:.1f}% (pool 12.0)")
        self.stdout.write("")

    # ── H1 / H2 / H3 ────────────────────────────────────────────────────────────

    def _h_delta_signal(self):
        records, player_rows = [], []
        for src_year, tgt_year in PERSISTENCE_PAIRS:
            rec, pr = self._build_pair_records(src_year, tgt_year)
            records += rec
            player_rows += pr
        self._records = records          # reused by K1/K2/K3
        self._player_rows = player_rows

        # H1 — residual ~ roster_delta (actual Y+1 minutes weighting).
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            "H1 — DELTA SIGNAL  residual(Y+1) ~ roster_delta   [actual Y+1 minutes]"))
        self.stdout.write(self.style.SUCCESS("=" * 72))
        xs = [r["delta_actual"] for r in records]
        ys = [r["residual"] for r in records]
        slope, intercept, rr, rmse = _ols_with_intercept(xs, ys)
        self.stdout.write(
            f"  N={len(records)}  r={rr:+.3f}  slope={slope:+.3f}  "
            f"intercept={intercept:+.3f}  RMSE={rmse:.3f}")
        self.stdout.write(
            f"  (residual = adj_net(Y+1) − {PERSISTENCE_SLOPE}×adj_net(Y); "
            f"roster_delta = carry − team_bpr_Y)")
        self.stdout.write("")

        # H2 — minutes sensitivity.
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            "H2 — MINUTES SENSITIVITY (carry weighting: actual Y+1 vs projected)"))
        self.stdout.write(self.style.SUCCESS("=" * 72))
        r_actual = _pearson([r["delta_actual"] for r in records], ys)
        r_proj = _pearson([r["delta_proj"] for r in records], ys)
        self.stdout.write(f"  (i)  actual Y+1 minutes  : r={r_actual:+.3f}  (optimistic upper bound)")
        self.stdout.write(f"  (ii) projected minutes   : r={r_proj:+.3f}  (honest ex-ante)")
        self.stdout.write(f"  allocator cost = {r_actual - r_proj:+.3f} r")
        self.stdout.write("")

        # H3 — continuity conditioning.
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            "H3 — CONTINUITY CONDITIONING (PV-path vs persistence RMSE by tercile)"))
        self.stdout.write(self.style.SUCCESS("=" * 72))
        ordered = sorted(records, key=lambda r: r["continuity"])
        n = len(ordered)
        t = n // 3
        terciles = [
            ("LOW  continuity", ordered[:t]),
            ("MID  continuity", ordered[t:2 * t]),
            ("HIGH continuity", ordered[2 * t:]),
        ]
        for label, grp in terciles:
            if not grp:
                continue
            pv_rmse = self._rmse([r["pv_pred"] for r in grp], [r["adj_net_yp1"] for r in grp])
            pers_rmse = self._rmse([r["pers_pred"] for r in grp], [r["adj_net_yp1"] for r in grp])
            lo = min(r["continuity"] for r in grp)
            hi = max(r["continuity"] for r in grp)
            self.stdout.write(
                f"  {label}  cont=[{lo*100:.0f}%–{hi*100:.0f}%]  n={len(grp):2d}  "
                f"PV RMSE={pv_rmse:.3f}   persistence RMSE={pers_rmse:.3f}   "
                f"Δ={pv_rmse - pers_rmse:+.3f}")
        self.stdout.write("")

    @staticmethod
    def _rmse(pred, actual):
        n = len(pred)
        if n == 0:
            return float("nan")
        return math.sqrt(sum((p - a) ** 2 for p, a in zip(pred, actual)) / n)

    @staticmethod
    def _norm_clamp_waterfill(weights, target, floor, ceil):
        """Scale weights to sum=target, clamp to [floor, ceil], water-fill."""
        tot = sum(weights) or 1.0
        shares = [max(floor, min(ceil, w / tot * target)) for w in weights]
        for _ in range(60):
            t = sum(shares)
            if abs(t - target) < 1e-6:
                break
            d = (t - target) / len(shares)
            shares = [max(floor, min(ceil, s - d)) for s in shares]
        return shares

    def _demand_shares(self, carry_vals, target):
        """Current demand allocator shares for a Y+1 roster at pool=target."""
        orig = dns.TOTAL_SHARES
        try:
            dns.TOTAL_SHARES = target
            players = [{"proj_bpr": v, "mpg": m} for _, m, v in carry_vals]
            _ds_allocate(players)
            return [p["minutes_share"] for p in players]
        finally:
            dns.TOTAL_SHARES = orig

    def _persist_shares(self, carry_vals, this_team_ympg, global_ympg,
                        y_roster_ids, y_has, vacated, target):
        """
        K1 persistence allocator: base = prior actual minutes (returner=this
        team's Y MPG, acquisition=their Y MPG elsewhere, rookie=v2 pin eff-MPG);
        vacated departed-minutes redistributed by CURRENT demand; normalize to
        target with FLOOR/CEIL + water-fill. Aligned to carry_vals order.
        """
        bases, demands = [], []
        for pid, _m, v in carry_vals:
            if pid in y_roster_ids:
                base = this_team_ympg.get(pid, 0.0)
            elif pid in y_has:
                base = global_ympg.get(pid, 0.0)
            else:
                base = rookie_eff_mpg(None, None)  # rookie: default v2 pin eff-MPG
            bases.append(base)
            demands.append((max(0.0, v + REPLACEMENT_LEVEL) + base / 36.0) ** POWER_EXPONENT)
        dtot = sum(demands) or 1.0
        weights = [b + (d / dtot) * vacated for b, d in zip(bases, demands)]
        return self._norm_clamp_waterfill(weights, target, MINUTES_FLOOR, MINUTES_CEIL)

    def _build_pair_records(self, src_year, tgt_year):
        """
        Per-team records + per-player rows for one historical pair, ACTUAL
        rosters both seasons. records carry delta_actual / delta_proj /
        delta_persist / carry_persist / residual / continuity / pv_pred /
        pers_pred / adj_net_yp1 / pair. player_rows carry (actual, current_p12,
        persist_p12) share for the K2 minutes-accuracy test.
        """
        try:
            src = NBASeason.objects.get(year=src_year)
            tgt = NBASeason.objects.get(year=tgt_year)
        except NBASeason.DoesNotExist:
            return [], []

        # League BPR baseline for the Z3 PV fallback (mirrors production line 325).
        lg_qs = NBAPlayerSeasonStats.objects.filter(
            season=src, season_type="regular", mpg__gte=MIN_MPG, bpr__isnull=False)
        lg_bpr = lg_qs.aggregate(v=Avg("bpr"))["v"] or 0.0
        lg_bpr_sd = lg_qs.aggregate(v=StdDev("bpr"))["v"] or 1.0
        rookie_pv_fallback = (ROOKIE_PRIOR_BPR - lg_bpr) / lg_bpr_sd

        # Y roster per team + player→Y-BPR / Y-PV maps (minutes-weighted across teams).
        y_rows = NBAPlayerSeasonStats.objects.filter(
            season=src, season_type="regular", mpg__gte=MIN_MPG, bpr__isnull=False,
        ).only("team_id", "player_id", "mpg", "bpr", "projection_value")
        y_team = {}          # team_id -> [(pid, mpg, bpr)]
        y_bpr_num, y_bpr_den = {}, {}
        y_pv_num, y_pv_den = {}, {}
        for r in y_rows:
            if r.team_id is None:
                continue
            m = r.mpg or 0.0
            y_team.setdefault(r.team_id, []).append((r.player_id, m, float(r.bpr)))
            y_bpr_num[r.player_id] = y_bpr_num.get(r.player_id, 0.0) + m * float(r.bpr)
            y_bpr_den[r.player_id] = y_bpr_den.get(r.player_id, 0.0) + m
            if r.projection_value is not None:
                y_pv_num[r.player_id] = y_pv_num.get(r.player_id, 0.0) + m * float(r.projection_value)
                y_pv_den[r.player_id] = y_pv_den.get(r.player_id, 0.0) + m
        y_bpr = {pid: (y_bpr_num[pid] / y_bpr_den[pid]) if y_bpr_den[pid] else 0.0
                 for pid in y_bpr_num}
        y_has = set(y_bpr_num)  # players with any Y minutes
        # Y PV per player: stored projection_value if any, else the BPR fallback.
        y_pv = {
            pid: (y_pv_num[pid] / y_pv_den[pid]) if y_pv_den.get(pid)
            else (y_bpr[pid] - lg_bpr) / lg_bpr_sd
            for pid in y_has
        }

        # Y+1 roster per team (actual minutes weights).
        yp1_rows = NBAPlayerSeasonStats.objects.filter(
            season=tgt, season_type="regular", mpg__gte=MIN_MPG,
        ).only("team_id", "player_id", "mpg")
        yp1_team = {}
        for r in yp1_rows:
            if r.team_id is None:
                continue
            yp1_team.setdefault(r.team_id, []).append((r.player_id, r.mpg or 0.0))

        net_y = self._adj_net_by_team(src)
        net_yp1 = self._adj_net_by_team(tgt)

        # PV path (returner-roster team_pv for season Y, pool 5) + season baseline.
        hist_pv = self._historical_team_pv(src)
        lg_pv = sum(hist_pv.values()) / len(hist_pv) if hist_pv else 0.0

        records, player_rows = [], []
        for team_id, roster_y in y_team.items():
            if team_id not in yp1_team or team_id not in net_y or team_id not in net_yp1:
                continue
            roster_yp1 = yp1_team[team_id]

            den_y = sum(m for _, m, _ in roster_y) or 1.0
            team_bpr_y = sum(m * b for _, m, b in roster_y) / den_y

            y_roster_ids = {pid for pid, _, _ in roster_y}
            this_team_ympg = {pid: m for pid, m, _ in roster_y}
            yp1_ids = {pid for pid, _ in roster_yp1}
            carry_vals = [(pid, m, y_bpr.get(pid, ROOKIE_PRIOR_BPR)) for pid, m in roster_yp1]

            den_a = sum(m for _, m, _ in carry_vals) or 1.0
            carry_actual = sum(m * v for _, m, v in carry_vals) / den_a

            # current demand allocator (pool 5, H2(ii) parity — scale-invariant carry)
            cur5 = self._demand_shares(carry_vals, dns.TOTAL_SHARES)
            den_p = sum(cur5) or 1.0
            carry_proj = sum(sh * v for sh, (_, _, v) in zip(cur5, carry_vals)) / den_p

            # K1 persistence allocator (pool 12)
            vacated = sum(this_team_ympg[pid] for pid in y_roster_ids if pid not in yp1_ids)
            persist12 = self._persist_shares(
                carry_vals, this_team_ympg, y_bpr_den, y_roster_ids, y_has, vacated, 12.0)
            den_k = sum(persist12) or 1.0
            carry_persist = sum(sh * v for sh, (_, _, v) in zip(persist12, carry_vals)) / den_k

            # K2 per-player share rows (pool 12 both allocators vs actual)
            cur12 = self._demand_shares(carry_vals, 12.0)
            for (pid, m, _v), c12, p12 in zip(carry_vals, cur12, persist12):
                player_rows.append((m / 20.0, c12, p12))  # actual, current, persist (shares)

            returner_min = sum(m for pid, m in roster_yp1 if pid in y_roster_ids)
            continuity = returner_min / (sum(m for _, m in roster_yp1) or 1.0)

            # Z3 — same persistence allocator, PV metric instead of BPR.
            # Fallback convention (matches production line 325): a player with a
            # stored Y projection_value uses it; a player with Y minutes but no
            # stored PV uses z(Y bpr) = (bpr − lg_bpr)/lg_bpr_sd; a player with no
            # Y minutes at all (rookie) uses the rookie-prior z (rookie_pv_fallback).
            team_pv_y = sum(m * y_pv[pid] for pid, m, _ in roster_y) / den_y
            carry_pv = sum(
                sh * y_pv.get(pid, rookie_pv_fallback)
                for sh, (pid, _, _) in zip(persist12, carry_vals)) / den_k
            # persist-share-weighted fraction of Y+1 slots on the fallback path
            pv_fallback_share = sum(
                sh for sh, (pid, _, _) in zip(persist12, carry_vals)
                if pid not in y_pv_den) / den_k

            records.append({
                "team_id": team_id,
                "pair": (src_year, tgt_year),
                "net_y": net_y[team_id],
                "delta_actual": carry_actual - team_bpr_y,
                "delta_proj": carry_proj - team_bpr_y,
                "delta_persist": carry_persist - team_bpr_y,
                "delta_pv": carry_pv - team_pv_y,
                "pv_fallback_share": pv_fallback_share,
                "carry_persist": carry_persist,
                "residual": net_yp1[team_id] - PERSISTENCE_SLOPE * net_y[team_id],
                "continuity": continuity,
                "pv_pred": PV_SLOPE * (hist_pv.get(team_id, lg_pv) - lg_pv),
                "pers_pred": PERSISTENCE_SLOPE * net_y[team_id],
                "adj_net_yp1": net_yp1[team_id],
            })
        return records, player_rows

    # ── J1 ──────────────────────────────────────────────────────────────────────

    def _pool_ceiling_fit(self, total_shares, ceil):
        """
        Pooled through-origin PV backtest over the 3 pairs with dns.TOTAL_SHARES
        and dns.MINUTES_CEIL patched in-memory. Returns
        (slope, r, rmse, sd_team_pv, binding_count, N). Restores globals.
        """
        orig_ts, orig_ceil = dns.TOTAL_SHARES, dns.MINUTES_CEIL
        pooled_x, pooled_y = [], []
        binding = 0
        try:
            dns.TOTAL_SHARES = total_shares
            dns.MINUTES_CEIL = ceil
            for src_year, tgt_year in PERSISTENCE_PAIRS:
                try:
                    src = NBASeason.objects.get(year=src_year)
                    tgt = NBASeason.objects.get(year=tgt_year)
                except NBASeason.DoesNotExist:
                    continue
                team_players = self._historical_team_players(src)
                tpv = {
                    t: (sum(p["minutes_share"] * p["pv_effective"] for p in ps)
                        / (sum(p["minutes_share"] for p in ps) or 1.0))
                    for t, ps in team_players.items()
                }
                lg = sum(tpv.values()) / len(tpv) if tpv else 0.0
                net_tgt = self._adj_net_by_team(tgt)
                for t in team_players:
                    if t in net_tgt:
                        pooled_x.append(tpv[t] - lg)
                        pooled_y.append(net_tgt[t])
                binding += sum(
                    1 for ps in team_players.values() for p in ps
                    if p["minutes_share"] >= ceil - 1e-6)
        finally:
            dns.TOTAL_SHARES, dns.MINUTES_CEIL = orig_ts, orig_ceil
        slope, r, rmse = _through_origin_fit(pooled_x, pooled_y)
        sd_pv = self._sd(pooled_x)
        return slope, r, rmse, sd_pv, binding, len(pooled_y)

    def _j1_pool12_skill(self):
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            "J1 — POOL-12 SKILL (PV backtest r under TOTAL_SHARES=12, CEIL=1.80)"))
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(
            f"  {'pool':>6s} {'PV_SLOPE':>9s} {'r':>7s} {'RMSE':>6s} {'SD(team_pv)':>12s} {'N':>4s}")
        for pool in (5.0, 12.0):
            slope, r, rmse, sd_pv, _bind, n = self._pool_ceiling_fit(pool, 1.80)
            self.stdout.write(
                f"  {pool:6.1f} {slope:9.3f} {r:+7.3f} {rmse:6.3f} {sd_pv:12.3f} {n:4d}")
        self.stdout.write(
            "  baseline (documented pool 5): r=+0.478 RMSE=4.58 SLOPE=5.591")
        self.stdout.write("")

    # ── J2 ──────────────────────────────────────────────────────────────────────

    def _j2_ceiling_sensitivity(self):
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            "J2 — CEILING SENSITIVITY AT POOL 12 (r / RMSE / binding vs MINUTES_CEIL)"))
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(
            f"  {'CEIL':>8s} {'PV_SLOPE':>9s} {'r':>7s} {'RMSE':>6s} {'binding':>8s}")
        settings = [("1.60", 1.60), ("1.80", 1.80), ("2.00", 2.00), ("none", 99.0)]
        best = None
        for label, ceil in settings:
            slope, r, rmse, _sd, binding, _n = self._pool_ceiling_fit(12.0, ceil)
            self.stdout.write(
                f"  {label:>8s} {slope:9.3f} {r:+7.3f} {rmse:6.3f} {binding:8d}")
            if best is None or r > best[1]:
                best = (label, r)
        self.stdout.write(self.style.SUCCESS(
            f"  → r-maximizing ceiling: {best[0]} (r={best[1]:+.3f})"))
        self.stdout.write("")

    # ── K1 / K2 / K3 ────────────────────────────────────────────────────────────

    def _k_persistence_allocator(self):
        records = getattr(self, "_records", [])
        player_rows = getattr(self, "_player_rows", [])
        ys = [r["residual"] for r in records]

        # K1 — residual ~ roster_delta under the persistence allocator.
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            "K1 — PERSISTENCE ALLOCATOR  residual(Y+1) ~ roster_delta [persist minutes]"))
        self.stdout.write(self.style.SUCCESS("=" * 72))
        xs_p = [r["delta_persist"] for r in records]
        slope, intercept, rr, rmse = _ols_with_intercept(xs_p, ys)
        self.stdout.write(
            f"  N={len(records)}  r={rr:+.3f}  slope={slope:+.3f}  "
            f"intercept={intercept:+.3f}  RMSE={rmse:.3f}")
        self.stdout.write(
            f"  vs H2(i) actual minutes  r=+0.504   (upper bound)\n"
            f"  vs H2(ii) demand alloc   r=+0.196   (current ex-ante)")
        self.stdout.write("")

        # K2 — minutes accuracy (per-player, pooled) vs actual Y+1 share.
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            "K2 — MINUTES ACCURACY (projected vs actual Y+1 share, per player)"))
        self.stdout.write(self.style.SUCCESS("=" * 72))
        actual = [pr[0] for pr in player_rows]
        cur = [pr[1] for pr in player_rows]
        per = [pr[2] for pr in player_rows]
        r_cur = _pearson(cur, actual)
        r_per = _pearson(per, actual)
        mae_cur = sum(abs(c - a) for c, a in zip(cur, actual)) / len(actual) * 20
        mae_per = sum(abs(p - a) for p, a in zip(per, actual)) / len(actual) * 20
        self.stdout.write(f"  n_players={len(actual)}  (shares at pool 12; MAE in MPG)")
        self.stdout.write(
            f"  current demand allocator : r={r_cur:+.3f}  MAE={mae_cur:.2f} MPG")
        self.stdout.write(
            f"  K1 persistence allocator : r={r_per:+.3f}  MAE={mae_per:.2f} MPG")
        self.stdout.write(self.style.WARNING(
            "  NOTE: current allocator's demand includes actual Y+1 MPG/36 — a leak "
            "that FLATTERS it; K1 is strictly ex-ante (prior minutes only)."))
        self.stdout.write("")

        # K3 — continuity terciles, roster path under K1 vs persistence RMSE.
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            "K3 — CONTINUITY BREAKDOWN (K1 roster path vs persistence RMSE by tercile)"))
        self.stdout.write(self.style.SUCCESS("=" * 72))
        # Center carry_persist within each pair, then through-origin fit pooled.
        by_pair = {}
        for r in records:
            by_pair.setdefault(r["pair"], []).append(r)
        for r in records:
            grp = by_pair[r["pair"]]
            mean_c = sum(x["carry_persist"] for x in grp) / len(grp)
            r["carry_persist_ctr"] = r["carry_persist"] - mean_c
        slope_k3, _r, _rmse = _through_origin_fit(
            [r["carry_persist_ctr"] for r in records],
            [r["adj_net_yp1"] for r in records])
        for r in records:
            r["k1_pred"] = slope_k3 * r["carry_persist_ctr"]

        self.stdout.write(f"  (K1 roster→rating slope fit through origin = {slope_k3:+.3f})")
        ordered = sorted(records, key=lambda r: r["continuity"])
        n = len(ordered)
        t = n // 3
        for label, grp in (("LOW  continuity", ordered[:t]),
                           ("MID  continuity", ordered[t:2 * t]),
                           ("HIGH continuity", ordered[2 * t:])):
            if not grp:
                continue
            k1_rmse = self._rmse([r["k1_pred"] for r in grp], [r["adj_net_yp1"] for r in grp])
            pers_rmse = self._rmse([r["pers_pred"] for r in grp], [r["adj_net_yp1"] for r in grp])
            lo = min(r["continuity"] for r in grp)
            hi = max(r["continuity"] for r in grp)
            self.stdout.write(
                f"  {label}  cont=[{lo*100:.0f}%–{hi*100:.0f}%]  n={len(grp):2d}  "
                f"K1 RMSE={k1_rmse:.3f}   persistence RMSE={pers_rmse:.3f}   "
                f"Δ={k1_rmse - pers_rmse:+.3f}")
        self.stdout.write("")

    # ── Z0 — 2026 BPR LINEAGE (BLOCKING) ─────────────────────────────────────────

    def _fresh_bpr(self, season_year):
        """
        Fresh final-BPR solve for `season_year` via the current pipeline (same
        code path as nba_compute_final_bpr / derive_nba_slope._lineage_check),
        no writes. Returns (fresh_obpr, fresh_dbpr) keyed by player_id.
        """
        from nba.management.commands.nba_compute_final_bpr import (
            Command as FinalBprCommand,
            DEFAULT_LAMBDA,
            DEFAULT_RAPM_WINDOW,
            LAMBDA_TIERS,
            LEBRON_LAMBDA_CAP,
            LEBRON_LAMBDA_SCALE,
            LEBRON_PRIOR_DEF_W,
            LEBRON_PRIOR_W,
            _build_lambda_array,
            _load_lebron_priors,
        )
        from nba.analytics.rapm import fit_prior_informed_rapm

        fb = FinalBprCommand()
        fb.stdout = self.stdout
        fb.stderr = self.stderr

        prior_obpr, prior_dbpr, minutes_by_id = fb._load_priors(season_year)
        lebron_raw = _load_lebron_priors(season_year, list(prior_obpr.keys()))
        if LEBRON_PRIOR_W > 0 and lebron_raw:
            prior_obpr, prior_dbpr = fb._blend_lebron_priors(
                season_year, prior_obpr, prior_dbpr, LEBRON_PRIOR_W,
                def_weight=LEBRON_PRIOR_DEF_W, lebron_map=lebron_raw,
            )
        observations, ps_index, n_ps = fb._load_stints(season_year, DEFAULT_RAPM_WINDOW)
        keys = sorted(ps_index, key=ps_index.get)
        lam_arr = _build_lambda_array(
            keys, minutes_by_id, LAMBDA_TIERS["A_conservative"],
            lebron_map=lebron_raw if LEBRON_LAMBDA_SCALE > 0 else None,
            lebron_scale=LEBRON_LAMBDA_SCALE,
            lebron_cap=LEBRON_LAMBDA_CAP,
        )
        lambda_by_id = {pid: float(lam_arr[i]) for i, (pid, _yr) in enumerate(keys)}

        result = fit_prior_informed_rapm(
            observations=observations,
            player_season_index=ps_index,
            n_player_seasons=n_ps,
            prior_obpr=prior_obpr,
            prior_dbpr=prior_dbpr,
            lambda_val=DEFAULT_LAMBDA,
            lambda_by_nba_id=lambda_by_id,
            target_season_year=season_year,
            cross_season_decay=1.0,
            within_season_half_life=90.0,
        )
        fresh_obpr = {pid: v for (pid, yr), v in result["obpr"].items() if yr == season_year}
        fresh_dbpr = {pid: v for (pid, yr), v in result["dbpr"].items() if yr == season_year}
        return fresh_obpr, fresh_dbpr

    def _z0_bpr_lineage(self, season_year):
        from nba.management.commands.derive_nba_slope import LINEAGE_MAD_THRESHOLD

        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            f"Z0 — {season_year} BPR LINEAGE (BLOCKING)  fresh vs stored, all rows"))
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(
            f"  Fresh final-BPR solve for {season_year} (no writes)… this is the "
            "RAPM solve, slow.")

        fresh_obpr, fresh_dbpr = self._fresh_bpr(season_year)

        rows = (
            NBAPlayerSeasonStats.objects.filter(
                season__year=season_year, season_type="regular", bpr__isnull=False,
            )
            .select_related("player", "team")
            .only("player__player_id", "player__name", "bpr", "mpg", "gp",
                  "team__abbreviation")
        )
        devs, detail = [], []
        n_missing = 0
        for r in rows:
            pid = r.player.player_id
            if pid not in fresh_obpr:
                n_missing += 1
                continue
            fresh = fresh_obpr[pid] + fresh_dbpr.get(pid, 0.0)
            dev = abs(float(r.bpr) - fresh)
            devs.append(dev)
            detail.append((
                dev, r.player.name,
                r.team.abbreviation if r.team else "?",
                r.mpg or 0.0, float(r.bpr), fresh,
            ))

        if not devs:
            self.stdout.write(self.style.ERROR(
                "  no comparable players — cannot run lineage gate. FAIL."))
            return False

        devs_sorted = sorted(devs)
        n = len(devs)
        mean = sum(devs) / n
        median = devs_sorted[n // 2]
        p95 = devs_sorted[min(n - 1, int(0.95 * n))]
        mx = devs_sorted[-1]

        self.stdout.write(
            f"  N compared={n}  (unmatched, no fresh solve: {n_missing})")
        self.stdout.write(
            f"  |stored − fresh|:  mean={mean:.3f}  median={median:.3f}  "
            f"p95={p95:.3f}  max={mx:.3f}")
        self.stdout.write(
            f"  admit threshold (2022–25 pairs passed at ~0.09–0.12): "
            f"mean ≤ {LINEAGE_MAD_THRESHOLD}")
        self.stdout.write("\n  20 largest absolute divergences:")
        self.stdout.write(
            f"    {'player':26s} {'tm':>4s} {'mpg':>5s} {'stored':>7s} "
            f"{'fresh':>7s} {'|Δ|':>6s}")
        for dev, name, tm, mpg, stored, fresh in sorted(detail, reverse=True)[:20]:
            self.stdout.write(
                f"    {name[:26]:26s} {tm:>4s} {mpg:5.1f} {stored:+7.2f} "
                f"{fresh:+7.2f} {dev:6.2f}")

        verdict = mean <= LINEAGE_MAD_THRESHOLD
        style = self.style.SUCCESS if verdict else self.style.ERROR
        self.stdout.write("")
        self.stdout.write(style(
            f"  Z0 VERDICT: {'PASS' if verdict else 'FAIL'} — mean |Δ| = {mean:.3f} "
            f"vs threshold {LINEAGE_MAD_THRESHOLD}"))
        if not verdict:
            self.stdout.write(self.style.ERROR(
                "  → 2026 stored BPR carries pipeline drift. T1/T2/Z1–Z4 are VOID: "
                "constants fit on clean 2022–25 data would be applied to a dirty base. "
                "Re-run nba_compute_final_bpr for 2026 before anything ships."))
        else:
            self.stdout.write(
                "  → 2026 base is clean. Batch (T1/T2/Z1–Z4) is safe to run.")
        self.stdout.write("")
        return verdict

    # ── Ratings / wins helpers (T1, T2, Z4) ─────────────────────────────────────

    def _adj_net_first_n(self, season_year, n):
        """
        {team_pk: adj_net} recomputed from each team's FIRST n regular-season
        games via the production opponent-adjustment solver (services.ratings_
        engine.iterative_adjust) — no writes. n large (e.g. 82) ≈ stored adj_net.
        """
        from nba.models import NBATeamGameStats
        from nba.ratings_config import NBA_RATINGS_CONFIG
        from services.ratings_engine import GameRecord, RatingsConfig, iterative_adjust

        stats_list = list(
            NBATeamGameStats.objects.filter(
                game__season__year=season_year,
                game__counts_toward_regular_season=True,
                poss__isnull=False, poss__gt=0,
            ).select_related("game", "team")
        )
        # opponent lookup + per-team chronological order
        game_stats, by_team = {}, {}
        for s in stats_list:
            game_stats.setdefault(s.game_id, {})[s.team_id] = s
            by_team.setdefault(s.team_id, []).append(s)
        first_n = set()
        for tid, lst in by_team.items():
            lst.sort(key=lambda s: (s.game.date, s.game_id))
            for s in lst[:n]:
                first_n.add((s.team_id, s.game_id))

        records = []
        for s in stats_list:
            if (s.team_id, s.game_id) not in first_n:
                continue
            opp = next((o for tid, o in game_stats[s.game_id].items() if tid != s.team_id), None)
            if opp is None or s.raw_ortg is None or s.raw_drtg is None:
                continue
            records.append(GameRecord(
                team_id=s.team_id, opp_id=opp.team_id,
                raw_ortg=s.raw_ortg, raw_drtg=s.raw_drtg, poss=s.poss,
                is_home=s.is_home,
                rest_days=s.game.rest_days_home if s.is_home else s.game.rest_days_away,
                is_b2b=s.game.home_b2b if s.is_home else s.game.away_b2b,
                counts_toward_ratings=True,
            ))
        c = NBA_RATINGS_CONFIG
        cfg = RatingsConfig(
            iterations=c["iterations"], convergence_threshold=c["convergence_threshold"],
            prior_games=c["prior_games"], prior_ortg=c["prior_ortg"],
            prior_drtg=c["prior_drtg"], home_court_adj=c["home_court_adj"],
            rest_adj_per_day=c["rest_adj_per_day"], b2b_penalty=c["b2b_penalty"],
        )
        res = iterative_adjust(records, cfg)
        return {tid: r["adj_net"] for tid, r in res.items()}

    def _wins_by_team(self, season_year):
        """{team_pk: regular-season wins} from NBAGame results."""
        from nba.models import NBAGame
        wins = {}
        qs = NBAGame.objects.filter(
            season__year=season_year, season_type="regular",
            counts_toward_regular_season=True, status="Final",
        ).only("home_score", "away_score", "home_team_id", "away_team_id")
        for g in qs:
            if g.home_score is None or g.away_score is None:
                continue
            w = g.home_team_id if g.home_score > g.away_score else g.away_team_id
            wins[w] = wins.get(w, 0) + 1
        return wins

    @staticmethod
    def _ols2(x1, x2, y):
        """OLS y = a + b1·x1 + b2·x2. Returns dict with coefs, R, RMSE, partials."""
        n = len(y)
        m1, m2, my = sum(x1) / n, sum(x2) / n, sum(y) / n
        s11 = sum((a - m1) ** 2 for a in x1)
        s22 = sum((a - m2) ** 2 for a in x2)
        s12 = sum((a - m1) * (b - m2) for a, b in zip(x1, x2))
        s1y = sum((a - m1) * (b - my) for a, b in zip(x1, y))
        s2y = sum((a - m2) * (b - my) for a, b in zip(x2, y))
        det = s11 * s22 - s12 * s12
        if abs(det) < 1e-12:
            return None
        b1 = (s22 * s1y - s12 * s2y) / det
        b2 = (s11 * s2y - s12 * s1y) / det
        a = my - b1 * m1 - b2 * m2
        resid = [yi - (a + b1 * xi1 + b2 * xi2) for yi, xi1, xi2 in zip(y, x1, x2)]
        rmse = math.sqrt(sum(e * e for e in resid) / n)
        pred = [a + b1 * xi1 + b2 * xi2 for xi1, xi2 in zip(x1, x2)]
        R = _pearson(pred, y)
        r_y1, r_y2, r_12 = _pearson(y, x1), _pearson(y, x2), _pearson(x1, x2)
        def _partial(ra, rb, rab):
            d = math.sqrt(max(1e-12, (1 - rb ** 2) * (1 - rab ** 2)))
            return (ra - rb * rab) / d
        return {
            "b1": b1, "b2": b2, "intercept": a, "R": R, "rmse": rmse,
            "pr1": _partial(r_y1, r_y2, r_12), "pr2": _partial(r_y2, r_y1, r_12),
            "r12": r_12,
        }

    # ── T1 ──────────────────────────────────────────────────────────────────────

    def _t1_tanking(self):
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            "T1 — TANKING CONTAMINATION  adj_net(Y+1 full) ~ adj_net(Y, first N)"))
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(f"  {'N':>4s} {'r':>7s} {'RMSE':>6s} {'slope':>7s}  (pooled, N=90)")

        best = None
        self._first_n_cache = {}  # (year, N) -> {team: adj_net}, reused by Z1
        for N in (41, 62, 72, 82):
            xs, ys = [], []
            for src_year, tgt_year in PERSISTENCE_PAIRS:
                first = self._adj_net_first_n(src_year, N)
                self._first_n_cache[(src_year, N)] = first
                full_tgt = self._adj_net_by_team(
                    NBASeason.objects.get(year=tgt_year))
                for t in first:
                    if t in full_tgt:
                        xs.append(first[t])
                        ys.append(full_tgt[t])
            slope, intercept, r, rmse = _ols_with_intercept(xs, ys)
            self.stdout.write(f"  {N:>4d} {r:+7.3f} {rmse:6.3f} {slope:+7.3f}")
            if best is None or r > best[1]:
                best = (N, r)
        self.stdout.write(self.style.SUCCESS(
            f"  → r-maximizing N = {best[0]} (r={best[1]:+.3f}); "
            f"full-season baseline is N=82"))
        self.stdout.write("")
        return best[0]

    # ── T2 ──────────────────────────────────────────────────────────────────────

    def _t2_asymmetry(self):
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            "T2 — ASYMMETRY  mean signed residual by wins(Y) tercile "
            "(full-season persistence)"))
        self.stdout.write(self.style.SUCCESS("=" * 72))

        rows = []  # (wins_y, residual)
        for src_year, tgt_year in PERSISTENCE_PAIRS:
            net_y = self._adj_net_by_team(NBASeason.objects.get(year=src_year))
            net_yp1 = self._adj_net_by_team(NBASeason.objects.get(year=tgt_year))
            wins_y = self._wins_by_team(src_year)
            for t in net_y:
                if t in net_yp1 and t in wins_y:
                    resid = net_yp1[t] - PERSISTENCE_SLOPE * net_y[t]
                    rows.append((wins_y[t], resid))
        rows.sort(key=lambda r: r[0])
        n = len(rows)
        t = n // 3
        for label, grp in (("LOW  wins", rows[:t]),
                           ("MID  wins", rows[t:2 * t]),
                           ("HIGH wins", rows[2 * t:])):
            if not grp:
                continue
            mean_res = sum(r for _, r in grp) / len(grp)
            lo = min(w for w, _ in grp)
            hi = max(w for w, _ in grp)
            self.stdout.write(
                f"  {label}  wins=[{lo}–{hi}]  n={len(grp):2d}  "
                f"mean signed residual = {mean_res:+.3f}")
        self.stdout.write(
            "  (positive = team beat persistence forecast; a strong negative LOW "
            "tercile = tanked Y depressed adj_net(Y), team bounces back)")
        self.stdout.write("")

    # ── Z1 ──────────────────────────────────────────────────────────────────────

    def _z1_joint_fit(self, best_n):
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            "Z1 — JOINT FIT  adj_net(Y+1) ~ ρ·adj_net(Y) + β·roster_delta_K1"))
        self.stdout.write(self.style.SUCCESS("=" * 72))
        records = getattr(self, "_records", [])
        y = [r["adj_net_yp1"] for r in records]
        x2 = [r["delta_persist"] for r in records]

        # (a) full-season adj_net(Y)
        x1_full = [r["net_y"] for r in records]
        fa = self._ols2(x1_full, x2, y)
        self._report_joint("full-season adj_net(Y)", fa)

        # (b) tanking-corrected adj_net(Y) from best_n
        cache = getattr(self, "_first_n_cache", {})
        x1_corr, x2_corr, y_corr = [], [], []
        for r in records:
            src_year = r["pair"][0]
            first = cache.get((src_year, best_n)) or self._adj_net_first_n(src_year, best_n)
            cache[(src_year, best_n)] = first
            if r["team_id"] in first:
                x1_corr.append(first[r["team_id"]])
                x2_corr.append(r["delta_persist"])
                y_corr.append(r["adj_net_yp1"])
        cb = self._ols2(x1_corr, x2_corr, y_corr)
        self._report_joint(f"tanking-corrected adj_net(Y, first {best_n})", cb)
        self.stdout.write("")

    def _report_joint(self, label, f):
        if f is None:
            self.stdout.write(f"  {label}: singular — cannot fit")
            return
        self.stdout.write(f"  {label}:")
        self.stdout.write(
            f"    ρ={f['b1']:+.3f}  β={f['b2']:+.3f}  intercept={f['intercept']:+.3f}  "
            f"R={f['R']:+.3f}  RMSE={f['rmse']:.3f}")
        self.stdout.write(
            f"    partial r: adj_net(Y)={f['pr1']:+.3f}  roster_delta={f['pr2']:+.3f}  "
            f"| corr(predictors)={f['r12']:+.3f}")

    # ── Z2 ──────────────────────────────────────────────────────────────────────

    def _z2_loyo(self):
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            "Z2 — LOYO  leave-one-pair-out CV (joint model vs persistence-only)"))
        self.stdout.write(self.style.SUCCESS("=" * 72))
        records = getattr(self, "_records", [])
        pairs = list(dict.fromkeys(r["pair"] for r in records))

        joint_pred, joint_act, pers_pred, pers_act = [], [], [], []
        for held in pairs:
            train = [r for r in records if r["pair"] != held]
            test = [r for r in records if r["pair"] == held]
            # joint fit on train
            f = self._ols2([r["net_y"] for r in train],
                           [r["delta_persist"] for r in train],
                           [r["adj_net_yp1"] for r in train])
            # persistence-only slope on train (through origin, matches PERSISTENCE_SLOPE style)
            ps, _pi, _pr, _pm = _ols_with_intercept(
                [r["net_y"] for r in train], [r["adj_net_yp1"] for r in train])
            pi = _pi
            jp = [f["intercept"] + f["b1"] * r["net_y"] + f["b2"] * r["delta_persist"]
                  for r in test]
            pp = [pi + ps * r["net_y"] for r in test]
            act = [r["adj_net_yp1"] for r in test]
            jr = self._rmse(jp, act)
            pr = self._rmse(pp, act)
            self.stdout.write(
                f"  fold {held[0]}→{held[1]}  n={len(test):2d}  "
                f"joint: r={_pearson(jp, act):+.3f} RMSE={jr:.3f}   "
                f"persist: r={_pearson(pp, act):+.3f} RMSE={pr:.3f}")
            joint_pred += jp; joint_act += act
            pers_pred += pp; pers_act += act
        self.stdout.write(self.style.SUCCESS(
            f"  POOLED held-out  joint: r={_pearson(joint_pred, joint_act):+.3f} "
            f"RMSE={self._rmse(joint_pred, joint_act):.3f}   "
            f"persistence: r={_pearson(pers_pred, pers_act):+.3f} "
            f"RMSE={self._rmse(pers_pred, pers_act):.3f}"))
        self.stdout.write("")

    # ── Z3 ──────────────────────────────────────────────────────────────────────

    def _z3_delta_metric(self):
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            "Z3 — DELTA METRIC CHOICE  residual ~ roster_delta  (BPR vs PV)"))
        self.stdout.write(self.style.SUCCESS("=" * 72))
        records = getattr(self, "_records", [])
        ys = [r["residual"] for r in records]
        r_bpr = _pearson([r["delta_persist"] for r in records], ys)
        r_pv = _pearson([r["delta_pv"] for r in records], ys)
        self.stdout.write(f"  (i)  roster_delta on raw BPR        : r={r_bpr:+.3f}")
        self.stdout.write(f"  (ii) roster_delta on projection_value: r={r_pv:+.3f}")
        self.stdout.write(
            "  (PV beat BPR on levels 0.601 vs 0.583; this tests whether it "
            "holds for deltas)")
        self.stdout.write("")

    # ── Z4 ──────────────────────────────────────────────────────────────────────

    def _z4_wins_added(self):
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            "Z4 — WINS_ADDED RECALIBRATION  Σ(share×bpr)@pool12 → wins − 20"))
        self.stdout.write(self.style.SUCCESS("=" * 72))

        xs, ys = [], []
        for year in (2022, 2023, 2024, 2025):
            try:
                NBASeason.objects.get(year=year)
            except NBASeason.DoesNotExist:
                continue
            wins = self._wins_by_team(year)
            # actual-season rosters, pool-12 demand allocation, stored BPR
            rows = NBAPlayerSeasonStats.objects.filter(
                season__year=year, season_type="regular", mpg__gte=MIN_MPG,
                bpr__isnull=False,
            ).only("team_id", "mpg", "bpr")
            team_players = {}
            for r in rows:
                if r.team_id is None:
                    continue
                team_players.setdefault(r.team_id, []).append(
                    (r.mpg or 0.0, float(r.bpr)))
            for tid, ps in team_players.items():
                if tid not in wins:
                    continue
                carry_vals = [(i, m, b) for i, (m, b) in enumerate(ps)]
                shares = self._demand_shares(carry_vals, 12.0)
                x = sum(sh * b for sh, (_, _, b) in zip(shares, carry_vals))
                xs.append(x)
                ys.append(wins[tid] - 20.0)

        slope, r, rmse = _through_origin_fit(xs, ys)
        self.stdout.write(
            f"  N={len(xs)} team-seasons  through-origin scalar = {slope:.4f}  "
            f"(r={r:+.3f}, RMSE={rmse:.2f} wins)")
        self.stdout.write(self.style.WARNING(
            f"  current WINS_ADDED_SCALAR = 0.38 (pool-5 calibrated). At pool 12 "
            f"the fitted scalar is {slope:.4f} — {0.38/slope if slope else 0:.2f}x apart."))
        self.stdout.write("")

    # ── Z5 ──────────────────────────────────────────────────────────────────────

    def _z5_loyo_pv_delta(self):
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            "Z5 — LOYO, JOINT MODEL WITH PV DELTA  "
            "adj_net(Y+1) ~ ρ·adj_net(Y) + β·roster_delta_PV"))
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(
            "  fallback (matches Z3/production line 325): stored projection_value "
            "where present;\n  else z(Y bpr) for players with Y minutes; else "
            "rookie-prior z for zero-Y-minute rookies.")
        records = getattr(self, "_records", [])

        # (a) in-sample joint
        x1 = [r["net_y"] for r in records]
        x2 = [r["delta_pv"] for r in records]
        y = [r["adj_net_yp1"] for r in records]
        f = self._ols2(x1, x2, y)
        self.stdout.write("\n  (a) IN-SAMPLE:")
        self.stdout.write(
            f"      ρ={f['b1']:+.3f}  β={f['b2']:+.3f}  R={f['R']:+.3f}  "
            f"RMSE={f['rmse']:.3f}")
        self.stdout.write(
            f"      partial r: adj_net(Y)={f['pr1']:+.3f}  roster_delta_PV="
            f"{f['pr2']:+.3f}  | corr(predictors)={f['r12']:+.3f}")
        self.stdout.write(
            f"      vs Z1 (BPR delta): ρ=+0.716 β=+2.347 R=+0.614")

        # (b) LOYO
        pairs = list(dict.fromkeys(r["pair"] for r in records))
        jp_all, ja_all = [], []
        self.stdout.write("\n  (b) LOYO by pair:")
        for held in pairs:
            train = [r for r in records if r["pair"] != held]
            test = [r for r in records if r["pair"] == held]
            ft = self._ols2([r["net_y"] for r in train],
                            [r["delta_pv"] for r in train],
                            [r["adj_net_yp1"] for r in train])
            jp = [ft["intercept"] + ft["b1"] * r["net_y"] + ft["b2"] * r["delta_pv"]
                  for r in test]
            act = [r["adj_net_yp1"] for r in test]
            self.stdout.write(
                f"      fold {held[0]}→{held[1]}  n={len(test):2d}  "
                f"r={_pearson(jp, act):+.3f}  RMSE={self._rmse(jp, act):.3f}")
            jp_all += jp; ja_all += act
        self.stdout.write(self.style.SUCCESS(
            f"      POOLED held-out: r={_pearson(jp_all, ja_all):+.3f}  "
            f"RMSE={self._rmse(jp_all, ja_all):.3f}"))
        self.stdout.write(
            "      vs Z2 joint-BPR (0.576) and persistence (0.538)")

        # (c) fallback coverage per fold
        self.stdout.write("\n  (c) PV fallback coverage (persist-share-weighted, per pair):")
        for held in pairs:
            grp = [r for r in records if r["pair"] == held]
            mean_fb = sum(r["pv_fallback_share"] for r in grp) / len(grp)
            self.stdout.write(
                f"      {held[0]}→{held[1]}: mean fallback share = {mean_fb*100:.1f}%")
        self.stdout.write("")

    # ── Z6 ──────────────────────────────────────────────────────────────────────

    def _z6_wins_closure(self):
        self.stdout.write(self.style.SUCCESS("=" * 72))
        self.stdout.write(self.style.SUCCESS(
            f"Z6 — WINS_ADDED CLOSURE  scalar={WINS_ADDED_SCALAR_P12} @ pool 12"))
        self.stdout.write(self.style.SUCCESS("=" * 72))

        all_wa, all_y = [], []
        for year in (2022, 2023, 2024, 2025):
            try:
                NBASeason.objects.get(year=year)
            except NBASeason.DoesNotExist:
                continue
            wins = self._wins_by_team(year)
            rows = NBAPlayerSeasonStats.objects.filter(
                season__year=year, season_type="regular", mpg__gte=MIN_MPG,
                bpr__isnull=False,
            ).only("team_id", "mpg", "bpr")
            team_players = {}
            for r in rows:
                if r.team_id is None:
                    continue
                team_players.setdefault(r.team_id, []).append((r.mpg or 0.0, float(r.bpr)))
            season_wa = 0.0
            season_target = 0.0
            for tid, ps in team_players.items():
                if tid not in wins:
                    continue
                carry_vals = [(i, m, b) for i, (m, b) in enumerate(ps)]
                shares = self._demand_shares(carry_vals, 12.0)
                wa = WINS_ADDED_SCALAR_P12 * sum(
                    sh * b for sh, (_, _, b) in zip(shares, carry_vals))
                season_wa += wa
                season_target += wins[tid] - 20.0
                all_wa.append(wa)
                all_y.append(wins[tid] - 20.0)
            self.stdout.write(
                f"  {year}: Σ wins_added={season_wa:7.1f}  "
                f"Σ(wins−20)={season_target:6.1f}  ratio={season_wa/season_target if season_target else 0:.3f}")

        pooled_wa = sum(all_wa)
        pooled_target = sum(all_y)
        r = _pearson(all_wa, all_y)
        rmse = self._rmse(all_wa, all_y)
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"  POOLED N={len(all_wa)}  Σ wins_added={pooled_wa:.1f}  "
            f"Σ(wins−20)={pooled_target:.1f}  ratio={pooled_wa/pooled_target if pooled_target else 0:.3f}"))
        self.stdout.write(
            f"  per-team wins_added vs (wins−20): r={r:+.3f}  RMSE={rmse:.2f} wins")
        self.stdout.write(
            "  (closure target: per-season Σ wins_added ≈ Σ(wins−20) = 630)")
        self.stdout.write("")
