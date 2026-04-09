"""
nba_sync_player_advanced — pull advanced + impact stats from NBA.com into
NBAPlayerSeasonStats rows that already exist (created by nba_compute_player_stats).

Data sources (all via LeagueDashPlayerStats):
  1. Advanced/PerGame  → E_OFF/DEF/NET_RATING, EFG_PCT, TS_PCT, USG_PCT,
                         AST_PCT, AST_TO, OREB_PCT, DREB_PCT, E_TOV_PCT,
                         PIE, POSS, raw ON/DEF/NET ratings
  2. Base/PerGame      → OREB, DREB, FTM, FTA (per-game averages)
  3. Defense/PerGame   → PCT_STL, PCT_BLK

Computed post-fetch:
  - mpir         = E_NET_RATING   (Bayesian-stabilised on-court net impact)
  - o_mpir       = E_OFF_RATING − league_avg_off  (positive = good)
  - d_mpir       = league_avg_def − E_DEF_RATING  (positive = good)

Only updates rows that already exist in NBAPlayerSeasonStats.  Players
present in the NBA.com data but absent from our DB are logged and skipped.

Usage:
    python manage.py nba_sync_player_advanced --season 2026
    python manage.py nba_sync_player_advanced --season 2026 --sleep 1.5
    python manage.py nba_sync_player_advanced --season 2026 --dry-run
"""

import logging
import time

from django.core.management.base import BaseCommand, CommandError

from nba.models import NBASeason, NBAPlayerSeasonStats

logger = logging.getLogger(__name__)


def _season_str(year: int) -> str:
    """2026 → '2025-26'"""
    return f"{year - 1}-{str(year)[2:]}"


def _safe_float(value) -> "float | None":
    try:
        if value is None or str(value).strip() in ("", "None", "nan"):
            return None
        return float(value)
    except (ValueError, TypeError):
        return None


