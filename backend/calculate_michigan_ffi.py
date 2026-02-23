"""
Calculate Michigan's Four Factor Index step by step
"""
from core.models import Team, Season, TeamSeasonMetrics, TeamSeasonRatings
import math

def compute_stats(values):
    """Compute mean and standard deviation"""
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    
    mean = sum(values) / n
    
    if n == 1:
        return mean, 0.0
    
    variance = sum((x - mean) ** 2 for x in values) / n
    std_dev = math.sqrt(variance)
    
    return mean, std_dev

def compute_z_score(value, mean, std_dev):
    """Compute z-score with protection against zero std dev"""
    if std_dev == 0:
        return 0.0
    return (value - mean) / std_dev

# Get season
season = Season.objects.get(year=2026)

# Get Michigan
michigan = Team.objects.get(name="Michigan")
michigan_metrics = TeamSeasonMetrics.objects.get(team=michigan, season=season)
michigan_ratings = TeamSeasonRatings.objects.get(team=michigan, season=season)

print("=" * 80)
print("MICHIGAN FOUR FACTOR INDEX CALCULATION")
print("=" * 80)

# ========================================
# PART 1: RAW FOUR FACTOR INDEX
# ========================================
print("\n" + "=" * 80)
print("PART 1: RAW FOUR FACTOR INDEX (From Game Statistics)")
print("=" * 80)

# Get all D1 teams' raw margins
all_metrics = TeamSeasonMetrics.objects.filter(season=season, team__is_d1=True)

raw_efg_margins = [m.efg_margin for m in all_metrics]
raw_tov_edges = [m.tov_edge for m in all_metrics]
raw_reb_edges = [m.reb_edge for m in all_metrics]
raw_ftr_margins = [m.ftr_margin for m in all_metrics]

# Compute season statistics
efg_mean, efg_std = compute_stats(raw_efg_margins)
tov_mean, tov_std = compute_stats(raw_tov_edges)
reb_mean, reb_std = compute_stats(raw_reb_edges)
ftr_mean, ftr_std = compute_stats(raw_ftr_margins)

print(f"\n{'Season Statistics (All D1 Teams)':^80}")
print("-" * 80)
print(f"eFG Margin:  Mean = {efg_mean:7.2f}%, Std Dev = {efg_std:6.2f}%")
print(f"TOV Edge:    Mean = {tov_mean:7.2f}%, Std Dev = {tov_std:6.2f}%")
print(f"REB Edge:    Mean = {reb_mean:7.2f}%, Std Dev = {reb_std:6.2f}%")
print(f"FTR Margin:  Mean = {ftr_mean:7.2f}%, Std Dev = {ftr_std:6.2f}%")

# Michigan's raw margins
print(f"\n{'Michigan Raw Margins':^80}")
print("-" * 80)
print(f"eFG Margin:  {michigan_metrics.efg_margin:7.2f}%")
print(f"TOV Edge:    {michigan_metrics.tov_edge:7.2f}%")
print(f"REB Edge:    {michigan_metrics.reb_edge:7.2f}%")
print(f"FTR Margin:  {michigan_metrics.ftr_margin:7.2f}%")

# Compute z-scores
z_efg = compute_z_score(michigan_metrics.efg_margin, efg_mean, efg_std)
z_tov = compute_z_score(michigan_metrics.tov_edge, tov_mean, tov_std)
z_reb = compute_z_score(michigan_metrics.reb_edge, reb_mean, reb_std)
z_ftr = compute_z_score(michigan_metrics.ftr_margin, ftr_mean, ftr_std)

print(f"\n{'Step 1: Calculate Z-Scores':^80}")
print("-" * 80)
print(f"z_eFG = (eFG_margin - mean) / std_dev")
print(f"      = ({michigan_metrics.efg_margin:.2f} - {efg_mean:.2f}) / {efg_std:.2f}")
print(f"      = {z_efg:.4f}")
print()
print(f"z_TOV = (TOV_edge - mean) / std_dev")
print(f"      = ({michigan_metrics.tov_edge:.2f} - {tov_mean:.2f}) / {tov_std:.2f}")
print(f"      = {z_tov:.4f}")
print()
print(f"z_REB = (REB_edge - mean) / std_dev")
print(f"      = ({michigan_metrics.reb_edge:.2f} - {reb_mean:.2f}) / {reb_std:.2f}")
print(f"      = {z_reb:.4f}")
print()
print(f"z_FTR = (FTR_margin - mean) / std_dev")
print(f"      = ({michigan_metrics.ftr_margin:.2f} - {ftr_mean:.2f}) / {ftr_std:.2f}")
print(f"      = {z_ftr:.4f}")

