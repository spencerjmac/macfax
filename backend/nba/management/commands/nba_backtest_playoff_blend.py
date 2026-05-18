"""
nba_backtest_playoff_blend — Validate whether blending playoff ratings improves predictions.

For each completed playoff game in the target season, runs two predictions:
  1. Regular-only: uses season-end regular-season ratings
  2. Blended: weights playoff ratings by cumulative games played before each game date

Compares both against actual outcomes via Brier score and log-loss.

LEAKAGE NOTE: adj_off/adj_def values come from season-end playoff ratings (include all
playoff games). Blend weights use cumulative game counts at prediction time (partial
mitigation). Results are directionally valid but optimistically biased for the blended
strategy in later rounds.

Usage
─────
    uv run python manage.py nba_backtest_playoff_blend --season 2025
    uv run python manage.py nba_backtest_playoff_blend --season 2025 --round-breakdown
"""

import logging
import math
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError

from nba.matchup_engine import NBA_PACE_DEFAULT, get_nba_model_params
from nba.models import NBAGame, NBASeason, NBATeamGameStats, NBATeamSeasonRatings
from api.matchup_engine import forecast_game

logger = logging.getLogger(__name__)

BLEND_FIELDS = [
    "adj_off", "adj_def", "adj_net", "pace",
    "efg_pct", "opp_efg_pct",
    "tov_rate", "opp_tov_rate",
    "oreb_pct", "opp_oreb_pct",
    "fta_rate", "opp_fta_rate",
]


def _blend_weight(n: int) -> float:
    return min(n / (n + 8.0), 0.7) if n >= 4 else 0.0


def _apply_blend(reg, po, w: float) -> dict:
    result = {}
    for f in BLEND_FIELDS:
        r_val = getattr(reg, f)
        p_val = getattr(po, f)
        if r_val is not None and p_val is not None:
            result[f] = (1.0 - w) * r_val + w * p_val
        else:
            result[f] = r_val
    return result


