"""
Elo-based match outcome model for the World Cup.

Provides:
- win_expectancy: standard Elo expected-score formula (shared with build_elo)
- match_outcome_probs: splits expected score into win/draw/loss probabilities
- simulate_group: exact enumeration of a 4-team round-robin group to compute
  each team's probability of winning the group / advancing to the knockouts
"""

import itertools
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import WorldCupTeam


# Draw probability for an even matchup (~int'l avg draw rate). Decays toward
# 0 as the Elo gap widens, via a Gaussian centered at dr=0.
DRAW_MAX = 0.28
DRAW_SCALE = 400.0


def win_expectancy(rating_a: float, rating_b: float, home_adv: float = 0.0) -> float:
    dr = rating_a - rating_b + home_adv
    return 1.0 / (1.0 + 10.0 ** (-dr / 400.0))


def match_outcome_probs(elo_a: float, elo_b: float) -> tuple[float, float, float]:
    """
    Returns (p_a_win, p_draw, p_b_win), summing to 1.0.

    Neutral venue (no home_adv) — elo_rating already bakes in the World Cup
    host bonus for USA/Canada/Mexico.

    Elo's expected score already equals p_a_win + 0.5*p_draw, so the draw
    probability is layered on top of that identity rather than estimated
    independently.
    """
    dr = elo_a - elo_b
    we_a = win_expectancy(elo_a, elo_b)

    p_draw = DRAW_MAX * math.exp(-((dr / DRAW_SCALE) ** 2))
    p_draw = min(p_draw, 2 * min(we_a, 1 - we_a))  # keep both win probs >= 0

    p_a_win = we_a - 0.5 * p_draw
    p_b_win = (1 - we_a) - 0.5 * p_draw
    return p_a_win, p_draw, p_b_win


def simulate_group(teams: list["WorldCupTeam"]) -> dict:
    """
    teams: exactly 4 WorldCupTeam (one group's worth).

    Round-robin = 6 fixtures, each with 3 possible outcomes (A win / draw /
    B win) = 3^6 = 729 combinations, enumerated exactly (no RNG).

    For each combination: award points (W=3/D=1/L=0), rank by points, break
    ties within a tied group via head-to-head points among just the tied
    teams (derivable from the combination itself), then by raw elo_rating
    (no goal-difference model).

    Returns {"standings": [{"team", "win_group_pct", "advance_pct"}, ...],
             "fixtures": [{"team_a", "team_b", "p_a_win", "p_draw", "p_b_win"}, ...]}
    """
    n = len(teams)
    pairs = list(itertools.combinations(range(n), 2))  # 6 (i, j) index pairs, i < j

    pair_probs = {
        (i, j): match_outcome_probs(teams[i].elo_rating, teams[j].elo_rating)
        for i, j in pairs
    }

    win_group_mass = [0.0] * n
    advance_mass = [0.0] * n

    # outcome encoding per fixture: 0 = i wins, 1 = draw, 2 = j wins
    for combo in itertools.product((0, 1, 2), repeat=len(pairs)):
        combo_prob = 1.0
        points = [0] * n
        results = {}  # (i, j) -> outcome, for head-to-head lookups

        for (i, j), outcome in zip(pairs, combo):
            combo_prob *= pair_probs[(i, j)][outcome]
            results[(i, j)] = outcome
            if outcome == 0:
                points[i] += 3
            elif outcome == 1:
                points[i] += 1
                points[j] += 1
            else:
                points[j] += 3

        if combo_prob == 0.0:
            continue

        # Group team indices into tiers by points (descending)
        order = sorted(range(n), key=lambda t: points[t], reverse=True)
        tiers: list[list[int]] = []
        for idx in order:
            if tiers and points[tiers[-1][0]] == points[idx]:
                tiers[-1].append(idx)
            else:
                tiers.append([idx])

        # Resolve ties within each tier via head-to-head points, then Elo
        standings_order: list[int] = []
        for tier in tiers:
            if len(tier) == 1:
                standings_order.extend(tier)
                continue

            h2h_points = {t: 0 for t in tier}
            for a, b in itertools.combinations(tier, 2):
                i, j = (a, b) if a < b else (b, a)
                outcome = results[(i, j)]
                if outcome == 0:
                    h2h_points[i] += 3
                elif outcome == 1:
                    h2h_points[i] += 1
                    h2h_points[j] += 1
                else:
                    h2h_points[j] += 3

            tier_sorted = sorted(
                tier,
                key=lambda t: (h2h_points[t], teams[t].elo_rating),
                reverse=True,
            )
            standings_order.extend(tier_sorted)

        win_group_mass[standings_order[0]] += combo_prob
        advance_mass[standings_order[0]] += combo_prob
        advance_mass[standings_order[1]] += combo_prob

    # Across all 729 combos, combo_prob sums to ~1.0 (each fixture's 3
    # outcome probs sum to 1). Each combo contributes to exactly one team's
    # win_group_mass and exactly two teams' advance_mass, so both arrays are
    # already on a 0-1 probability scale — divide by the same total purely
    # for floating-point cleanup (not a true renormalization).
    total_prob = sum(win_group_mass) or 1.0

    standings = [
        {
            "team": teams[t],
            "win_group_pct": win_group_mass[t] / total_prob,
            "advance_pct": advance_mass[t] / total_prob,
        }
        for t in range(n)
    ]

    fixtures = [
        {
            "team_a": teams[i].name,
            "team_b": teams[j].name,
            "p_a_win": pair_probs[(i, j)][0],
            "p_draw": pair_probs[(i, j)][1],
            "p_b_win": pair_probs[(i, j)][2],
        }
        for i, j in pairs
    ]

    return {"standings": standings, "fixtures": fixtures}
