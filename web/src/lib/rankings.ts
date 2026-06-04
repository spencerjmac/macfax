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

  // Dynamically calculate thresholds using standard deviations
  // Z-scores based on historical champion minimums
  const minZEFGMargin = 1.39; // 1.3936
  const minZTOVEdge = -0.10; // -0.1009
  const minZRebEdge = 0.15; // 0.1491
  const minZFTRMargin = -0.47; // -0.4703
  const minZFFI = 1.64; // 1.6378
  
  let efgMean = 0, efgStd = 1, tovMean = 0, tovStd = 1;
  let rebMean = 0, rebStd = 1, ftrMean = 0, ftrStd = 1;
  let ffiMean = 0, ffiStd = 1;

  if (allTeams && allTeams.length > 0) {
      const calcMean = (arr: number[]) => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;
      const calcStd = (arr: number[], mean: number) => arr.length ? Math.sqrt(arr.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / arr.length) : 1;

      const efgArr = allTeams.filter(t => t.eFG_margin != null).map(t => t.eFG_margin!);
      const tovArr = allTeams.filter(t => t.tov_edge != null).map(t => t.tov_edge!);
      const rebArr = allTeams.filter(t => t.reb_edge != null).map(t => t.reb_edge!);
      const ftrArr = allTeams.filter(t => t.ftr_margin != null).map(t => t.ftr_margin!);
      const ffiArr = allTeams.filter(t => t.four_factor_index_100 != null).map(t => t.four_factor_index_100!);

      efgMean = calcMean(efgArr); efgStd = calcStd(efgArr, efgMean);
      tovMean = calcMean(tovArr); tovStd = calcStd(tovArr, tovMean);
      rebMean = calcMean(rebArr); rebStd = calcStd(rebArr, rebMean);
      ftrMean = calcMean(ftrArr); ftrStd = calcStd(ftrArr, ftrMean);
      ffiMean = calcMean(ffiArr); ffiStd = calcStd(ffiArr, ffiMean);
  }

  const threshEFG = efgMean + (minZEFGMargin * efgStd);
  const threshTOV = tovMean + (minZTOVEdge * tovStd);
  const threshReb = rebMean + (minZRebEdge * rebStd);
  const threshFTR = ftrMean + (minZFTRMargin * ftrStd);
  const threshFFI = ffiMean + (minZFFI * ffiStd);

  // 9) Four Factor Index dynamically derived
  const goodFFI = team.four_factor_index_100 != null ? team.four_factor_index_100 >= threshFFI : false;

  // 10) eFG Margin dynamically derived
  const goodEFGMargin = (team.eFG_margin ?? 0) >= threshEFG;

  // 11) TOV Edge dynamically derived
  const goodTOVEdge = (team.tov_edge ?? 0) >= threshTOV;

  // 12) REB Edge dynamically derived
  const goodRebEdge = (team.reb_edge ?? 0) >= threshReb;

  // 13) FTR Margin dynamically derived
  const goodFTRMargin = (team.ftr_margin ?? 0) >= threshFTR;

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
      key: 'four_factor_index',
      label: 'Four Factor Index',
      passed: goodFFI,
      valueDisplay: team.four_factor_index_100 != null ? team.four_factor_index_100.toFixed(1) : 'N/A',
      thresholdDisplay: `≥ ${threshFFI.toFixed(1)}`,
    },
    {
      key: 'efg_margin',
      label: 'eFG Margin',
      passed: goodEFGMargin,
      valueDisplay: team.eFG_margin != null ? `${(team.eFG_margin * 100).toFixed(1)}%` : 'N/A',
      thresholdDisplay: `≥ ${(threshEFG * 100).toFixed(1)}%`,
    },
    {
      key: 'tov_edge',
      label: 'Turnover Edge',
      passed: goodTOVEdge,
      valueDisplay: team.tov_edge != null ? `${(team.tov_edge * 100).toFixed(1)}%` : 'N/A',
      thresholdDisplay: `≥ ${(threshTOV * 100).toFixed(1)}%`,
    },
    {
      key: 'reb_edge',
      label: 'Rebounding Edge',
      passed: goodRebEdge,
      valueDisplay: team.reb_edge != null ? `${(team.reb_edge * 100).toFixed(1)}%` : 'N/A',
      thresholdDisplay: `≥ ${(threshReb * 100).toFixed(1)}%`,
    },
    {
      key: 'ftr_margin',
      label: 'FTR Margin',
      passed: goodFTRMargin,
      valueDisplay: team.ftr_margin != null ? team.ftr_margin.toFixed(2) : 'N/A',
      thresholdDisplay: `≥ ${threshFTR.toFixed(2)}`,
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

// ---------------------------------------------------------------------------
// Cinderella Index  (mirrors backend cinderella_views.py logic)
// ---------------------------------------------------------------------------

export interface CinderellaIndexResult {
  profileScore: number;
  underseededStrength: number;
  defenseScore: number;
  possessionScore: number;
  varianceScore: number;
  resumeScore: number;
  seedResidual: number | null;
  components: {
    adj_em_pct: number;
    adj_d_pct: number;
    opp_efg_pct: number;
    opp_tov_pct: number;
    tov_avoid_pct: number;
    orb_pct: number;
    fg3_rate_pct: number;
    fg3_pct_pct: number;
    slow_tempo_pct: number;
    wab_pct: number;
    sos_pct: number;
  };
}

/** Fraction of values in arr that are <= val (higher-is-better percentile). */
function pctHigher(val: number, arr: number[]): number {
  if (arr.length === 0) return 0.5;
  return arr.filter((v) => v <= val).length / arr.length;
}

/** Fraction of values in arr that are >= val (lower-is-better percentile). */
function pctLower(val: number, arr: number[]): number {
  if (arr.length === 0) return 0.5;
  return arr.filter((v) => v >= val).length / arr.length;
}

/**
 * Compute the Cinderella Index for a single team relative to all D1 teams.
 * Values in TeamSeason are already /100 (e.g. tov = 0.156 for 15.6%) — the
 * percentile comparison is still valid since all teams use the same scale.
 */
export function buildCinderellaIndex(
  teams: TeamSeason[],
  team: TeamSeason,
): CinderellaIndexResult {
  // Build per-metric arrays
  const allAdjEM      = teams.map((t) => t.adjEM);
  const allAdjD       = teams.map((t) => t.adjD);
  const allOppEFG     = teams.map((t) => t.eFG_d ?? 0);
  const allOppTOV     = teams.map((t) => t.tov_d ?? 0);
  const allTOV        = teams.map((t) => t.tov ?? 0);
  const allORB        = teams.map((t) => t.orb ?? 0);
  const allFG3Rate    = teams.filter((t) => t.fg3_rate != null).map((t) => t.fg3_rate as number);
  const allFG3Pct     = teams.filter((t) => t.fg3_pct != null).map((t) => t.fg3_pct as number);
  const allTempo      = teams.map((t) => t.adjTempo);
  const allWAB        = teams.filter((t) => t.wab != null).map((t) => t.wab as number);
  const allSOS        = teams.filter((t) => t.sos_win_pct != null).map((t) => t.sos_win_pct as number);

  // AdjEM rank within D1 for expected seed
  const sortedByEM = [...teams].sort((a, b) => b.adjEM - a.adjEM);
  const adjEmRank = sortedByEM.findIndex((t) => t.teamId === team.teamId) + 1;

  // Seed residuals across all seeded teams
  const seededTeams = teams.filter((t) => t.tournament_seed != null);
  const allSeedResiduals = seededTeams.map((t) => {
    const expectedSeed = Math.min(16, Math.max(1, Math.ceil(
      (sortedByEM.findIndex((s) => s.teamId === t.teamId) + 1) / 4,
    )));
    return (t.tournament_seed as number) - expectedSeed;
  });

  // ── Underseeded Strength ───────────────────────────────────────────────
  const adjEmPct = pctHigher(team.adjEM, allAdjEM);

  let seedResidual: number | null = null;
  let underseeded = adjEmPct;

  if (team.tournament_seed != null && allSeedResiduals.length > 0) {
    const expectedSeed = Math.min(16, Math.max(1, Math.ceil(adjEmRank / 4)));
    seedResidual = team.tournament_seed - expectedSeed;
    const seedResPct = pctHigher(seedResidual, allSeedResiduals);
    underseeded = 0.70 * adjEmPct + 0.30 * seedResPct;
  }

  // ── Defense ───────────────────────────────────────────────────────────
  const adjDPct   = pctLower(team.adjD,       allAdjD);
  const oppEFGPct = pctLower(team.eFG_d ?? 0, allOppEFG);
  const oppTOVPct = pctHigher(team.tov_d ?? 0, allOppTOV);
  const defense   = 0.50 * adjDPct + 0.30 * oppEFGPct + 0.20 * oppTOVPct;

  // ── Possession ────────────────────────────────────────────────────────
  const tovAvoidPct = pctLower(team.tov ?? 0, allTOV);
  const orbPct      = pctHigher(team.orb ?? 0, allORB);
  const possession  = 0.40 * tovAvoidPct + 0.35 * oppTOVPct + 0.25 * orbPct;

  // ── Variance ──────────────────────────────────────────────────────────
  const fg3RateP   = team.fg3_rate != null && allFG3Rate.length > 0 ? pctHigher(team.fg3_rate, allFG3Rate) : 0.5;
  const fg3PctP    = team.fg3_pct  != null && allFG3Pct.length  > 0 ? pctHigher(team.fg3_pct,  allFG3Pct)  : 0.5;
  const slowTempoP = pctLower(team.adjTempo, allTempo);
  const variance   = 0.45 * fg3RateP + 0.25 * fg3PctP + 0.30 * slowTempoP;

  // ── Resume ────────────────────────────────────────────────────────────
  const wabP   = team.wab         != null && allWAB.length > 0 ? pctHigher(team.wab,         allWAB) : 0.5;
  const sosP   = team.sos_win_pct != null && allSOS.length > 0 ? pctLower(team.sos_win_pct,  allSOS) : 0.5;
  const resume = 0.60 * wabP + 0.40 * sosP;

  // ── Combined ──────────────────────────────────────────────────────────
  const profile = 0.28 * underseeded + 0.27 * defense + 0.21 * possession + 0.14 * variance + 0.10 * resume;

  const r = (v: number) => Math.round(v * 1000) / 10; // → one decimal place

  return {
    profileScore:        r(profile),
    underseededStrength: r(underseeded),
    defenseScore:        r(defense),
    possessionScore:     r(possession),
    varianceScore:       r(variance),
    resumeScore:         r(resume),
    seedResidual,
    components: {
      adj_em_pct:      r(adjEmPct),
      adj_d_pct:       r(adjDPct),
      opp_efg_pct:     r(oppEFGPct),
      opp_tov_pct:     r(oppTOVPct),
      tov_avoid_pct:   r(tovAvoidPct),
      orb_pct:         r(orbPct),
      fg3_rate_pct:    r(fg3RateP),
      fg3_pct_pct:     r(fg3PctP),
      slow_tempo_pct:  r(slowTempoP),
      wab_pct:         r(wabP),
      sos_pct:         r(sosP),
    },
  };
}
