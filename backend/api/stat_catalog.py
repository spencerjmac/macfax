"""
Stat Catalog for Viz Builder

This module defines all available statistics for the scatter plot builder.
Each stat has a unique key, human-readable label, data source, format type, and display metadata.

Format types:
- rating: efficiency ratings (e.g., 105.2)
- percent: percentages stored as 0-100 (e.g., 52.3% stored as 52.3)
- per_game: per-game averages (e.g., 12.5)
- decimal: general decimal values (e.g., 0.78)
"""

from typing import Dict, List, TypedDict


class StatMetadata(TypedDict):
    """Type definition for stat metadata"""
    key: str
    label: str
    group: str  # Data source: KenPom, Torvik, Evan Miya, CBB Analytics
    description: str
    format: str  # rating, percent, per_game, decimal
    decimals: int  # Number of decimal places to display
    higher_is_better: bool  # For color scaling (optional)


# All available stats for the viz builder
STAT_CATALOG: List[StatMetadata] = [
    # ==================== KenPom ====================
    {
        'key': 'adj_o',
        'label': 'Adj Offensive Efficiency',
        'group': 'KenPom',
        'description': 'Points scored per 100 possessions (opponent-adjusted)',
        'format': 'rating',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'adj_d',
        'label': 'Adj Defensive Efficiency',
        'group': 'KenPom',
        'description': 'Points allowed per 100 possessions (opponent-adjusted)',
        'format': 'rating',
        'decimals': 1,
        'higher_is_better': False,  # Lower is better for defense
    },
    {
        'key': 'adj_em',
        'label': 'Adj Efficiency Margin',
        'group': 'KenPom',
        'description': 'Point margin per 100 possessions (Adj O - Adj D)',
        'format': 'rating',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'adj_tempo',
        'label': 'Adj Tempo',
        'group': 'KenPom',
        'description': 'Possessions per 40 minutes (tempo-free adjusted)',
        'format': 'rating',
        'decimals': 1,
        'higher_is_better': True,  # Neutral, but higher = faster
    },
    {
        'key': 'luck',
        'label': 'Luck',
        'group': 'KenPom',
        'description': 'Deviation from expected wins based on efficiency',
        'format': 'decimal',
        'decimals': 3,
        'higher_is_better': True,
    },
    
    # ==================== Evan Miya ====================
    {
        'key': 'em_kill_shots_pg',
        'label': 'Kill Shots per game',
        'group': 'Evan Miya',
        'description': 'High-leverage field goal attempts made per game',
        'format': 'per_game',
        'decimals': 2,
        'higher_is_better': True,
    },
    {
        'key': 'em_kill_shots_conceded_pg',
        'label': 'Kill Shots Conceded per game',
        'group': 'Evan Miya',
        'description': 'High-leverage field goal attempts allowed per game',
        'format': 'per_game',
        'decimals': 2,
        'higher_is_better': False,
    },
    {
        'key': 'em_kill_shot_margin_pg',
        'label': 'Kill Shot Margin per game',
        'group': 'Evan Miya',
        'description': 'Kill shots made minus kill shots conceded per game',
        'format': 'per_game',
        'decimals': 2,
        'higher_is_better': True,
    },
    
    # ==================== Bart Torvik ====================
    {
        'key': 'efg_pct',
        'label': 'Effective FG%',
        'group': 'Bart Torvik',
        'description': 'Field goal percentage adjusted for 3-pointers being worth more',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'efg_pct_d',
        'label': 'Effective FG% Defense',
        'group': 'Bart Torvik',
        'description': 'Opponent effective field goal percentage',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': False,
    },
    {
        'key': 'orb_pct',
        'label': 'Offensive Rebound %',
        'group': 'Bart Torvik',
        'description': 'Percentage of available offensive rebounds grabbed',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'drb_pct',
        'label': 'Opponent Offensive Rebound %',
        'group': 'Bart Torvik',
        'description': 'Percentage of available rebounds opponent grabs (inverse of DRB%)',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': False,  # Lower opponent ORB% is better
    },
    {
        'key': 'tov_pct',
        'label': 'Turnover %',
        'group': 'Bart Torvik',
        'description': 'Turnovers per 100 possessions',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': False,
    },
    {
        'key': 'tov_pct_d',
        'label': 'Turnover % Defense',
        'group': 'Bart Torvik',
        'description': 'Opponent turnovers forced per 100 possessions',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'ftr',
        'label': 'Free Throw Rate',
        'group': 'Bart Torvik',
        'description': 'Free throw attempts per field goal attempt',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'ftr_d',
        'label': 'Opponent Free Throw Rate',
        'group': 'Bart Torvik',
        'description': 'Opponent free throw attempts per field goal attempt',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': False,
    },
    {
        'key': 'four_factor_index_100',
        'label': 'Four Factor Index (WZ100)',
        'group': 'Bart Torvik',
        'description': 'Composite index of the Four Factors (0-100 scale)',
        'format': 'rating',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'fg3_pct',
        'label': '3 Point %',
        'group': 'Bart Torvik',
        'description': 'Three-point shooting percentage',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'fg3_pct_d',
        'label': '3 Point % D',
        'group': 'Bart Torvik',
        'description': 'Opponent three-point shooting percentage',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': False,
    },
    {
        'key': 'fg2_pct',
        'label': '2 Point %',
        'group': 'Bart Torvik',
        'description': 'Two-point shooting percentage',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'fg2_pct_d',
        'label': '2 Point % D',
        'group': 'Bart Torvik',
        'description': 'Opponent two-point shooting percentage',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': False,
    },
    {
        'key': 'fg3_rate',
        'label': 'Three Point Rate',
        'group': 'Bart Torvik',
        'description': 'Percentage of field goal attempts that are three-pointers',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': True,  # Neutral, but higher = more threes
    },
    {
        'key': 'fg3_rate_d',
        'label': 'Three Point Rate D',
        'group': 'Bart Torvik',
        'description': 'Percentage of opponent field goal attempts that are three-pointers',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': False,  # Lower opponent 3PR is generally better
    },
    
    # ==================== CBB Analytics ====================
    {
        'key': 'cbb_ast_g',
        'label': 'AST/G',
        'group': 'CBB Analytics',
        'description': 'Assists per game',
        'format': 'per_game',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'cbb_ast_pct',
        'label': 'AST%',
        'group': 'CBB Analytics',
        'description': 'Percentage of field goals assisted',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'cbb_blk_g',
        'label': 'BLK/G',
        'group': 'CBB Analytics',
        'description': 'Blocks per game',
        'format': 'per_game',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'cbb_blk_pct',
        'label': 'BLK%',
        'group': 'CBB Analytics',
        'description': 'Block percentage',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'cbb_dpf_g',
        'label': 'DPF/G',
        'group': 'CBB Analytics',
        'description': 'Defensive personal fouls per game',
        'format': 'per_game',
        'decimals': 1,
        'higher_is_better': False,
    },
    {
        'key': 'cbb_drb_g',
        'label': 'DRB/G',
        'group': 'CBB Analytics',
        'description': 'Defensive rebounds per game',
        'format': 'per_game',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'cbb_fg_pct',
        'label': 'FG%',
        'group': 'CBB Analytics',
        'description': 'Field goal percentage',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'ft_pct',
        'label': 'FT%',
        'group': 'CBB Analytics',
        'description': 'Free throw percentage',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'cbb_hkm_pct',
        'label': 'HKM%',
        'group': 'CBB Analytics',
        'description': 'Help-Kill Metric percentage',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'cbb_opf_g',
        'label': 'OPF/G',
        'group': 'CBB Analytics',
        'description': 'Offensive personal fouls per game',
        'format': 'per_game',
        'decimals': 1,
        'higher_is_better': False,
    },
    {
        'key': 'cbb_pace_raw',
        'label': 'PACE (RAW)',
        'group': 'CBB Analytics',
        'description': 'Raw pace (possessions per game)',
        'format': 'rating',
        'decimals': 1,
        'higher_is_better': True,  # Neutral
    },
    {
        'key': 'cbb_pf_g',
        'label': 'PF/G',
        'group': 'CBB Analytics',
        'description': 'Personal fouls per game',
        'format': 'per_game',
        'decimals': 1,
        'higher_is_better': False,
    },
    {
        'key': 'cbb_pts_g',
        'label': 'PTS/G',
        'group': 'CBB Analytics',
        'description': 'Points per game',
        'format': 'per_game',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'cbb_reb_g',
        'label': 'REB/G',
        'group': 'CBB Analytics',
        'description': 'Rebounds per game',
        'format': 'per_game',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'cbb_stl_g',
        'label': 'STL/G',
        'group': 'CBB Analytics',
        'description': 'Steals per game',
        'format': 'per_game',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'cbb_tov_g',
        'label': 'TOV/G',
        'group': 'CBB Analytics',
        'description': 'Turnovers per game',
        'format': 'per_game',
        'decimals': 1,
        'higher_is_better': False,
    },
]


def get_stat_catalog() -> List[StatMetadata]:
    """Return the full stat catalog"""
    return STAT_CATALOG


def get_stat_metadata(key: str) -> StatMetadata | None:
    """Get metadata for a specific stat by key"""
    for stat in STAT_CATALOG:
        if stat['key'] == key:
            return stat
    return None


def is_valid_stat_key(key: str) -> bool:
    """Check if a stat key is valid"""
    return any(stat['key'] == key for stat in STAT_CATALOG)


def get_stats_by_group() -> Dict[str, List[StatMetadata]]:
    """Return stats grouped by data source"""
    grouped = {}
    for stat in STAT_CATALOG:
        group = stat['group']
        if group not in grouped:
            grouped[group] = []
        grouped[group].append(stat)
    return grouped
