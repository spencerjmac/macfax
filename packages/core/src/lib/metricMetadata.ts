export type Better = 'higher' | 'lower' | 'neutral';

// 'number1pct' — formats as X.X% without multiplying by 100 (value already in pct-point form)
// 'signed1' — X.X with an explicit sign (+1.8 / -0.6)
export type MetricFormat = 'number1' | 'number2' | 'percent1' | 'number1pct' | 'int' | 'signed1';

export interface MetricMeta {
  key: string;
  label: string;
  tooltip: string;
  format: MetricFormat;
  better: Better;
  showRank?: boolean;
  heatmap?: boolean;
  /** First click sorts high to low; defaults to better === 'higher' */
  sortDescFirst?: boolean;
}

const BASE_METRICS: MetricMeta[] = [
  { key: 'adjEM', label: 'Adj EM', tooltip: 'Adjusted Efficiency Margin (Adj O - Adj D).', format: 'number1', better: 'higher', showRank: true, heatmap: true },
  { key: 'adjO', label: 'Adj O', tooltip: 'Adjusted Offensive Efficiency.', format: 'number1', better: 'higher', showRank: true, heatmap: true },
  { key: 'adjD', label: 'Adj D', tooltip: 'Adjusted Defensive Efficiency.', format: 'number1', better: 'lower', showRank: true, heatmap: true },
  { key: 'adjTempo', label: 'Adj T', tooltip: 'Adjusted Tempo (possessions per 40).', format: 'number1', better: 'neutral', showRank: false, heatmap: false },
  { key: 'four_factor_index_100', label: 'FFI', tooltip: 'Four Factor Index (adjusted).', format: 'number1', better: 'higher', showRank: true, heatmap: true },
  { key: 'sos_rank', label: 'SOS', tooltip: 'Strength of schedule rank (1 = hardest): expected win% for an average D1 team vs this schedule.', format: 'int', better: 'lower', showRank: false, heatmap: true },
  { key: 'luck_wins', label: 'Luck', tooltip: 'Games won above what our ratings expect vs this schedule; tends not to repeat.', format: 'signed1', better: 'neutral', showRank: false, heatmap: false, sortDescFirst: true },
  { key: 'wab', label: 'WAB', tooltip: 'Wins Above Bubble: wins beyond what a bubble-level team would expect against this schedule.', format: 'number1', better: 'higher', showRank: true, heatmap: true },

  { key: 'raw_eFG', label: 'Raw eFG%', tooltip: 'Raw effective FG% (offense).', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'raw_eFG_d', label: 'Raw eFG% D', tooltip: 'Raw effective FG% allowed.', format: 'percent1', better: 'lower', showRank: true, heatmap: true },
  { key: 'raw_eFG_margin', label: 'Raw eFG Margin', tooltip: 'Raw eFG% offense minus defense.', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'raw_tov', label: 'Raw TOV%', tooltip: 'Raw turnover rate (offense).', format: 'percent1', better: 'lower', showRank: true, heatmap: true },
  { key: 'raw_tov_d', label: 'Raw TOV% D', tooltip: 'Raw opponent turnover rate.', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'raw_tov_edge', label: 'Raw TOV Edge', tooltip: 'Raw TOV% edge (opponent - team).', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'raw_orb', label: 'Raw ORB%', tooltip: 'Raw offensive rebound rate.', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'raw_drb', label: 'Raw DRB%', tooltip: 'Raw defensive rebound rate.', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'raw_reb_edge', label: 'Raw REB Edge', tooltip: 'Raw rebound edge (ORB% - opp ORB%).', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'raw_ftr', label: 'Raw FTR', tooltip: 'Raw free throw rate (offense).', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'raw_ftr_d', label: 'Raw FTR D', tooltip: 'Raw free throw rate allowed.', format: 'percent1', better: 'lower', showRank: true, heatmap: true },
  { key: 'raw_ftr_margin', label: 'Raw FTR Margin', tooltip: 'Raw FTR margin (team - opponent).', format: 'number1pct', better: 'higher', showRank: true, heatmap: true },
  { key: 'raw_four_factor_index_100', label: 'Raw FFI', tooltip: 'Raw Four Factor Index.', format: 'number1', better: 'higher', showRank: true, heatmap: true },

  { key: 'eFG', label: 'Adj eFG%', tooltip: 'Adjusted effective FG% (offense).', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'eFG_d', label: 'Adj eFG% D', tooltip: 'Adjusted effective FG% allowed.', format: 'percent1', better: 'lower', showRank: true, heatmap: true },
  { key: 'eFG_margin', label: 'Adj eFG Margin', tooltip: 'Adjusted eFG% offense minus defense.', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'tov', label: 'Adj TOV%', tooltip: 'Adjusted turnover rate (offense).', format: 'percent1', better: 'lower', showRank: true, heatmap: true },
  { key: 'tov_d', label: 'Adj TOV% D', tooltip: 'Adjusted opponent turnover rate.', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'tov_edge', label: 'Adj TOV Edge', tooltip: 'Adjusted TOV% edge (opponent - team).', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'orb', label: 'Adj ORB%', tooltip: 'Adjusted offensive rebound rate.', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'drb', label: 'Adj DRB%', tooltip: 'Adjusted defensive rebound rate.', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'reb_edge', label: 'Adj REB Edge', tooltip: 'Adjusted rebound edge (ORB% - opp ORB%).', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'ftr', label: 'Adj FTR', tooltip: 'Adjusted free throw rate (offense).', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'ftr_d', label: 'Adj FTR D', tooltip: 'Adjusted free throw rate allowed.', format: 'percent1', better: 'lower', showRank: true, heatmap: true },
  { key: 'ftr_margin', label: 'Adj FTR Margin', tooltip: 'Adjusted FTR margin (team - opponent).', format: 'number1pct', better: 'higher', showRank: true, heatmap: true },

  // Traditional per-game stats
  { key: 'd1_games_played', label: 'GP', tooltip: 'D1 games', format: 'int', better: 'neutral', showRank: false, heatmap: false },
  { key: 'ppg', label: 'PTS', tooltip: 'Points per game.', format: 'number1', better: 'higher', showRank: true, heatmap: true },
  { key: 'papg', label: 'OPP PTS', tooltip: 'Opponent points per game.', format: 'number1', better: 'lower', showRank: true, heatmap: true },
  { key: 'fg_pct', label: 'FG%', tooltip: 'Field goal percentage.', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'fg2_pct', label: '2P%', tooltip: 'Two-point field goal percentage.', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'fg3_pct', label: '3P%', tooltip: 'Three-point field goal percentage.', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'ft_pct', label: 'FT%', tooltip: 'Free throw percentage.', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'orpg', label: 'OREB', tooltip: 'Offensive rebounds per game.', format: 'number1', better: 'higher', showRank: true, heatmap: true },
  { key: 'drpg', label: 'DREB', tooltip: 'Defensive rebounds per game.', format: 'number1', better: 'higher', showRank: true, heatmap: true },
  { key: 'rpg', label: 'REB', tooltip: 'Total rebounds per game.', format: 'number1', better: 'higher', showRank: true, heatmap: true },
  { key: 'apg', label: 'AST', tooltip: 'Assists per game.', format: 'number1', better: 'higher', showRank: true, heatmap: true },
  { key: 'spg', label: 'STL', tooltip: 'Steals per game.', format: 'number1', better: 'higher', showRank: true, heatmap: true },
  { key: 'bpg', label: 'BLK', tooltip: 'Blocks per game.', format: 'number1', better: 'higher', showRank: true, heatmap: true },
  { key: 'topg', label: 'TOV', tooltip: 'Turnovers per game.', format: 'number1', better: 'lower', showRank: true, heatmap: true },
  { key: 'pfpg', label: 'PF', tooltip: 'Personal fouls committed per game.', format: 'number1', better: 'lower', showRank: true, heatmap: true },
  { key: 'pfdpg', label: 'PFD', tooltip: 'Personal fouls drawn per game (opponent fouls).', format: 'number1', better: 'higher', showRank: true, heatmap: true },
];

export const METRIC_DEFINITIONS: Record<string, MetricMeta> = Object.fromEntries(
  BASE_METRICS.map((meta) => [meta.key, meta])
);
