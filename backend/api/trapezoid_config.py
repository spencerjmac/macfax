"""
Trapezoid of Excellence Configuration

These quantile values define the trapezoid boundaries based on the 
distribution of teams in the current filtered dataset.

Adjust these constants to fine-tune the trapezoid shape without 
changing the core calculation logic.
"""

# Quantile values for trapezoid X-axis (Adjusted Tempo)
X_LEFT_TOP_QUANTILE = 0.05      # Left edge at top (5th percentile)
X_RIGHT_TOP_QUANTILE = 0.95     # Right edge at top (95th percentile)
X_LEFT_BOT_QUANTILE = 0.25      # Left edge at bottom (25th percentile)
X_RIGHT_BOT_QUANTILE = 0.75     # Right edge at bottom (75th percentile)

# Quantile values for trapezoid Y-axis (Adjusted Efficiency Margin)
Y_TOP_QUANTILE = 1.0            # Top edge (100th percentile - includes all teams)
Y_BOT_QUANTILE = 0.90           # Bottom edge (90th percentile)

# Fallback quantiles if primary quantiles create invalid shape
X_LEFT_BOT_FALLBACK = 0.33
X_RIGHT_BOT_FALLBACK = 0.67
Y_BOT_FALLBACK = 0.85

# Quantile interpolation method
# Options: 'linear', 'lower', 'higher', 'midpoint', 'nearest'
QUANTILE_METHOD = 'linear'