# Weighted FFI z-score
print(f"\n{'Step 2: Calculate Weighted FFI Z-Score':^80}")
print("-" * 80)
print("FFI_z = 0.4069 × z_eFG + 0.4069 × z_TOV + 0.1432 × z_REB + 0.0428 × z_FTR")
print()
print(f"FFI_z = 0.4069 × {z_efg:.4f} + 0.4069 × {z_tov:.4f} + 0.1432 × {z_reb:.4f} + 0.0428 × {z_ftr:.4f}")
print(f"      = {0.4069 * z_efg:.4f} + {0.4069 * z_tov:.4f} + {0.1432 * z_reb:.4f} + {0.0428 * z_ftr:.4f}")

ffi_z_raw = (
    0.4069 * z_efg +
    0.4069 * z_tov +
    0.1432 * z_reb +
    0.0428 * z_ftr
)
print(f"      = {ffi_z_raw:.4f}")

# Scale to 0-100
print(f"\n{'Step 3: Scale to 0-100 Range':^80}")
print("-" * 80)
print("FFI_100 = clamp(50 + 20 × FFI_z, 0, 100)")
print(f"        = clamp(50 + 20 × {ffi_z_raw:.4f}, 0, 100)")
print(f"        = clamp({50 + 20 * ffi_z_raw:.4f}, 0, 100)")

ffi_100_raw = max(0, min(100, 50 + 20 * ffi_z_raw))
print(f"        = {ffi_100_raw:.1f}")

print(f"\n{'=' * 80}")
print(f"MICHIGAN RAW FOUR FACTOR INDEX: {ffi_100_raw:.1f}")
print(f"Database Value: {michigan_ratings.ffi_raw:.1f}")
print(f"{'=' * 80}")

# ========================================
# PART 2: ADJUSTED FOUR FACTOR INDEX
# ========================================
print("\n\n" + "=" * 80)
print("PART 2: ADJUSTED FOUR FACTOR INDEX (Opponent-Adjusted)")
print("=" * 80)

# Get all D1 teams' adjusted margins
all_ratings = TeamSeasonRatings.objects.filter(season=season, team__is_d1=True)

adj_efg_margins = [r.adj_efg_margin for r in all_ratings]
adj_tov_edges = [r.adj_tov_edge for r in all_ratings]
adj_reb_edges = [r.adj_reb_edge for r in all_ratings]
adj_ftr_margins = [r.adj_ftr_margin for r in all_ratings]

# Compute season statistics
adj_efg_mean, adj_efg_std = compute_stats(adj_efg_margins)
adj_tov_mean, adj_tov_std = compute_stats(adj_tov_edges)
adj_reb_mean, adj_reb_std = compute_stats(adj_reb_edges)
adj_ftr_mean, adj_ftr_std = compute_stats(adj_ftr_margins)

print(f"\n{'Season Statistics (All D1 Teams)':^80}")
print("-" * 80)
print(f"Adj eFG Margin:  Mean = {adj_efg_mean:7.2f}%, Std Dev = {adj_efg_std:6.2f}%")
print(f"Adj TOV Edge:    Mean = {adj_tov_mean:7.2f}%, Std Dev = {adj_tov_std:6.2f}%")
print(f"Adj REB Edge:    Mean = {adj_reb_mean:7.2f}%, Std Dev = {adj_reb_std:6.2f}%")
print(f"Adj FTR Margin:  Mean = {adj_ftr_mean:7.2f}%, Std Dev = {adj_ftr_std:6.2f}%")

