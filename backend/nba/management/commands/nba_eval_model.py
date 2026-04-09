"""
nba_eval_model — Phase 3 model validation & calibration.

Runs four analyses on completed regular-season games and writes results to
NBAModelCalibration; the record is upserted per season so it is safe to re-run
at any point in the season as more games complete.

Analyses performed
──────────────────
1. Straight-up prediction accuracy
   For each completed game where both teams have season-end adj_net ratings,
   predict the winner as the team with (home_adj_net - away_adj_net + HCA > 0).
   Reports: correct %, Brier score, log-loss.
   NOTE: season-end ratings are used retroactively — this is a consistency
   check, NOT true held-out prediction. Accuracy will be optimistically biased.

2. Empirical HCA + B2B calibration (OLS regression)
   Fits: home_margin ~ β₀·1 + β₁·adj_net_diff + β₂·home_b2b + β₃·away_b2b
   β₀ ≈ empirical home-court advantage (in raw points).
   β₂ / β₃ ≈ raw-point penalty for B2B travel.
   Compare these to NBA_RATINGS_CONFIG values.

3. FFI weight derivation (cross-sectional OLS)
   Fits: adj_net ~ w₀ + w₁·efg_margin + w₂·tov_edge + w₃·oreb_edge + w₄·fta_margin
   across all 30 teams for the season.  Normalises the positive coefficients to
   produce proposed FFI weights.  Reports R² and the proposed vs current weights.

Usage
─────
    uv run python manage.py nba_eval_model --season 2026
    uv run python manage.py nba_eval_model --season 2026 --no-write   # print only
"""

import logging
import math

import numpy as np
from django.core.management.base import BaseCommand, CommandError

from nba.models import NBAGame, NBAModelCalibration, NBASeason, NBATeamSeasonRatings
from nba.ratings_config import NBA_FFI_WEIGHTS, NBA_RATINGS_CONFIG

logger = logging.getLogger(__name__)

