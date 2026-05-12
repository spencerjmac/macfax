/**
 * NBA API client functions — macfax NBA app
 *
 * Mirrors the structure of lib/api.ts but scoped to /api/nba/* endpoints.
 */

import type {
  NBASeasonInfo,
  NBATeam,
  NBATeamSeasonRatings,
  NBAGame,
  NBATeamDetailResponse,
  NBAHealthData,
  NBAMatchupResult,
  NBAModelCalibration,
  NBAPlayerSeasonStats,
} from '@/types/nba';

const API_BASE_URL = (process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const NBA_API_ROOT = `${API_BASE_URL}/api/nba`;

type QueryParams = Record<string, string | number | boolean | undefined | null>;

function buildUrl(path: string, params?: QueryParams): string {
  const url = new URL(`${NBA_API_ROOT}${path.startsWith('/') ? '' : '/'}${path}`);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null || value === '') return;
      url.searchParams.set(key, String(value));
    });
  }
  return url.toString();
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`NBA API request failed (${res.status}): ${text.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

function unwrapResults<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[];
  if (data && typeof data === 'object' && Array.isArray((data as { results?: unknown }).results)) {
    return (data as { results: T[] }).results;
  }
  return [];
}

export const nbaApi = {
  async getSeasons(): Promise<NBASeasonInfo[]> {
    const data = await fetchJson<unknown>(buildUrl('/seasons/'));
    return unwrapResults<NBASeasonInfo>(data);
  },

  async getTeams(conference?: 'East' | 'West'): Promise<NBATeam[]> {
    const data = await fetchJson<unknown>(buildUrl('/teams/', { conference }));
    return unwrapResults<NBATeam>(data);
  },

  async getRankings(season?: number, seasonType?: string): Promise<NBATeamSeasonRatings[]> {
    const data = await fetchJson<unknown>(buildUrl('/rankings/', { season, season_type: seasonType }));
    return unwrapResults<NBATeamSeasonRatings>(data);
  },

  async getGames(params: {
    season?: number;
    team?: string;
    season_type?: string;
  }): Promise<NBAGame[]> {
    const data = await fetchJson<unknown>(buildUrl('/games/', params));
    return unwrapResults<NBAGame>(data);
  },

  async getTeamDetail(slug: string, season?: number): Promise<NBATeamDetailResponse> {
    return fetchJson<NBATeamDetailResponse>(buildUrl(`/team/${slug}/`, { season }));
  },

  async getHealth(): Promise<NBAHealthData> {
    return fetchJson<NBAHealthData>(buildUrl('/health/'));
  },

  async getModelCalibration(season?: number): Promise<NBAModelCalibration> {
    return fetchJson<NBAModelCalibration>(buildUrl('/model-calibration/', { season }));
  },

  async getTeamRoster(slug: string, season?: number): Promise<NBAPlayerSeasonStats[]> {
    return fetchJson<NBAPlayerSeasonStats[]>(buildUrl(`/team/${slug}/players/`, { season }));
  },

  async getMatchup(
    teamA: string,
    teamB: string,
    site: 'neutral' | 'home' | 'away',
    season?: number,
    mode?: 'game' | 'series',
  ): Promise<NBAMatchupResult> {
    return fetchJson<NBAMatchupResult>(buildUrl('/matchup/', { teamA, teamB, site, season, mode }));
  },

  async getLeaguePlayers(params?: {
    season?: number;
    ordering?: string;
    min_gp?: number;
    season_type?: string;
  }): Promise<NBAPlayerSeasonStats[]> {
    const data = await fetchJson<unknown>(buildUrl('/players/', params));
    return Array.isArray(data) ? (data as NBAPlayerSeasonStats[]) : [];
  },
};
