"""
Management command: nba_compute_final_bpr

Computes the final displayed BPR for NBA players using prior-informed RAPM:
  - Prior mean: box_obpr / box_dbpr (per-player, from nba_compute_box_bpr)
  - Data: 3-year pooled lineup stints (same window as nba_compute_baseline_rapm)
  - Regularization: λ=1000 (CV-matched to baseline RAPM)

This is the LEBRON-style "Box prior Regularized On-off" approach. Results are
written to NBAPlayerSeasonStats.obpr / .dbpr / .bpr — the fields the frontend
should display instead of box_bpr.

Run order:
  1. nba_compute_baseline_rapm --season YYYY --rapm-years YYYY-2 YYYY-1 YYYY
  2. nba_compute_box_bpr --season YYYY
  3. nba_compute_final_bpr --season YYYY          ← this command

Usage:
  python manage.py nba_compute_final_bpr --season 2026
  python manage.py nba_compute_final_bpr --season 2026 --lambda-val 500
  python manage.py nba_compute_final_bpr --season 2026 --dry-run
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from nba.analytics.rapm import build_nba_observations, fit_prior_informed_rapm
from nba.models import NBAPlayerSeasonStats

logger = logging.getLogger(__name__)

DEFAULT_LAMBDA = 1000.0
DEFAULT_RAPM_WINDOW = 3   # seasons to pool


class Command(BaseCommand):
    help = "Compute final BPR (prior-informed RAPM) and write to obpr/dbpr/bpr"

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument(
            "--lambda-val", type=float, default=DEFAULT_LAMBDA,
            help=f"Ridge regularization λ (default {DEFAULT_LAMBDA})",
        )
        parser.add_argument(
            "--rapm-window", type=int, default=DEFAULT_RAPM_WINDOW,
            help=f"Seasons of stints to pool (default {DEFAULT_RAPM_WINDOW})",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        season_year: int = options["season"]
        lambda_val: float = options["lambda_val"]
        rapm_window: int = options["rapm_window"]
        dry_run: bool = options["dry_run"]

        self.stdout.write(f"\n[FINAL BPR] Season {season_year}  λ={lambda_val}  window={rapm_window}yr")
        if dry_run:
            self.stdout.write("[DRY RUN] No writes")

        # ── 1. Load box_bpr priors ─────────────────────────────────────────────
        box_stats = list(
            NBAPlayerSeasonStats.objects.filter(
                season__year=season_year,
                season_type="regular",
                box_obpr__isnull=False,
            ).select_related("player").only(
                "player__player_id", "box_obpr", "box_dbpr",
            )
        )
        if not box_stats:
            raise CommandError(
                f"No box_obpr found for {season_year}. "
                "Run nba_compute_box_bpr first."
            )

        prior_obpr: dict[int, float] = {}
        prior_dbpr: dict[int, float] = {}
        for row in box_stats:
            nba_id = row.player.player_id
            if nba_id:
                prior_obpr[nba_id] = row.box_obpr or 0.0
                prior_dbpr[nba_id] = row.box_dbpr or 0.0

        self.stdout.write(f"Box priors loaded: {len(prior_obpr)} players")

        # ── 2. Load pooled stint observations ──────────────────────────────────
        rapm_years = list(range(season_year - rapm_window + 1, season_year + 1))
        self.stdout.write(f"Loading stints for {rapm_years}...")

        observations = build_nba_observations(
            season_year=season_year,
            rapm_years=rapm_years,
        )
        if not observations:
            raise CommandError(
                f"No stint observations found. "
                "Run nba_sync_play_by_play for the relevant seasons first."
            )
        self.stdout.write(f"  {len(observations)} lineup observations")

        # ── 3. Build player-season index ───────────────────────────────────────
        all_ps: set[tuple[int, int]] = set()
        for obs in observations:
            yr = obs["season_year"]
            for pid in obs["home_player_ids"] + obs["away_player_ids"]:
                all_ps.add((pid, yr))
        player_season_index = {ps: i for i, ps in enumerate(sorted(all_ps))}
        n_ps = len(player_season_index)
        self.stdout.write(
            f"  {n_ps} player-season columns "
            f"({len({ps[0] for ps in all_ps})} unique players)"
        )

        # ── 4. Fit prior-informed RAPM ─────────────────────────────────────────
        self.stdout.write(f"Fitting prior-informed RAPM (λ={lambda_val})...")
        result = fit_prior_informed_rapm(
            observations=observations,
            player_season_index=player_season_index,
            n_player_seasons=n_ps,
            prior_obpr=prior_obpr,
            prior_dbpr=prior_dbpr,
            lambda_val=lambda_val,
        )

        # Extract target-season coefficients keyed by NBA.com player_id
        final_obpr: dict[int, float] = {
            pid: v for (pid, yr), v in result["obpr"].items() if yr == season_year
        }
        final_dbpr: dict[int, float] = {
            pid: v for (pid, yr), v in result["dbpr"].items() if yr == season_year
        }
        self.stdout.write(
            f"  {len(final_obpr)} players with final BPR for {season_year}"
        )

        if dry_run:
            self._print_leaderboard(final_obpr, final_dbpr, season_year)
            return

        # ── 5. Write to DB ─────────────────────────────────────────────────────
        stats_qs = NBAPlayerSeasonStats.objects.filter(
            season__year=season_year,
            season_type="regular",
        ).select_related("player")

        now = timezone.now()
        updated = skipped = 0
        for row in stats_qs:
            nba_id = row.player.player_id
            if nba_id not in final_obpr:
                skipped += 1
                continue
            o = final_obpr[nba_id]
            d = final_dbpr.get(nba_id, 0.0)
            row.obpr = round(o, 3)
            row.dbpr = round(d, 3)
            row.bpr  = round(o + d, 3)
            row.bpr_last_updated = now
            row.save(update_fields=["obpr", "dbpr", "bpr", "bpr_last_updated"])
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"[OK] Final BPR written: {updated} updated, {skipped} skipped"
            )
        )
        self._print_leaderboard(final_obpr, final_dbpr, season_year)

    def _print_leaderboard(
        self,
        final_obpr: dict[int, float],
        final_dbpr: dict[int, float],
        season_year: int,
    ) -> None:
        from nba.models import NBAPlayer

        name_map: dict[int, str] = {
            p.player_id: p.name
            for p in NBAPlayer.objects.filter(player_id__in=final_obpr.keys()).only("player_id", "name")
        }

        # Deduplicate by player_id (traded players may appear via multiple team rows)
        ranked = sorted(
            [(pid, final_obpr[pid], final_dbpr.get(pid, 0.0)) for pid in final_obpr],
            key=lambda x: x[1] + x[2],
            reverse=True,
        )

        self.stdout.write(f"\nTop 20 by final BPR — Season {season_year}:")
        self.stdout.write(f"  {'Player':<30} {'OBPR':>6} {'DBPR':>6} {'BPR':>7}")
        self.stdout.write("  " + "-" * 55)
        for pid, o, d in ranked[:20]:
            name = name_map.get(pid, f"id={pid}")
            self.stdout.write(f"  {name:<30} {o:>+6.2f} {d:>+6.2f} {o+d:>+7.2f}")