# Logistic scale factor for converting adj_net spread to win probability.
# ~10 pts/100 poss corresponds to a very strong mismatch, so P(home) ≈ 0.88.
# Calibrating this properly would require a separate logistic regression —
# for now we use the same value as many public basketball models.
LOGISTIC_SCALE = 10.0


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def _r_squared(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0


class Command(BaseCommand):
    help = "Phase 3 — evaluate model accuracy and calibrate HCA, B2B, and FFI weights."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season", type=int, required=True,
            help="Ending season year (e.g. 2026 for 2025-26)",
        )
        parser.add_argument(
            "--no-write", action="store_true",
            help="Print results without persisting to NBAModelCalibration",
        )

    def handle(self, *args, **options):  # noqa: C901
        season_year: int = options["season"]
        no_write: bool = options["no_write"]

        try:
            season = NBASeason.objects.get(year=season_year)
        except NBASeason.DoesNotExist:
            raise CommandError(
                f"NBASeason year={season_year} not found. "
                "Run nba_sync_games first."
            )

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n╔═══════════════════════════════════════╗\n"
                f"║  NBA Model Evaluation — {season.display_name:<12} ║\n"
                f"╚═══════════════════════════════════════╝"
            )
        )

        # ── Load data ────────────────────────────────────────────────────────

        completed_games = list(
            NBAGame.objects.select_related("home_team", "away_team")
            .filter(
                season=season,
                counts_toward_regular_season=True,
                status="Final",
                home_score__isnull=False,
                away_score__isnull=False,
            )
        )

        ratings = {
            r.team_id: r
            for r in NBATeamSeasonRatings.objects.filter(season=season)
        }

        self.stdout.write(
            f"\nCompleted regular-season games: {len(completed_games)}"
            f"\nTeams with season ratings:      {len(ratings)}"
        )

        if not completed_games:
            raise CommandError("No completed games found. Play some basketball first.")

        if not ratings:
            raise CommandError(
                "No NBATeamSeasonRatings — run nba_compute_ratings first."
            )

        # ── Analysis 1: Straight-up prediction accuracy ───────────────────

        self.stdout.write(self.style.MIGRATE_HEADING("\n── 1. Prediction Accuracy (season-end ratings)"))

        configured_hca = NBA_RATINGS_CONFIG["home_court_adj"]
        correct = 0
        total = 0
        brier_sum = 0.0
        log_loss_sum = 0.0

        for game in completed_games:
            hr = ratings.get(game.home_team_id)
            ar = ratings.get(game.away_team_id)
            if hr is None or ar is None:
                continue
            if hr.adj_net is None or ar.adj_net is None:
                continue

            spread = (hr.adj_net - ar.adj_net) + configured_hca
            p_home = _sigmoid(spread / LOGISTIC_SCALE)
            actual = 1 if game.home_score > game.away_score else 0
            predicted = 1 if spread > 0 else 0

            correct += predicted == actual
            brier_sum += (p_home - actual) ** 2
            log_loss_sum += -(
                actual * math.log(max(p_home, 1e-15))
                + (1 - actual) * math.log(max(1 - p_home, 1e-15))
            )
            total += 1

        if total == 0:
            straight_up_accuracy = brier_score = log_loss_val = None
            self.stdout.write(self.style.WARNING("  No games with complete ratings — skipping."))
        else:
            straight_up_accuracy = correct / total * 100
            brier_score = brier_sum / total
            log_loss_val = log_loss_sum / total
            self.stdout.write(
                f"  Games evaluated:    {total}\n"
                f"  Correct picks:      {correct} / {total}\n"
                f"  Straight-up acc:    {straight_up_accuracy:.1f}%\n"
                f"  Brier score:        {brier_score:.4f}  (random=0.25, perfect=0.0)\n"
                f"  Log-loss:           {log_loss_val:.4f}  (random=0.693, perfect=0.0)"
            )

        # ── Analysis 2+3: HCA & B2B via OLS ──────────────────────────────────

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n── 2 & 3. Empirical HCA + B2B Calibration (OLS)"
        ))
        self.stdout.write(
            "  Model: home_margin ~ β₀ + β₁·(home_adj_net − away_adj_net) + β₂·home_b2b + β₃·away_b2b"
        )

        X_rows, y_vals = [], []
        for game in completed_games:
            hr = ratings.get(game.home_team_id)
            ar = ratings.get(game.away_team_id)
            if hr is None or ar is None:
                continue
            if hr.adj_net is None or ar.adj_net is None:
                continue
            adj_diff = hr.adj_net - ar.adj_net
            X_rows.append([1.0, adj_diff, float(game.home_b2b), float(game.away_b2b)])
            y_vals.append(float(game.home_score - game.away_score))

        ols_games = ols_r_sq = empirical_hca = ols_scale = emp_home_b2b = emp_away_b2b = None

        if len(X_rows) >= 10:
            X_np = np.array(X_rows)
            y_np = np.array(y_vals)
            coeffs, _, _, _ = np.linalg.lstsq(X_np, y_np, rcond=None)
            y_pred = X_np @ coeffs
            ols_games = len(y_np)
            ols_r_sq = _r_squared(y_np, y_pred)
            empirical_hca = float(coeffs[0])
            ols_scale = float(coeffs[1])
            emp_home_b2b = float(coeffs[2])
            emp_away_b2b = float(coeffs[3])
            configured_b2b = NBA_RATINGS_CONFIG["b2b_penalty"]

            self.stdout.write(
                f"  OLS games:          {ols_games}\n"
                f"  R²:                 {ols_r_sq:.3f}\n"
                f"\n  β₀ (HCA):\n"
                f"    Empirical:        {empirical_hca:+.2f} raw pts\n"
                f"    Configured:       {configured_hca:+.2f} pts/100 poss\n"
                f"\n  β₁ (model scale):  {ols_scale:.3f}  (goal ≈ 1.0)\n"
                f"\n  B2B penalties:\n"
                f"    Home B2B (β₂):    {emp_home_b2b:+.2f} raw pts  "
                f"(configured −{configured_b2b:.1f})\n"
                f"    Away B2B (β₃):    {emp_away_b2b:+.2f} raw pts  "
                f"(configured +{configured_b2b:.1f} to home team)"
            )

            if ols_r_sq < 0.15:
                self.stdout.write(self.style.WARNING(
                    "  ⚠  Low R² — model may have low explanatory power this early in the season."
                ))
        else:
            configured_b2b = NBA_RATINGS_CONFIG["b2b_penalty"]
            self.stdout.write(self.style.WARNING(
                f"  Need ≥10 rated completed games for OLS (have {len(X_rows)})."
            ))

        # ── Analysis 4: FFI weight regression ────────────────────────────────

        self.stdout.write(self.style.MIGRATE_HEADING("\n── 4. FFI Weight Derivation (cross-sectional OLS)"))
        self.stdout.write(
            "  Model: adj_net ~ w₀ + w₁·eFG_margin + w₂·TOV_edge + w₃·OREB_edge + w₄·FTA_margin"
        )

        ffi_X, ffi_y = [], []
        for r in ratings.values():
            vals = [r.efg_margin, r.tov_edge, r.oreb_edge, r.fta_margin, r.adj_net]
            if any(v is None for v in vals):
                continue
            ffi_X.append([r.efg_margin, r.tov_edge, r.oreb_edge, r.fta_margin])
            ffi_y.append(r.adj_net)

        ffi_r_sq = prop_efg = prop_tov = prop_oreb = prop_fta = None
        ffi_teams = 0

        current_w = NBA_FFI_WEIGHTS

        if len(ffi_y) >= 5:
            X_np = np.column_stack([np.ones(len(ffi_X)), np.array(ffi_X)])
            y_np = np.array(ffi_y)
            coeffs, _, _, _ = np.linalg.lstsq(X_np, y_np, rcond=None)
            y_pred = X_np @ coeffs
            ffi_r_sq = _r_squared(y_np, y_pred)
            ffi_teams = len(ffi_y)

            # Normalize positive coefficients to [0,1] summing to 1.
            raw = [float(coeffs[1]), float(coeffs[2]), float(coeffs[3]), float(coeffs[4])]
            pos = [max(w, 0.0) for w in raw]
            total_pos = sum(pos) or 1.0
            prop_efg, prop_tov, prop_oreb, prop_fta = [w / total_pos for w in pos]

            rows = [
                ("eFG margin", prop_efg, current_w["efg_margin"], raw[0]),
                ("TOV edge",   prop_tov, current_w["tov_edge"],   raw[1]),
                ("OREB edge",  prop_oreb, current_w["oreb_edge"],  raw[2]),
                ("FTA margin", prop_fta, current_w["fta_margin"],  raw[3]),
            ]
            self.stdout.write(
                f"  Teams used:         {ffi_teams}\n"
                f"  R²:                 {ffi_r_sq:.3f}\n"
                f"\n  {'Factor':<14}  {'Proposed':>9}  {'Current':>9}  {'Raw coeff':>10}"
            )
            for name, proposed, current_v, raw_coeff in rows:
                diff_marker = ""
                if abs(proposed - current_v) > 0.08:
                    diff_marker = " ◄ notable diff"
                self.stdout.write(
                    f"    {name:<12}  {proposed:>9.3f}  {current_v:>9.3f}  {raw_coeff:>10.3f}{diff_marker}"
                )

            if ffi_teams < 20:
                self.stdout.write(self.style.WARNING(
                    f"  ⚠  Only {ffi_teams} teams — regression unreliable. Run again at season end."
                ))
            elif ffi_r_sq < 0.50:
                self.stdout.write(self.style.WARNING(
                    "  ⚠  R² < 0.50 — four factors alone are not tightly capturing adj_net this season."
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"  ✓  R² = {ffi_r_sq:.3f} — four factors explain adj_net well. "
                    "Consider updating NBA_FFI_WEIGHTS when season is complete."
                ))
        else:
            self.stdout.write(self.style.WARNING(
                f"  Need ≥5 teams with complete four-factor data (have {len(ffi_y)})."
            ))

        # ── Persist to NBAModelCalibration ────────────────────────────────────

        if no_write:
            self.stdout.write(self.style.WARNING(
                "\n  --no-write set — results not persisted."
            ))
            return

        configured_b2b_val = NBA_RATINGS_CONFIG["b2b_penalty"]
        calibration, created = NBAModelCalibration.objects.update_or_create(
            season=season,
            defaults={
                # Analysis 1
                "games_predicted": total if total else None,
                "correct_predictions": correct if total else None,
                "straight_up_accuracy": straight_up_accuracy,
                "brier_score": brier_score,
                "log_loss": log_loss_val,
                # Analysis 2+3
                "ols_games": ols_games,
                "ols_r_squared": ols_r_sq,
                "empirical_hca": empirical_hca,
                "configured_hca": configured_hca,
                "ols_model_scale": ols_scale,
                "empirical_home_b2b_penalty": emp_home_b2b,
                "empirical_away_b2b_penalty": emp_away_b2b,
                "configured_b2b_penalty": configured_b2b_val,
                # Analysis 4
                "ffi_teams_used": ffi_teams if ffi_teams else None,
                "ffi_adj_net_r_squared": ffi_r_sq,
                "ffi_proposed_weight_efg": prop_efg,
                "ffi_proposed_weight_tov": prop_tov,
                "ffi_proposed_weight_oreb": prop_oreb,
                "ffi_proposed_weight_fta": prop_fta,
                "ffi_current_weight_efg": current_w["efg_margin"],
                "ffi_current_weight_tov": current_w["tov_edge"],
                "ffi_current_weight_oreb": current_w["oreb_edge"],
                "ffi_current_weight_fta": current_w["fta_margin"],
            },
        )

        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(
            f"\n✓  {verb} NBAModelCalibration for {season.display_name} (pk={calibration.pk})"
        ))
