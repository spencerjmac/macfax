/**
 * NBA sport configuration — column definitions, labels, thresholds.
 *
 * Metric labels, glossary text, and thresholds are NBA-specific.
 * Do not copy NCAA weights or thresholds here — they are different sports.
 */

import type { Better } from '@/lib/metricMetadata';

export const NBA_SPORT_CONFIG = {
  id: 'nba' as const,
  label: 'NBA',
  shortLabel: 'NBA',
  baseRoute: '/nba',
  rankingsRoute: '/nba/rankings',
  teamRoute: (slug: string) => `/nba/team/${slug}`,
  vizRoute: '/nba/viz',
} as const;

// ─────────────────────────────────────────────────────────────────────────────
// Metric metadata for NBA rankings table
// ─────────────────────────────────────────────────────────────────────────────

export interface NBAMetricMeta {
  key: string;
  label: string;
  tooltip: string;
  format: 'number1' | 'number2' | 'percent1' | 'number1pct' | 'int';
  better: Better;
  showRank?: boolean;
  heatmap?: boolean;
}

export const NBA_METRIC_DEFINITIONS: Record<string, NBAMetricMeta> = {
  adj_off: {
    key: 'adj_off',
    label: 'Adj Off',
    tooltip: 'Opponent-adjusted offensive rating — points scored per 100 possessions vs average NBA defense.',
    format: 'number1',
    better: 'higher',
    showRank: true,
    heatmap: true,
  },
  adj_def: {
    key: 'adj_def',
    label: 'Adj Def',
    tooltip: 'Opponent-adjusted defensive rating — points allowed per 100 possessions vs average NBA offense. Lower is better.',
    format: 'number1',
    better: 'lower',
    showRank: true,
    heatmap: true,
  },
  adj_net: {
    key: 'adj_net',
    label: 'Adj Net',
    tooltip: 'Adjusted Net Rating (Adj Off − Adj Def). The primary NBA efficiency ranking metric.',
    format: 'number1',
    better: 'higher',
    showRank: true,
    heatmap: true,
  },
  pace: {
    key: 'pace',
    label: 'Pace',
    tooltip: 'Estimated possessions per 48 minutes. NBA average is approximately 99–100.',
    format: 'number1',
    better: 'neutral',
    showRank: false,
    heatmap: false,
  },
  ffi: {
    key: 'ffi',
    label: 'FFI',
    tooltip: 'Four Factor Index — weighted composite of eFG margin, TOV edge, OREB edge, and FTA margin.',
    format: 'number1',
    better: 'higher',
    showRank: true,
    heatmap: true,
  },
  efg_pct: {
    key: 'efg_pct',
    label: 'eFG%',
    tooltip: 'Effective FG% (offense). Accounts for 3-pointers being worth 1.5x a 2.',
    format: 'percent1',
    better: 'higher',
    showRank: false,
    heatmap: true,
  },
  opp_efg_pct: {
    key: 'opp_efg_pct',
    label: 'Opp eFG%',
    tooltip: 'Opponent effective FG% allowed (defense). Lower is better.',
    format: 'percent1',
    better: 'lower',
    showRank: false,
    heatmap: true,
  },
  efg_margin: {
    key: 'efg_margin',
    label: 'eFG Margin',
    tooltip: 'eFG% (offense) minus opponent eFG% (defense). Shooting efficiency advantage.',
    format: 'percent1',
    better: 'higher',
    showRank: true,
    heatmap: true,
  },
  tov_rate: {
    key: 'tov_rate',
    label: 'TOV%',
    tooltip: 'Team turnover rate — turnovers per possession.',
    format: 'percent1',
    better: 'lower',
    showRank: false,
    heatmap: true,
  },
  opp_tov_rate: {
    key: 'opp_tov_rate',
    label: 'Opp TOV%',
    tooltip: 'Opponent turnover rate forced by defense.',
    format: 'percent1',
    better: 'higher',
    showRank: false,
    heatmap: true,
  },
  tov_edge: {
    key: 'tov_edge',
    label: 'TOV Edge',
    tooltip: 'Opponent turnover rate minus team turnover rate. Positive = you force more turnovers than you commit.',
    format: 'percent1',
    better: 'higher',
    showRank: true,
    heatmap: true,
  },
  oreb_pct: {
    key: 'oreb_pct',
    label: 'OREB%',
    tooltip: 'Offensive rebound percentage.',
    format: 'percent1',
    better: 'higher',
    showRank: false,
    heatmap: true,
  },
  opp_oreb_pct: {
    key: 'opp_oreb_pct',
    label: 'Opp OREB%',
    tooltip: 'Opponent offensive rebound percentage allowed.',
    format: 'percent1',
    better: 'lower',
    showRank: false,
    heatmap: true,
  },
  oreb_edge: {
    key: 'oreb_edge',
    label: 'OREB Edge',
    tooltip: 'Team OREB% minus opponent OREB%. Rebounding advantage on the offensive glass.',
    format: 'percent1',
    better: 'higher',
    showRank: true,
    heatmap: true,
  },
  fta_rate: {
    key: 'fta_rate',
    label: 'FTA/FGA',
    tooltip: 'Team free throw attempt rate (FTA/FGA).',
    format: 'number2',
    better: 'higher',
    showRank: false,
    heatmap: true,
  },
  opp_fta_rate: {
    key: 'opp_fta_rate',
    label: 'Opp FTA/FGA',
    tooltip: 'Opponent free throw attempt rate allowed.',
    format: 'number2',
    better: 'lower',
    showRank: false,
    heatmap: true,
  },
  fta_margin: {
    key: 'fta_margin',
    label: 'FTA Margin',
    tooltip: 'FTA/FGA rate (offense) minus opponent FTA/FGA rate. Getting to the line advantage.',
    format: 'number2',
    better: 'higher',
    showRank: true,
    heatmap: true,
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Team profile tab structure for NBA
// (Tabs without data in Phase 1/2 show a placeholder)
// ─────────────────────────────────────────────────────────────────────────────

export interface NBATabConfig {
  id: string;
  label: string;
  phase: number;    // phase when this tab becomes live
}

export const NBA_TEAM_TABS: NBATabConfig[] = [
  { id: 'overview',     label: 'Overview',     phase: 2 },
  { id: 'ratings',      label: 'Ratings',      phase: 2 },
  { id: 'four-factors', label: 'Four Factors', phase: 2 },
  { id: 'game-log',     label: 'Game Log',     phase: 2 },
  { id: 'players',      label: 'Players',      phase: 4 },
  { id: 'lineups',      label: 'Lineups',      phase: 4 },
  { id: 'injuries',     label: 'Injuries',     phase: 4 },
];
