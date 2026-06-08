from ncaa.models import TeamSeasonRatings
from ncaa.management.commands.backfill_tournament import TOURNAMENT_RESULTS

print("--- Pre-Tournament Win Percentages of Champions ---")

min_pct_all = 1.0
min_pct_uconn = 1.0

for year, data in TOURNAMENT_RESULTS.items():
    champ_list = data.get("Champ")
    if not champ_list:
        continue
    champ_name = champ_list[0]
    
    if champ_name == "UConn":
        champ_name = "Connecticut"

    # Get pre-tournament ratings
    try:
        ratings = TeamSeasonRatings.all_objects.filter(
            season__year=year,
            team__name=champ_name,
            is_pre_tournament=True
        ).first()
        if not ratings:
            print(f"Skipping {year} {champ_name} (no pre-tourney rating)")
            continue
    except Exception as e:
        print(f"Error fetching {year} {champ_name}: {e}")
        continue
    
    games = ratings.games_played
    wins = ratings.wins
    pct = wins / games if games else 0.0
    
    print(f"{year} {champ_name}: {wins}-{games-wins} ({pct*100:.1f}%)")
    
    min_pct_all = min(min_pct_all, pct)
    
    if year not in [2011, 2014]:
        min_pct_uconn = min(min_pct_uconn, pct)

print("\n--- Minimum Thresholds ---")
print(f"All Champions: > {min_pct_all*100:.2f}%")
print(f"UConn Rule (Excluding '11 & '14): > {min_pct_uconn*100:.2f}%")
