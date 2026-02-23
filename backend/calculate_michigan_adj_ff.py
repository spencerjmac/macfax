"""
Calculate Michigan's Adjusted Four Factors step by step
Shows the formula and calculations for each game
"""
from core.models import Team, Season, TeamGameStats, NationalAverages, TeamSeasonRatings, TeamSeasonMetrics

# Get season
season = Season.objects.get(year=2026)

# Get Michigan
michigan = Team.objects.get(name="Michigan")

# Get national averages
nat_avg = NationalAverages.objects.get(season=season)

# Get Michigan's games
michigan_games = TeamGameStats.objects.filter(
    team=michigan,
    game__season_year=season.year
).select_related('game').order_by('game__game_date')

# Get Michigan's ratings (which have the final adjusted values)
michigan_ratings = TeamSeasonRatings.objects.get(team=michigan, season=season)
michigan_metrics = TeamSeasonMetrics.objects.get(team=michigan, season=season)

print("=" * 100)
print("MICHIGAN ADJUSTED FOUR FACTORS CALCULATION")
print("=" * 100)

print(f"\n{'NATIONAL AVERAGES (2025-26 Season)':^100}")
print("-" * 100)
print(f"National Avg eFG%:  {nat_avg.avg_efg:.2f}%")
print(f"National Avg TOV%:  {nat_avg.avg_tov:.2f}%")
print(f"National Avg ORB%:  {nat_avg.avg_orb:.2f}%")
print(f"National Avg FTR:   {nat_avg.avg_ftr:.2f}%")

print(f"\n{'MICHIGAN RAW FOUR FACTORS (Season Averages)':^100}")
print("-" * 100)
print(f"Raw eFG%:     {michigan_metrics.efg_pct:.2f}%")
print(f"Raw TOV%:     {michigan_metrics.tov_pct:.2f}%")
print(f"Raw ORB%:     {michigan_metrics.orb_pct:.2f}%")
print(f"Raw FTR:      {michigan_metrics.ftr:.2f}%")
print()
print(f"Raw eFG%_d:   {michigan_metrics.opp_efg_pct:.2f}%")
print(f"Raw TOV%_d:   {michigan_metrics.opp_tov_pct:.2f}%")
print(f"Raw ORB%_d:   {michigan_metrics.opp_orb_pct:.2f}%")
print(f"Raw DRB%:     {michigan_metrics.drb_pct:.2f}%")
print(f"Raw FTR_d:    {michigan_metrics.opp_ftr:.2f}%")

print(f"\n{'ADJUSTMENT FORMULA':^100}")
print("=" * 100)
print("For each game, adjusted stats are calculated as:")
print()
print("  Adj_eFG_game = Raw_eFG_game × (National_eFG / Opponent_Adj_Def_eFG) × Site_Factor")
print("  Adj_TOV_game = Raw_TOV_game × (National_TOV / Opponent_Adj_Def_TOV) × Site_Factor")
print("  Adj_ORB_game = Raw_ORB_game × (National_ORB / Opponent_Adj_ORB) × Site_Factor")
print("  Adj_FTR_game = Raw_FTR_game × (National_FTR / Opponent_Adj_Def_FTR) × Site_Factor")
print()
print("Site Factors: Home = 1.014, Away = 0.986, Neutral = 1.000")
print()
print("Then all games are averaged using possession-weighted averaging:")
print("  Adj_eFG_season = Σ(Poss_game × Adj_eFG_game) / Σ(Poss_game)")
print()

print(f"\n{'SAMPLE GAMES (First 5 Games)':^100}")
print("=" * 100)

# Get opponent ratings for all Michigan games
from collections import defaultdict
opp_ratings_cache = {}

# Pre-fetch all opponent ratings
for tgs in michigan_games:
    opp_tgs = tgs._get_opp_stats()
    if opp_tgs:
        opp_team = opp_tgs.team
        if opp_team.id not in opp_ratings_cache:
            try:
                opp_rating = TeamSeasonRatings.objects.get(team=opp_team, season=season)
                opp_ratings_cache[opp_team.id] = opp_rating
            except:
                pass

# Process first 5 games for detailed display
sum_weighted_efg = 0.0
sum_weights = 0.0

