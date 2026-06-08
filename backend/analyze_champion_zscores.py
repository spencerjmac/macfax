import os
import django
import numpy as np

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from ncaa.models import TeamSeasonRatings

def analyze_champs():
    champs = TeamSeasonRatings.all_objects.filter(tournament_finish='Champ', is_pre_tournament=True).order_by('season__year')
    
    if not champs.exists():
        print("No pre-tournament champions found. Ensure backfill_pre_tournament is done.")
        return

    min_z = {
        'adj_efg_margin': float('inf'),
        'adj_tov_edge': float('inf'),
        'adj_reb_edge': float('inf'),
        'adj_ftr_margin': float('inf'),
        'ffi_adj': float('inf')
    }
    
    for champ in champs:
        if champ.season.year in [2011, 2014]:
            continue
        year = champ.season.year
        
        # Get all D1 teams for this season
        all_teams = TeamSeasonRatings.all_objects.filter(season=champ.season, team__is_d1=True, is_pre_tournament=True)
        
        metrics = {
            'adj_efg_margin': [],
            'adj_tov_edge': [],
            'adj_reb_edge': [],
            'adj_ftr_margin': [],
            'ffi_adj': []
        }
        
        for t in all_teams:
            if t.adj_efg_margin is not None: metrics['adj_efg_margin'].append(t.adj_efg_margin)
            if t.adj_tov_edge is not None: metrics['adj_tov_edge'].append(t.adj_tov_edge)
            if t.adj_reb_edge is not None: metrics['adj_reb_edge'].append(t.adj_reb_edge)
            if t.adj_ftr_margin is not None: metrics['adj_ftr_margin'].append(t.adj_ftr_margin)
            if t.ffi_adj is not None: metrics['ffi_adj'].append(t.ffi_adj)
            
        print(f"\n--- {year} Champion: {champ.team.name} ---")
        for key in min_z.keys():
            arr = np.array(metrics[key])
            if len(arr) == 0:
                continue
                
            mean = np.mean(arr)
            std = np.std(arr)
            val = getattr(champ, key)
            
            if val is not None:
                z = (val - mean) / std
                print(f"  {key}: val={val:.2f}, mean={mean:.2f}, std={std:.2f} -> Z={z:.3f}")
                if z < min_z[key]:
                    min_z[key] = z
                    
    print("\n" + "="*50)
    print("MINIMUM Z-SCORES ACROSS ALL CHAMPIONS")
    print("="*50)
    for k, v in min_z.items():
        print(f"{k}: {v:.4f}")
        
if __name__ == "__main__":
    analyze_champs()
