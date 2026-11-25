"""
Luck: wins above (or below) what a team's game-by-game forecasts expected.

    luck = (wins - sum of win probabilities) / games

Win probabilities come from unshrunk ratings and a per-season sigma:

- Ratings: the production solver (compute_adjusted_ratings) with shrinkage 0 and no BPR prior, solved in
  memory (--no-write). The stored ratings are shrunk toward the mean, which made every forecast
  underconfident (favorites won 2-4 points more often than forecast) and so made strong teams look lucky:
  r(luck, AdjEM) was +0.27 every season. Unshrunk, it was +0.12.
- Sigma: fitted by maximum likelihood to the same games' results, per season and mode (full season or
  pre-tournament). With it r(luck, AdjEM) averaged +0.04 over 2005-2026 and the forecasts were
  calibrated to within 0.006 in every decile (replay study, 2026-11-24).

The margin is forecast_game's, unrounded: expected efficiencies at the harmonic-mean pace, plus half the
season's HCA to the home side (none on a neutral floor).
"""

import io

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.stats import norm

from api.matchup_engine import apply_hca_adjustment, compute_expected_efficiency, compute_pace

SIGMA_BOUNDS = (3.0, 40.0)


def unshrunk_ratings(season_year: int, is_pre_tournament: bool) -> dict:
    """{team_id: {"aor", "adr", "pace"}} from the production solver with shrinkage 0, no BPR prior,
    nothing written."""
    from django.core.management import call_command
    from ncaa.management.commands.compute_adjusted_ratings import Command as Solver

    solver = Solver()
    kwargs = {"season": season_year, "shrinkage": 0.0, "no_bpr_prior": True, "no_write": True,
              "stdout": io.StringIO(), "stderr": io.StringIO()}
    if is_pre_tournament:
        kwargs["pre_tournament"] = True
    call_command(solver, **kwargs)
    return getattr(solver, "solved", {}) or {}


def forecast_margin(team: dict, opp: dict, nat_avg_ortg: float, hca_points: float, site: str) -> float:
    """Expected margin for `team` (forecast_game's margin, unrounded); site from the team's side."""
    pace = compute_pace(team["pace"], opp["pace"])
    pts_a = compute_expected_efficiency(team["aor"], opp["adr"], nat_avg_ortg) * pace / 100
    pts_b = compute_expected_efficiency(opp["aor"], team["adr"], nat_avg_ortg) * pace / 100
    pts_a, pts_b = apply_hca_adjustment(pts_a, pts_b, site, hca_points)
    return pts_a - pts_b


def fit_sigma(margins, wins) -> float:
    """Maximum-likelihood sigma for P(win) = Phi(margin / sigma)."""
    m = np.asarray(margins, dtype=float)
    sign = np.where(np.asarray(wins, dtype=int) == 1, 1.0, -1.0)

    def nll(s):
        return -float(np.sum(norm.logcdf(sign * m / s)))

    return float(minimize_scalar(nll, bounds=SIGMA_BOUNDS, method="bounded").x)


def season_luck(games, ratings: dict, nat_avg_ortg: float, hca_points: float):
    """games: (team_id, opponent_id, site, won) per team-game. Returns ({team_id: luck}, sigma, n games used).

    A game counts when both teams have a rating. Each game appears once per side, so wins minus expected
    wins sums to zero across the season.
    """
    rows = []
    for team_id, opp_id, site, won in games:
        t, o = ratings.get(team_id), ratings.get(opp_id)
        if t is None or o is None or won is None:
            continue
        rows.append((team_id, forecast_margin(t, o, nat_avg_ortg, hca_points, site), int(won)))
    if not rows:
        return {}, None, 0
    sigma = fit_sigma([m for _, m, _ in rows], [w for _, _, w in rows])
    totals: dict = {}
    for team_id, m, w in rows:
        acc = totals.setdefault(team_id, [0.0, 0])
        acc[0] += w - norm.cdf(m / sigma)
        acc[1] += 1
    return {t: s / n for t, (s, n) in totals.items()}, sigma, len(rows)
