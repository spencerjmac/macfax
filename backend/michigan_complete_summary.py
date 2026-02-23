"""
Michigan Complete Summary - All Adjusted Metrics
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Team, TeamSeasonRatings, TeamSeasonMetrics, Game, TeamGameStats
from datetime import date

# Get Michigan
michigan = Team.objects.get(name='Michigan')
ratings = TeamSeasonRatings.objects.get(team=michigan, season__year=2026)
metrics = TeamSeasonMetrics.objects.get(team=michigan, season__year=2026)

#Schedule
all_home = list(michigan.home_games.filter(season_year=2026).order_by('game_date'))
all_away = list(michigan.away_games.filter(season_year=2026).order_by('game_date'))
all_games = sorted(all_home + all_away, key=lambda g: g.game_date)

print("=" * 120)
print("MICHIGAN 2025-26 COMPLETE SCHEDULE")
print("=" * 120)
print()

wins = 0
losses = 0

for i, game in enumerate(all_games, 1):
    mich_stats = TeamGameStats.objects.filter(game=game, team=michigan).first()
    
    if game.home_team == michigan:
        opp = game.away_team
        location = "vs"
        opp_stats = TeamGameStats.objects.filter(game=game, team=opp).first()
    else:
        opp = game.home_team
        location = "@"
        opp_stats = TeamGameStats.objects.filter(game=game, team=opp).first()
    
    if mich_stats and opp_stats:
        mich_score = mich_stats.pts
        opp_score = opp_stats.pts
        
        if mich_score > opp_score:
            result = "W"
            wins += 1
        else:
            result = "L"
            losses += 1
        
        score_display = f"{mich_score}-{opp_score}"
        print(f"{i:2}. {str(game.game_date):<12} {location} {opp.name:<30} {score_display:<10} {result}")
    else:
        print(f"{i:2}. {str(game.game_date):<12} {location} {opp.name:<30} {'(Scheduled)':<10}")

print()
print("=" * 120)
print(f"RECORD: {wins}-{losses} ({wins + losses} games played)")
print(f"National Rank: #{ratings.rank_adj_em}")
print("=" * 120)
print()

# Adjusted Metrics from TeamSeasonRatings
print("ADJUSTED EFFICIENCY METRICS (Opponent-Adjusted)")
print("=" * 120)
print(f"  Adjusted Offensive Rating (Adj O):  {ratings.adj_o:.2f}  (Rank: #{ratings.rank_adj_o})")
print(f"  Adjusted Defensive Rating (Adj D):  {ratings.adj_d:.2f}  (Rank: #{ratings.rank_adj_d})")
print(f"  Adjusted Efficiency Margin (Adj EM): {ratings.adj_em:+.2f}  (Rank: #{ratings.rank_adj_em})")
print(f"  Adjusted Tempo (Pace):                {ratings.adj_tempo:.1f}")
print()

# Raw Metrics from TeamSeasonMetrics
print("RAW EFFICIENCY METRICS (Unadjusted)")
print("=" * 120)
print(f"  Offensive Rating (ORtg):  {metrics.ortg:.1f}")
print(f"  Defensive Rating (DRtg):  {metrics.drtg:.1f}")
print(f"  Net Rating (EM):          {metrics.net_rtg:+.1f}")
print(f"  Pace:                     {metrics.pace:.1f} poss/game")
print(f"  Points Per Game:          {metrics.ppg:.1f}")
print(f"  Points Allowed Per Game:  {metrics.papg:.1f}")
print()

# Four Factor Index
print("FOUR FACTOR INDEX")
print("=" * 120)
print(f"  Raw Four Factor Index:      {ratings.ffi_raw:.1f}")
print(f"  Adjusted Four Factor Index: {ratings.ffi_adj:.1f}  (#2 in nation)")
print()

# Adjusted Four Factors
print("ADJUSTED FOUR FACTORS (Opponent-Adjusted)")
print("=" * 120)
print("  OFFENSE:")
print(f"    eFG%:  {ratings.adj_efg_pct:.1f}%")
print(f"    TOV%:  {ratings.adj_tov_pct:.1f}%")
print(f"    ORB%:  {ratings.adj_orb_pct:.1f}%")
print(f"    FTR:   {ratings.adj_ftr:.1f}")
print()
print("  DEFENSE:")
print(f"    Opp eFG%: {ratings.adj_opp_efg_pct:.1f}%")
print(f"    Opp TOV%: {ratings.adj_opp_tov_pct:.1f}%")
print(f"    Opp ORB%: {ratings.adj_opp_orb_pct:.1f}%")
print(f"    Opp FTR:  {ratings.adj_opp_ftr:.1f}")
print()
print("  MARGINS:")
print(f"    eFG Margin:  {ratings.adj_efg_margin:+.1f}%")
print(f"    TOV Edge:    {ratings.adj_tov_edge:+.1f}%")
print(f"    REB Edge:    {ratings.adj_reb_edge:+.1f}%")
print(f"    FTR Margin:  {ratings.adj_ftr_margin:+.1f}")
print()

# Raw Four Factors
print("RAW FOUR FACTORS (Unadjusted - Season Totals)")
print("=" * 120)
print("  OFFENSE:")
print(f"    eFG%:  {metrics.efg_pct:.1f}%")
print(f"    TOV%:  {metrics.tov_pct:.1f}%")
print(f"    ORB%:  {metrics.orb_pct:.1f}%")
print(f"    FTR:   {metrics.ftr:.1f}")
print()
print("  DEFENSE:")
print(f"    Opp eFG%: {metrics.opp_efg_pct:.1f}%")
print(f"    Opp TOV%: {metrics.opp_tov_pct:.1f}%")
print(f"    DRB%:     {metrics.drb_pct:.1f}%")
print(f"    Opp FTR:  {metrics.opp_ftr:.1f}")
print()

print("=" * 120)
print("ALL METRICS COMPUTED AND READY FOR WEBSITE!")
print("=" * 120)
