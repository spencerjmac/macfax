"""
derive_freshman_priors — composite-rating → freshman-season production mapping.

Phase 5 Stage 1 (REPORT ONLY — commits nothing).

COVERAGE GATE (Phase 4 doctrine — the derivation refuses to fit on data that
cannot support it):
  The predictor side requires historical recruiting ratings joined to freshman
  outcomes. As of 2026-07-17 the DB holds 48 profiles — ALL class-2026
  five-stars (one tier, one class). Doc 13 (bpr_audit, commit b873df2) reached
  the same verdict on 2026-07-06: freshman-tier curves are BLOCKED pending
  recruiting CSVs for classes 2021-2026 (priority list of 5,962 espn_id-
  prefilled players at backtest_output/bpr_audit/recruiting_missing_profiles.csv;
  source terms: CSVs manually exported/provided — no scraping).

  This command therefore:
    1. Reports the census (outcome side + predictor side + constructible pairs).
    2. HARD-GATES the fit: requires >= MIN_PAIRS pairs spanning >= MIN_CLASSES
       classes and >= MIN_TIERS star tiers. Below the gate it reports what IS
       computable (currently the single five-star/2026 cell) and exits nonzero.
    3. The fit/LOYO/closure machinery lands WITH the data (Phase 4.6 lesson:
       derivation code written blind to its data gets rewritten; the census +
       gate is the durable part).

Universe discipline once data lands (Phase 4.6 convictions, pre-registered):
  - Universe = ALL rated recruits in a class, zero-minute recruits contribute 0
    (expectation, not qualifier-conditional mean).
  - Minutes target = EFFECTIVE share (total minutes / TEAM games), never
    per-game MPG (availability bias).
  - Decomposition: E[contribution] = E[eff minutes | rating] × E[BPR | played,
    rating]; both reported separately.
  - Closure: implied league-wide freshman minutes share must sit in the
    historically actual band, computed from the data itself.
  - One-row-per-target assertions throughout.

Usage:
    python manage.py derive_freshman_priors --classes 2022,2023,2024,2025,2026
"""

from __future__ import annotations

import statistics

from django.core.management.base import BaseCommand

from ncaa.models import PlayerRecruitingProfile, PlayerSeasonStats

MIN_PAIRS = 150
MIN_CLASSES = 2
MIN_TIERS = 2


