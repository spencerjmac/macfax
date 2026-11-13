"""
Configuration constants for CBB Analytics
"""

# Four Factor Index Configuration
# SCALE controls the spread of the 0-100 distribution
# Higher SCALE = more spread out values (more teams at extremes)
# Lower SCALE = more compressed values (teams clustered near 50)
# Default: 20 (provides good separation while keeping outliers within bounds)
FOUR_FACTOR_SCALE = 20

# Four Factor Weights: the single source for every Four Factor Index (team ffi_adj/ffi_raw in
# compute_four_factor_index; player on_court_ffi and four_factor_impact_index).
# Hand-tuned for college basketball, not fitted (train_four_factor_regression fits margin coefficients
# for the matchup model, not these weights). History: Dean Oliver's 0.4069/0.4069/0.1432/0.0428 until
# 2026-02; 0.45/0.24/0.22/0.09 in compute_four_factor_index until 2026-03-17 (59f2840), then
# 0.47/0.24/0.21/0.08 via PipelineConfig while this constant still said 0.45/0.24/0.22/0.09.
# Consolidated 2026-11-13 (Task 7c.2) on 0.47/0.24/0.21/0.08 so team ffi_adj keeps its values.
FOUR_FACTOR_WEIGHTS = {
    'efg': 0.47,        # Effective FG% margin (most important)
    'tov': 0.24,        # Turnover edge
    'reb': 0.21,        # Rebounding edge
    'ftr': 0.08,        # Free throw rate margin
}
