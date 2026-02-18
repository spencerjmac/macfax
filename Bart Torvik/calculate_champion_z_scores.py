"""
Calculate Four Factor Index for champions using season-specific Z-scores.

This approach:
1. Loads all historical season data (all teams from each season)
2. For each champion, calculates Z-scores based on their season's distribution
3. Uses the same formula as the current season backend calculation
4. Weights: eFG (40.69%), TOV (40.69%), REB (14.32%), FTR (4.28%)
5. Converts to 0-100 scale: MIN(100, MAX(0, 50 + 20 * weighted_z))
"""
import pandas as pd
import numpy as np

# Load champions data and historical data
champions_df = pd.read_csv('torvik_champions.csv')
historical_df = pd.read_csv('torvik_historical_all_teams.csv')

print("="*70)
print("CALCULATING CHAMPION FOUR FACTOR INDEX")
print("="*70)
print()
print(f"Loaded {len(champions_df)} champions")
print(f"Loaded {len(historical_df)} historical team records")
print()

# Calculate the four margins/edges for champions
champions_df['efg_margin'] = champions_df['efg_pct'] - champions_df['efg_pct_d']
champions_df['ftr_margin'] = champions_df['ftr'] - champions_df['ftrd']
champions_df['turnover_edge'] = champions_df['tord'] - champions_df['tor']
champions_df['rebounding_edge'] = champions_df['orb'] - champions_df['drb']

# Calculate the four margins/edges for all historical teams
historical_df['efg_margin'] = historical_df['efg_pct'] - historical_df['efg_pct_d']
historical_df['ftr_margin'] = historical_df['ftr'] - historical_df['ftrd']
historical_df['turnover_edge'] = historical_df['tord'] - historical_df['tor']
historical_df['rebounding_edge'] = historical_df['orb'] - historical_df['drb']

print("="*70)
print("CALCULATING SEASON-SPECIFIC Z-SCORES")
print("="*70)
print()

# Four Factor weights (from backend constants.py)
WEIGHTS = {
    'efg': 0.4069,
    'tov': 0.4069,
    'reb': 0.1432,
    'ftr': 0.0428
}
SCALE = 20

# Initialize columns for z-scores and final index
champions_df['efg_margin_z'] = np.nan
champions_df['ftr_margin_z'] = np.nan
champions_df['turnover_edge_z'] = np.nan
champions_df['rebounding_edge_z'] = np.nan
champions_df['four_factor_index_wz'] = np.nan
champions_df['four_factor_score'] = np.nan

# Calculate Z-scores for each champion based on their season's distribution
for idx, champion in champions_df.iterrows():
    year = champion['year']
    
    # Get all teams from this champion's season
    season_teams = historical_df[historical_df['year'] == year].copy()
    
    if len(season_teams) == 0:
        print(f"  WARNING: No historical data for {year} {champion['team_name']}")
        continue
    
    # Calculate season statistics
    efg_mean = season_teams['efg_margin'].mean()
    efg_std = season_teams['efg_margin'].std()
    tov_mean = season_teams['turnover_edge'].mean()
    tov_std = season_teams['turnover_edge'].std()
    reb_mean = season_teams['rebounding_edge'].mean()
    reb_std = season_teams['rebounding_edge'].std()
    ftr_mean = season_teams['ftr_margin'].mean()
    ftr_std = season_teams['ftr_margin'].std()
    
    # Calculate Z-scores for this champion
    efg_z = (champion['efg_margin'] - efg_mean) / efg_std
    tov_z = (champion['turnover_edge'] - tov_mean) / tov_std
    reb_z = (champion['rebounding_edge'] - reb_mean) / reb_std
    ftr_z = (champion['ftr_margin'] - ftr_mean) / ftr_std
    
    # Calculate weighted Z-score (NO division by 4!)
    wz = (WEIGHTS['efg'] * efg_z + 
          WEIGHTS['tov'] * tov_z + 
          WEIGHTS['reb'] * reb_z + 
          WEIGHTS['ftr'] * ftr_z)
    
    # Convert to 0-100 scale with clamping
    ffi_100 = max(0, min(100, 50 + SCALE * wz))
    
    # Store results
    champions_df.at[idx, 'efg_margin_z'] = efg_z
    champions_df.at[idx, 'ftr_margin_z'] = ftr_z
    champions_df.at[idx, 'turnover_edge_z'] = tov_z
    champions_df.at[idx, 'rebounding_edge_z'] = reb_z
    champions_df.at[idx, 'four_factor_index_wz'] = wz
    champions_df.at[idx, 'four_factor_score'] = ffi_100
    
    print(f"{year} {champion['team_name'][:30]:30s}: FFI = {ffi_100:5.1f}  (n={len(season_teams)} teams)")

