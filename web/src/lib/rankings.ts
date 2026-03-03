import type { TeamSeason } from '@/types';

export interface TeamRanks {
  adjEM: number | null;
  adjO: number | null;
  adjD: number | null;
  adjT: number | null;
  fourFactorIndex: number | null;
  eFG: number | null;
  eFG_d: number | null;
  eFG_margin: number | null;
  tov: number | null;
  tov_d: number | null;
  tov_edge: number | null;
  orb: number | null;
  drb: number | null;
  reb_edge: number | null;
  ftr: number | null;
  ftr_d: number | null;
  ftr_margin: number | null;
  fg2_pct: number | null;
  fg2_pct_d: number | null;
  fg3_pct: number | null;
  fg3_pct_d: number | null;
  fg3_rate: number | null;
  fg3_rate_d: number | null;
  wab: number | null;
}

export interface ChecklistItem {
  key: string;
  label: string;
  passed: boolean;
  valueDisplay: string;
  thresholdDisplay: string;
  detail?: string;
}

function rankByMetric(teams: TeamSeason[], metric: keyof TeamSeason, better: 'higher' | 'lower'): Map<string, number> {
  const entries = teams
    .map((team) => ({ teamId: team.teamId, value: team[metric] as unknown as number | null }))
    .filter((entry) => typeof entry.value === 'number' && !Number.isNaN(entry.value));

  const sorted = entries.sort((a, b) => {
    if (better === 'lower') return (a.value as number) - (b.value as number);
    return (b.value as number) - (a.value as number);
  });

  const map = new Map<string, number>();
  sorted.forEach((entry, idx) => {
    map.set(entry.teamId, idx + 1);
  });

  return map;
}

export function buildTeamRanks(teams: TeamSeason[], team: TeamSeason): TeamRanks {
  const adjEM = rankByMetric(teams, 'adjEM', 'higher').get(team.teamId) ?? null;
  const adjO = rankByMetric(teams, 'adjO', 'higher').get(team.teamId) ?? null;
  const adjD = rankByMetric(teams, 'adjD', 'lower').get(team.teamId) ?? null;
  const adjT = rankByMetric(teams, 'adjTempo', 'higher').get(team.teamId) ?? null;
  const fourFactorIndex = rankByMetric(teams, 'four_factor_index_100', 'higher').get(team.teamId) ?? null;

  const eFG = rankByMetric(teams, 'eFG', 'higher').get(team.teamId) ?? null;
  const eFG_d = rankByMetric(teams, 'eFG_d', 'lower').get(team.teamId) ?? null;
  const eFG_margin = rankByMetric(teams, 'eFG_margin', 'higher').get(team.teamId) ?? null;
  const tov = rankByMetric(teams, 'tov', 'lower').get(team.teamId) ?? null;
  const tov_d = rankByMetric(teams, 'tov_d', 'higher').get(team.teamId) ?? null;
  const tov_edge = rankByMetric(teams, 'tov_edge', 'higher').get(team.teamId) ?? null;
  const orb = rankByMetric(teams, 'orb', 'higher').get(team.teamId) ?? null;
  const drb = rankByMetric(teams, 'drb', 'higher').get(team.teamId) ?? null;
  const reb_edge = rankByMetric(teams, 'reb_edge', 'higher').get(team.teamId) ?? null;
  const ftr = rankByMetric(teams, 'ftr', 'higher').get(team.teamId) ?? null;
  const ftr_d = rankByMetric(teams, 'ftr_d', 'lower').get(team.teamId) ?? null;
  const ftr_margin = rankByMetric(teams, 'ftr_margin', 'higher').get(team.teamId) ?? null;
  const fg2_pct = rankByMetric(teams, 'fg2_pct', 'higher').get(team.teamId) ?? null;
  const fg2_pct_d = rankByMetric(teams, 'fg2_pct_d', 'lower').get(team.teamId) ?? null;
  const fg3_pct = rankByMetric(teams, 'fg3_pct', 'higher').get(team.teamId) ?? null;
  const fg3_pct_d = rankByMetric(teams, 'fg3_pct_d', 'lower').get(team.teamId) ?? null;
  const fg3_rate = rankByMetric(teams, 'fg3_rate', 'higher').get(team.teamId) ?? null;
  const fg3_rate_d = rankByMetric(teams, 'fg3_rate_d', 'lower').get(team.teamId) ?? null;
  const wab = rankByMetric(teams, 'wab', 'higher').get(team.teamId) ?? null;

  return {
    adjEM,
    adjO,
    adjD,
    adjT,
    fourFactorIndex,
    eFG,
    eFG_d,
    eFG_margin,
    tov,
    tov_d,
    tov_edge,
    orb,
    drb,
    reb_edge,
    ftr,
    ftr_d,
    ftr_margin,
    fg2_pct,
    fg2_pct_d,
    fg3_pct,
    fg3_pct_d,
    fg3_rate,
    fg3_rate_d,
    wab,
  };
}

