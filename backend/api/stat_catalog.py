"""
Stat Catalog for Viz Builder

This module defines all available statistics computed from game log data.
All stats are calculated from our proprietary game log scraper and rating system.

Format types:
- rating: efficiency ratings (e.g., 105.2)
- percent: percentages stored as 0-100 (e.g., 52.3% stored as 52.3)
- index: index values on 0-100 scale (e.g., 65.4)
"""

from typing import Dict, List, TypedDict


class StatMetadata(TypedDict):
    """Type definition for stat metadata"""
    key: str
    label: str
    group: str  # Logical category for organization
    description: str
    format: str  # rating, percent, index
    decimals: int  # Number of decimal places to display
    higher_is_better: bool  # For color scaling


# All available stats from TeamSeasonRatings model
STAT_CATALOG: List[StatMetadata] = [
    # ==================== Efficiency Ratings ====================
    {
        'key': 'adj_o',
        'label': 'Adj Offensive Rating',
        'group': 'Efficiency',
        'description': 'Points scored per 100 possessions (opponent-adjusted)',
        'format': 'rating',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'adj_d',
        'label': 'Adj Defensive Rating',
        'group': 'Efficiency',
        'description': 'Points allowed per 100 possessions (opponent-adjusted)',
        'format': 'rating',
        'decimals': 1,
        'higher_is_better': False,
    },
    {
        'key': 'adj_em',
        'label': 'Adj Efficiency Margin',
        'group': 'Efficiency',
        'description': 'Point margin per 100 possessions (Adj O - Adj D)',
        'format': 'rating',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'adj_tempo',
        'label': 'Adj Tempo',
        'group': 'Efficiency',
        'description': 'Possessions per game (opponent-adjusted)',
        'format': 'rating',
        'decimals': 1,
        'higher_is_better': True,
    },
    
    # ==================== Four Factors - Offense ====================
    {
        'key': 'adj_efg_pct',
        'label': 'Adj eFG%',
        'group': 'Four Factors',
        'description': 'Effective FG% (opponent-adjusted)',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'adj_tov_pct',
        'label': 'Adj TOV%',
        'group': 'Four Factors',
        'description': 'Turnover % (opponent-adjusted)',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': False,
    },
    {
        'key': 'adj_orb_pct',
        'label': 'Adj ORB%',
        'group': 'Four Factors',
        'description': 'Offensive Rebound % (opponent-adjusted)',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'adj_ftr',
        'label': 'Adj FTR',
        'group': 'Four Factors',
        'description': 'Free Throw Rate (opponent-adjusted)',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'adj_opp_efg_pct',
        'label': 'Adj Opp eFG%',
        'group': 'Four Factors',
        'description': 'Opponent eFG% (opponent-adjusted)',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': False,
    },
    {
        'key': 'adj_opp_tov_pct',
        'label': 'Adj Opp TOV%',
        'group': 'Four Factors',
        'description': 'Opponent TOV% forced (opponent-adjusted)',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'adj_opp_orb_pct',
        'label': 'Adj Opp ORB%',
        'group': 'Four Factors',
        'description': 'Opponent ORB% allowed (opponent-adjusted)',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': False,
    },
    {
        'key': 'adj_drb_pct',
        'label': 'Adj DRB%',
        'group': 'Four Factors',
        'description': 'Defensive Rebound % (opponent-adjusted)',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'adj_opp_ftr',
        'label': 'Adj Opp FTR',
        'group': 'Four Factors',
        'description': 'Opponent FTR allowed (opponent-adjusted)',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': False,
    },
    
    # ==================== Four Factor Margins ====================
    {
        'key': 'adj_efg_margin',
        'label': 'Adj eFG Margin',
        'group': 'Margins',
        'description': 'eFG% margin (adjusted)',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'adj_tov_edge',
        'label': 'Adj TOV Edge',
        'group': 'Margins',
        'description': 'Turnover edge (adjusted)',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'adj_reb_edge',
        'label': 'Adj REB Edge',
        'group': 'Margins',
        'description': 'Rebounding edge (adjusted)',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'adj_ftr_margin',
        'label': 'Adj FTR Margin',
        'group': 'Margins',
        'description': 'Free throw rate margin (adjusted)',
        'format': 'percent',
        'decimals': 1,
        'higher_is_better': True,
    },
    
    # ==================== Four Factor Index ====================
    {
        'key': 'ffi_raw',
        'label': 'Four Factor Index (Raw)',
        'group': 'Index',
        'description': 'Four Factor Index from raw margins (0-100 scale)',
        'format': 'index',
        'decimals': 1,
        'higher_is_better': True,
    },
    {
        'key': 'ffi_adj',
        'label': 'Four Factor Index (Adj)',
        'group': 'Index',
        'description': 'Four Factor Index from adjusted margins (0-100 scale)',
        'format': 'index',
        'decimals': 1,
        'higher_is_better': True,
    },
]


def get_stat_catalog(exclude_external: bool = True) -> List[StatMetadata]:
    """
    Return the stat catalog.
    
    All stats are computed from our game log scraper and rating system.
    The exclude_external parameter is maintained for compatibility but has no effect
    since all stats are now from our computed data.
    """
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


def get_stats_by_group(exclude_external: bool = True) -> Dict[str, List[StatMetadata]]:
    """
    Return stats grouped by logical category.
    
    All stats are computed from our game log scraper and rating system.
    The exclude_external parameter is maintained for compatibility but has no effect.
    """
    catalog = get_stat_catalog(exclude_external=exclude_external)
    grouped = {}
    for stat in catalog:
        group = stat['group']
        if group not in grouped:
            grouped[group] = []
        grouped[group].append(stat)
    return grouped