for idx, tgs in enumerate(michigan_games[:5], 1):
    opp_tgs = tgs._get_opp_stats()
    if not opp_tgs:
        continue
    
    opp_team = opp_tgs.team
    opp_rating = opp_ratings_cache.get(opp_team.id)
    
    if not opp_rating:
        continue
    
    # Get raw stats
    raw_efg = tgs.efg_pct
    raw_tov = tgs.tov_pct
    raw_orb = tgs.orb_pct
    raw_ftr = tgs.ftr
    
    # Site factor
    site_factor = tgs.site_factor
    site_text = "Home" if site_factor > 1.0 else ("Away" if site_factor < 1.0 else "Neutral")
    
    # Weight
    weight = tgs.poss_game
    
    # Opponent's defensive stats (what they typically allow)
    opp_def_efg = opp_rating.adj_opp_efg_pct
    opp_def_tov = opp_rating.adj_opp_tov_pct
    opp_off_orb = opp_rating.adj_orb_pct
    opp_def_ftr = opp_rating.adj_opp_ftr
    
    print(f"\nGame {idx}: vs {opp_team.name} ({site_text})")
    print("-" * 100)
    print(f"{'Stat':<15} {'Michigan Raw':<15} {'Opponent Adj':<20} {'National Avg':<15} {'Site Factor':<12} {'Adjusted':<15}")
    print("-" * 100)
    
    # eFG%
    if raw_efg and opp_def_efg > 0:
        adj_efg_g = raw_efg * (nat_avg.avg_efg / opp_def_efg) * site_factor
        print(f"{'eFG%':<15} {raw_efg:>6.2f}%{'':<8} {opp_def_efg:>6.2f}% (allow){'':<6} {nat_avg.avg_efg:>6.2f}%{'':<8} {site_factor:>6.3f}{'':<6} {adj_efg_g:>6.2f}%{'':<8}")
        print(f"{'':15} Calculation: {raw_efg:.2f} × ({nat_avg.avg_efg:.2f} / {opp_def_efg:.2f}) × {site_factor:.3f} = {adj_efg_g:.2f}%")
        sum_weighted_efg += weight * adj_efg_g
    
    # TOV%
    if raw_tov and opp_def_tov > 0:
        adj_tov_g = raw_tov * (nat_avg.avg_tov / opp_def_tov) * site_factor
        print(f"{'TOV%':<15} {raw_tov:>6.2f}%{'':<8} {opp_def_tov:>6.2f}% (force){'':<6} {nat_avg.avg_tov:>6.2f}%{'':<8} {site_factor:>6.3f}{'':<6} {adj_tov_g:>6.2f}%{'':<8}")
    
    # ORB%
    if raw_orb and opp_off_orb > 0:
        adj_orb_g = raw_orb * (nat_avg.avg_orb / opp_off_orb) * site_factor
        print(f"{'ORB%':<15} {raw_orb:>6.2f}%{'':<8} {opp_off_orb:>6.2f}% (opp off){'':<1} {nat_avg.avg_orb:>6.2f}%{'':<8} {site_factor:>6.3f}{'':<6} {adj_orb_g:>6.2f}%{'':<8}")
    
    # FTR
    if raw_ftr and opp_def_ftr > 0:
        adj_ftr_g = raw_ftr * (nat_avg.avg_ftr / opp_def_ftr) * site_factor
        print(f"{'FTR':<15} {raw_ftr:>6.2f}%{'':<8} {opp_def_ftr:>6.2f}% (allow){'':<6} {nat_avg.avg_ftr:>6.2f}%{'':<8} {site_factor:>6.3f}{'':<6} {adj_ftr_g:>6.2f}%{'':<8}")
    
    print(f"\nPossessions: {weight:.1f}")
    sum_weights += weight

print(f"\n\n{'FULL SEASON CALCULATION':^100}")
print("=" * 100)

# Calculate full season for all stats
sum_weighted_efg = 0.0
sum_weighted_tov = 0.0
sum_weighted_orb = 0.0
sum_weighted_ftr = 0.0
sum_weighted_opp_efg = 0.0
sum_weighted_opp_tov = 0.0
sum_weighted_drb = 0.0
sum_weighted_opp_ftr = 0.0
sum_weights = 0.0

