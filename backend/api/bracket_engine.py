"""
Bracket Engine — NCAA Tournament simulation using Adjusted Efficiency Ratings.

Exports:
  BracketTeam            — lightweight team data for simulation
  R64_PODS               — standard R64 seed matchups: [(1,16), (8,9), ...]
  R32_PAIRINGS           — R64 pod-index pairs for R32 games
  S16_PAIRINGS           — R32 game-index pairs for S16 games
  FF_PAIRINGS            — regional pairing for Final Four
  build_bracket_from_ratings(all_ratings) → bracket | None
  simulate_tournament(bracket, nat_avg_ortg, sigma, n_sims) → {slug: probabilities}
  compute_p_sweet16(team, region_bracket, nat_avg_ortg, sigma) → float | None
"""
import random
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from scipy import stats as scipy_stats

from .matchup_engine import compute_pace, compute_expected_efficiency

# ---------------------------------------------------------------------------
# Bracket structure constants
# ---------------------------------------------------------------------------

BRACKET_REGIONS = ('East', 'West', 'South', 'Midwest')

# R64 seed matchup pairs, in display order (top to bottom of bracket half)
R64_PODS: List[Tuple[int, int]] = [
    (1, 16), (8, 9),
    (5, 12), (4, 13),
    (6, 11), (3, 14),
    (7, 10), (2, 15),
]

# R32: indices into R64_PODS whose winners play each other
R32_PAIRINGS: List[Tuple[int, int]] = [(0, 1), (2, 3), (4, 5), (6, 7)]

# S16: indices into the list of R32 winners
S16_PAIRINGS: List[Tuple[int, int]] = [(0, 1), (2, 3)]

# Final Four regional pairings
FF_PAIRINGS: List[Tuple[str, str]] = [('East', 'South'), ('West', 'Midwest')]


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class BracketTeam:
    team_id: int
    name: str
    slug: str
    logo_url: Optional[str]
    seed: int
    region: str
    adj_o: float
    adj_d: float
    adj_em: float
    adj_tempo: float
    wins: int
    losses: int
    is_first_four: bool = False


# ---------------------------------------------------------------------------
# Win-probability helpers (no scipy confidence bands — fast path)
# ---------------------------------------------------------------------------

def _raw_win_prob(a: BracketTeam, b: BracketTeam, nat_avg_ortg: float, sigma: float) -> float:
    """P(a wins) on a neutral court."""
    pace = compute_pace(a.adj_tempo, b.adj_tempo)
    pts_a = compute_expected_efficiency(a.adj_o, b.adj_d, nat_avg_ortg) * (pace / 100)
    pts_b = compute_expected_efficiency(b.adj_o, a.adj_d, nat_avg_ortg) * (pace / 100)
    margin = pts_a - pts_b
    return float(scipy_stats.norm.cdf(margin / sigma))


def _precompute_probs(
    all_teams: List[BracketTeam],
    nat_avg_ortg: float,
    sigma: float,
) -> Dict[Tuple[int, int], float]:
    """Pre-compute win probability for every ordered (id_a, id_b) pair."""
    probs: Dict[Tuple[int, int], float] = {}
    for i, a in enumerate(all_teams):
        for b in all_teams[i + 1:]:
            p = _raw_win_prob(a, b, nat_avg_ortg, sigma)
            probs[(a.team_id, b.team_id)] = p
            probs[(b.team_id, a.team_id)] = 1.0 - p
    return probs


# ---------------------------------------------------------------------------
# Build bracket from already-loaded TeamSeasonRatings
# ---------------------------------------------------------------------------

def build_bracket_from_ratings(all_ratings) -> Optional[Dict[str, Dict[int, List[BracketTeam]]]]:
    """
    Build the bracket structure from an iterable of TeamSeasonRatings.

    Returns {region: {seed: [BracketTeam, ...]}} or None if no tournament data.
    Seeds with 2 BracketTeam entries are First Four slots.
    """
    bracket: Dict[str, Dict[int, List[BracketTeam]]] = {r: {} for r in BRACKET_REGIONS}

    for tr in all_ratings:
        if tr.tournament_seed is None:
            continue
        region = tr.tournament_region
        if region not in bracket:
            continue

        team = BracketTeam(
            team_id=tr.team_id,
            name=tr.team.name,
            slug=tr.team.slug,
            logo_url=tr.team.logo_url,
            seed=tr.tournament_seed,
            region=region,
            adj_o=tr.adj_o,
            adj_d=tr.adj_d,
            adj_em=tr.adj_em,
            adj_tempo=tr.adj_tempo,
            wins=tr.wins,
            losses=tr.losses,
        )
        bracket[region].setdefault(tr.tournament_seed, []).append(team)

    # Mark First Four teams
    for region_seeds in bracket.values():
        for teams in region_seeds.values():
            if len(teams) == 2:
                for t in teams:
                    t.is_first_four = True

    # Return None if no data was loaded
    if not any(region_seeds for region_seeds in bracket.values()):
        return None

    return bracket