print()

# Save results
output_file = 'torvik_champions_with_z_scores.csv'
champions_df.to_csv(output_file, index=False)

print(f"Saved results to: {output_file}")
print()

# Display final results
print("="*70)
print("FINAL CHAMPION FOUR FACTOR INDEX (1-100)")
print("="*70)
print()

display_cols = ['year', 'team_name', 'four_factor_score', 
                'efg_margin', 'efg_margin_z',
                'turnover_edge', 'turnover_edge_z',
                'rebounding_edge', 'rebounding_edge_z',
                'four_factor_index_wz']

result_df = champions_df[display_cols].sort_values('four_factor_score', ascending=False)
print(result_df.to_string(index=False))

print()
print("="*70)
print("TOP 5 CHAMPIONS BY FOUR FACTOR INDEX")
print("="*70)
top5 = champions_df.nlargest(5, 'four_factor_score')[
    ['year', 'team_name', 'efg_margin', 'turnover_edge', 
     'rebounding_edge', 'ftr_margin', 'four_factor_score']
]
print(top5.to_string(index=False))

print()
print("="*70)
print("SUMMARY STATISTICS")
print("="*70)
print(f"Mean FFI:   {champions_df['four_factor_score'].mean():.1f}")
print(f"Median FFI: {champions_df['four_factor_score'].median():.1f}")
print(f"Std Dev:    {champions_df['four_factor_score'].std():.1f}")
print(f"Min FFI:    {champions_df['four_factor_score'].min():.1f} ({champions_df.loc[champions_df['four_factor_score'].idxmin(), 'year']} {champions_df.loc[champions_df['four_factor_score'].idxmin(), 'team_name']})")
print(f"Max FFI:    {champions_df['four_factor_score'].max():.1f} ({champions_df.loc[champions_df['four_factor_score'].idxmax(), 'year']} {champions_df.loc[champions_df['four_factor_score'].idxmax(), 'team_name']})")

print("="*70)
print("SUMMARY STATISTICS")
print("="*70)
print(f"Average Four Factor Score: {champions_df['four_factor_score'].mean():.2f}")
print(f"Highest Score: {champions_df['four_factor_score'].max():.2f} ({champions_df.loc[champions_df['four_factor_score'].idxmax(), 'team_name']})")
print(f"Lowest Score: {champions_df['four_factor_score'].min():.2f} ({champions_df.loc[champions_df['four_factor_score'].idxmin(), 'team_name']})")

print()
print("="*70)
print("NOTES")
print("="*70)
print()
print("These Z-scores are calculated using all champions as the baseline.")
print("This approach:")
print("  ✓ Allows comparison of champions across different eras")
print("  ✓ Uses actual champion data (not estimated season-wide stats)")
print("  ✓ Provides a 'championship standard' benchmark")
print()
print("To compare current teams to champions, use the same formulas:")
print("  1. Calculate the four margins (EFG, FTR, TO Edge, Reb Edge)")
print("  2. Calculate Z-scores using the season means/std from champions")
print("  3. Apply weights and convert to 0-100 score")
print()
print("="*70)
