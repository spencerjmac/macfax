"""
compute_ncaa_player_impact — aggregate PlayerGameStint rows into per-season
on-court ratings and write them into PlayerSeasonStats.

Run AFTER:
  1. sync_ncaa_player_gamelogs  (creates PlayerGameStats + PlayerSeasonStats base)
  2. sync_ncaa_pbp              (creates PlayerGameStint rows)

Metrics written to PlayerSeasonStats:

  On-court raw ratings (pts-based):
    on_court_secs_pg, on_court_pts_pg, on_court_def_pg, on_court_net_pg
    on_court_ortg, on_court_drtg, on_court_net

  On-court Four Factors (Phase D — requires sync_ncaa_pbp with box events):
    on_court_efg_pct, on_court_tov_pct, on_court_orb_pct, on_court_ftr
    on_court_opp_efg_pct, on_court_opp_tov_pct, on_court_drb_pct, on_court_opp_ftr
    on_court_efg_margin, on_court_tov_edge, on_court_reb_edge, on_court_ftr_margin
    on_court_ffi  (0-100 Four Factor Index relative to all qualifying players)

  MPIR (Macfax Player Impact Rating — Bayesian blend of on-court and box priors):
    o_mpir  (Offensive MPIR)
    d_mpir  (Defensive MPIR)
    mpir    (O-MPIR + D-MPIR)

Usage:
    python manage.py compute_ncaa_player_impact --season 2026
"""

import logging
import math
import statistics
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.constants import FOUR_FACTOR_SCALE, FOUR_FACTOR_WEIGHTS
from core.models import Game, PlayerGameStint, PlayerSeasonStats, Season

logger = logging.getLogger(__name__)

SECS_PER_40_MIN = 40 * 60  # 2400
# Minimum total on-court FGA to bother computing Four Factors (avoids /0 and noise)
MIN_FF_FGA = 30


def _per40(total_pts: float, total_secs: float) -> float | None:
    """Points per 40 minutes on court. Returns None for tiny samples."""
    if total_secs < 60:
        return None
    return round(total_pts / total_secs * SECS_PER_40_MIN, 2)


def _safe_pct(num: int, denom: int) -> float | None:
    """Return num/denom * 100 rounded to 2dp, or None if denom == 0."""
    return round(num / denom * 100, 2) if denom > 0 else None