# ---------------------------------------------------------------------------
# Monte Carlo simulation
# ---------------------------------------------------------------------------

def _simulate_region(
    seed_to_teams: Dict[int, List[BracketTeam]],
    win_probs: Dict[Tuple[int, int], float],
    counts: Dict[str, Dict[str, int]],
    rng: random.Random,
) -> BracketTeam:
    """Simulate one region. Returns Elite 8 winner. Updates round-advance counts."""

    def sample(a: BracketTeam, b: BracketTeam) -> BracketTeam:
        p = win_probs.get((a.team_id, b.team_id), 0.5)
        return a if rng.random() < p else b

    # Step 1: Resolve First Four → exactly one team per seed slot
    resolved: Dict[int, BracketTeam] = {}
    for seed, teams in seed_to_teams.items():
        if len(teams) == 2:
            w = sample(teams[0], teams[1])
            counts[w.slug]['p_r64'] += 1
            resolved[seed] = w
        else:
            resolved[seed] = teams[0]
            # Non-First-Four teams are already "in R64" — count set at init

    # Step 2: Round of 64 — one game per pod
    r32: List[BracketTeam] = []
    for s_high, s_low in R64_PODS:
        a = resolved.get(s_high)
        b = resolved.get(s_low)
        if a is None or b is None:
            continue
        w = sample(a, b)
        counts[w.slug]['p_r32'] += 1
        r32.append(w)

    # Step 3: Round of 32
    s16: List[BracketTeam] = []
    for i, j in R32_PAIRINGS:
        if i >= len(r32) or j >= len(r32):
            continue
        w = sample(r32[i], r32[j])
        counts[w.slug]['p_s16'] += 1
        s16.append(w)

    # Step 4: Sweet 16
    e8: List[BracketTeam] = []
    for i, j in S16_PAIRINGS:
        if i >= len(s16) or j >= len(s16):
            continue
        w = sample(s16[i], s16[j])
        counts[w.slug]['p_e8'] += 1
        e8.append(w)

    # Step 5: Elite 8 (regional final)
    if len(e8) < 2:
        return e8[0] if e8 else r32[0]
    reg_winner = sample(e8[0], e8[1])
    counts[reg_winner.slug]['p_ff'] += 1
    return reg_winner


def simulate_tournament(
    bracket: Dict[str, Dict[int, List[BracketTeam]]],
    nat_avg_ortg: float,
    sigma: float,
    n_sims: int = 2000,
) -> Dict[str, Dict[str, float]]:
    """
    Run n_sims Monte Carlo simulations of the full NCAA tournament.

    Returns:
        {slug: {'p_r64', 'p_r32', 'p_s16', 'p_e8', 'p_ff', 'p_final', 'p_champion'}}

    p_rXX = probability team APPEARS IN that round (i.e., won the previous round).
    For non-First-Four teams p_r64 = 1.0 (they're already in R64).
    For First-Four teams     p_r64 = P(win First Four game).
    """
    # Flatten all bracket teams
    all_teams: List[BracketTeam] = [
        t
        for region_seeds in bracket.values()
        for teams in region_seeds.values()
        for t in teams
    ]

    # Pre-compute pairwise win probabilities for speed
    win_probs = _precompute_probs(all_teams, nat_avg_ortg, sigma)

    # Initialize counts
    counts: Dict[str, Dict[str, int]] = {}
    for t in all_teams:
        counts[t.slug] = {
            'p_r64': 0, 'p_r32': 0, 'p_s16': 0,
            'p_e8': 0, 'p_ff': 0, 'p_final': 0, 'p_champion': 0,
        }
    # Non-First-Four teams are automatically in R64
    for region_seeds in bracket.values():
        for teams in region_seeds.values():
            if len(teams) == 1:
                counts[teams[0].slug]['p_r64'] = n_sims

    rng = random.Random()

    for _ in range(n_sims):
        regional_winners: Dict[str, BracketTeam] = {}
        for region in BRACKET_REGIONS:
            if region not in bracket or not bracket[region]:
                continue
            regional_winners[region] = _simulate_region(
                bracket[region], win_probs, counts, rng
            )

        # Final Four
        ff_winners: List[BracketTeam] = []
        for reg_a, reg_b in FF_PAIRINGS:
            if reg_a not in regional_winners or reg_b not in regional_winners:
                continue
            p = win_probs.get(
                (regional_winners[reg_a].team_id, regional_winners[reg_b].team_id), 0.5
            )
            ff_winner = regional_winners[reg_a] if rng.random() < p else regional_winners[reg_b]
            counts[ff_winner.slug]['p_final'] += 1
            ff_winners.append(ff_winner)

        # Championship
        if len(ff_winners) == 2:
            p = win_probs.get((ff_winners[0].team_id, ff_winners[1].team_id), 0.5)
            champ = ff_winners[0] if rng.random() < p else ff_winners[1]
            counts[champ.slug]['p_champion'] += 1

    # Convert to probabilities
    return {
        slug: {key: round(val / n_sims, 4) for key, val in c.items()}
        for slug, c in counts.items()
    }


