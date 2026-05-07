"""
Management command: nba_compute_baseline_rapm

Loads NBAPlayerGameStint rows, builds RAPM lineup observations, fits baseline
RAPM with 5-fold game CV, and writes baseline_obpr / baseline_dbpr /
off_poss / def_poss to NBAPlayerSeasonStats.

After this runs, re-run nba_compute_box_bpr to retrain box BPR using
baseline_obpr / baseline_dbpr as targets instead of the MPIR proxy.

Usage:
  python manage.py nba_compute_baseline_rapm --season 2026
  python manage.py nba_compute_baseline_rapm --season 2026 --rapm-years 2024 2025 2026
  python manage.py nba_compute_baseline_rapm --season 2026 --lambda-override 500
  python manage.py nba_compute_baseline_rapm --season 2026 --dry-run
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from nba.analytics.rapm import build_nba_observations, fit_baseline_rapm
from nba.models import NBAPlayerSeasonStats, NBAPlayer

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Fit baseline RAPM and write baseline_obpr / baseline_dbpr to NBAPlayerSeasonStats"

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True, help="Target season ending year")
        parser.add_argument(
            "--rapm-years", type=int, nargs="+",
            help="Season years to pool for multi-year RAPM (e.g. --rapm-years 2024 2025 2026). "
                 "Defaults to --season only.",
        )
        parser.add_argument(
            "--lambda-override", type=float,
            help="Skip CV and use this λ directly (e.g. --lambda-override 500)",
        )
        parser.add_argument("--dry-run", action="store_true", help="Compute but do not write")

    def handle(self, *args, **options):
        season_year: int = options["season"]
        rapm_years: list[int] | None = options.get("rapm_years")
        lambda_override: float | None = options.get("lambda_override")
        dry_run: bool = options["dry_run"]

        self.stdout.write(f"\n[BASELINE RAPM] Target season: {season_year}")
        if rapm_years:
            self.stdout.write(f"  Pooling seasons: {rapm_years}")
        if lambda_override:
            self.stdout.write(f"  λ override: {lambda_override} (skipping CV)")
        if dry_run:
            self.stdout.write("[DRY RUN] No writes")

        # ── 1. Build observations ─────────────────────────────────────────────
        self.stdout.write("Loading stint observations...")
        observations = build_nba_observations(
            season_year=season_year,
            rapm_years=rapm_years,
        )

        if not observations:
            raise CommandError(
                f"No observations found. Run nba_sync_play_by_play --season {season_year} first."
            )

        self.stdout.write(f"  {len(observations)} lineup observations loaded")

        # ── 2. Build player-season index ──────────────────────────────────────
        all_player_season_keys: set[tuple[int, int]] = set()
        for obs in observations:
            year = obs["season_year"]
            for pid in obs["home_player_ids"] + obs["away_player_ids"]:
                all_player_season_keys.add((pid, year))

        player_season_index = {
            ps: i for i, ps in enumerate(sorted(all_player_season_keys))
        }
        n_player_seasons = len(player_season_index)
        self.stdout.write(
            f"  {n_player_seasons} player-season columns "
            f"({len({ps[0] for ps in all_player_season_keys})} unique players)"
        )

        # ── 3. Fit RAPM ───────────────────────────────────────────────────────
        self.stdout.write("Fitting baseline RAPM (5-fold CV)..." if not lambda_override
                          else f"Fitting baseline RAPM (λ={lambda_override})...")
        result = fit_baseline_rapm(
            observations=observations,
            player_season_index=player_season_index,
            n_player_seasons=n_player_seasons,
            run_cv=(lambda_override is None),
            lambda_override=lambda_override,
        )

        best_lambda = result["lambda"]
        obpr_all = result["obpr"]   # {(player_id, season_year): float}
        dbpr_all = result["dbpr"]
        self.stdout.write(
            f"  λ={best_lambda:.1f}  HCA={result['hca']:.2f}  intercept={result['intercept']:.2f}"
        )

        if result.get("cv_metrics"):
            cv = result["cv_metrics"]
            self.stdout.write(f"  CV best WMSE: {cv['mean_wmse'][best_lambda]:.4f}")

        # ── 4. Extract target-season results ──────────────────────────────────
        target_obpr: dict[int, float] = {
            pid: v for (pid, yr), v in obpr_all.items() if yr == season_year
        }
        target_dbpr: dict[int, float] = {
            pid: v for (pid, yr), v in dbpr_all.items() if yr == season_year
        }
        self.stdout.write(
            f"  {len(target_obpr)} players with baseline RAPM for {season_year}"
        )

        # ── 5. Compute poss totals for target season ───────────────────────────
        off_poss_map: dict[int, float] = {}
        def_poss_map: dict[int, float] = {}
        for obs in observations:
            if obs["season_year"] != season_year:
                continue
            for pid in obs["home_player_ids"]:
                off_poss_map[pid] = off_poss_map.get(pid, 0.0) + obs["home_poss"]
                def_poss_map[pid] = def_poss_map.get(pid, 0.0) + obs["away_poss"]
            for pid in obs["away_player_ids"]:
                off_poss_map[pid] = off_poss_map.get(pid, 0.0) + obs["away_poss"]
                def_poss_map[pid] = def_poss_map.get(pid, 0.0) + obs["home_poss"]

        # ── 6. Print leaderboard ───────────────────────────────────────────────
        self._print_leaderboard(target_obpr, target_dbpr)

        if dry_run:
            return

        # ── 7. Write to NBAPlayerSeasonStats ──────────────────────────────────
        # Build player_id (NBA.com) → NBAPlayer.pk map
        nbacom_to_pk: dict[int, int] = {
            p.player_id: p.pk
            for p in NBAPlayer.objects.filter(
                player_id__in=target_obpr.keys()
            ).only("pk", "player_id")
        }

        stats_qs = NBAPlayerSeasonStats.objects.filter(
            season__year=season_year,
            season_type="regular",
        ).select_related("player")

        updated = 0
        skipped = 0

        for stat_row in stats_qs:
            nba_player_id = stat_row.player.player_id
            if nba_player_id not in target_obpr:
                skipped += 1
                continue
            stat_row.baseline_obpr = round(target_obpr[nba_player_id], 4)
            stat_row.baseline_dbpr = round(target_dbpr.get(nba_player_id, 0.0), 4)
            stat_row.off_poss = round(off_poss_map.get(nba_player_id, 0.0), 1)
            stat_row.def_poss = round(def_poss_map.get(nba_player_id, 0.0), 1)
            stat_row.save(update_fields=["baseline_obpr", "baseline_dbpr", "off_poss", "def_poss"])
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\n[OK] baseline_obpr/dbpr written: {updated} updated, {skipped} skipped "
                f"(no RAPM data — not enough stints or traded player)"
            )
        )
        self.stdout.write(
            "Next: run nba_compute_box_bpr --season {season_year} to retrain box BPR with RAPM targets."
        )

    def _print_leaderboard(
        self,
        obpr: dict[int, float],
        dbpr: dict[int, float],
        n: int = 20,
    ) -> None:
        combined = {pid: obpr[pid] + dbpr.get(pid, 0.0) for pid in obpr}
        sorted_pids = sorted(combined, key=combined.get, reverse=True)

        name_map: dict[int, str] = {
            p.player_id: p.name
            for p in NBAPlayer.objects.filter(player_id__in=sorted_pids[:n]).only("player_id", "name")
        }

        self.stdout.write(f"\nTop {n} by baseline RAPM (OBPR + DBPR):")
        for pid in sorted_pids[:n]:
            o = obpr.get(pid, 0.0)
            d = dbpr.get(pid, 0.0)
            name = name_map.get(pid, f"player_id={pid}")
            self.stdout.write(
                f"  {name:30s}  obpr={o:+.2f}  dbpr={d:+.2f}  total={o+d:+.2f}"
            )
