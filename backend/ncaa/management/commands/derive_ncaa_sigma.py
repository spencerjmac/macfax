"""
derive_ncaa_sigma — empirical sigma calibration for NCAA team projections.

Phase 3 Stage 1 (REPORT ONLY — commits nothing).

For each source→actual season pair:
  - stored TeamSeasonProjection (from_season = source year):
    projected_adj_o / adj_d / adj_em + team_projection_uncertainty
  - actual TeamSeasonRatings for the target season, D1 teams only,
    is_pre_tournament=False filtered EXPLICITLY (not via default manager),
    with a hard one-row-per-team assertion (Phase 2 lesson: playoff/pre-
    tournament snapshots silently corrupting join targets).

Reports per pair and pooled:
  - bias + RMSE of (projected − actual) for O, D, EM
  - correlation of O residuals vs D residuals (EM band multiplier evidence:
    ρ≈0 → √2 combine; ρ≈1 → 2x combine)
  - RMSE by team_projection_uncertainty quintile (RAW residuals)
  - OLS fits sigma_o(u)=a+b·u, sigma_d(u), sigma_em(u) on the pooled RAW
    quintile bins, vs the current implicit sigma_rating = 3.5 + 2.5u
    (and implicit sigma_em = 7 + 5u from the ±2σ EM band).

Phase 3 Stage 2 (operator decision D1): O/D bands answer "team strength
relative to the field," not "where will the league's absolute numbers
land." League-wide scoring-environment drift shifts a whole season's O and
D residuals by a common offset (both pair biases are negative, and O/D
residuals anticorrelate at ρ≈−0.35 pooled) — that drift inflates raw O/D
RMSE without telling you anything about a team's rank-relative accuracy.
So this command ALSO reports a DEMEANED section: per pair, subtract that
pair's own mean O bias and mean D bias before computing RMSE / quintile
fits, then pool the demeaned residuals across pairs. EM is NOT demeaned
(operator decision D2) — environment drift cancels in the O−D margin by
construction, which is exactly what the negative O/D correlation says.

Usage:
    python manage.py derive_ncaa_sigma --pairs 2022:2023,2023:2024,2024:2025,2025:2026
"""

from __future__ import annotations

import math

from django.core.management.base import BaseCommand, CommandError

from ncaa.models import Season, TeamSeasonProjection, TeamSeasonRatings


def _mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def _rmse(xs):
    return math.sqrt(sum(x * x for x in xs) / len(xs)) if xs else float("nan")


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = _mean(xs), _mean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def _ols(xs, ys):
    """Simple OLS y = a + b·x."""
    n = len(xs)
    mx, my = _mean(xs), _mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return my, 0.0
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - b * mx, b