# ---------------------------------------------------------------------------
# Analytical P(Sweet 16) for Cinderella scoring
# ---------------------------------------------------------------------------

def compute_p_sweet16(
    team: BracketTeam,
    region_bracket: Dict[int, List[BracketTeam]],
    nat_avg_ortg: float,
    sigma: float,
) -> Optional[float]:
    """
    Analytical P(sweet 16) for a single team given the region bracket.

    Accounts for:
      - First Four: P(win First Four game) before R64
      - R64: win probability vs R64 opponent
      - R32: win probability considering both possible R32 opponents (weighted
             by each one's probability of winning their own R64 game)
    """
    seed = team.seed

    def p_ab(a: BracketTeam, b: BracketTeam) -> float:
        return _raw_win_prob(a, b, nat_avg_ortg, sigma)

    # ── P(enters R64) ────────────────────────────────────────────────────
    p_enter_r64 = 1.0
    if team.is_first_four:
        ff_slot = region_bracket.get(seed, [])
        ff_opp = next((t for t in ff_slot if t.team_id != team.team_id), None)
        p_enter_r64 = p_ab(team, ff_opp) if ff_opp else 0.5

    # ── Find R64 opponent seed ────────────────────────────────────────────
    pod_idx: Optional[int] = None
    r64_opp_seed: Optional[int] = None
    for i, (s_high, s_low) in enumerate(R64_PODS):
        if seed in (s_high, s_low):
            pod_idx = i
            r64_opp_seed = s_low if seed == s_high else s_high
            break

    if pod_idx is None or r64_opp_seed is None:
        return None

    r64_opp_teams = region_bracket.get(r64_opp_seed, [])
    if not r64_opp_teams:
        return None

    # P(win R64) — if opponent side has a First Four, weight by their entry prob
    if len(r64_opp_teams) == 2:
        p_opp0 = p_ab(r64_opp_teams[0], r64_opp_teams[1])
        p_win_r64 = (
            p_opp0 * p_ab(team, r64_opp_teams[0]) +
            (1 - p_opp0) * p_ab(team, r64_opp_teams[1])
        )
    else:
        p_win_r64 = p_ab(team, r64_opp_teams[0])

    # ── Find R32 partner pod ──────────────────────────────────────────────
    partner_pod_idx: Optional[int] = None
    for i, j in R32_PAIRINGS:
        if pod_idx == i:
            partner_pod_idx = j
            break
        if pod_idx == j:
            partner_pod_idx = i
            break

    if partner_pod_idx is None:
        return None

    ps_high, ps_low = R64_PODS[partner_pod_idx]
    partner_a_teams = region_bracket.get(ps_high, [])
    partner_b_teams = region_bracket.get(ps_low, [])
    if not partner_a_teams or not partner_b_teams:
        return None

    # Enumerate (First Four × First Four) scenarios for partner pod
    def ff_entries(teams: List[BracketTeam]):
        """Return [(team, p_enters_r64)] list."""
        if len(teams) == 2:
            p = p_ab(teams[0], teams[1])
            return [(teams[0], p), (teams[1], 1 - p)]
        return [(teams[0], 1.0)]

    pa_entries = ff_entries(partner_a_teams)
    pb_entries = ff_entries(partner_b_teams)

    p_win_r32 = 0.0
    for pa, p_pa in pa_entries:
        for pb, p_pb in pb_entries:
            p_pa_wins_r64 = p_ab(pa, pb)
            p_win_r32 += p_pa * p_pb * (
                p_pa_wins_r64 * p_ab(team, pa) +
                (1 - p_pa_wins_r64) * p_ab(team, pb)
            )

    return round(p_enter_r64 * p_win_r64 * p_win_r32, 4)
