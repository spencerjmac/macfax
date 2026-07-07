"""
derive_nba_slope — re-derive SLOPE / SIGMA_EM (legacy BPR path) and
PV_SLOPE / PV_SIGMA_EM (Projection Value path) under the CURRENT allocator.

Phase 2 context: raising MINUTES_CEIL changes base_off/base_def spread and
minutes-weighted team PV league-wide, so slopes calibrated under the old
allocator are stale the moment the allocator changes. This command rebuilds
each source-season team's aggregates with the allocator constants imported
directly from compute_nba_team_outlooks (always in sync with production),
then OLS-fits next-season actual adj_net.

Functional-form parity with the pipeline (forced through the same centering,
no intercept):
  legacy: adj_em = SLOPE × [(base_off − lg_off) + (base_def − lg_def)]
  PV:     adj_em = PV_SLOPE × (team_pv − league_pv_mean)

DOES NOT WRITE ANY CONSTANT OR DB ROW. Output is a report for human review;
the operator approves values before they enter compute_nba_team_outlooks.py.

Data-lineage exclusion (preserved from the SLOPE=0.48 derivation): the
2025→2026 pair is EXCLUDED — stored BPR for the 2025 season was computed
under an earlier pipeline version and is materially different from current
output (e.g. Amen Thompson stored ≈5.7 vs freshly-computed 9.43). That pair
would measure stale inputs → 2026 outcomes, not the current model.

Usage:
    python manage.py derive_nba_slope --pairs 2024:2025
    python manage.py derive_nba_slope --pairs 2023:2024,2024:2025
"""

import math
import statistics

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Avg, StdDev

from nba.models import NBASeason, NBATeam, NBAPlayerSeasonStats, NBATeamSeasonRatings

# Import the production allocator constants so this derivation always runs
# under whatever the pipeline currently uses (incl. the Phase 2 ceiling).
from nba.management.commands.compute_nba_team_outlooks import (
    MIN_MPG,
    MINUTES_CEIL,
    MINUTES_FLOOR,
    POWER_EXPONENT,
    REPLACEMENT_LEVEL,
    SHRINKAGE_RETURNER,
    TOTAL_SHARES,
)

EXCLUDED_PAIRS = {(2025, 2026)}

# Lineage gate: a pair is usable only if the source season's STORED BPR matches
# what the current final-BPR pipeline produces. Mean |stored − fresh| above this
# (in BPR pts, over the top-minutes sample) excludes the pair — it would measure
# stale inputs → outcomes, not the current model.
LINEAGE_MAD_THRESHOLD = 0.5
LINEAGE_SAMPLE_SIZE = 10


def _water_fill(shares, target, max_iter=25):
    shares = list(shares)
    for _ in range(max_iter):
        total = sum(shares)
        if abs(total - target) < 1e-6:
            break
        delta = (target - total) / len(shares)
        shares = [max(MINUTES_FLOOR, min(MINUTES_CEIL, s + delta)) for s in shares]
    return shares


def _allocate_minutes(players):
    demands = []
    for p in players:
        bpr_above_repl = max(0.0, p["proj_bpr"] + REPLACEMENT_LEVEL)
        mpg_component = (p["mpg"] or 15.0) / 36.0
        demands.append(bpr_above_repl + mpg_component)
    powered = [d ** POWER_EXPONENT for d in demands]
    total = sum(powered) or 1.0
    raw = [pw / total * TOTAL_SHARES for pw in powered]
    clamped = [max(MINUTES_FLOOR, min(MINUTES_CEIL, s)) for s in raw]
    normalized = _water_fill(clamped, TOTAL_SHARES)
    for p, share in zip(players, normalized):
        p["minutes_share"] = share


