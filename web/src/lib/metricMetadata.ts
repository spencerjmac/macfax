export type Better = 'higher' | 'lower' | 'neutral';

export type MetricFormat = 'number1' | 'number2' | 'percent1' | 'int';

export interface MetricMeta {
  key: string;
  label: string;
  tooltip: string;
  format: MetricFormat;
  better: Better;
  showRank?: boolean;
  heatmap?: boolean;
}

const BASE_METRICS: MetricMeta[] = [
  { key: 'adjEM', label: 'Adj EM', tooltip: 'Adjusted Efficiency Margin (Adj O - Adj D).', format: 'number1', better: 'higher', showRank: true, heatmap: true },
  { key: 'adjO', label: 'Adj O', tooltip: 'Adjusted Offensive Efficiency.', format: 'number1', better: 'higher', showRank: true, heatmap: true },
  { key: 'adjD', label: 'Adj D', tooltip: 'Adjusted Defensive Efficiency.', format: 'number1', better: 'lower', showRank: true, heatmap: true },
  { key: 'adjTempo', label: 'Adj T', tooltip: 'Adjusted Tempo (possessions per 40).', format: 'number1', better: 'neutral', showRank: false, heatmap: false },
  { key: 'four_factor_index_100', label: 'FFI', tooltip: 'Four Factor Index (adjusted).', format: 'number1', better: 'higher', showRank: true, heatmap: true },

  { key: 'raw_eFG', label: 'Raw eFG%', tooltip: 'Raw effective FG% (offense).', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'raw_eFG_d', label: 'Raw eFG% D', tooltip: 'Raw effective FG% allowed.', format: 'percent1', better: 'lower', showRank: true, heatmap: true },
  { key: 'raw_eFG_margin', label: 'Raw eFG Margin', tooltip: 'Raw eFG% offense minus defense.', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'raw_tov', label: 'Raw TOV%', tooltip: 'Raw turnover rate (offense).', format: 'percent1', better: 'lower', showRank: true, heatmap: true },
  { key: 'raw_tov_d', label: 'Raw TOV% D', tooltip: 'Raw opponent turnover rate.', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'raw_tov_edge', label: 'Raw TOV Edge', tooltip: 'Raw TOV% edge (opponent - team).', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'raw_orb', label: 'Raw ORB%', tooltip: 'Raw offensive rebound rate.', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'raw_drb', label: 'Raw DRB%', tooltip: 'Raw defensive rebound rate.', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'raw_reb_edge', label: 'Raw REB Edge', tooltip: 'Raw rebound edge (ORB% - opp ORB%).', format: 'percent1', better: 'higher', showRank: true, heatmap: true },
  { key: 'raw_ftr', label: 'Raw FTR', tooltip: 'Raw free throw rate (offense).', format: 'number2', better: 'higher', showRank: true, heatmap: true },
  { key: 'raw_ftr_d', label: 'Raw FTR D', tooltip: 'Raw free throw rate allowed.', format: 'number2', better: 'lower', showRank: true, heatmap: true },
  { key: 'raw_ftr_margin', label: 'Raw FTR Margin', tooltip: 'Raw FTR margin (team - opponent).', format: 'number2', better: 'higher', showRank: true, heatmap: true },
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
  { key: 'ftr', label: 'Adj FTR', tooltip: 'Adjusted free throw rate (offense).', format: 'number2', better: 'higher', showRank: true, heatmap: true },
  { key: 'ftr_d', label: 'Adj FTR D', tooltip: 'Adjusted free throw rate allowed.', format: 'number2', better: 'lower', showRank: true, heatmap: true },
  { key: 'ftr_margin', label: 'Adj FTR Margin', tooltip: 'Adjusted FTR margin (team - opponent).', format: 'number2', better: 'higher', showRank: true, heatmap: true },
];

export const METRIC_DEFINITIONS: Record<string, MetricMeta> = Object.fromEntries(
  BASE_METRICS.map((meta) => [meta.key, meta])
);