class Command(BaseCommand):
    help = "Freshman prior derivation: census + coverage gate (report only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--classes", type=str, default="2022,2023,2024,2025,2026",
            help="Comma-separated class years (= first-season year) to census.",
        )
        parser.add_argument(
            "--min-mpg", type=float, default=8.0,
            help="Qualifying-minutes threshold for the outcome census column.",
        )

    def handle(self, *args, **options):
        classes = [int(y) for y in options["classes"].split(",")]
        min_mpg = options["min_mpg"]

        # ── Outcome side: newcomers per class (first PSS season, doc-13 conv.)
        from django.db.models import Min
        firsts = {
            r["player_id"]: r["first"]
            for r in PlayerSeasonStats.objects.values("player_id")
            .annotate(first=Min("season__year"))
        }
        self.stdout.write(f"\n{'='*70}\nCENSUS A — freshman/newcomer outcomes")
        self.stdout.write(
            f"  {'class':>6} {'newcomers':>10} {'>=%.0fmpg' % min_mpg:>9} {'w/ BPR':>7}"
        )
        outcome_n = {}
        for yr in classes:
            newcomers = [p for p, f in firsts.items() if f == yr]
            qs = PlayerSeasonStats.objects.filter(season__year=yr, player_id__in=newcomers)
            n_min = qs.filter(mpg__gte=min_mpg).count()
            n_bpr = qs.filter(mpg__gte=min_mpg, obpr__isnull=False).count()
            outcome_n[yr] = n_bpr
            self.stdout.write(f"  {yr:>6} {len(newcomers):>10} {n_min:>9} {n_bpr:>7}")

        # ── Predictor side: rated profiles per class × tier ──────────────────
        self.stdout.write(f"\nCENSUS B — recruiting profiles (predictor side)")
        pair_count = 0
        classes_covered = set()
        tiers_covered = set()
        for yr in classes:
            profs = PlayerRecruitingProfile.objects.filter(class_year=yr)
            n = profs.count()
            by_star = {}
            for s in (5, 4, 3, 2, 1, None):
                c = profs.filter(stars=s).count()
                if c:
                    by_star[s] = c
            # constructible pairs: resolved profile + outcome row same year
            pairs = profs.filter(
                player__isnull=False,
                player__season_stats__season__year=yr,
            ).distinct().count()
            if pairs:
                classes_covered.add(yr)
                tiers_covered.update(k for k in by_star if k is not None)
            pair_count += pairs
            self.stdout.write(
                f"  {yr}: profiles={n}  by_star={by_star or '—'}  constructible pairs={pairs}"
            )

        self.stdout.write(
            f"\nCENSUS C — verdict: {pair_count} constructible pairs across "
            f"{len(classes_covered)} class(es), {len(tiers_covered)} star tier(s)."
        )

        # ── Coverage gate ────────────────────────────────────────────────────
        gate_ok = (
            pair_count >= MIN_PAIRS
            and len(classes_covered) >= MIN_CLASSES
            and len(tiers_covered) >= MIN_TIERS
        )
        if not gate_ok:
            self._report_computable_cells(classes)
            self.stderr.write(self.style.ERROR(
                f"\nCOVERAGE GATE FAILED — need >= {MIN_PAIRS} pairs spanning "
                f">= {MIN_CLASSES} classes and >= {MIN_TIERS} tiers "
                f"(have {pair_count}/{len(classes_covered)}/{len(tiers_covered)}). "
                "Fit/LOYO/closure NOT run: a tier curve cannot be estimated from "
                "one tier of one class. Blocker: historical recruiting CSVs "
                "(doc 13 §10; ingest list backtest_output/bpr_audit/"
                "recruiting_missing_profiles.csv, 5,962 espn_ids prefilled)."
            ))
            raise SystemExit(1)

        self.stdout.write(self.style.WARNING(
            "\nCoverage gate PASSED — fit machinery not yet implemented "
            "(lands with the data per Phase 4.6 doctrine). Extend this command "
            "with the pre-registered universe discipline in the module docstring."
        ))

    # ── What IS computable today ──────────────────────────────────────────────

    def _report_computable_cells(self, classes):
        """Per-tier outcome means for whatever (tier, class) cells exist."""
        self.stdout.write(f"\nCOMPUTABLE CELLS (only cells with data; no curve fit):")
        for yr in classes:
            profs = PlayerRecruitingProfile.objects.filter(
                class_year=yr, player__isnull=False
            ).select_related("player")
            by_star: dict[int, list] = {}
            for pr in profs:
                pss_rows = list(
                    PlayerSeasonStats.objects.filter(
                        player=pr.player, season__year=yr
                    ).values("mpg", "gp", "obpr", "dbpr")
                )
                total_min = sum((r["mpg"] or 0) * (r["gp"] or 0) for r in pss_rows)
                bpr_rows = [r for r in pss_rows if r["obpr"] is not None]
                by_star.setdefault(pr.stars, []).append({
                    "eff": total_min / 31.0,  # ≈ D1 team games; census-grade only
                    "obpr": statistics.mean([r["obpr"] for r in bpr_rows]) if bpr_rows else None,
                    "dbpr": statistics.mean([r["dbpr"] for r in bpr_rows]) if bpr_rows else None,
                    "played": total_min > 0,
                })
            for star, rows in sorted(by_star.items(), key=lambda kv: -(kv[0] or 0)):
                played = [r for r in rows if r["played"]]
                withb = [r for r in rows if r["obpr"] is not None]
                self.stdout.write(
                    f"  class {yr}, {star or '?'}★: N={len(rows)}  played={len(played)}  "
                    f"mean eff-min/team-game={statistics.mean([r['eff'] for r in rows]):.1f}  "
                    + (
                        f"mean obpr={statistics.mean([r['obpr'] for r in withb]):+.2f} "
                        f"dbpr={statistics.mean([r['dbpr'] for r in withb]):+.2f} (n={len(withb)})"
                        if withb else "no BPR rows"
                    )
                )