class Command(BaseCommand):
    help = "Backtest regular-only vs blended playoff ratings on playoff game outcomes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season", type=int, required=True,
            help="Ending season year (e.g. 2025 for 2024-25)",
        )
        parser.add_argument(
            "--round-breakdown", action="store_true",
            help="Show per-round Brier/log-loss breakdown (grouped by week)",
        )

    def handle(self, *args, **options):
        season_year: int = options["season"]
        round_breakdown: bool = options["round_breakdown"]

        try:
            season = NBASeason.objects.get(year=season_year)
        except NBASeason.DoesNotExist:
            raise CommandError(
                f"NBASeason year={season_year} not found. "
                "Run nba_sync_games first."
            )

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n╔══════════════════════════════════════════════╗\n"
                f"║  Playoff Blend Backtest — {season.display_name:<16} ║\n"
                f"╚══════════════════════════════════════════════╝"
            )
        )

        # ── Load data ─────────────────────────────────────────────────────────

        games = list(
            NBAGame.objects.select_related("home_team", "away_team")
            .filter(
                season=season,
                season_type="playoffs",
                status="Final",
                home_score__isnull=False,
                away_score__isnull=False,
            )
            .order_by("date")
        )

        if not games:
            raise CommandError(
                f"No completed playoff games found for {season.display_name}. "
                "Run nba_sync_games --season-type playoffs first."
            )

        reg_ratings = {
            r.team_id: r
            for r in NBATeamSeasonRatings.objects.filter(
                season=season, season_type="regular"
            )
        }
        po_ratings = {
            r.team_id: r
            for r in NBATeamSeasonRatings.objects.filter(
                season=season, season_type="playoffs"
            )
        }

        self.stdout.write(
            f"\nCompleted playoff games:        {len(games)}"
            f"\nTeams with regular ratings:     {len(reg_ratings)}"
            f"\nTeams with playoff ratings:     {len(po_ratings)}"
        )

        if not reg_ratings:
            raise CommandError(
                "No regular-season NBATeamSeasonRatings — run nba_compute_ratings first."
            )

        # ── Build cumulative game-date lists per team ─────────────────────────
        # Used to compute games_before(team_id, game_date) without data leakage
        # on blend weights (ratings values are still season-end — see leakage note).

        po_game_stats = list(
            NBATeamGameStats.objects.filter(
                game__season=season,
                game__season_type="playoffs",
            )
            .select_related("game")
            .order_by("game__date")
        )

        team_po_dates: dict[int, list] = defaultdict(list)
        for s in po_game_stats:
            team_po_dates[s.team_id].append(s.game.date)

        def games_before(team_id: int, game_date) -> int:
            return sum(1 for d in team_po_dates[team_id] if d < game_date)

        # ── Model params (from regular-season calibration) ────────────────────

        params = get_nba_model_params(season)
        nat_avg_ortg = params["nat_avg_ortg"]
        hca_points = params["hca_points"]
        sigma = params["sigma"]
        ols_model_scale = params["ols_model_scale"]

        self.stdout.write(
            f"\nModel params: HCA={hca_points:.2f}  σ={sigma:.2f}  "
            f"nat_avg_ortg={nat_avg_ortg:.1f}"
            + (f"  β₁={ols_model_scale:.3f}" if ols_model_scale else "  β₁=none")
        )

        # ── Per-game evaluation ───────────────────────────────────────────────

        brier_reg = brier_blend = 0.0
        ll_reg = ll_blend = 0.0
        total = 0
        skipped = 0
        missing_po: set[str] = set()

        # For round breakdown: group by week-of-playoffs
        # week 1 = games 1-7 days after first playoff game date
        first_date = games[0].date if games else None
        week_buckets: dict[int, dict] = defaultdict(
            lambda: {"brier_reg": 0.0, "brier_blend": 0.0,
                     "ll_reg": 0.0, "ll_blend": 0.0, "n": 0}
        )

        for game in games:
            hr = reg_ratings.get(game.home_team_id)
            ar = reg_ratings.get(game.away_team_id)
            if hr is None or ar is None:
                skipped += 1
                continue
            if hr.adj_net is None or ar.adj_net is None:
                skipped += 1
                continue

            actual = 1 if game.home_score > game.away_score else 0

            # ── Regular-only forecast ──────────────────────────────────────
            fc_reg = forecast_game(
                adj_o_a=hr.adj_off or nat_avg_ortg,
                adj_d_a=hr.adj_def or nat_avg_ortg,
                adj_em_a=hr.adj_net or 0.0,
                tempo_a=hr.pace or NBA_PACE_DEFAULT,
                adj_o_b=ar.adj_off or nat_avg_ortg,
                adj_d_b=ar.adj_def or nat_avg_ortg,
                adj_em_b=ar.adj_net or 0.0,
                tempo_b=ar.pace or NBA_PACE_DEFAULT,
                nat_avg_ortg=nat_avg_ortg,
                hca_points=hca_points,
                sigma=sigma,
                site="home",
                ols_scale=ols_model_scale,
            )
            p_reg = fc_reg["prob_a"]

            # ── Blended forecast ──────────────────────────────────────────
            h_po = po_ratings.get(game.home_team_id)
            a_po = po_ratings.get(game.away_team_id)
            h_count = games_before(game.home_team_id, game.date)
            a_count = games_before(game.away_team_id, game.date)

            if h_po and h_count >= 4:
                h_fields = _apply_blend(hr, h_po, _blend_weight(h_count))
            else:
                h_fields = {f: getattr(hr, f) for f in BLEND_FIELDS}
                if not h_po:
                    missing_po.add(game.home_team.name)

            if a_po and a_count >= 4:
                a_fields = _apply_blend(ar, a_po, _blend_weight(a_count))
            else:
                a_fields = {f: getattr(ar, f) for f in BLEND_FIELDS}
                if not a_po:
                    missing_po.add(game.away_team.name)

            fc_blend = forecast_game(
                adj_o_a=h_fields["adj_off"] or nat_avg_ortg,
                adj_d_a=h_fields["adj_def"] or nat_avg_ortg,
                adj_em_a=h_fields["adj_net"] or 0.0,
                tempo_a=h_fields["pace"] or NBA_PACE_DEFAULT,
                adj_o_b=a_fields["adj_off"] or nat_avg_ortg,
                adj_d_b=a_fields["adj_def"] or nat_avg_ortg,
                adj_em_b=a_fields["adj_net"] or 0.0,
                tempo_b=a_fields["pace"] or NBA_PACE_DEFAULT,
                nat_avg_ortg=nat_avg_ortg,
                hca_points=hca_points,
                sigma=sigma,
                site="home",
                ols_scale=ols_model_scale,
            )
            p_blend = fc_blend["prob_a"]

            # ── Accumulate metrics ─────────────────────────────────────────
            b_reg = (p_reg - actual) ** 2
            b_bld = (p_blend - actual) ** 2
            l_reg = -(actual * math.log(max(p_reg, 1e-15))
                      + (1 - actual) * math.log(max(1 - p_reg, 1e-15)))
            l_bld = -(actual * math.log(max(p_blend, 1e-15))
                      + (1 - actual) * math.log(max(1 - p_blend, 1e-15)))

            brier_reg += b_reg
            brier_blend += b_bld
            ll_reg += l_reg
            ll_blend += l_bld
            total += 1

            if round_breakdown and first_date is not None:
                days_in = (game.date - first_date).days
                week = days_in // 7 + 1
                wb = week_buckets[week]
                wb["brier_reg"] += b_reg
                wb["brier_blend"] += b_bld
                wb["ll_reg"] += l_reg
                wb["ll_blend"] += l_bld
                wb["n"] += 1

        # ── Output ────────────────────────────────────────────────────────────

        self.stdout.write(
            self.style.WARNING(
                "\nNOTE: adj_off/adj_def values come from season-end playoff ratings"
                " (acknowledged leakage).\n"
                "      Blend WEIGHTS use cumulative game counts at prediction time"
                " (partial mitigation)."
            )
        )

        if total == 0:
            self.stdout.write(self.style.ERROR("\nNo games evaluated — check data."))
            return

        mean_brier_reg = brier_reg / total
        mean_brier_bld = brier_blend / total
        mean_ll_reg = ll_reg / total
        mean_ll_bld = ll_blend / total
        delta_brier = mean_brier_bld - mean_brier_reg
        delta_ll = mean_ll_bld - mean_ll_reg

        def _dir(delta):
            if abs(delta) < 0.0001:
                return "≈ no change"
            return ("▼ better" if delta < 0 else "▲ worse") + f" by {abs(delta):.4f}"

        self.stdout.write(
            f"\n{'Strategy':<18} {'Brier':>8} {'Log-loss':>10}\n"
            f"{'─'*38}\n"
            f"{'Regular-only':<18} {mean_brier_reg:>8.4f} {mean_ll_reg:>10.4f}\n"
            f"{'Blended':<18} {mean_brier_bld:>8.4f} {mean_ll_bld:>10.4f}\n"
            f"{'─'*38}\n"
            f"{'Delta (blend-reg)':<18} {delta_brier:>+8.4f} {delta_ll:>+10.4f}"
            f"  [lower = better]\n"
            f"\n  Brier:    {_dir(delta_brier)}"
            f"\n  Log-loss: {_dir(delta_ll)}"
            f"\n\nGames evaluated: {total}"
            + (f"  |  Skipped (missing reg ratings): {skipped}" if skipped else "")
        )

        if round_breakdown and week_buckets:
            self.stdout.write(self.style.MIGRATE_HEADING("\n── Round Breakdown (by week of playoffs)"))
            self.stdout.write(
                f"\n{'Week':<6} {'N':>4}  {'Brier-reg':>10} {'Brier-bld':>10}"
                f"  {'LL-reg':>8} {'LL-bld':>8}"
            )
            for week in sorted(week_buckets):
                wb = week_buckets[week]
                n = wb["n"]
                if n == 0:
                    continue
                self.stdout.write(
                    f"{week:<6} {n:>4}  {wb['brier_reg']/n:>10.4f} {wb['brier_blend']/n:>10.4f}"
                    f"  {wb['ll_reg']/n:>8.4f} {wb['ll_blend']/n:>8.4f}"
                )

        if missing_po:
            self.stdout.write(
                f"\nTeams missing playoff ratings (fell back to regular-only): "
                + ", ".join(sorted(missing_po))
            )

        verdict = None
        if delta_brier < -0.002 and delta_ll < -0.002:
            verdict = self.style.SUCCESS("VERDICT: Blend improves accuracy on both metrics — consider enabling.")
        elif delta_brier > 0.002 or delta_ll > 0.002:
            verdict = self.style.ERROR("VERDICT: Blend hurts accuracy — keep regular-only.")
        else:
            verdict = self.style.WARNING("VERDICT: Inconclusive — delta too small to act on.")

        self.stdout.write(f"\n{verdict}\n")
