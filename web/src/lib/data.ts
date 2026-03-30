import type { TeamsData, TeamSeason, DatasetMetadata, SeasonInfo } from '@/types';
import { buildTeamRanks, buildChampionChecklist, buildCinderellaIndex } from './rankings';

const API_RANKINGS_PATH = '/api/rankings/';
const API_SEASONS_PATH = '/api/seasons/'

/** Map API ranking row (snake_case) to frontend TeamSeason */
function mapApiRowToTeamSeason(team: Record<string, unknown>): TeamSeason {
  const record = (team.record as string) || '0-0';
  const [wins, losses] = record.split('-').map(Number);
  const games = (wins || 0) + (losses || 0);
  const pct = (v: unknown): number | null =>
    v != null && typeof v === 'number' ? v / 100 : null;
  const num = (v: unknown): number | null =>
    v != null && typeof v === 'number' ? v : null;
  return {
    teamId: (team.team_slug as string) || '',
    teamName: (team.team_name as string) || '',
    teamNameAlt: [(team.team_name as string) || ''],
    conference: (team.conference as string) || 'Ind',
    logoUrl: (team.team_logo as string) || '/logos/default.png',
    season: (team.season_display as string) || '',
    lastUpdated: new Date().toISOString().slice(0, 10),
    games,
    record,
    rank: (team.rank as number) ?? 0,
    adjEM: (team.adj_em as number) ?? 0,
    adjO: (team.adj_o as number) ?? 0,
    adjD: (team.adj_d as number) ?? 0,
    adjTempo: (team.adj_tempo as number) ?? 0,
    eFG: pct(team.efg_pct) ?? 0,
    tov: pct(team.tov_pct) ?? 0,
    orb: pct(team.orb_pct) ?? 0,
    ftr: pct(team.ftr) ?? 0,
    eFG_d: pct(team.efg_pct_d) ?? 0,
    tov_d: pct(team.tov_pct_d) ?? 0,
    drb: team.orb_pct_d != null ? (100 - Number(team.orb_pct_d)) / 100 : 0,
    ftr_d: pct(team.ftr_d) ?? 0,
    eFG_margin: pct(team.efg_margin) ?? 0,
    tov_edge: pct(team.tov_edge) ?? 0,
    reb_edge: pct(team.reb_edge) ?? 0,
    ftr_margin: num(team.ftr_margin) ?? 0,
    raw_eFG: pct(team.raw_efg_pct),
    raw_tov: pct(team.raw_tov_pct),
    raw_orb: pct(team.raw_orb_pct),
    raw_ftr: pct(team.raw_ftr),
    raw_eFG_d: pct(team.raw_efg_pct_d),
    raw_tov_d: pct(team.raw_tov_pct_d),
    raw_orb_d: pct(team.raw_orb_pct_d),
    raw_drb: team.raw_orb_pct_d != null ? (100 - Number(team.raw_orb_pct_d)) / 100 : null,
    raw_ftr_d: pct(team.raw_ftr_d),
    raw_eFG_margin: pct(team.raw_efg_margin),
    raw_tov_edge: pct(team.raw_tov_edge),
    raw_reb_edge: pct(team.raw_reb_edge),
    raw_ftr_margin: num(team.raw_ftr_margin),
    four_factor_index_100: num(team.four_factor_index_100),
    raw_four_factor_index_100: num(team.raw_four_factor_index_100),
    rank_four_factor_index_100: num(team.rank_four_factor_index_100),
    fg2_pct: pct(team.fg2_pct),
    fg2_pct_d: pct(team.fg2_pct_d),
    fg3_pct: pct(team.fg3_pct),
    fg3_pct_d: pct(team.fg3_pct_d),
    fg3_rate: pct(team.fg3_rate),
    fg3_rate_d: pct(team.fg3_rate_d),
    ft_pct: pct(team.ft_pct),
    wab: num(team.wab),
    sor_rank: num(team.sor_rank),
    net_rank: num(team.net_rank),
    sos_rank: num(team.sos_rank),
    sos_win_pct: num(team.sos_win_pct),
    ap_poll_week6: (team.ap_poll_week6 as number) ?? null,
    tournament_seed: (team.tournament_seed as number) ?? null,
    tournament_region: (team.tournament_region as string) ?? null,
    sor: null,
    luck: null,
    sos_adjEM: null,
    ncsos_adjEM: null,
    barthag: null,
    sources: { kenpom: false, torvik: false, cbbAnalytics: false },
  };
}