def _compute_four_factors(b: dict) -> dict:
    """
    Given accumulated box-event totals for one player's season, compute all
    on-court Four Factor rates and margins.  Returns a dict of field → value.

    b keys: team_fgm, team_fga, team_fg3m, team_fta, team_tov, team_oreb, team_dreb
            opp_fgm,  opp_fga,  opp_fg3m,  opp_fta,  opp_tov,  opp_oreb,  opp_dreb
    """
    # ── Offensive Four Factors ────────────────────────────────────────────────
    efg = _safe_pct(b["team_fgm"] + b["team_fg3m"] // 2, b["team_fga"])
    # eFG% = (FGM + 0.5*FG3M) / FGA — avoid integer truncation
    if b["team_fga"] > 0:
        efg = round((b["team_fgm"] + 0.5 * b["team_fg3m"]) / b["team_fga"] * 100, 2)

    tov_denom = b["team_fga"] + round(0.44 * b["team_fta"]) + b["team_tov"]
    tov_pct = _safe_pct(b["team_tov"], tov_denom)

    orb_denom = b["team_oreb"] + b["opp_dreb"]
    orb_pct = _safe_pct(b["team_oreb"], orb_denom)

    ftr = _safe_pct(b["team_fta"], b["team_fga"])

    # ── Defensive Four Factors (opponent) ─────────────────────────────────────
    opp_efg = None
    if b["opp_fga"] > 0:
        opp_efg = round((b["opp_fgm"] + 0.5 * b["opp_fg3m"]) / b["opp_fga"] * 100, 2)

    opp_tov_denom = b["opp_fga"] + round(0.44 * b["opp_fta"]) + b["opp_tov"]
    opp_tov_pct = _safe_pct(b["opp_tov"], opp_tov_denom)

    opp_orb_denom = b["opp_oreb"] + b["team_dreb"]
    opp_orb_pct = _safe_pct(b["opp_oreb"], opp_orb_denom)   # opp ORB%
    drb_pct = (round(100 - opp_orb_pct, 2) if opp_orb_pct is not None else None)  # team DRB%

    opp_ftr = _safe_pct(b["opp_fta"], b["opp_fga"])

    # ── Margins ───────────────────────────────────────────────────────────────
    efg_margin = (round(efg - opp_efg, 2)
                  if efg is not None and opp_efg is not None else None)
    # TOV edge: opp_tov_pct - team_tov_pct (higher = better, we force more turnovers than we commit)
    tov_edge = (round(opp_tov_pct - tov_pct, 2)
                if tov_pct is not None and opp_tov_pct is not None else None)
    # Reb edge: team_orb_pct - opp_orb_pct
    reb_edge = (round(orb_pct - opp_orb_pct, 2)
                if orb_pct is not None and opp_orb_pct is not None else None)
    ftr_margin = (round(ftr - opp_ftr, 2)
                  if ftr is not None and opp_ftr is not None else None)

    return dict(
        on_court_efg_pct=efg,
        on_court_tov_pct=tov_pct,
        on_court_orb_pct=orb_pct,
        on_court_ftr=ftr,
        on_court_opp_efg_pct=opp_efg,
        on_court_opp_tov_pct=opp_tov_pct,
        on_court_drb_pct=drb_pct,
        on_court_opp_ftr=opp_ftr,
        on_court_efg_margin=efg_margin,
        on_court_tov_edge=tov_edge,
        on_court_reb_edge=reb_edge,
        on_court_ftr_margin=ftr_margin,
    )


def _compute_ffi(efg_margin: float, tov_edge: float,
                 reb_edge: float, ftr_margin: float,
                 means: dict, stds: dict) -> float:
    """
    Weighted Z-score → 0-100 FFI using same formula as team compute_four_factor_index.
    means/stds: {efg, tov, reb, ftr} → float
    """
    def _z(val, key):
        s = stds[key]
        return (val - means[key]) / s if s > 0 else 0.0

    wz = (
        FOUR_FACTOR_WEIGHTS["efg"] * _z(efg_margin, "efg") +
        FOUR_FACTOR_WEIGHTS["tov"] * _z(tov_edge,   "tov") +
        FOUR_FACTOR_WEIGHTS["reb"] * _z(reb_edge,   "reb") +
        FOUR_FACTOR_WEIGHTS["ftr"] * _z(ftr_margin, "ftr")
    )
    return max(0.0, min(100.0, 50.0 + FOUR_FACTOR_SCALE * wz))


class Command(BaseCommand):
    help = "Roll up PlayerGameStint data into on-court ratings on PlayerSeasonStats."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season", type=int, required=True,
            help="Ending season year (e.g., 2026)",
        )
        parser.add_argument(
            "--min-secs", type=int, default=120,
            help="Minimum total on-court seconds to compute ratings (default 120)",
        )

    def handle(self, *args, **options):
        season_year: int = options["season"]
        min_secs: int = options["min_secs"]

        try:
            season = Season.objects.get(year=season_year)
        except Season.DoesNotExist:
            raise CommandError(
                f"Season {season_year} not found.  Run season setup first."
            )

        # All game IDs for this season
        game_ids = set(
            Game.objects.filter(season_year=season_year).values_list("id", flat=True)
        )
        if not game_ids:
            self.stdout.write(self.style.WARNING(f"No games for season {season_year}."))
            return

        # All stints for this season
        stints_qs = (
            PlayerGameStint.objects.filter(game_id__in=game_ids)
            .select_related("player", "team")
        )

        stint_count = stints_qs.count()
        if stint_count == 0:
            self.stdout.write(
                self.style.WARNING(
                    "No PlayerGameStint rows found for this season.  "
                    f"Run: python manage.py sync_ncaa_pbp --season {season_year}"
                )
            )
            return

        self.stdout.write(
            f"Aggregating {stint_count} stints for {season.display_name}..."
        )

        # ── Aggregate by (player_id, team_id) ────────────────────────────────
        # Same grouping as PlayerSeasonStats.
        totals: dict[int, dict] = defaultdict(
            lambda: defaultdict(lambda: {
                "secs": 0, "pts": 0, "def_pts": 0, "game_ids": set(),
                # Box events (populated after Phase D sync)
                "team_fgm": 0, "team_fga": 0, "team_fg3m": 0,
                "team_fta": 0, "team_tov": 0, "team_oreb": 0, "team_dreb": 0,
                "opp_fgm":  0, "opp_fga":  0, "opp_fg3m":  0,
                "opp_fta":  0, "opp_tov":  0, "opp_oreb":  0, "opp_dreb":  0,
            })
        )

        for stint in stints_qs:
            pid = stint.player_id
            tid = stint.team_id
            b = totals[pid][tid]
            b["secs"]     += stint.secs_on
            b["pts"]      += stint.pts_scored
            b["def_pts"]  += stint.pts_allowed
            b["game_ids"].add(stint.game_id)
            # Box events
            b["team_fgm"]  += stint.team_fgm
            b["team_fga"]  += stint.team_fga
            b["team_fg3m"] += stint.team_fg3m
            b["team_fta"]  += stint.team_fta
            b["team_tov"]  += stint.team_tov
            b["team_oreb"] += stint.team_oreb
            b["team_dreb"] += stint.team_dreb
            b["opp_fgm"]  += stint.opp_fgm
            b["opp_fga"]  += stint.opp_fga
            b["opp_fg3m"] += stint.opp_fg3m
            b["opp_fta"]  += stint.opp_fta
            b["opp_tov"]  += stint.opp_tov
            b["opp_oreb"] += stint.opp_oreb
            b["opp_dreb"] += stint.opp_dreb

        # ── Load season stats map ─────────────────────────────────────────────
        season_stats_map: dict[tuple, PlayerSeasonStats] = {}
        for stat in PlayerSeasonStats.objects.filter(season=season).select_related("player", "team"):
            season_stats_map[(stat.player_id, stat.team_id)] = stat

        # ── First pass: compute all values and collect margins for FFI z-scores
        computed: dict[tuple, dict] = {}

        for player_id, team_buckets in totals.items():
            for team_id, data in team_buckets.items():
                total_secs = data["secs"]
                if total_secs < min_secs:
                    continue
                gp = len(data["game_ids"])
                if gp == 0:
                    continue
                stat = season_stats_map.get((player_id, team_id))
                if stat is None:
                    continue

                total_pts = data["pts"]
                total_def = data["def_pts"]
                secs_pg   = round(total_secs / gp, 2)
                pts_pg    = round(total_pts  / gp, 2)
                def_pg    = round(total_def  / gp, 2)
                net_pg    = round((total_pts - total_def) / gp, 2)
                ortg      = _per40(total_pts, total_secs)
                drtg      = _per40(total_def, total_secs)
                net_rating = (
                    round(ortg - drtg, 2)
                    if ortg is not None and drtg is not None else None
                )

                entry: dict = dict(
                    on_court_secs_pg=secs_pg,
                    on_court_pts_pg=pts_pg,
                    on_court_def_pg=def_pg,
                    on_court_net_pg=net_pg,
                    on_court_ortg=ortg,
                    on_court_drtg=drtg,
                    on_court_net=net_rating,
                    # FF fields default to None until box events populated
                    on_court_efg_pct=None, on_court_tov_pct=None,
                    on_court_orb_pct=None, on_court_ftr=None,
                    on_court_opp_efg_pct=None, on_court_opp_tov_pct=None,
                    on_court_drb_pct=None, on_court_opp_ftr=None,
                    on_court_efg_margin=None, on_court_tov_edge=None,
                    on_court_reb_edge=None, on_court_ftr_margin=None,
                    on_court_ffi=None,
                )

                # Compute Four Factors only if box events were recorded
                if data["team_fga"] >= MIN_FF_FGA:
                    ff = _compute_four_factors(data)
                    entry.update(ff)

                computed[(player_id, team_id)] = entry

        # ── FFI: collect margins from all players with complete FF data ────────
        efg_vals, tov_vals, reb_vals, ftr_vals = [], [], [], []
        for entry in computed.values():
            if all(entry.get(k) is not None for k in (
                "on_court_efg_margin", "on_court_tov_edge",
                "on_court_reb_edge", "on_court_ftr_margin"
            )):
                efg_vals.append(entry["on_court_efg_margin"])
                tov_vals.append(entry["on_court_tov_edge"])
                reb_vals.append(entry["on_court_reb_edge"])
                ftr_vals.append(entry["on_court_ftr_margin"])

        has_ffi = len(efg_vals) >= 5  # need enough players for meaningful z-scores
        if has_ffi:
            def _ms(vals):
                m = statistics.mean(vals)
                s = statistics.stdev(vals) if len(vals) > 1 else 1.0
                return m, s
            efg_m, efg_s = _ms(efg_vals)
            tov_m, tov_s = _ms(tov_vals)
            reb_m, reb_s = _ms(reb_vals)
            ftr_m, ftr_s = _ms(ftr_vals)
            means = {"efg": efg_m, "tov": tov_m, "reb": reb_m, "ftr": ftr_m}
            stds  = {"efg": efg_s, "tov": tov_s, "reb": reb_s, "ftr": ftr_s}
            self.stdout.write(
                f"FFI: computing on {len(efg_vals)} players with full Four Factor data"
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Not enough players with Four Factor data ({len(efg_vals)}) "
                    "to compute FFI.  Re-run sync_ncaa_pbp --force to populate box events."
                )
            )

        # ── Fill in FFI for qualifying players ────────────────────────────────
        if has_ffi:
            for entry in computed.values():
                m = entry.get("on_court_efg_margin")
                t = entry.get("on_court_tov_edge")
                r = entry.get("on_court_reb_edge")
                f = entry.get("on_court_ftr_margin")
                if m is not None and t is not None and r is not None and f is not None:
                    entry["on_court_ffi"] = round(
                        _compute_ffi(m, t, r, f, means, stds), 2
                    )

        # ── MPIR: Macfax Player Impact Rating ────────────────────────────────
        # Blend weight w = total_min / (total_min + PRIOR_MINS)
        # At 300 min: w=0.50 (50/50 on-court vs box prior)
        # At 900 min: w=0.75 (typical starter), at 0 min: w=0 (box prior only)
        PRIOR_MINS = 300

        # Collect league-average values from on-court and box data
        ortg_vals, drtg_vals, pts40_vals, def40_vals = [], [], [], []
        for (pid, tid), entry in computed.items():
            stat = season_stats_map.get((pid, tid))
            if stat is None:
                continue
            if entry.get("on_court_ortg") is not None:
                ortg_vals.append(entry["on_court_ortg"])
            if entry.get("on_court_drtg") is not None:
                drtg_vals.append(entry["on_court_drtg"])
            if stat.mpg and stat.mpg > 5:
                pts40_vals.append(stat.pts / stat.mpg * 40)
                def40_vals.append((stat.stl * 2.5 + stat.blk) / stat.mpg * 40)

        league_avg_ortg  = statistics.mean(ortg_vals)  if ortg_vals  else 0.0
        league_avg_drtg  = statistics.mean(drtg_vals)  if drtg_vals  else 0.0
        league_avg_pts40 = statistics.mean(pts40_vals) if pts40_vals else 0.0
        league_avg_def40 = statistics.mean(def40_vals) if def40_vals else 0.0
        self.stdout.write(
            f"MPIR league avgs: ortg={league_avg_ortg:.1f}  drtg={league_avg_drtg:.1f}  "
            f"pts40={league_avg_pts40:.1f}  def40={league_avg_def40:.1f}"
        )

        for (player_id, team_id), entry in computed.items():
            stat = season_stats_map.get((player_id, team_id))
            if stat is None:
                continue

            # Total minutes for this player (use on_court_secs_pg × gp)
            gp = len(totals[player_id][team_id]["game_ids"])
            total_min = (entry.get("on_court_secs_pg") or 0) * gp / 60
            w = total_min / (total_min + PRIOR_MINS) if total_min > 0 else 0.0

            on_off = (
                entry["on_court_ortg"] - league_avg_ortg
                if entry.get("on_court_ortg") is not None else None
            )
            on_def = (
                league_avg_drtg - entry["on_court_drtg"]
                if entry.get("on_court_drtg") is not None else None
            )

            if stat.mpg and stat.mpg >= 5 and stat.gp and stat.gp >= 3:
                box_off = stat.pts / stat.mpg * 40 - league_avg_pts40
                box_def = (stat.stl * 2.5 + stat.blk) / stat.mpg * 40 - league_avg_def40
            else:
                box_off = box_def = None

            o_mpir = d_mpir = mpir = None
            if on_off is not None and box_off is not None:
                o_mpir = round(w * on_off + (1 - w) * box_off, 2)
            if on_def is not None and box_def is not None:
                d_mpir = round(w * on_def + (1 - w) * box_def, 2)
            if o_mpir is not None and d_mpir is not None:
                mpir = round(o_mpir + d_mpir, 2)

            entry["o_mpir"] = o_mpir
            entry["d_mpir"] = d_mpir
            entry["mpir"]   = mpir

        # ── Write to DB ───────────────────────────────────────────────────────
        FF_FIELDS = [
            "on_court_secs_pg", "on_court_pts_pg", "on_court_def_pg",
            "on_court_net_pg", "on_court_ortg", "on_court_drtg", "on_court_net",
            "on_court_efg_pct", "on_court_tov_pct", "on_court_orb_pct", "on_court_ftr",
            "on_court_opp_efg_pct", "on_court_opp_tov_pct", "on_court_drb_pct", "on_court_opp_ftr",
            "on_court_efg_margin", "on_court_tov_edge", "on_court_reb_edge", "on_court_ftr_margin",
            "on_court_ffi",
            "o_mpir", "d_mpir", "mpir",
        ]

        updated = skipped = 0
        with transaction.atomic():
            for (player_id, team_id), entry in computed.items():
                stat = season_stats_map.get((player_id, team_id))
                if stat is None:
                    skipped += 1
                    continue
                for field, val in entry.items():
                    setattr(stat, field, val)
                stat.save(update_fields=FF_FIELDS)
                updated += 1

        # Count players with FFI
        ffi_count = sum(
            1 for e in computed.values() if e.get("on_court_ffi") is not None
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Done.  updated={updated}  skipped={skipped}  "
                f"with_ffi={ffi_count}  (min_secs={min_secs})"
            )
        )
