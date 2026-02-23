import json

# Load the teams data
with open('../web/public/data/teams.json', 'r') as f:
    data = json.load(f)

# Find Michigan
michigan = [t for t in data['teams'] if t['teamName'] == 'Michigan'][0]

print("=" * 60)
print("MICHIGAN - RAW FOUR FACTORS (from games)")
print("=" * 60)
print(f"eFG%:     {michigan['raw_eFG']:.4f} ({michigan['raw_eFG']*100:.2f}%)")
print(f"TOV%:     {michigan['raw_tov']:.4f} ({michigan['raw_tov']*100:.2f}%)")
print(f"ORB%:     {michigan['raw_orb']:.4f} ({michigan['raw_orb']*100:.2f}%)")
print(f"FTR:      {michigan['raw_ftr']:.4f} ({michigan['raw_ftr']*100:.2f}%)")
print()
print(f"eFG%_d:   {michigan['raw_eFG_d']:.4f} ({michigan['raw_eFG_d']*100:.2f}%)")
print(f"TOV%_d:   {michigan['raw_tov_d']:.4f} ({michigan['raw_tov_d']*100:.2f}%)")
print(f"DRB%:     {michigan['raw_drb']:.4f} ({michigan['raw_drb']*100:.2f}%)")
print(f"ORB%_d:   {(1-michigan['raw_drb']):.4f} ({(1-michigan['raw_drb'])*100:.2f}%)")
print(f"FTR_d:    {michigan['raw_ftr_d']:.4f} ({michigan['raw_ftr_d']*100:.2f}%)")
print()
print(f"Raw Four Factor Index: {michigan['raw_four_factor_index_100']}")
print()

print("=" * 60)
print("MICHIGAN - ADJUSTED FOUR FACTORS (opponent-adjusted)")
print("=" * 60)
print(f"eFG%:     {michigan['eFG']:.4f} ({michigan['eFG']*100:.2f}%)")
print(f"TOV%:     {michigan['tov']:.4f} ({michigan['tov']*100:.2f}%)")
print(f"ORB%:     {michigan['orb']:.4f} ({michigan['orb']*100:.2f}%)")
print(f"FTR:      {michigan['ftr']:.4f} ({michigan['ftr']*100:.2f}%)")
print()
print(f"eFG%_d:   {michigan['eFG_d']:.4f} ({michigan['eFG_d']*100:.2f}%)")
print(f"TOV%_d:   {michigan['tov_d']:.4f} ({michigan['tov_d']*100:.2f}%)")
print(f"DRB%:     {michigan['drb']:.4f} ({michigan['drb']*100:.2f}%)")
print(f"ORB%_d:   {(1-michigan['drb']):.4f} ({(1-michigan['drb'])*100:.2f}%)")
print(f"FTR_d:    {michigan['ftr_d']:.4f} ({michigan['ftr_d']*100:.2f}%)")
print()
print(f"Adjusted Four Factor Index: {michigan['four_factor_index_100']}")