function formatRank(rank: number | null): string {
  return rank == null ? 'N/A' : `#${rank}`;
}

export function buildChampionChecklist(team: TeamSeason, ranks: TeamRanks) {
  const items: ChecklistItem[] = [
    {
      key: 'adj_em_top_25',
      label: 'Top 25 Adj EM',
      passed: ranks.adjEM != null ? ranks.adjEM <= 25 : false,
      valueDisplay: formatRank(ranks.adjEM),
      thresholdDisplay: '#25',
    },
    {
      key: 'adj_o_top_40',
      label: 'Top 40 Adj O',
      passed: ranks.adjO != null ? ranks.adjO <= 40 : false,
      valueDisplay: formatRank(ranks.adjO),
      thresholdDisplay: '#40',
    },
    {
      key: 'adj_d_top_40',
      label: 'Top 40 Adj D',
      passed: ranks.adjD != null ? ranks.adjD <= 40 : false,
      valueDisplay: formatRank(ranks.adjD),
      thresholdDisplay: '#40',
    },
    {
      key: 'ffi_top_30',
      label: 'Top 30 FFI',
      passed: ranks.fourFactorIndex != null ? ranks.fourFactorIndex <= 30 : false,
      valueDisplay: formatRank(ranks.fourFactorIndex),
      thresholdDisplay: '#30',
    },
    {
      key: 'efg_margin_positive',
      label: 'Positive eFG Margin',
      passed: (team.eFG_margin ?? 0) > 0,
      valueDisplay: team.eFG_margin == null ? 'N/A' : `${(team.eFG_margin * 100).toFixed(1)}%`,
      thresholdDisplay: '> 0%',
    },
    {
      key: 'tov_edge_positive',
      label: 'Positive TOV Edge',
      passed: (team.tov_edge ?? 0) > 0,
      valueDisplay: team.tov_edge == null ? 'N/A' : `${(team.tov_edge * 100).toFixed(1)}%`,
      thresholdDisplay: '> 0%',
    },
    {
      key: 'reb_edge_positive',
      label: 'Positive REB Edge',
      passed: (team.reb_edge ?? 0) > 0,
      valueDisplay: team.reb_edge == null ? 'N/A' : `${(team.reb_edge * 100).toFixed(1)}%`,
      thresholdDisplay: '> 0%',
    },
    {
      key: 'ftr_margin_positive',
      label: 'Positive FTR Margin',
      passed: (team.ftr_margin ?? 0) > 0,
      valueDisplay: team.ftr_margin == null ? 'N/A' : `${team.ftr_margin.toFixed(2)}`,
      thresholdDisplay: '> 0.00',
    },
    {
      key: 'top_100_tempo',
      label: 'Top 100 Tempo',
      passed: ranks.adjT != null ? ranks.adjT <= 100 : false,
      valueDisplay: formatRank(ranks.adjT),
      thresholdDisplay: '#100',
    },
    {
      key: 'top_50_efg',
      label: 'Top 50 eFG%',
      passed: ranks.eFG != null ? ranks.eFG <= 50 : false,
      valueDisplay: formatRank(ranks.eFG),
      thresholdDisplay: '#50',
    },
    {
      key: 'top_50_tov',
      label: 'Top 50 TOV%',
      passed: ranks.tov != null ? ranks.tov <= 50 : false,
      valueDisplay: formatRank(ranks.tov),
      thresholdDisplay: '#50',
    },
    {
      key: 'top_50_orb',
      label: 'Top 50 ORB%',
      passed: ranks.orb != null ? ranks.orb <= 50 : false,
      valueDisplay: formatRank(ranks.orb),
      thresholdDisplay: '#50',
    },
    {
      key: 'top_50_drb',
      label: 'Top 50 DRB%',
      passed: ranks.drb != null ? ranks.drb <= 50 : false,
      valueDisplay: formatRank(ranks.drb),
      thresholdDisplay: '#50',
    },
    {
      key: 'top_50_ftr',
      label: 'Top 50 FTR',
      passed: ranks.ftr != null ? ranks.ftr <= 50 : false,
      valueDisplay: formatRank(ranks.ftr),
      thresholdDisplay: '#50',
    },
    {
      key: 'top_50_efg_d',
      label: 'Top 50 Opp eFG%',
      passed: ranks.eFG_d != null ? ranks.eFG_d <= 50 : false,
      valueDisplay: formatRank(ranks.eFG_d),
      thresholdDisplay: '#50',
    },
  ];

  return {
    passedCount: items.filter((item) => item.passed).length,
    total: items.length,
    items,
  };
}
