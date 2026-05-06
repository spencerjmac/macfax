"""
nba_compute_ratings — compute opponent-adjusted ratings + FFI for one NBA season.

Reads NBATeamGameStats (populated by nba_sync_games), runs the sport-agnostic
iterative solver from services/ratings_engine, computes four factor season
averages, and writes NBATeamSeasonRatings records.

Also assigns integer ranks (rank_adj_net, rank_ffi) as derived presentation
values — they are NOT source of truth, just convenience fields.

Usage:
    uv run python manage.py nba_compute_ratings --season 2026
    uv run python manage.py nba_compute_ratings --season 2026 --dry-run
"""

import logging

from django.core.management.base import BaseCommand, CommandError

from nba.models import NBASeason, NBATeam, NBATeamGameStats, NBATeamSeasonRatings
from nba.ratings_config import NBA_RATINGS_CONFIG, NBA_FFI_WEIGHTS
from services.ratings_engine import GameRecord, RatingsConfig, iterative_adjust

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Compute opponent-adjusted ratings + FFI for an NBA season."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season", type=int, required=True,
            help="Ending season year (e.g., 2026 for the 2025-26 season)",
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--season-type", default="regular", choices=["regular", "playoffs"],
            help="Which game type to compute ratings for (default: regular)",
        )

    def handle(self, *args, **options):  # noqa: C901
        season_year: int = options["season"]
        dry_run: bool = options["dry_run"]
        season_type: str = options["season_type"]

        try:
            season = NBASeason.objects.get(year=season_year)
        except NBASeason.DoesNotExist:
            raise CommandError(
                f"NBASeason year={season_year} not found. "
                "Run nba_sync_games first to seed the season."
            )

        # ── Load qualifying game stats ────────────────────────────────────────
        if season_type == "playoffs":
            game_filter = {"game__season": season, "game__season_type": "playoffs"}
        else:
            game_filter = {"game__season": season, "game__counts_toward_regular_season": True}

        stats_qs = (
            NBATeamGameStats.objects
            .filter(
                **game_filter,
                poss__isnull=False,
                poss__gt=0,
            )
            .select_related("game", "team")
        )
        stats_list = list(stats_qs)

        if not stats_list:
            raise CommandError(
                f"No qualifying NBATeamGameStats found for season {season_year}. "
                "Run nba_sync_games first."
            )

        self.stdout.write(f"Loaded {len(stats_list)} team-game stats for {season.display_name}.")

        # ── Build opponent lookup: game_id + team_pk -> opponent stats ────────
        # For each game, there are two NBATeamGameStats rows. We need the opponent.
        game_stats: dict[str, dict[int, NBATeamGameStats]] = {}
        for stat in stats_list:
            gid = stat.game_id
            if gid not in game_stats:
                game_stats[gid] = {}
            game_stats[gid][stat.team_id] = stat

        # ── Build GameRecord list ─────────────────────────────────────────────
        game_records: list[GameRecord] = []
        skipped = 0
        for stat in stats_list:
            gid = stat.game_id
            game_pair = game_stats.get(gid, {})
            # Find opponent's stats for this game
            opp_stat = next(
                (s for tid, s in game_pair.items() if tid != stat.team_id), None
            )
            if opp_stat is None or stat.raw_ortg is None or stat.raw_drtg is None:
                skipped += 1
                continue

            game_records.append(
                GameRecord(
                    team_id=stat.team_id,
                    opp_id=opp_stat.team_id,
                    raw_ortg=stat.raw_ortg,
                    raw_drtg=stat.raw_drtg,
                    poss=stat.poss,
                    is_home=stat.is_home,
                    rest_days=stat.game.rest_days_home if stat.is_home else stat.game.rest_days_away,
                    is_b2b=stat.game.home_b2b if stat.is_home else stat.game.away_b2b,
                    counts_toward_ratings=True,
                )
            )

        self.stdout.write(
            f"Built {len(game_records)} GameRecords (skipped {skipped} incomplete)."
        )

        if not game_records:
            raise CommandError("No valid game records — cannot compute ratings.")

        # ── Run iterative solver ─────────────────────────────────────────────
        cfg = RatingsConfig(
            iterations=NBA_RATINGS_CONFIG["iterations"],
            convergence_threshold=NBA_RATINGS_CONFIG["convergence_threshold"],
            prior_games=NBA_RATINGS_CONFIG["prior_games"],
            prior_ortg=NBA_RATINGS_CONFIG["prior_ortg"],
            prior_drtg=NBA_RATINGS_CONFIG["prior_drtg"],
            home_court_adj=NBA_RATINGS_CONFIG["home_court_adj"],
            rest_adj_per_day=NBA_RATINGS_CONFIG["rest_adj_per_day"],
            b2b_penalty=NBA_RATINGS_CONFIG["b2b_penalty"],
        )
        self.stdout.write("Running iterative opponent-adjustment solver …")
        solver_results = iterative_adjust(game_records, cfg)

        # ── Compute season-level four factor aggregates ────────────────────
        # team_pk -> {fgm, fga, fg3m, fg3a, ftm, fta, oreb, dreb, tov, ...}
        ff_agg: dict[int, dict] = {}
        for stat in stats_list:
            tid = stat.team_id
            if tid not in ff_agg:
                ff_agg[tid] = dict(
                    fgm=0, fga=0, fg3m=0, fg3a=0, ftm=0, fta=0,
                    oreb=0, dreb=0, tov=0, pts=0, poss_sum=0.0, games=0,
                    opp_fgm=0, opp_fga=0, opp_fg3m=0, opp_fg3a=0,
                    opp_ftm=0, opp_fta=0, opp_oreb=0, opp_dreb=0, opp_tov=0,
                )
            agg = ff_agg[tid]

            def _safe(v):
                return v if v is not None else 0

            agg["fgm"] += _safe(stat.fgm)
            agg["fga"] += _safe(stat.fga)
            agg["fg3m"] += _safe(stat.fg3m)
            agg["fg3a"] += _safe(stat.fg3a)
            agg["ftm"] += _safe(stat.ftm)
            agg["fta"] += _safe(stat.fta)
            agg["oreb"] += _safe(stat.oreb)
            agg["dreb"] += _safe(stat.dreb)
            agg["tov"] += _safe(stat.tov)
            agg["poss_sum"] += stat.poss or 0.0
            agg["games"] += 1

            # Opponent's box score — look it up in the game pair
            gid = stat.game_id
            opp_stat = next(
                (s for tid2, s in game_stats.get(gid, {}).items() if tid2 != tid), None
            )
            if opp_stat:
                agg["opp_fgm"] += _safe(opp_stat.fgm)
                agg["opp_fga"] += _safe(opp_stat.fga)
                agg["opp_fg3m"] += _safe(opp_stat.fg3m)
                agg["opp_fg3a"] += _safe(opp_stat.fg3a)
                agg["opp_ftm"] += _safe(opp_stat.ftm)
                agg["opp_fta"] += _safe(opp_stat.fta)
                agg["opp_oreb"] += _safe(opp_stat.oreb)
                agg["opp_dreb"] += _safe(opp_stat.dreb)
                agg["opp_tov"] += _safe(opp_stat.tov)

        # ── Derive four factor rates per team ────────────────────────────────
        def _safe_div(num, denom, default=None):
            return num / denom if denom and denom > 0 else default

        team_ff: dict[int, dict] = {}
        for tid, agg in ff_agg.items():
            efg_pct = _safe_div(agg["fgm"] + 0.5 * agg["fg3m"], agg["fga"])
            opp_efg_pct = _safe_div(agg["opp_fgm"] + 0.5 * agg["opp_fg3m"], agg["opp_fga"])

            tov_denom = agg["fga"] + 0.44 * agg["fta"] + agg["tov"]
            tov_rate = _safe_div(agg["tov"], tov_denom)
            opp_tov_denom = agg["opp_fga"] + 0.44 * agg["opp_fta"] + agg["opp_tov"]
            opp_tov_rate = _safe_div(agg["opp_tov"], opp_tov_denom)

            oreb_denom = agg["oreb"] + agg["opp_dreb"]
            oreb_pct = _safe_div(agg["oreb"], oreb_denom)
            opp_oreb_denom = agg["opp_oreb"] + agg["dreb"]
            opp_oreb_pct = _safe_div(agg["opp_oreb"], opp_oreb_denom)

            fta_rate = _safe_div(agg["fta"], agg["fga"])
            opp_fta_rate = _safe_div(agg["opp_fta"], agg["opp_fga"])

            efg_margin = (
                efg_pct - opp_efg_pct
                if efg_pct is not None and opp_efg_pct is not None else None
            )
            tov_edge = (
                opp_tov_rate - tov_rate
                if tov_rate is not None and opp_tov_rate is not None else None
            )
            oreb_edge = (
                oreb_pct - opp_oreb_pct
                if oreb_pct is not None and opp_oreb_pct is not None else None
            )
            fta_margin = (
                fta_rate - opp_fta_rate
                if fta_rate is not None and opp_fta_rate is not None else None
            )

            # Pace: average possessions per game
            games = agg["games"] or 1
            pace = agg["poss_sum"] / games

            team_ff[tid] = dict(
                efg_pct=efg_pct,
                opp_efg_pct=opp_efg_pct,
                tov_rate=tov_rate,
                opp_tov_rate=opp_tov_rate,
                oreb_pct=oreb_pct,
                opp_oreb_pct=opp_oreb_pct,
                fta_rate=fta_rate,
                opp_fta_rate=opp_fta_rate,
                efg_margin=efg_margin,
                tov_edge=tov_edge,
                oreb_edge=oreb_edge,
                fta_margin=fta_margin,
                pace=pace,
                games=agg["games"],
            )

        # ── Compute FFI ──────────────────────────────────────────────────────
        #  Z-score each margin relative to all 30 teams, then weight and sum.
        #  This makes FFI comparable across seasons despite different margin scales.
        def _zscore_margins(metric_key: str) -> dict[int, float | None]:
            vals = [(tid, ff[metric_key]) for tid, ff in team_ff.items() if ff[metric_key] is not None]
            if len(vals) < 2:
                return {tid: None for tid in team_ff}
            values = [v for _, v in vals]
            mean = sum(values) / len(values)
            std = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
            if std < 1e-9:
                return {tid: 0.0 for tid, _ in vals}
            z = {tid: (v - mean) / std for tid, v in vals}
            return z

        z_efg = _zscore_margins("efg_margin")
        z_tov = _zscore_margins("tov_edge")
        z_oreb = _zscore_margins("oreb_edge")
        z_fta = _zscore_margins("fta_margin")

        w = NBA_FFI_WEIGHTS
        team_ffi: dict[int, float | None] = {}
        for tid in team_ff:
            zs = [z_efg.get(tid), z_tov.get(tid), z_oreb.get(tid), z_fta.get(tid)]
            if any(z is None for z in zs):
                team_ffi[tid] = None
            else:
                ffi_z = (
                    zs[0] * w["efg_margin"]
                    + zs[1] * w["tov_edge"]
                    + zs[2] * w["oreb_edge"]
                    + zs[3] * w["fta_margin"]
                )
                midpoint = w.get("scale_midpoint", 50.0)
                multiplier = w.get("scale_multiplier", 20.0)
                team_ffi[tid] = max(0.0, min(100.0, midpoint + multiplier * ffi_z))

        # ── Resolve team DB objects ───────────────────────────────────────────
        team_obj_map: dict[int, NBATeam] = {t.pk: t for t in NBATeam.objects.all()}

        # solver_results keys are team PKs (from GameRecord.team_id)
        all_team_ids = set(solver_results.keys()) & set(team_ff.keys())

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"DRY RUN — would write {len(all_team_ids)} NBATeamSeasonRatings records"
            ))
            for tid in sorted(all_team_ids):
                team = team_obj_map.get(tid)
                r = solver_results[tid]
                self.stdout.write(
                    f"  {team.abbreviation if team else tid:5s}  "
                    f"adjO={r['adj_off']:.1f}  adjD={r['adj_def']:.1f}  "
                    f"adjN={r['adj_net']:.1f}  g={r['game_count']}"
                )
            return

        # ── Write NBATeamSeasonRatings ───────────────────────────────────────
        written = 0
        rating_objects: list[tuple[int, NBATeamSeasonRatings]] = []
        for tid in all_team_ids:
            team = team_obj_map.get(tid)
            if not team:
                logger.warning("team_pk=%s not found in NBATeam table — skipping", tid)
                continue
            r = solver_results[tid]
            ff = team_ff[tid]
            obj, _ = NBATeamSeasonRatings.objects.update_or_create(
                team=team,
                season=season,
                season_type=season_type,
                defaults={
                    "games": ff["games"],
                    "adj_off": r["adj_off"],
                    "adj_def": r["adj_def"],
                    "adj_net": r["adj_net"],
                    "pace": ff["pace"],
                    "efg_pct": ff["efg_pct"],
                    "opp_efg_pct": ff["opp_efg_pct"],
                    "tov_rate": ff["tov_rate"],
                    "opp_tov_rate": ff["opp_tov_rate"],
                    "oreb_pct": ff["oreb_pct"],
                    "opp_oreb_pct": ff["opp_oreb_pct"],
                    "fta_rate": ff["fta_rate"],
                    "opp_fta_rate": ff["opp_fta_rate"],
                    "efg_margin": ff["efg_margin"],
                    "tov_edge": ff["tov_edge"],
                    "oreb_edge": ff["oreb_edge"],
                    "fta_margin": ff["fta_margin"],
                    "ffi": team_ffi.get(tid),
                },
            )
            written += 1
            rating_objects.append((tid, obj))

        # ── Assign ranks ─────────────────────────────────────────────────────
        # rank_adj_net: 1 = best (highest adj_net)
        sorted_by_net = sorted(
            rating_objects,
            key=lambda x: solver_results[x[0]]["adj_net"],
            reverse=True,
        )
        for rank, (tid, obj) in enumerate(sorted_by_net, start=1):
            obj.rank_adj_net = rank

        # rank_ffi: 1 = best (highest ffi)
        ffi_ranked = sorted(
            rating_objects,
            key=lambda x: (team_ffi.get(x[0]) or float("-inf")),
            reverse=True,
        )
        for rank, (tid, obj) in enumerate(ffi_ranked, start=1):
            obj.rank_ffi = rank

        NBATeamSeasonRatings.objects.bulk_update(
            [obj for _, obj in rating_objects],
            ["rank_adj_net", "rank_ffi"],
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done — wrote {written} NBATeamSeasonRatings records for {season.display_name}."
            )
        )
