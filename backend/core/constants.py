"""
Configuration constants for CBB Analytics
"""

# Four Factor Index Configuration
# SCALE controls the spread of the 0-100 distribution
# Higher SCALE = more spread out values (more teams at extremes)
# Lower SCALE = more compressed values (teams clustered near 50)
# Default: 20 (provides good separation while keeping outliers within bounds)
FOUR_FACTOR_SCALE = 20

# Four Factor Weights (updated March 2026 — tuned for college basketball)
# Previously used Dean Oliver's original weights (efg=tov=0.4069, reb=0.1432, ftr=0.0428)
FOUR_FACTOR_WEIGHTS = {
    'efg': 0.45,        # Effective FG% (most important)
    'tov': 0.24,        # Turnover Rate
    'reb': 0.22,        # Rebounding (elevated vs. Oliver — more impactful in college)
    'ftr': 0.09,        # Free Throw Rate
}
