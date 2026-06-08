from ncaa.models import TeamSeasonRatings, TeamSeasonMetrics
from ncaa.management.commands.backfill_tournament import TOURNAMENT_RESULTS

print("--- Pre-Tournament Criteria Metrics of Champions ---")

min_adjem = 100.0
max_adjo_rank = 0
max_adjd_rank = 0
min_adjo = 150.0
max_adjd = 0.0
min_wab = 20.0
min_3p = 100.0
min_ft = 100.0

for year, data in TOURNAMENT_RESULTS.items():
    champ_list = data.get("Champ")
    if not champ_list:
        continue
    champ_name = champ_list[0]
    if champ_name == "UConn":
        champ_name = "Connecticut"

    try:
        ratings = TeamSeasonRatings.all_objects.filter(
            season__year=year,
            team__name=champ_name,
            is_pre_tournament=True
        ).first()
        metrics = TeamSeasonMetrics.all_objects.filter(
            season__year=year,
            team__name=champ_name,
            is_pre_tournament=True
        ).first()
        
        if not ratings or not metrics:
            print(f"Skipping {year} {champ_name} (missing data)")
            continue
    except Exception as e:
        print(f"Error fetching {year} {champ_name}: {e}")
        continue
        
    adjem = ratings.adj_em
    adjo = ratings.adj_o
    adjd = ratings.adj_d
    
    # Calculate Ranks
    all_o = list(TeamSeasonRatings.all_objects.filter(season__year=year, is_pre_tournament=True).order_by('-adj_o'))
    adjo_rank = next((i+1 for i, r in enumerate(all_o) if r.team.name == champ_name), 0)
    
    all_d = list(TeamSeasonRatings.all_objects.filter(season__year=year, is_pre_tournament=True).order_by('adj_d'))
    adjd_rank = next((i+1 for i, r in enumerate(all_d) if r.team.name == champ_name), 0)
    
    wab = ratings.wab or 0.0
    fg3_pct = (metrics.total_fg3m / metrics.total_fg3a) * 100 if metrics.total_fg3a > 0 else 0.0
    ft_pct = (metrics.total_ftm / metrics.total_fta) * 100 if metrics.total_fta > 0 else 0.0
    
    print(f"{year} {champ_name}:")
    print(f"  AdjEM: {adjem:.1f}")
    print(f"  AdjO: {adjo:.1f} (Rank {adjo_rank}) | AdjD: {adjd:.1f} (Rank {adjd_rank})")
    print(f"  WAB: {wab:.1f}")
    print(f"  3P%: {fg3_pct:.1f}% | FT%: {ft_pct:.1f}%")
    
    if year not in [2011, 2014]:
        min_adjem = min(min_adjem, adjem)
        min_adjo = min(min_adjo, adjo)
        max_adjd = max(max_adjd, adjd)
        if adjo_rank > 0: max_adjo_rank = max(max_adjo_rank, adjo_rank)
        if adjd_rank > 0: max_adjd_rank = max(max_adjd_rank, adjd_rank)
        if wab != 0.0: min_wab = min(min_wab, wab)
        min_3p = min(min_3p, fg3_pct)
        min_ft = min(min_ft, ft_pct)

print("\n--- Minimum/Maximum Thresholds (Excluding '11 & '14 UConn) ---")
print(f"Lowest AdjEM: {min_adjem:.2f}")
print(f"Lowest AdjO: {min_adjo:.2f}")
print(f"Highest AdjD: {max_adjd:.2f}")
print(f"Worst AdjO Rank: {max_adjo_rank}")
print(f"Worst AdjD Rank: {max_adjd_rank}")
print(f"Lowest WAB: {min_wab:.2f}")
print(f"Lowest 3P%: {min_3p:.2f}%")
print(f"Lowest FT%: {min_ft:.2f}%")
