"""
Trapezoid of Excellence Configuration

NATIONAL BASELINE APPROACH:
The trapezoid boundaries are computed from ALL Division I teams in the 
current season snapshot, NOT from filtered teams. Filters only affect 
which teams are displayed.

Concept by Ryan Hammer
"""

# ==================== Y-AXIS (Efficiency Margin) ====================
# Elite floor: bottom boundary is computed from national distribution
Q_BOT_EM = 0.97  # 97th percentile of national Adj EM distribution

# Top boundary: always above the best team in the nation
Y_PAD_MIN = 0.50  # Minimum padding above max EM
Y_PAD_RATE = 0.02  # Additional padding as % of (y_max - y_bot) range

# ==================== X-AXIS (Tempo/Pace) ====================
# X-bounds are computed from the ELITE SUBSET (teams with adj_em >= y_bot)
# NOT from all teams - this creates the trapezoid shape
# Top edge uses MIN/MAX to capture full elite pace range
# (allows extreme-pace elite teams to be evaluated by slanted sides)
# Q_X_LEFT_TOP and Q_X_RIGHT_TOP are NOT USED (kept for reference)
Q_X_LEFT_TOP = 0.02   # NOT USED - top edge uses MIN(elite_tempo)
Q_X_RIGHT_TOP = 0.98  # NOT USED - top edge uses MAX(elite_tempo)
Q_X_LEFT_BOT = 0.30   # 30th percentile of elite subset tempo
Q_X_RIGHT_BOT = 0.75  # 75th percentile of elite subset tempo

# Padding to prevent logos from touching trapezoid outline
PACE_PAD = 0.75  # Added/subtracted from left_top and right_top

# ==================== COMPUTATION SETTINGS ====================
# Quantile interpolation method
# Options: 'linear', 'lower', 'higher', 'midpoint', 'nearest'
QUANTILE_METHOD = 'linear'