def _through_origin_fit(xs, ys):
    """Slope through origin + pearson r + RMSE of slope·x vs y."""
    sxx = sum(x * x for x in xs)
    if sxx <= 0:
        return 0.0, 0.0, float("nan")
    slope = sum(x * y for x, y in zip(xs, ys)) / sxx
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    r = (
        sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)
        if sx > 0 and sy > 0 else 0.0
    )
    rmse = math.sqrt(sum((slope * x - y) ** 2 for x, y in zip(xs, ys)) / n)
    return slope, r, rmse


class Command(BaseCommand):
    help = (
        "Re-derive SLOPE/SIGMA_EM and PV_SLOPE/PV_SIGMA_EM candidates under the "
        "current allocator. Report only — writes nothing."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--pairs", type=str, required=True,
            help="Comma-separated source:target season pairs, e.g. 2023:2024,2024:2025",
        )
        parser.add_argument(
            "--skip-lineage", action="store_true",
            help="Skip the fresh-BPR lineage check (RAPM solve per source season is slow). "
                 "Use only when the same pairs were lineage-verified in a recent run.",
        )
        parser.add_argument(
            "--lineage-sample", type=int, default=LINEAGE_SAMPLE_SIZE,
            help=f"Top-minutes players sampled per source season (default {LINEAGE_SAMPLE_SIZE}).",
        )

    def handle(self, *args, **options):
        pairs = []
        for chunk in options["pairs"].split(","):
            try:
                src, tgt = (int(v) for v in chunk.strip().split(":"))
            except ValueError:
                raise CommandError(f"Bad pair '{chunk}' — expected SRC:TGT (e.g. 2024:2025)")
            if (src, tgt) in EXCLUDED_PAIRS:
                self.stdout.write(self.style.WARNING(
                    f"Pair {src}→{tgt} HARD-EXCLUDED (data-lineage note, see module "
                    "docstring) — dropped."
                ))
                continue
            pairs.append((src, tgt))
        if not pairs:
            raise CommandError("No pairs left after hard exclusions.")

        self.stdout.write(f"Allocator: CEIL={MINUTES_CEIL} FLOOR={MINUTES_FLOOR} "
                          f"POW={POWER_EXPONENT} REPL={REPLACEMENT_LEVEL}")

        # ── Lineage gate per source season ────────────────────────────────────
        if options["skip_lineage"]:
            self.stdout.write(self.style.WARNING(
                "Lineage check SKIPPED (--skip-lineage) — pairs assumed verified."
            ))
            surviving = pairs
        else:
            surviving = []
            for src, tgt in pairs:
                ok = self._lineage_check(src, options["lineage_sample"])
                if ok:
                    surviving.append((src, tgt))
                else:
                    self.stdout.write(self.style.WARNING(
                        f"  → Pair {src}→{tgt} EXCLUDED by lineage check."
                    ))
        if not surviving:
            raise CommandError("No pairs survived the lineage gate — nothing to derive.")

        self.stdout.write(
            f"\nSurviving pairs: {', '.join(f'{s}→{t}' for s, t in surviving)}"
        )

        all_x_bpr, all_x_pv, all_y = [], [], []
        for src, tgt in surviving:
            x_bpr, x_pv, y, n = self._run_pair(src, tgt)
            all_x_bpr += x_bpr
            all_x_pv += x_pv
            all_y += y

        if len(surviving) > 1:
            self.stdout.write("")
            self._report(f"POOLED ({len(surviving)} pairs)", all_x_bpr, all_x_pv, all_y)

        self.stdout.write(self.style.WARNING(
            "\nHUMAN REVIEW GATE — no constants were written. Approve before committing."
        ))

    # ── Lineage check ──────────────────────────────────────────────────────────

    def _lineage_check(self, season_year: int, sample_size: int) -> bool:
        """
        Freshly solve final BPR for the source season with the CURRENT pipeline
        (same code path as nba_compute_final_bpr, no writes) and compare the
        top-minutes players' stored bpr against the fresh values.

        Scope note: the fresh solve consumes the STORED box_obpr/box_dbpr priors
        and LEBRON CSVs, so this verifies the final RAPM stage's lineage (the
        stage that invalidated 2025→2026, e.g. Amen Thompson stored ≈5.7 vs
        fresh 9.43). Upstream box-prior drift is not re-derived here.
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

        self.stdout.write(f"\nLineage check — source season {season_year} "
                          f"(fresh final-BPR solve, no writes)…")
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

        rows = (
            NBAPlayerSeasonStats.objects.filter(
                season__year=season_year, season_type="regular", bpr__isnull=False,
            )
            .select_related("player")
            .only("player__player_id", "player__name", "bpr", "mpg", "gp")
        )
        sample = sorted(
            (r for r in rows if r.player.player_id in fresh_obpr),
            key=lambda r: (r.mpg or 0.0) * (r.gp or 0),
            reverse=True,
        )[:sample_size]
        if not sample:
            self.stdout.write(self.style.ERROR("  no comparable players — FAIL"))
            return False

        devs = []
        for r in sample:
            pid = r.player.player_id
            fresh = fresh_obpr[pid] + fresh_dbpr.get(pid, 0.0)
            dev = abs(float(r.bpr) - fresh)
            devs.append(dev)
            self.stdout.write(
                f"    {r.player.name:28s} stored={float(r.bpr):+6.2f}  "
                f"fresh={fresh:+6.2f}  |Δ|={dev:.2f}"
            )
        mad = sum(devs) / len(devs)
        verdict = mad <= LINEAGE_MAD_THRESHOLD
        style = self.style.SUCCESS if verdict else self.style.ERROR
        self.stdout.write(style(
            f"  {season_year}: mean |Δ| = {mad:.3f} over {len(devs)} players → "
            f"{'PASS' if verdict else f'FAIL (> {LINEAGE_MAD_THRESHOLD})'}"
        ))
        return verdict

    def _run_pair(self, src_year, tgt_year):
        try:
            src = NBASeason.objects.get(year=src_year)
            tgt = NBASeason.objects.get(year=tgt_year)
        except NBASeason.DoesNotExist as exc:
            raise CommandError(f"Season missing for pair {src_year}:{tgt_year}: {exc}")

        # League shrinkage targets (mirrors pipeline)
        bpr_qs = NBAPlayerSeasonStats.objects.filter(
            season=src, season_type="regular", mpg__gte=MIN_MPG,
        )
        lg_obpr = bpr_qs.filter(obpr__isnull=False).aggregate(v=Avg("obpr"))["v"] or 0.0
        lg_dbpr = bpr_qs.filter(dbpr__isnull=False).aggregate(v=Avg("dbpr"))["v"] or 0.0
        lg_bpr  = bpr_qs.filter(bpr__isnull=False).aggregate(v=Avg("bpr"))["v"] or 0.0
        lg_bpr_sd = bpr_qs.filter(bpr__isnull=False).aggregate(v=StdDev("bpr"))["v"] or 1.0

        # RAPM-gap sigma for the inflation cap (mirrors pipeline)
        gap_qs = NBAPlayerSeasonStats.objects.filter(
            season=src, season_type="regular", gp__gte=20, mpg__gte=12,
            bpr__isnull=False, box_obpr__isnull=False, box_dbpr__isnull=False,
        ).only("bpr", "box_obpr", "box_dbpr")
        gaps = [float(r.bpr) - (float(r.box_obpr) + float(r.box_dbpr)) for r in gap_qs]
        cap_threshold = 1.6 * (statistics.stdev(gaps) if len(gaps) >= 20 else 3.5)

        # Per-team returner rosters (backtest has no historical offseason moves)
        rows = NBAPlayerSeasonStats.objects.filter(
            season=src, season_type="regular", mpg__gte=MIN_MPG, bpr__isnull=False,
        ).only("team_id", "mpg", "obpr", "dbpr", "bpr", "box_obpr", "box_dbpr",
               "projection_value")

        team_players: dict[int, list[dict]] = {}
        lam = SHRINKAGE_RETURNER
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
            # RAPM-inflation cap (asymmetric, mirrors pipeline)
            if row.box_obpr is not None and row.box_dbpr is not None:
                box_bpr = float(row.box_obpr) + float(row.box_dbpr)
                gap = p["proj_bpr"] - box_bpr
                if gap > cap_threshold:
                    excess = gap - cap_threshold
                    if abs(gap) > 0:
                        p["proj_obpr"] -= excess * (p["proj_obpr"] - float(row.box_obpr)) / gap
                        p["proj_dbpr"] -= excess * (p["proj_dbpr"] - float(row.box_dbpr)) / gap
                    p["proj_bpr"] -= excess
            # PV path: stored PV shrunk toward 0; fallback z(projected_bpr)
            if p["projection_value"] is None:
                p["pv_effective"] = (p["proj_bpr"] - lg_bpr) / lg_bpr_sd
            else:
                p["pv_effective"] = p["projection_value"] * (1.0 - lam)
            team_players.setdefault(row.team_id, []).append(p)

        for players in team_players.values():
            _allocate_minutes(players)

        # Two-pass centering (mirrors pipeline)
        base_off = {t: sum(p["minutes_share"] * p["proj_obpr"] for p in ps)
                    for t, ps in team_players.items()}
        base_def = {t: sum(p["minutes_share"] * p["proj_dbpr"] for p in ps)
                    for t, ps in team_players.items()}
        team_pv = {
            t: (sum(p["minutes_share"] * p["pv_effective"] for p in ps)
                / (sum(p["minutes_share"] for p in ps) or 1.0))
            for t, ps in team_players.items()
        }
        lg_off = sum(base_off.values()) / len(base_off)
        lg_def = sum(base_def.values()) / len(base_def)
        lg_pv  = sum(team_pv.values()) / len(team_pv)

        # season_type filter is load-bearing: without it, playoff rows overwrite
        # regular-season rows for the 16 playoff teams (Stage 1 derivation bug).
        actual = {
            r.team_id: float(r.adj_off - r.adj_def)
            for r in NBATeamSeasonRatings.objects.filter(
                season=tgt, season_type="regular"
            )
            if r.adj_off is not None and r.adj_def is not None
        }

        x_bpr, x_pv, y = [], [], []
        for t in team_players:
            if t not in actual:
                continue
            x_bpr.append((base_off[t] - lg_off) + (base_def[t] - lg_def))
            x_pv.append(team_pv[t] - lg_pv)
            y.append(actual[t])

        self.stdout.write(
            f"\nPair {src_year}→{tgt_year}: n={len(y)} teams, "
            f"lg_base off={lg_off:.2f} def={lg_def:.2f} pv={lg_pv:+.3f}, "
            f"cap={cap_threshold:.2f}"
        )
        self._report(f"{src_year}→{tgt_year}", x_bpr, x_pv, y)
        return x_bpr, x_pv, y, len(y)

    def _report(self, label, x_bpr, x_pv, y):
        if not y:
            self.stdout.write(f"  {label}: no matched teams")
            return
        s1, r1, rmse1 = _through_origin_fit(x_bpr, y)
        s2, r2, rmse2 = _through_origin_fit(x_pv, y)
        self.stdout.write(f"  [{label}] N={len(y)}")
        self.stdout.write(
            f"    legacy BPR form : SLOPE    = {s1:.3f}  r={r1:.3f}  RMSE={rmse1:.2f}"
            f"  → SIGMA_EM candidate {math.ceil(rmse1 * 10) / 10:.1f}"
        )
        self.stdout.write(
            f"    PV form         : PV_SLOPE = {s2:.3f}  r={r2:.3f}  RMSE={rmse2:.2f}"
            f"  → PV_SIGMA_EM candidate {math.ceil(rmse2 * 10) / 10:.1f}"
        )
