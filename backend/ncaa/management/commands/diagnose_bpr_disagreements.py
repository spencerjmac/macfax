"""
diagnose_bpr_disagreements — Audit BPR vs Box BPR disagreements and leaderboard composition.

Usage:
    python manage.py diagnose_bpr_disagreements --season 2026
    python manage.py diagnose_bpr_disagreements --season 2026 --top 50
    python manage.py diagnose_bpr_disagreements --season 2026 --source rapm

Outputs:
  1. Top-N strict_bpr leaderboard (bpr_source='rapm')
  2. Top-N full_two_sided leaderboard (both sides non-null, not partial)
  3. Top-N box_bpr leaderboard for comparison
  4. Players where BPR and Box BPR most disagree (sorted by |bpr - box_bpr|)
  5. Defensive inflation suspects (dbpr >> baseline_dbpr, obpr stable)
  6. Source composition of the full leaderboard and top-100
"""

import logging

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Audit BPR disagreements and leaderboard composition for a season."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=int,
            required=True,
            help="Season year (e.g. 2026).",
        )
        parser.add_argument(
            "--top",
            type=int,
            default=25,
            help="Number of players to show in each leaderboard (default: 25).",
        )
        parser.add_argument(
            "--source",
            choices=["rapm", "box_bpr", "mixed", "partial", "all"],
            default="all",
            help="Filter leaderboard by bpr_source (default: all).",
        )
        parser.add_argument(
            "--min-poss",
            type=int,
            default=200,
            help="Minimum offensive possessions to include (default: 200).",
        )

    def handle(self, *args, **options):
        season_year = options["season"]
        top_n = options["top"]
        source_filter = options["source"]
        min_poss = options["min_poss"]

        from ncaa.models import PlayerSeasonStats

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nBPR Disagreement Audit — Season {season_year}\n"
            )
        )

        # ── Base queryset ──────────────────────────────────────────────────────
        qs = (
            PlayerSeasonStats.objects
            .filter(
                season__year=season_year,
                bpr__isnull=False,
                off_poss__gte=min_poss,
            )
            .select_related("player", "team")
            .values(
                "player_id",
                "player__display_name",
                "team__name",
                "bpr", "obpr", "dbpr",
                "box_bpr", "box_obpr", "box_dbpr",
                "baseline_obpr", "baseline_dbpr",
                "off_poss", "def_poss",
                "bpr_source", "obpr_source", "dbpr_source",
            )
            .order_by("-bpr")
        )

        if source_filter != "all":
            qs = qs.filter(bpr_source=source_filter)

        records = list(qs)
        if not records:
            self.stdout.write(self.style.WARNING("No BPR records found."))
            return

        # ── 1. Source composition ──────────────────────────────────────────────
        all_records = list(
            PlayerSeasonStats.objects
            .filter(season__year=season_year, bpr__isnull=False)
            .values("bpr_source", "bpr", "off_poss")
            .order_by("-bpr")
        )
        source_counts: dict[str, int] = {}
        for r in all_records:
            src = r.get("bpr_source") or "unknown"
            source_counts[src] = source_counts.get(src, 0) + 1

        self.stdout.write("\n── Source composition (all players with BPR) ──")
        for src, cnt in sorted(source_counts.items(), key=lambda x: -x[1]):
            self.stdout.write(f"  {src:12s}: {cnt}")

        top100 = [r for r in sorted(all_records, key=lambda r: r["bpr"], reverse=True)][:100]
        non_rapm_top100 = sum(1 for r in top100 if r.get("bpr_source") != "rapm")
        self.stdout.write(
            f"\n  Non-rapm in top-100: {non_rapm_top100} "
            f"({100*non_rapm_top100/max(len(top100),1):.1f}%)"
        )

        # ── 2. Strict BPR leaderboard ──────────────────────────────────────────
        strict = sorted(
            [r for r in all_records if r.get("bpr_source") == "rapm"],
            key=lambda r: r["bpr"], reverse=True,
        )
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n── Top-{top_n} Strict BPR (bpr_source='rapm', min_poss={min_poss}) ──"
            )
        )
        strict_display = [
            r for r in records if r.get("bpr_source") == "rapm"
        ][:top_n]
        self._print_leaderboard(strict_display)

        # ── 3. Full two-sided leaderboard ──────────────────────────────────────
        two_sided = [
            r for r in records
            if r["obpr"] is not None and r["dbpr"] is not None
            and r.get("bpr_source") != "partial"
        ][:top_n]
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n── Top-{top_n} Full Two-Sided (both obpr+dbpr non-null) ──"
            )
        )
        self._print_leaderboard(two_sided)

        # ── 4. Box BPR leaderboard ─────────────────────────────────────────────
        box_ranked = sorted(
            [r for r in records if r["box_bpr"] is not None],
            key=lambda r: r["box_bpr"], reverse=True,
        )[:top_n]
        self.stdout.write(
            self.style.MIGRATE_HEADING(f"\n── Top-{top_n} Box BPR ──")
        )
        self._print_box_leaderboard(box_ranked)

        # ── 5. Largest BPR vs Box BPR disagreements ───────────────────────────
        paired = [r for r in records if r["bpr"] is not None and r["box_bpr"] is not None]
        disagreements = sorted(
            paired, key=lambda r: abs(r["bpr"] - r["box_bpr"]), reverse=True
        )[:top_n]
        self.stdout.write(
            self.style.MIGRATE_HEADING(f"\n── Largest |BPR − Box BPR| Disagreements ──")
        )
        self.stdout.write(
            f"  {'Name':<30} {'BPR':>6} {'BoxBPR':>7} {'Δ':>7} {'Source':<10}"
        )
        for r in disagreements:
            delta = r["bpr"] - r["box_bpr"]
            self.stdout.write(
                f"  {r.get('player__display_name','?'):<30} "
                f"{r['bpr']:>+6.2f} "
                f"{r['box_bpr']:>+7.2f} "
                f"{delta:>+7.2f} "
                f"{r.get('bpr_source','?'):<10}"
            )

        # ── 6. Defensive inflation suspects ────────────────────────────────────
        def_suspects = [
            r for r in records
            if r.get("dbpr") is not None and r.get("baseline_dbpr") is not None
            and (r["dbpr"] - r["baseline_dbpr"]) > 2.0
            and r.get("obpr") is not None and r.get("baseline_obpr") is not None
            and abs(r["obpr"] - r["baseline_obpr"]) < 1.0
        ]
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n── Defensive Inflation Suspects "
                f"(dbpr > baseline_dbpr + 2, obpr stable) ──"
            )
        )
        if def_suspects:
            self.stdout.write(
                f"  {'Name':<30} {'DBPR':>6} {'BaselineD':>9} {'ΔDef':>6} "
                f"{'OBPR':>6} {'BaselineO':>9} {'ΔOff':>6}"
            )
            for r in sorted(def_suspects, key=lambda r: -(r["dbpr"] - r["baseline_dbpr"])):
                self.stdout.write(
                    f"  {r.get('player__display_name','?'):<30} "
                    f"{r['dbpr']:>+6.2f} "
                    f"{r['baseline_dbpr']:>+9.2f} "
                    f"{r['dbpr']-r['baseline_dbpr']:>+6.2f} "
                    f"{r['obpr']:>+6.2f} "
                    f"{r['baseline_obpr']:>+9.2f} "
                    f"{r['obpr']-r['baseline_obpr']:>+6.2f}"
                )
        else:
            self.stdout.write("  None found.")

        self.stdout.write(self.style.SUCCESS("\nDone.\n"))

    def _print_leaderboard(self, records: list[dict]) -> None:
        self.stdout.write(
            f"  {'Rank':<5} {'Name':<30} {'BPR':>6} {'OBPR':>6} {'DBPR':>6} "
            f"{'Poss':>6} {'Source':<10}"
        )
        for i, r in enumerate(records, 1):
            self.stdout.write(
                f"  {i:<5} "
                f"{r.get('player__display_name','?'):<30} "
                f"{r['bpr']:>+6.2f} "
                f"{(r['obpr'] or 0):>+6.2f} "
                f"{(r['dbpr'] or 0):>+6.2f} "
                f"{int(r.get('off_poss') or 0):>6} "
                f"{r.get('bpr_source','?'):<10}"
            )

    def _print_box_leaderboard(self, records: list[dict]) -> None:
        self.stdout.write(
            f"  {'Rank':<5} {'Name':<30} {'BoxBPR':>7} {'BoxO':>6} {'BoxD':>6} "
            f"{'BPR':>6} {'Source':<10}"
        )
        for i, r in enumerate(records, 1):
            self.stdout.write(
                f"  {i:<5} "
                f"{r.get('player__display_name','?'):<30} "
                f"{(r['box_bpr'] or 0):>+7.2f} "
                f"{(r['box_obpr'] or 0):>+6.2f} "
                f"{(r['box_dbpr'] or 0):>+6.2f} "
                f"{(r['bpr'] or 0):>+6.2f} "
                f"{r.get('bpr_source','?'):<10}"
            )