class Command(BaseCommand):
    help = "Derive empirical projection sigmas (report only, commits nothing)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--pairs", type=str, required=True,
            help="Comma-separated source:actual season pairs, e.g. 2024:2025",
        )
        parser.add_argument(
            "--quintiles", type=int, default=5,
            help="Number of uncertainty buckets (default 5).",
        )

    def handle(self, *args, **options):
        pairs = []
        for chunk in options["pairs"].split(","):
            try:
                src, tgt = (int(v) for v in chunk.strip().split(":"))
            except ValueError:
                raise CommandError(f"Bad pair '{chunk}' — expected SRC:TGT")
            pairs.append((src, tgt))
        n_bins = options["quintiles"]

        pooled = []            # rows: (u, res_o, res_d, res_em) — RAW
        pooled_demeaned = []   # rows: (u, res_o_dm, res_d_dm, res_em) — O/D demeaned per pair
        for src, tgt in pairs:
            rows = self._collect_pair(src, tgt)
            if not rows:
                continue
            self._report_pair(f"{src}→{tgt}", rows)
            pooled.extend(rows)

            mean_o = _mean([r[1] for r in rows])
            mean_d = _mean([r[2] for r in rows])
            pooled_demeaned.extend(
                (u, ro - mean_o, rd - mean_d, rem) for u, ro, rd, rem in rows
            )
            self.stdout.write(
                f"    demeaning this pair: subtract O bias {mean_o:+.2f}, "
                f"D bias {mean_d:+.2f} before pooling"
            )

        if not pooled:
            raise CommandError("No joinable pairs.")

        self.stdout.write("\n" + "=" * 66)
        self._report_pair(f"POOLED RAW ({len(pairs)} pairs)", pooled)
        self._report_quintiles(pooled, n_bins, label="RAW")

        self.stdout.write("\n" + "=" * 66)
        self.stdout.write(
            "POOLED DEMEANED (O/D only — each pair's own O/D bias removed "
            "before pooling; EM carried through unchanged, per D2)"
        )
        self._report_pair(f"POOLED DEMEANED ({len(pairs)} pairs)", pooled_demeaned)
        self._report_quintiles(pooled_demeaned, n_bins, label="DEMEANED", em=False)

        self.stdout.write(self.style.WARNING(
            "\nHUMAN REVIEW GATE — no constants written; band construction "
            "unchanged. Approve before committing."
        ))

    # ── Data collection ────────────────────────────────────────────────────────

    def _collect_pair(self, src_year: int, tgt_year: int):
        try:
            src = Season.objects.get(year=src_year)
            tgt = Season.objects.get(year=tgt_year)
        except Season.DoesNotExist as exc:
            self.stdout.write(self.style.WARNING(f"Pair {src_year}→{tgt_year}: {exc} — skipped"))
            return []

        proj_rows = list(
            TeamSeasonProjection.objects.filter(from_season=src)
            .values(
                "team_id",
                "projected_adj_o", "projected_adj_d", "projected_adj_em",
                "team_projection_uncertainty",
            )
        )
        if not proj_rows:
            self.stdout.write(self.style.WARNING(
                f"Pair {src_year}→{tgt_year}: no stored projections — skipped"
            ))
            return []

        # Actuals: final (post-tournament) snapshot, D1 only, EXPLICIT filter —
        # do not rely on the model's default PostTournamentManager silently
        # doing this. Hard one-row-per-team assertion (Phase 2 lesson).
        actual_rows = list(
            TeamSeasonRatings.all_objects.filter(
                season=tgt,
                is_pre_tournament=False,
                team__is_d1=True,
            ).values("team_id", "adj_o", "adj_d", "adj_em")
        )
        seen: dict[int, int] = {}
        for r in actual_rows:
            seen[r["team_id"]] = seen.get(r["team_id"], 0) + 1
        dupes = {t: c for t, c in seen.items() if c > 1}
        if dupes:
            from ncaa.models import Team
            names = list(
                Team.objects.filter(id__in=list(dupes)[:10]).values_list("name", flat=True)
            )
            raise CommandError(
                f"Pair {src_year}→{tgt_year}: {len(dupes)} teams with >1 final "
                f"ratings row for {tgt_year} — aborting. Offenders (first 10): {names}"
            )

        actual_by_team = {r["team_id"]: r for r in actual_rows}

        rows = []
        for p in proj_rows:
            a = actual_by_team.get(p["team_id"])
            if a is None:
                continue
            if p["projected_adj_o"] is None or p["projected_adj_em"] is None:
                continue
            rows.append((
                float(p["team_projection_uncertainty"] or 0.5),
                float(p["projected_adj_o"]) - float(a["adj_o"]),
                float(p["projected_adj_d"]) - float(a["adj_d"]),
                float(p["projected_adj_em"]) - float(a["adj_em"]),
            ))
        self.stdout.write(
            f"\nPair {src_year}→{tgt_year}: projections={len(proj_rows)}  "
            f"actual D1 final rows={len(actual_rows)} (one-row assertion PASS)  "
            f"joined N={len(rows)}"
        )
        return rows

    # ── Reporting ──────────────────────────────────────────────────────────────

    def _report_pair(self, label: str, rows):
        res_o = [r[1] for r in rows]
        res_d = [r[2] for r in rows]
        res_em = [r[3] for r in rows]
        self.stdout.write(f"  [{label}] N={len(rows)}")
        self.stdout.write(
            f"    AdjO : bias={_mean(res_o):+6.2f}  RMSE={_rmse(res_o):5.2f}\n"
            f"    AdjD : bias={_mean(res_d):+6.2f}  RMSE={_rmse(res_d):5.2f}\n"
            f"    AdjEM: bias={_mean(res_em):+6.2f}  RMSE={_rmse(res_em):5.2f}"
        )
        rho = _pearson(res_o, res_d)
        # EM combine multiplier implied by the O/D residual correlation:
        # sigma_em = sqrt(s_o² + s_d² − 2ρ·s_o·s_d)  (EM error = O err − D err)
        s_o, s_d = _rmse(res_o), _rmse(res_d)
        implied_em = math.sqrt(max(s_o**2 + s_d**2 - 2 * rho * s_o * s_d, 0.0))
        self.stdout.write(
            f"    corr(res_O, res_D) = {rho:+.3f}  → implied sigma_em from O/D = "
            f"{implied_em:.2f} (vs direct {_rmse(res_em):.2f}; "
            f"ρ=0 ⇒ √2 combine, ρ=+1 ⇒ subtractive, ρ=−1 ⇒ 2x)"
        )

    def _report_quintiles(self, rows, n_bins: int, label: str = "RAW", em: bool = True):
        rows = sorted(rows, key=lambda r: r[0])
        n = len(rows)
        self.stdout.write(f"\n  Uncertainty-bucketed RMSE ({label}, pooled, {n_bins} bins):")
        self.stdout.write(
            f"    {'bin':>3} {'mean_u':>7} {'N':>5} {'RMSE_O':>7} {'RMSE_D':>7} {'RMSE_EM':>8}"
            f"   {'cur σ_rating(u)':>16} {'cur σ_em(u)':>12}"
        )
        bin_stats = []
        for i in range(n_bins):
            lo, hi = i * n // n_bins, (i + 1) * n // n_bins
            chunk = rows[lo:hi]
            if not chunk:
                continue
            u = _mean([r[0] for r in chunk])
            ro = _rmse([r[1] for r in chunk])
            rd = _rmse([r[2] for r in chunk])
            rem = _rmse([r[3] for r in chunk])
            cur_rating = 3.5 + 2.5 * u          # UNCERTAINTY_SIGMA_SCALE→MAX mapping
            cur_em = 2 * cur_rating             # engine's ±2σ EM band
            bin_stats.append((u, ro, rd, rem))
            self.stdout.write(
                f"    {i+1:>3} {u:7.3f} {len(chunk):>5} {ro:7.2f} {rd:7.2f} {rem:8.2f}"
                f"   {cur_rating:16.2f} {cur_em:12.2f}"
            )

        us = [b[0] for b in bin_stats]
        targets = [("sigma_o", 1), ("sigma_d", 2)]
        if em:
            targets.append(("sigma_em", 3))
        for name, idx in targets:
            a, b = _ols(us, [bs[idx] for bs in bin_stats])
            self.stdout.write(
                f"\n  [{label}] Fitted {name}(u) = {a:.2f} + {b:.2f}·u   "
                f"(OLS on {len(bin_stats)} bins)"
            )
        self.stdout.write(
            "  Current implicit: sigma_rating(u) = 3.50 + 2.50·u  (O and D bands, ±1σ)\n"
            "                    sigma_em(u)     = 7.00 + 5.00·u  (EM band, ±2σ_rating)"
        )