/** Fetch rankings from backend API */
async function fetchRankingsFromApi(season?: number): Promise<TeamsData> {
  // Server-side: prefer the internal Docker URL (never exposed to browsers).
  // Client-side: falls back to the public URL baked in at build time.
  const base = process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
  const params = season ? `?season=${season}` : '';
  const url = `${base}${API_RANKINGS_PATH}${params}`;

  const res = await fetch(url, { cache: 'no-store' });

  if (!res.ok) {
    console.error('[fetchRankingsFromApi] Fetch failed:', res.status, res.statusText);
    return {
      metadata: {
        lastUpdated: new Date().toISOString(),
        season: 'N/A',
        teamCount: 0,
        sources: { kenpom: 0, torvik: 0, cbbAnalytics: 0 },
      },
      teams: [],
    };
  }
  const json = (await res.json()) as { results?: Record<string, unknown>[]; count?: number };
  const results = json.results ?? [];
  const teams = results.map(r => mapApiRowToTeamSeason(r));

  // Derive season display from the first result, or fall back to a computed value
  const seasonDisplay = teams[0]?.season || (season ? `${season - 1}-${String(season).slice(2)}` : 'N/A');

  return {
    metadata: {
      lastUpdated: new Date().toISOString(),
      season: seasonDisplay,
      teamCount: teams.length,
      sources: { kenpom: 0, torvik: 0, cbbAnalytics: 0 },
    },
    teams,
  };
}

/** Fetch the list of seasons that have computed ratings */
async function fetchSeasonsFromApi(): Promise<SeasonInfo[]> {
  const base = process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
  const url = `${base}${API_SEASONS_PATH}?has_ratings=true`;
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) return [];
  const json = (await res.json()) as SeasonInfo[] | { results?: SeasonInfo[] };
  return Array.isArray(json) ? json : (json.results ?? []);
}

const emptyMetadata: DatasetMetadata = {
  lastUpdated: new Date().toISOString(),
  season: 'N/A',
  teamCount: 0,
  sources: { kenpom: 0, torvik: 0, cbbAnalytics: 0 },
};

/** During Next.js production build (e.g. Docker) no backend is running; avoid fetch. */
const isBuildPhase = () => process.env.NEXT_PHASE === 'phase-production-build';

export async function getAllSeasons(): Promise<SeasonInfo[]> {
  if (isBuildPhase()) return [];
  return fetchSeasonsFromApi();
}

export async function getAllTeams(season?: number): Promise<TeamSeason[]> {
  if (isBuildPhase()) return [];
  const apiData = await fetchRankingsFromApi(season);
  return apiData.teams;
}

export async function getMetadata(season?: number): Promise<DatasetMetadata> {
  if (isBuildPhase()) return emptyMetadata;
  const apiData = await fetchRankingsFromApi(season);
  return apiData.metadata;
}

export async function getTeamWithContext(slug: string): Promise<
  | {
      team: TeamSeason;
      ranks: ReturnType<typeof buildTeamRanks>;
      checklist: ReturnType<typeof buildChampionChecklist>;
      cinderella: ReturnType<typeof buildCinderellaIndex>;
    }
  | null
> {
  if (isBuildPhase()) return null;
  const apiData = await fetchRankingsFromApi();
  const teams = apiData.teams;
  const team = teams.find((t) => t.teamId === slug || t.teamName?.toLowerCase() === slug.toLowerCase());
  if (!team) return null;

  const ranks = buildTeamRanks(teams, team);
  const checklist = buildChampionChecklist(team, ranks, teams);
  const cinderella = buildCinderellaIndex(teams, team);

  return { team, ranks, checklist, cinderella };
}