for tgs in michigan_games:
    opp_tgs = tgs._get_opp_stats()
    if not opp_tgs:
        continue
    
    opp_rating = opp_ratings_cache.get(opp_tgs.team_id)
    if not opp_rating:
        continue
    
    raw_efg = tgs.efg_pct
    raw_tov = tgs.tov_pct
    raw_orb = tgs.orb_pct
    raw_ftr = tgs.ftr
    raw_opp_efg = tgs.opp_efg_pct
    raw_opp_tov = tgs.opp_tov_pct
    raw_drb = 100 - tgs.opp_orb_pct if tgs.opp_orb_pct else 0
    raw_opp_ftr = tgs.opp_ftr
    
    site_factor = tgs.site_factor
    weight = tgs.poss_game or 0
    
    if weight == 0:
        continue
    
    opp_def_efg = opp_rating.adj_opp_efg_pct
    opp_def_tov = opp_rating.adj_opp_tov_pct
    opp_off_orb = opp_rating.adj_orb_pct
    opp_def_ftr = opp_rating.adj_opp_ftr
    opp_off_efg = opp_rating.adj_efg_pct
    opp_off_tov = opp_rating.adj_tov_pct
    opp_off_ftr = opp_rating.adj_ftr
    
    # Offensive adjustments
    if raw_efg and opp_def_efg > 0:
        adj_efg_g = raw_efg * (nat_avg.avg_efg / opp_def_efg) * site_factor
        sum_weighted_efg += weight * adj_efg_g
    
    if raw_tov and opp_def_tov > 0:
        adj_tov_g = raw_tov * (nat_avg.avg_tov / opp_def_tov) * site_factor
        sum_weighted_tov += weight * adj_tov_g
    
    if raw_orb and opp_off_orb > 0:
        adj_orb_g = raw_orb * (nat_avg.avg_orb / opp_off_orb) * site_factor
        sum_weighted_orb += weight * adj_orb_g
    
    if raw_ftr and opp_def_ftr > 0:
        adj_ftr_g = raw_ftr * (nat_avg.avg_ftr / opp_def_ftr) * site_factor
        sum_weighted_ftr += weight * adj_ftr_g
    
    # Defensive adjustments
    if raw_opp_efg and opp_off_efg > 0:
        adj_opp_efg_g = raw_opp_efg * (nat_avg.avg_efg / opp_off_efg) * site_factor
        sum_weighted_opp_efg += weight * adj_opp_efg_g
    
    if raw_opp_tov and opp_off_tov > 0:
        adj_opp_tov_g = raw_opp_tov * (nat_avg.avg_tov / opp_off_tov) * site_factor
        sum_weighted_opp_tov += weight * adj_opp_tov_g
    
    if raw_drb and opp_off_orb > 0:
        adj_drb_g = raw_drb * (nat_avg.avg_orb / opp_off_orb) * site_factor
        sum_weighted_drb += weight * adj_drb_g
    
    if raw_opp_ftr and opp_off_ftr > 0:
        adj_opp_ftr_g = raw_opp_ftr * (nat_avg.avg_ftr / opp_off_ftr) * site_factor
        sum_weighted_opp_ftr += weight * adj_opp_ftr_g
    
    sum_weights += weight

# Calculate final adjusted values
calc_adj_efg = sum_weighted_efg / sum_weights if sum_weights > 0 else 0
calc_adj_tov = sum_weighted_tov / sum_weights if sum_weights > 0 else 0
calc_adj_orb = sum_weighted_orb / sum_weights if sum_weights > 0 else 0
calc_adj_ftr = sum_weighted_ftr / sum_weights if sum_weights > 0 else 0
calc_adj_opp_efg = sum_weighted_opp_efg / sum_weights if sum_weights > 0 else 0
calc_adj_opp_tov = sum_weighted_opp_tov / sum_weights if sum_weights > 0 else 0
calc_adj_drb = sum_weighted_drb / sum_weights if sum_weights > 0 else 0
calc_adj_opp_ftr = sum_weighted_opp_ftr / sum_weights if sum_weights > 0 else 0

print(f"Total Possessions: {sum_weights:.1f}")
print(f"Number of Games: {michigan_games.count()}")
print()

print(f"{'OFFENSIVE FOUR FACTORS (Adjusted)':^100}")
print("-" * 100)
print(f"{'Stat':<20} {'Calculated':<20} {'Database':<20} {'Match?':<15}")
print("-" * 100)
print(f"{'Adj eFG%':<20} {calc_adj_efg:>8.2f}%{'':<11} {michigan_ratings.adj_efg_pct:>8.2f}%{'':<11} {'✓' if abs(calc_adj_efg - michigan_ratings.adj_efg_pct) < 0.5 else '✗':<15}")
print(f"{'Adj TOV%':<20} {calc_adj_tov:>8.2f}%{'':<11} {michigan_ratings.adj_tov_pct:>8.2f}%{'':<11} {'✓' if abs(calc_adj_tov - michigan_ratings.adj_tov_pct) < 0.5 else '✗':<15}")
print(f"{'Adj ORB%':<20} {calc_adj_orb:>8.2f}%{'':<11} {michigan_ratings.adj_orb_pct:>8.2f}%{'':<11} {'✓' if abs(calc_adj_orb - michigan_ratings.adj_orb_pct) < 0.5 else '✗':<15}")
print(f"{'Adj FTR':<20} {calc_adj_ftr:>8.2f}%{'':<11} {michigan_ratings.adj_ftr:>8.2f}%{'':<11} {'✓' if abs(calc_adj_ftr - michigan_ratings.adj_ftr) < 0.5 else '✗':<15}")

