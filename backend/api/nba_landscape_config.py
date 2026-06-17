"""
NBA Efficiency Landscape Configuration

Tier-line thresholds backtested in
backend/backtesting/management/commands/backtest_nba_landscape.py against 10
seasons (2016-2025, 300 team-seasons) of NBATeamSeasonRatings +
playoff_finish (from nba_sync_playoff_results).

NATIONAL BASELINE APPROACH: tier lines are computed from ALL 30 teams in the
current season snapshot (rank-based on adj_net), not from a filtered subset,
so the lines stay stable when conference filters are applied.
"""

# Champion line = adj_net of the Nth-ranked team by adj_net. Rank-based
# (not gap-from-max) so the line stays stable regardless of how dominant the
# top team is — mirrors NCAA's "Title Favorite" line, which moved from
# gap-based to rank-based for the same reason.
# Backtest: N=6 captures 9/10 champions 2016-2025; the lone miss is 2023
# Denver (rank 7, adj_net +0.38) — accepted as an outlier, same as NCAA's
# "UConn rule" exceptions below the trapezoid.
CHAMPION_RANK = 6

# Contender line = adj_net of the 10th-ranked team. Captures 16/20 (80%) of
# champion+runner-up team-seasons 2016-2025; the 4 misses (2018 CLE, 2023
# MIA, 2024 DAL, 2025 IND) were Cinderella playoff runs that outperformed
# their regular-season efficiency.
CONTENDER_RANK = 10

# Playoff line = break-even adj_net. Backtest: 95% of adj_net<0 teams missed
# the playoffs or lost in Round 1; 91% of adj_net>=0 teams made the playoffs.
PLAYOFF_NET = 0.0