# Michigan's adjusted margins
print(f"\n{'Michigan Adjusted Margins':^80}")
print("-" * 80)
print(f"Adj eFG Margin:  {michigan_ratings.adj_efg_margin:7.2f}%")
print(f"Adj TOV Edge:    {michigan_ratings.adj_tov_edge:7.2f}%")
print(f"Adj REB Edge:    {michigan_ratings.adj_reb_edge:7.2f}%")
print(f"Adj FTR Margin:  {michigan_ratings.adj_ftr_margin:7.2f}%")

# Compute z-scores
adj_z_efg = compute_z_score(michigan_ratings.adj_efg_margin, adj_efg_mean, adj_efg_std)
adj_z_tov = compute_z_score(michigan_ratings.adj_tov_edge, adj_tov_mean, adj_tov_std)
adj_z_reb = compute_z_score(michigan_ratings.adj_reb_edge, adj_reb_mean, adj_reb_std)
adj_z_ftr = compute_z_score(michigan_ratings.adj_ftr_margin, adj_ftr_mean, adj_ftr_std)

print(f"\n{'Step 1: Calculate Z-Scores':^80}")
print("-" * 80)
print(f"z_eFG = (Adj_eFG_margin - mean) / std_dev")
print(f"      = ({michigan_ratings.adj_efg_margin:.2f} - {adj_efg_mean:.2f}) / {adj_efg_std:.2f}")
print(f"      = {adj_z_efg:.4f}")
print()
print(f"z_TOV = (Adj_TOV_edge - mean) / std_dev")
print(f"      = ({michigan_ratings.adj_tov_edge:.2f} - {adj_tov_mean:.2f}) / {adj_tov_std:.2f}")
print(f"      = {adj_z_tov:.4f}")
print()
print(f"z_REB = (Adj_REB_edge - mean) / std_dev")
print(f"      = ({michigan_ratings.adj_reb_edge:.2f} - {adj_reb_mean:.2f}) / {adj_reb_std:.2f}")
print(f"      = {adj_z_reb:.4f}")
print()
print(f"z_FTR = (Adj_FTR_margin - mean) / std_dev")
print(f"      = ({michigan_ratings.adj_ftr_margin:.2f} - {adj_ftr_mean:.2f}) / {adj_ftr_std:.2f}")
print(f"      = {adj_z_ftr:.4f}")

# Weighted FFI z-score
print(f"\n{'Step 2: Calculate Weighted FFI Z-Score':^80}")
print("-" * 80)
print("FFI_z = 0.4069 × z_eFG + 0.4069 × z_TOV + 0.1432 × z_REB + 0.0428 × z_FTR")
print()
print(f"FFI_z = 0.4069 × {adj_z_efg:.4f} + 0.4069 × {adj_z_tov:.4f} + 0.1432 × {adj_z_reb:.4f} + 0.0428 × {adj_z_ftr:.4f}")
print(f"      = {0.4069 * adj_z_efg:.4f} + {0.4069 * adj_z_tov:.4f} + {0.1432 * adj_z_reb:.4f} + {0.0428 * adj_z_ftr:.4f}")

ffi_z_adj = (
    0.4069 * adj_z_efg +
    0.4069 * adj_z_tov +
    0.1432 * adj_z_reb +
    0.0428 * adj_z_ftr
)
print(f"      = {ffi_z_adj:.4f}")

# Scale to 0-100
print(f"\n{'Step 3: Scale to 0-100 Range':^80}")
print("-" * 80)
print("FFI_100 = clamp(50 + 20 × FFI_z, 0, 100)")
print(f"        = clamp(50 + 20 × {ffi_z_adj:.4f}, 0, 100)")
print(f"        = clamp({50 + 20 * ffi_z_adj:.4f}, 0, 100)")

ffi_100_adj = max(0, min(100, 50 + 20 * ffi_z_adj))
print(f"        = {ffi_100_adj:.1f}")

print(f"\n{'=' * 80}")
print(f"MICHIGAN ADJUSTED FOUR FACTOR INDEX: {ffi_100_adj:.1f}")
print(f"Database Value: {michigan_ratings.ffi_adj:.1f}")
print(f"{'=' * 80}")

print(f"\n\n{'SUMMARY':^80}")
print("=" * 80)
print(f"Michigan Raw Four Factor Index:      {ffi_100_raw:.1f}")
print(f"Michigan Adjusted Four Factor Index: {ffi_100_adj:.1f}")
print("=" * 80)
