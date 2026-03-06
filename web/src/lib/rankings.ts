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

// ---- Trapezoid of Excellence (ported from trapezoid_views.py) ----
const Q_BOT_EM = 0.965;
const Y_PAD_MIN = 0.50;
const Y_PAD_RATE = 0.02;
const Q_X_LEFT_BOT = 0.25;
const Q_X_RIGHT_BOT = 0.75;
const PACE_PAD = 0.25;

function quantile(sorted: number[], q: number): number {
  const idx = q * (sorted.length - 1);
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
}

function computeTrapezoidBoundaries(tempos: number[], ems: number[]) {
  const emSorted = [...ems].sort((a, b) => a - b);
  const yBot = quantile(emSorted, Q_BOT_EM);
  const yMax = Math.max(...ems);
  const yRange = yMax - yBot;
  const yPad = Math.max(Y_PAD_MIN, Y_PAD_RATE * yRange);
  const yTop = yMax + yPad;

  let eliteTempos = tempos.filter((_, i) => ems[i] >= yBot);
  if (eliteTempos.length < 10) eliteTempos = tempos;

  const eliteSorted = [...eliteTempos].sort((a, b) => a - b);
  let xLeftTop = Math.min(...eliteTempos) - PACE_PAD;
  let xRightTop = Math.max(...eliteTempos) + PACE_PAD;
  let xLeftBot = quantile(eliteSorted, Q_X_LEFT_BOT);
  let xRightBot = quantile(eliteSorted, Q_X_RIGHT_BOT);

  if (!(xLeftTop < xLeftBot && xLeftBot < xRightBot && xRightBot < xRightTop)) {
    const allSorted = [...tempos].sort((a, b) => a - b);
    xLeftTop = Math.min(...tempos) - PACE_PAD;
    xRightTop = Math.max(...tempos) + PACE_PAD;
    xLeftBot = quantile(allSorted, Q_X_LEFT_BOT);
    xRightBot = quantile(allSorted, Q_X_RIGHT_BOT);
  }

  return { xLeftTop, xRightTop, xLeftBot, xRightBot, yTop, yBot };
}

function isInsideTrapezoid(
  x: number, y: number,
  t: ReturnType<typeof computeTrapezoidBoundaries>
): boolean {
  if (x < t.xLeftTop || x > t.xRightTop) return false;
  if (y > t.yTop) return false;

  let yMin: number;
  if (x <= t.xLeftBot) {
    if (t.xLeftBot === t.xLeftTop) { yMin = t.yBot; }
    else {
      const slope = (t.yBot - t.yTop) / (t.xLeftBot - t.xLeftTop);
      yMin = t.yTop + slope * (x - t.xLeftTop);
    }
  } else if (x < t.xRightBot) {
    yMin = t.yBot;
  } else {
    if (t.xRightTop === t.xRightBot) { yMin = t.yBot; }
    else {
      const slope = (t.yTop - t.yBot) / (t.xRightTop - t.xRightBot);
      yMin = t.yBot + slope * (x - t.xRightBot);
    }
  }
  return y >= yMin;
}
// ---- End Trapezoid helpers ----

