"""
Configuration constants for CBB Analytics
"""

# Four Factor Index Configuration
# SCALE controls the spread of the 0-100 distribution
# Higher SCALE = more spread out values (more teams at extremes)
# Lower SCALE = more compressed values (teams clustered near 50)
# Default: 20 (provides good separation while keeping outliers within bounds)
FOUR_FACTOR_SCALE = 20

# Four Factor Weights (Dean Oliver's research)
# Source: Basketball on Paper (Oliver, 2004)
# These sum to ~1.0 and represent the relative importance of each factor
FOUR_FACTOR_WEIGHTS = {
    'efg': 0.4069,      # Effective FG% (most important)
    'tov': 0.4069,      # Turnover Rate (equally important)
    'reb': 0.1432,      # Rebounding (moderately important)
    'ftr': 0.0428,      # Free Throw Rate (least important)
}
