import type { TeamSeason } from '../types';

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

/** Which rating rows the Crystal Ball checklist was scored on. */
export type ChecklistBasis = 'selection_sunday' | 'live';

export function checklistBasisLabel(basis: ChecklistBasis): string {
  return basis === 'selection_sunday' ? 'Selection Sunday profile' : 'Current profile';
}

/** One team's Crystal Ball checklist, as the team page shows it. */
export interface TeamChecklist {
  passedCount: number;
  total: number;
  items: ChecklistItem[];
  basis: ChecklistBasis;
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
