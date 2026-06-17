"""
NBA Crystal Ball Checklist Configuration

Thresholds derived by
backend/backtesting/management/commands/backtest_nba_checklist.py from 10
seasons (2016-2025, 300 team-seasons) of NBATeamSeasonRatings +
playoff_finish/conference_seed (from nba_sync_playoff_results) +
NBAPlayerSeasonStats.bpr (2022+ only).

Selection rule: maximize champion capture (x/10), then minimize field
pass-rate among ties. Final combined run: champion passedCount mean 9.50/10
(median 10) vs field mean 4.04/10 (median 3) across all 300 team-seasons —
clear separation.
"""

# Net Rating Top-N: net_ranks[team_id] <= N
# Backtest: N=7 captures 10/10 champions, field pass-rate 23.3%.
NET_RATING_RANK = 7

# Elite Net Rating: adj_net Z-score >= MIN_Z_NET
# Backtest: Z>=1.0 captures 9/10 champions (field pass-rate 15.3%); the lone
# miss is 2023 Denver (adj_net Z < 1.0 despite a top-7 finish) — accepted as
# an outlier, consistent with Denver's other outlier appearances below.
MIN_Z_NET = 1.0

# Top Conference Seed: conference_seed <= N
# Backtest: N=3 captures 10/10 champions, field pass-rate 20.0%.
TOP_CONFERENCE_SEED = 3

# Elite Offense: off_ranks[team_id] <= N
# Backtest: N=15 (top half of the league) is the loosest rank that captures
# 10/10 champions; field pass-rate 50.0%.
ELITE_OFFENSE_RANK = 15

# Elite Defense: def_ranks[team_id] <= N
# Backtest: N=18 (top 60% of the league) is the loosest rank that captures
# 10/10 champions; field pass-rate 60.0%.
ELITE_DEFENSE_RANK = 18

# Four Factor Index: ffi Z-score >= MIN_Z_FFI
# Backtest: Z>=0.75 captures 10/10 champions, field pass-rate 20.3%.
MIN_Z_FFI = 0.75

# eFG Margin: efg_margin Z-score >= MIN_Z_EFG
# Backtest: Z>=0.75 captures 10/10 champions, field pass-rate 23.7%.
MIN_Z_EFG = 0.75

# Turnover Edge: tov_edge Z-score >= MIN_Z_TOV
# Backtest: Z>=-0.5 (the loosest candidate swept) is the best available,
# capturing 8/10 champions at field pass-rate 69.3%. Turnover edge is a
# weaker signal for NBA champions than for NCAA; 2018 GSW and 2023 DEN are
# accepted outliers (both ran negative turnover-edge title seasons).
MIN_Z_TOV = -0.5

# No Glaring Weakness: max(factor_ranks[team_id].values()) <= N
# Backtest: N=25 is the loosest rank that comes closest to full capture
# (8/10 champions), field pass-rate 50.0%. 2018 GSW and 2025 OKC are accepted
# outliers (each had one four-factor edge ranked in the bottom 5).
NO_GLARING_WEAKNESS_RANK = 25

# Star Player Impact: best roster bpr >= MIN_STAR_BPR
# Backtest (2022-2025 only, pre-2022 exempted): BPR>=5 captures 10/10
# champions, field pass-rate 72.3% (BPR>=5 is "above-average starter" level —
# most contenders have at least one).
MIN_STAR_BPR = 5

# Player BPR data only exists 2022+; seasons before this are exempted from
# the star-player check (counted as a pass).
STAR_BPR_EXEMPT_BEFORE_YEAR = 2022