export function buildChampionChecklist(team: TeamSeason, ranks: TeamRanks, allTeams?: TeamSeason[]) {
  // Season context from all teams (for Title Favorite and Trapezoid)
  const allEMs = allTeams ? allTeams.map((t) => t.adjEM) : [team.adjEM];
  const allTempos = allTeams ? allTeams.map((t) => t.adjTempo) : [team.adjTempo];
  const maxAdjEM = Math.max(...allEMs);

  // 1) Trapezoid of Excellence — real geometry from compute_trapezoid_boundaries
  const trapezoid = computeTrapezoidBoundaries(allTempos, allEMs);
  const inTrapezoid = isInsideTrapezoid(team.adjTempo, team.adjEM, trapezoid);

  // 2) KenPom Contender: (AdjO > 113.8 AND AdjD < 95.0) OR AdjEM > 30.0
  const kenpomContender = (team.adjO > 113.8 && team.adjD < 95.0) || team.adjEM > 30.0;

  // 3) Title Favorite: within 6.0 points of max AdjEM
  const titleFavoriteThreshold = maxAdjEM - 6.0;
  const titleFavorite = team.adjEM >= titleFavoriteThreshold;

  // 4) Win% > 74%
  const [winsStr, lossesStr] = team.record.split('-');
  const wins = parseInt(winsStr, 10) || 0;
  const losses = parseInt(lossesStr, 10) || 0;
  const totalGames = wins + losses || 1;
  const winPct = wins / totalGames;
  const goodWinPct = winPct > 0.74;

  // 5) Elite Off/Def Ranks: AdjO rank ≤ 21 AND AdjD rank ≤ 37
  const eliteRanks = (ranks.adjO != null ? ranks.adjO <= 21 : false) &&
                     (ranks.adjD != null ? ranks.adjD <= 37 : false);

  // 6) 3P% > 32% (stored as decimal, e.g. 0.348)
  const goodThreePct = team.fg3_pct != null ? team.fg3_pct > 0.32 : false;

  // 7) T-Rank ≤ 17 — not in rankings data
  // 8) AP Poll Week 6 ≤ 12
  const apPollWeek6 = team.ap_poll_week6 ?? null;
  const goodAPPoll = apPollWeek6 != null ? apPollWeek6 <= 12 : false;

  // 9) eFG Margin ≥ 6% (stored as decimal after /100, e.g. 0.1751 = 17.51%)
  const goodEFGMargin = (team.eFG_margin ?? 0) >= 0.06;

  // 10) FTR Margin ≥ -5.5 (stored as raw ratio, e.g. 17.54)
  const goodFTRMargin = (team.ftr_margin ?? 0) >= -5.5;

  // 11) Rebounding Edge ≥ 0 (stored as decimal)
  const goodRebEdge = (team.reb_edge ?? 0) >= 0;

  // 12) Turnover Edge ≥ 1.5% (stored as decimal, e.g. 0.0371 = 3.71%)
  const goodTOVEdge = (team.tov_edge ?? 0) >= 0.015;

  // 13) Four Factor Index > 80
  const goodFFI = team.four_factor_index_100 != null ? team.four_factor_index_100 > 80 : false;

  // 14) WAB > 5
  const goodWAB = team.wab != null ? team.wab > 5 : false;

  // 15) FT% > 70% (stored as decimal)
  const goodFTPct = team.ft_pct != null ? team.ft_pct > 0.70 : false;

  const items: ChecklistItem[] = [
    {
      key: 'trapezoid',
      label: 'Trapezoid of Excellence',
      passed: inTrapezoid,
      valueDisplay: inTrapezoid ? 'Inside' : 'Outside',
      thresholdDisplay: 'Inside trapezoid',
    },
    {
      key: 'kenpom_contender',
      label: 'KenPom Contender',
      passed: kenpomContender,
      valueDisplay: `O: ${team.adjO.toFixed(1)}, D: ${team.adjD.toFixed(1)}`,
      thresholdDisplay: '(O > 113.8 & D < 95) or EM > 30',
    },
    {
      key: 'title_favorite',
      label: 'Title Favorite (AdjEM)',
      passed: titleFavorite,
      valueDisplay: team.adjEM.toFixed(1),
      thresholdDisplay: `≥ ${titleFavoriteThreshold.toFixed(1)}`,
    },
    {
      key: 'win_pct',
      label: 'Win Percentage',
      passed: goodWinPct,
      valueDisplay: `${(winPct * 100).toFixed(1)}%`,
      thresholdDisplay: '> 74%',
    },
    {
      key: 'elite_ranks',
      label: 'Elite Off/Def Ranks',
      passed: eliteRanks,
      valueDisplay: `Off: ${formatRank(ranks.adjO)}, Def: ${formatRank(ranks.adjD)}`,
      thresholdDisplay: 'Off ≤ 21, Def ≤ 37',
    },
    {
      key: 'three_point_pct',
      label: '3-Point %',
      passed: goodThreePct,
      valueDisplay: team.fg3_pct != null ? `${(team.fg3_pct * 100).toFixed(1)}%` : 'N/A',
      thresholdDisplay: '> 32%',
    },
    {
      key: 'adj_em_rank_17',
      label: 'AdjEM Rank',
      passed: ranks.adjEM != null ? ranks.adjEM <= 17 : false,
      valueDisplay: formatRank(ranks.adjEM),
      thresholdDisplay: '≤ #17',
    },
    {
      key: 'ap_poll_week6',
      label: 'AP Poll Week 6',
      passed: goodAPPoll,
      valueDisplay: apPollWeek6 != null ? `#${apPollWeek6}` : 'N/A',
      thresholdDisplay: '≤ 12',
    },
    {
      key: 'efg_margin',
      label: 'eFG Margin',
      passed: goodEFGMargin,
      valueDisplay: `${((team.eFG_margin ?? 0) * 100).toFixed(1)}%`,
      thresholdDisplay: '≥ 6%',
    },
    {
      key: 'ftr_margin',
      label: 'FTR Margin',
      passed: goodFTRMargin,
      valueDisplay: (team.ftr_margin ?? 0).toFixed(2),
      thresholdDisplay: '≥ -5.50',
    },
    {
      key: 'rebounding_edge',
      label: 'Rebounding Edge',
      passed: goodRebEdge,
      valueDisplay: `${((team.reb_edge ?? 0) * 100).toFixed(1)}%`,
      thresholdDisplay: '≥ 0%',
    },
    {
      key: 'turnover_edge',
      label: 'Turnover Edge',
      passed: goodTOVEdge,
      valueDisplay: `${((team.tov_edge ?? 0) * 100).toFixed(1)}%`,
      thresholdDisplay: '≥ 1.5%',
    },
    {
      key: 'four_factor_index',
      label: 'Four Factor Index',
      passed: goodFFI,
      valueDisplay: team.four_factor_index_100 != null ? team.four_factor_index_100.toFixed(1) : 'N/A',
      thresholdDisplay: '> 80',
    },
    {
      key: 'wab',
      label: 'WAB (Wins Above Bubble)',
      passed: goodWAB,
      valueDisplay: team.wab != null ? team.wab.toFixed(1) : 'N/A',
      thresholdDisplay: '> 5',
    },
    {
      key: 'ft_pct',
      label: 'Free Throw %',
      passed: goodFTPct,
      valueDisplay: team.ft_pct != null ? `${(team.ft_pct * 100).toFixed(1)}%` : 'N/A',
      thresholdDisplay: '> 70%',
    },
  ];

  return {
    passedCount: items.filter((item) => item.passed).length,
    total: items.length,
    items,
  };
}
