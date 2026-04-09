"""
Diagnostic command: compare AdjEM results across multiple k-floor values (no DB writes).
Usage:
    python manage.py compare_k_floor --season 2026
    python manage.py compare_k_floor --season 2026 --floors 170 150 100 0
"""

import math
import statistics
from collections import defaultdict
from datetime import date

from django.core.management.base import BaseCommand
from django.db.models import Count

from core.models import Game, NationalAverages, Team, TeamGameStats

ITERATIONS = 75
CONVERGENCE = 0.001
RECENCY_LAMBDA = 0.0040
IMP_C = 40.0
IMP_FLOOR = 0.35
CLOSE_M = 12.0
BOOST_MAX = 1.25
FREEZE_ITERATION = 6


class Command(BaseCommand):
    help = "Compare AdjEM rankings under multiple k-floor values (no DB writes)"

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument(
            "--k-vals",
            type=float,
            nargs="+",
            default=[170.0, 150.0],
            help="Direct k (shrinkage) values to compare — no floor formula applied (default: 170 150)",
        )

    def handle(self, *args, **options):
        season_year = options["season"]
        floors = options["k_vals"]

        nat_avg = NationalAverages.objects.get(season__year=season_year)

        tgc = (
            TeamGameStats.objects.filter(
                game__season_year=season_year,
                game__status="final",
                opponent__is_d1=True,
                team__is_d1=True,
            )
            .values("team_id")
            .annotate(c=Count("id"))
        )
        num_d1 = tgc.count()
        avg_games = sum(r["c"] for r in tgc) / num_d1 if num_d1 else 0

        # Recency weights
        today = date.today()
        game_time_weights = {
            g["id"]: math.exp(-RECENCY_LAMBDA * max(0, (today - g["game_date"]).days))
            for g in Game.objects.filter(season_year=season_year, status="final").values("id", "game_date")
        }

        # Fetch all team-game stats (same approach as compute_adjusted_ratings)
        all_game_stats = list(
            TeamGameStats.objects.filter(
                game__season_year=season_year,
                game__status="final",
                team__is_d1=True,
                opponent__is_d1=True,
            ).select_related("game", "opponent", "team")
        )

        # Build opponent lookup: (game_id, team_id) -> stats object
        all_game_ids = list({gs.game_id for gs in all_game_stats})
        stats_lookup = {
            (gs.game_id, gs.team_id): gs
            for gs in TeamGameStats.objects.filter(game_id__in=all_game_ids).select_related("team")
        }

        # Per-team recency rescale
        sum_poss: defaultdict = defaultdict(float)
        sum_poss_w: defaultdict = defaultdict(float)
        for gs in all_game_stats:
            p = gs.poss_team
            if not p or p <= 0:
                continue
            sum_poss[gs.team_id] += p
            sum_poss_w[gs.team_id] += p * game_time_weights.get(gs.game_id, 1.0)
        team_time_scale = {
            tid: (sum_poss[tid] / sum_poss_w[tid]) if sum_poss_w[tid] > 0 else 1.0
            for tid in sum_poss
        }

        teams = list(Team.objects.filter(is_d1=True))
        team_ids = [t.id for t in teams]
        team_names = {t.id: t.name for t in teams}
        by_team: defaultdict = defaultdict(list)
        for gs in all_game_stats:
            by_team[gs.team_id].append(gs)

        # ------------------------------------------------------------------ #
        def run(k_floor):
            k = float(k_floor)  # use directly — no floor formula
            ratings = {
                tid: {"aor": nat_avg.avg_ortg, "adr": nat_avg.avg_ortg, "pace": nat_avg.avg_pace}
                for tid in team_ids
            }
            frozen_imp: dict = {}
            team_imp_scale: dict = {}

            for iteration in range(1, ITERATIONS + 1):
                current_imp: dict = {}
                new_ratings: dict = {}
                max_change = 0.0

                for tid in team_ids:
                    sw_aor = sw_adr = sw_pace = sw = 0.0

                    for gs in by_team[tid]:
                        poss_g = gs.poss_team
                        if not poss_g or poss_g <= 0:
                            continue
                        opp_id = gs.opponent_id
                        if opp_id not in ratings:
                            continue
                        opp_stats = stats_lookup.get((gs.game_id, opp_id))
                        if not opp_stats:
                            continue

                        minutes = gs.game_minutes or 40
                        raw_oe_g = 100 * gs.pts / poss_g
                        raw_de_g = 100 * opp_stats.pts / poss_g
                        raw_pace_g = 40 * poss_g / minutes

                        opp_aor = ratings[opp_id]["aor"]
                        opp_adr = ratings[opp_id]["adr"]
                        opp_pace = ratings[opp_id]["pace"]

                        aor_g = raw_oe_g * (nat_avg.avg_ortg / opp_adr) * gs.site_factor if opp_adr > 0 else raw_oe_g
                        adr_g = raw_de_g * (nat_avg.avg_ortg / opp_aor) * gs.defensive_site_factor if opp_aor > 0 else raw_de_g
                        blend = (opp_pace + nat_avg.avg_pace) / 2
                        pace_g = raw_pace_g * (nat_avg.avg_pace / blend) if blend > 0 else raw_pace_g

                        w_time = game_time_weights.get(gs.game_id, 1.0) * team_time_scale.get(tid, 1.0)

                        imp_key = (tid, gs.game_id)
                        if iteration <= FREEZE_ITERATION:
                            t_aem = ratings[tid]["aor"] - ratings[tid]["adr"]
                            o_aem = opp_aor - opp_adr
                            gap = abs(t_aem - o_aem)
                            base = max(IMP_FLOOR, 1.0 / (1.0 + (gap / IMP_C) ** 2))
                            closer = max(0.0, abs(t_aem - o_aem) - abs(aor_g - adr_g))
                            cf = 1.0 - math.exp(-closer / CLOSE_M)
                            w_imp = min(1.0, base * (1.0 + (BOOST_MAX - 1.0) * cf))
                            current_imp[imp_key] = w_imp
                        else:
                            w_imp = frozen_imp.get(imp_key, 1.0)

                        wt = poss_g * w_time * w_imp * team_imp_scale.get(tid, 1.0)
                        sw_aor += wt * aor_g
                        sw_adr += wt * adr_g
                        sw_pace += wt * pace_g
                        sw += wt

                    if sw > 0:
                        aor_s = (sw_aor + k * nat_avg.avg_ortg) / (sw + k)
                        adr_s = (sw_adr + k * nat_avg.avg_ortg) / (sw + k)
                        pace_s = (sw_pace + k * nat_avg.avg_pace) / (sw + k)
                    else:
                        aor_s = adr_s = nat_avg.avg_ortg
                        pace_s = nat_avg.avg_pace

                    old_aem = ratings[tid]["aor"] - ratings[tid]["adr"]
                    new_aem = aor_s - adr_s
                    max_change = max(max_change, abs(new_aem - old_aem))
                    new_ratings[tid] = {"aor": aor_s, "adr": adr_s, "pace": pace_s}

                if iteration == FREEZE_ITERATION:
                    frozen_imp = dict(current_imp)
                    sb: defaultdict = defaultdict(float)
                    si: defaultdict = defaultdict(float)
                    for gs in all_game_stats:
                        p = gs.poss_team
                        if not p or p <= 0:
                            continue
                        wt = game_time_weights.get(gs.game_id, 1.0) * team_time_scale.get(gs.team_id, 1.0)
                        wi = frozen_imp.get((gs.team_id, gs.game_id), 1.0)
                        sb[gs.team_id] += p * wt
                        si[gs.team_id] += p * wt * wi
                    team_imp_scale = {
                        t: max(0.85, min(1.30, (sb[t] / si[t]) if si[t] > 0 else 1.0))
                        for t in sb
                    }

                ratings = new_ratings
                if max_change < CONVERGENCE:
                    break

            return {tid: ratings[tid]["aor"] - ratings[tid]["adr"] for tid in team_ids}

        # ------------------------------------------------------------------ #
        # Run all k values
        results = {}
        for f in floors:
            self.stdout.write(f"Running k={f:.0f}...")
            results[f] = run(f)

        # Build rank dicts per floor
        ranks = {}
        for f, res in results.items():
            sorted_res = sorted(res.items(), key=lambda x: -x[1])
            ranks[f] = {tid: i + 1 for i, (tid, _) in enumerate(sorted_res)}

        baseline = floors[0]
        sorted_baseline = sorted(results[baseline].items(), key=lambda x: -x[1])

        # ── Spread summary ────────────────────────────────────────────────── #
        self.stdout.write(f"\navg games/team: {avg_games:.1f}\n")
        hdr = f"  {'k':>6}  {'min':>7}  {'max':>7}  {'range':>7}  {'std':>6}"
        self.stdout.write(hdr)
        self.stdout.write("-" * len(hdr))
        for f in floors:
            vals = list(results[f].values())
            self.stdout.write(
                f"  {f:>6.0f}  "
                f"{min(vals):>+7.2f}  {max(vals):>+7.2f}  "
                f"{max(vals) - min(vals):>7.2f}  {statistics.stdev(vals):>6.2f}"
            )

        # ── Top 10 table ──────────────────────────────────────────────────── #
        COL = 9
        self.stdout.write(f"\nTOP 10  (ranked by k={baseline:.0f})")
        hdr2 = f"  {'Rk':<4} {'Team':<28}"
        for f in floors:
            label = f"k={int(f)}"
            hdr2 += f"  {label:>{COL}}"
        self.stdout.write(hdr2)
        self.stdout.write("-" * (len(hdr2) + 2))
        for tid, _ in sorted_baseline[:10]:
            row = f"  {ranks[baseline][tid]:<4} {team_names[tid]:<28}"
            for f in floors:
                row += f"  {results[f][tid]:>+{COL}.2f}"
            self.stdout.write(row)

        # ── Biggest movers (floor[1] vs floor[0]) ────────────────────────── #
        if len(floors) > 1:
            compare = floors[1]
            self.stdout.write(
                f"\nTOP 10 BIGGEST AdjEM MOVERS  (k={compare:.0f} vs k={baseline:.0f})"
            )
            hdr3 = f"  {'Rk A→B':<10} {'Team':<28}  {'base':>9}  {'compare':>9}  {'Δ':>8}"
            self.stdout.write(hdr3)
            self.stdout.write("-" * len(hdr3))
            movers = sorted(team_ids, key=lambda tid: -abs(results[compare][tid] - results[baseline][tid]))
            for tid in movers[:10]:
                d = results[compare][tid] - results[baseline][tid]
                self.stdout.write(
                    f"  {ranks[baseline][tid]}→{ranks[compare][tid]:<6} {team_names[tid]:<28}"
                    f"  {results[baseline][tid]:>+9.2f}  {results[compare][tid]:>+9.2f}  {d:>+8.3f}"
                )