print(f"\n{'DEFENSIVE FOUR FACTORS (Adjusted)':^100}")
print("-" * 100)
print(f"{'Stat':<20} {'Calculated':<20} {'Database':<20} {'Match?':<15}")
print("-" * 100)
print(f"{'Adj eFG%_d':<20} {calc_adj_opp_efg:>8.2f}%{'':<11} {michigan_ratings.adj_opp_efg_pct:>8.2f}%{'':<11} {'✓' if abs(calc_adj_opp_efg - michigan_ratings.adj_opp_efg_pct) < 0.5 else '✗':<15}")
print(f"{'Adj TOV%_d':<20} {calc_adj_opp_tov:>8.2f}%{'':<11} {michigan_ratings.adj_opp_tov_pct:>8.2f}%{'':<11} {'✓' if abs(calc_adj_opp_tov - michigan_ratings.adj_opp_tov_pct) < 0.5 else '✗':<15}")
print(f"{'Adj DRB%':<20} {calc_adj_drb:>8.2f}%{'':<11} {michigan_ratings.adj_drb_pct:>8.2f}%{'':<11} {'✓' if abs(calc_adj_drb - michigan_ratings.adj_drb_pct) < 0.5 else '✗':<15}")
calc_adj_opp_orb = 100 - calc_adj_drb
db_adj_opp_orb = michigan_ratings.adj_opp_orb_pct
print(f"{'Adj ORB%_d':<20} {calc_adj_opp_orb:>8.2f}%{'':<11} {db_adj_opp_orb:>8.2f}%{'':<11} {'✓' if abs(calc_adj_opp_orb - db_adj_opp_orb) < 0.5 else '✗':<15}")
print(f"{'Adj FTR_d':<20} {calc_adj_opp_ftr:>8.2f}%{'':<11} {michigan_ratings.adj_opp_ftr:>8.2f}%{'':<11} {'✓' if abs(calc_adj_opp_ftr - michigan_ratings.adj_opp_ftr) < 0.5 else '✗':<15}")

print(f"\n{'=' * 100}")
print(f"{'SUMMARY - MICHIGAN ADJUSTED FOUR FACTORS':^100}")
print(f"{'=' * 100}")
print(f"\nOFFENSE:")
print(f"  Adjusted eFG%:  {michigan_ratings.adj_efg_pct:.2f}%  (vs raw {michigan_metrics.efg_pct:.2f}%)")
print(f"  Adjusted TOV%:  {michigan_ratings.adj_tov_pct:.2f}%  (vs raw {michigan_metrics.tov_pct:.2f}%)")
print(f"  Adjusted ORB%:  {michigan_ratings.adj_orb_pct:.2f}%  (vs raw {michigan_metrics.orb_pct:.2f}%)")
print(f"  Adjusted FTR:   {michigan_ratings.adj_ftr:.2f}%  (vs raw {michigan_metrics.ftr:.2f}%)")
print(f"\nDEFENSE:")
print(f"  Adjusted eFG%_d: {michigan_ratings.adj_opp_efg_pct:.2f}% (vs raw {michigan_metrics.opp_efg_pct:.2f}%)")
print(f"  Adjusted TOV%_d: {michigan_ratings.adj_opp_tov_pct:.2f}% (vs raw {michigan_metrics.opp_tov_pct:.2f}%)")
print(f"  Adjusted DRB%:   {michigan_ratings.adj_drb_pct:.2f}% (vs raw {michigan_metrics.drb_pct:.2f}%)")
print(f"  Adjusted ORB%_d: {db_adj_opp_orb:.2f}% (vs raw {michigan_metrics.opp_orb_pct:.2f}%)")
print(f"  Adjusted FTR_d:  {michigan_ratings.adj_opp_ftr:.2f}% (vs raw {michigan_metrics.opp_ftr:.2f}%)")
print(f"\n{'=' * 100}")
