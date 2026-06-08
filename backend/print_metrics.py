import sys
sys.path.append('.')
from ncaa.models import TeamSeasonRatings
from ncaa.management.commands.backfill_tournament import TOURNAMENT_RESULTS

for year, data in TOURNAMENT_RESULTS.items():
    champ_list = data.get("Champ")
    if not champ_list: continue
    champ_name = champ_list[0]
    if champ_name == "UConn": champ_name = "Connecticut"

    try:
        ratings = TeamSeasonRatings.all_objects.filter(season__year=year, team__name=champ_name, is_pre_tournament=True).first()
        if ratings:
            print(f"{year} {champ_name}: AdjO: {ratings.adj_o:.1f}, AdjD: {ratings.adj_d:.1f}, AdjEM: {ratings.adj_em:.1f}")
    except Exception as e:
        pass