class Command(BaseCommand):
    help = "Enrich NBAPlayerSeasonStats with advanced + impact stats from NBA.com."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season", type=int, required=True,
            help="Ending season year (e.g., 2026)",
        )
        parser.add_argument(
            "--sleep", type=float, default=1.2,
            help="Seconds to sleep between NBA.com API calls (default 1.2).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Fetch data and show what would be updated, but do not write.",
        )

    # ── Fetch helpers ─────────────────────────────────────────────────────────

    def _fetch(self, measure: str, per_mode: str, season: str, sleep: float):
        """Call LeagueDashPlayerStats and return a DataFrame."""
        from nba_api.stats.endpoints import leaguedashplayerstats  # type: ignore[import]

        self.stdout.write(
            f"  Fetching LeagueDashPlayerStats "
            f"measure={measure} per_mode={per_mode} season={season} …"
        )
        time.sleep(sleep)
        df = leaguedashplayerstats.LeagueDashPlayerStats(
            season=season,
            measure_type_detailed_defense=measure,
            per_mode_detailed=per_mode,
            timeout=45,
        ).get_data_frames()[0]
        self.stdout.write(f"    → {len(df)} rows returned")
        return df

    # ── Main ──────────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        season_year: int = options["season"]
        sleep: float = options["sleep"]
        dry_run: bool = options["dry_run"]

        try:
            season = NBASeason.objects.get(year=season_year)
        except NBASeason.DoesNotExist:
            raise CommandError(
                f"Season {season_year} not found. Run nba_sync_teams first."
            )

        season_s = _season_str(season_year)
        self.stdout.write(
            f"Syncing advanced player stats for {season.display_name} "
            + ("[DRY RUN] " if dry_run else "")
        )

        # ── Step 1: load all three NBA.com datasets ───────────────────────────
        df_adv = self._fetch("Advanced", "PerGame", season_s, sleep)
        df_base = self._fetch("Base", "PerGame", season_s, sleep)
        df_def = self._fetch("Defense", "PerGame", season_s, sleep)

        # ── Step 2: build lookup dicts keyed by (player_id, team_id) ─────────
        adv_map: dict[tuple[int, int], dict] = {}
        for _, row in df_adv.iterrows():
            pid, tid = int(row["PLAYER_ID"]), int(row["TEAM_ID"])
            adv_map[(pid, tid)] = row

        base_map: dict[tuple[int, int], dict] = {}
        for _, row in df_base.iterrows():
            pid, tid = int(row["PLAYER_ID"]), int(row["TEAM_ID"])
            base_map[(pid, tid)] = row

        def_map: dict[tuple[int, int], dict] = {}
        for _, row in df_def.iterrows():
            pid, tid = int(row["PLAYER_ID"]), int(row["TEAM_ID"])
            def_map[(pid, tid)] = row

        # ── Step 3: compute league-average off/def ratings (poss-weighted) ───
        # Used to centre E_OFF/E_DEF into MPIR components.
        import numpy as np  # numpy is always available in this stack

        poss_col = df_adv["POSS"].fillna(0)
        total_poss = poss_col.sum()
        if total_poss > 0:
            league_avg_off = float(
                (df_adv["E_OFF_RATING"].fillna(0) * poss_col).sum() / total_poss
            )
            league_avg_def = float(
                (df_adv["E_DEF_RATING"].fillna(0) * poss_col).sum() / total_poss
            )
        else:
            league_avg_off = float(df_adv["E_OFF_RATING"].mean())
            league_avg_def = float(df_adv["E_DEF_RATING"].mean())

        self.stdout.write(
            f"  League-avg E_OFF={league_avg_off:.1f}  E_DEF={league_avg_def:.1f}"
        )

        # ── Step 4: iterate over existing NBAPlayerSeasonStats rows ──────────
        qs = (
            NBAPlayerSeasonStats.objects
            .filter(season=season)
            .select_related("player", "team")
        )
        total = qs.count()
        if total == 0:
            self.stdout.write(
                self.style.WARNING(
                    "No NBAPlayerSeasonStats rows found for this season. "
                    "Run nba_compute_player_stats first."
                )
            )
            return

        self.stdout.write(f"  Updating {total} NBAPlayerSeasonStats rows …")

        updated = 0
        skipped = 0

        for stat_row in qs:
            pid = stat_row.player.player_id
            tid = stat_row.team.nba_team_id if stat_row.team else None

            # Primary key for NBA.com lookups
            key = (pid, tid) if tid else None

            # Fallback: if a player changed teams mid-season, NBA.com may
            # have a "TOT" row (team_id differs). Try player-only match.
            adv = adv_map.get(key) if key else None
            base = base_map.get(key) if key else None
            def_ = def_map.get(key) if key else None

            if adv is None:
                # Try any team row for this player (trade / TOT scenario)
                for k, v in adv_map.items():
                    if k[0] == pid:
                        adv = v
                        base = base_map.get(k)
                        def_ = def_map.get(k)
                        break

            if adv is None:
                logger.debug("No NBA.com advanced row for player_id=%d", pid)
                skipped += 1
                continue

            # ── Build update dict ─────────────────────────────────────────────
            e_off = _safe_float(adv.get("E_OFF_RATING"))
            e_def = _safe_float(adv.get("E_DEF_RATING"))
            e_net = _safe_float(adv.get("E_NET_RATING"))

            o_mpir = (e_off - league_avg_off) if e_off is not None else None
            d_mpir = (league_avg_def - e_def) if e_def is not None else None

            fields = {
                # Advanced efficiency
                "efg_pct":      _safe_float(adv.get("EFG_PCT")),
                "ts_pct":       _safe_float(adv.get("TS_PCT")),
                "usg_pct":      _safe_float(adv.get("USG_PCT")),
                "oreb_pct":     _safe_float(adv.get("OREB_PCT")),
                "dreb_pct":     _safe_float(adv.get("DREB_PCT")),
                "ast_pct":      _safe_float(adv.get("AST_PCT")),
                "tov_pct":      _safe_float(adv.get("E_TOV_PCT")),
                "ast_to":       _safe_float(adv.get("AST_TO")),
                "pie":          _safe_float(adv.get("PIE")),
                # Raw on-court ratings
                "on_court_ortg": _safe_float(adv.get("OFF_RATING")),
                "on_court_drtg": _safe_float(adv.get("DEF_RATING")),
                "on_court_net":  _safe_float(adv.get("NET_RATING")),
                "on_court_poss": _safe_float(adv.get("POSS")),
                # Bayesian-stabilised (E_*) on-court ratings
                "on_court_adj_o":  e_off,
                "on_court_adj_d":  e_def,
                "on_court_adj_em": e_net,
                # MPIR
                "mpir":   e_net,
                "o_mpir": o_mpir,
                "d_mpir": d_mpir,
            }

            if base is not None:
                fields.update({
                    "oreb_pg": _safe_float(base.get("OREB")),
                    "dreb_pg": _safe_float(base.get("DREB")),
                    "fta_pg":  _safe_float(base.get("FTA")),
                    "ftm_pg":  _safe_float(base.get("FTM")),
                })

            if def_ is not None:
                fields.update({
                    "stl_pct": _safe_float(def_.get("PCT_STL")),
                    "blk_pct": _safe_float(def_.get("PCT_BLK")),
                })

            if dry_run:
                self.stdout.write(
                    f"  [dry-run] {stat_row.player.name}: "
                    f"mpir={fields.get('mpir'):.2f}  "
                    f"efg={fields.get('efg_pct')}  ts={fields.get('ts_pct')}"
                )
                updated += 1
                continue

            for attr, val in fields.items():
                setattr(stat_row, attr, val)
            stat_row.save(update_fields=list(fields.keys()))
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. updated={updated}  skipped={skipped}"
                + (" [DRY RUN — no DB writes]" if dry_run else "")
            )
        )
