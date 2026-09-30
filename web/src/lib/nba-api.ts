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
  TeamRosterValueResponse,
  TeamSeasonOutlookSummary,
  TeamSeasonOutlookDetail,
} from '@macfax/core/types/nba';
import type { GameDetailResponse } from '@macfax/core/types/games';

import { createApi, unwrapResults, type ApiClientConfig, type QueryParams } from '@macfax/core/api-client';
import { LOCAL_API_ORIGIN, WEB_FETCH_OPTIONS, stripTrailingSlash, webApiOrigin } from './api-env';

const SERVER_API_BASE_URL = stripTrailingSlash(webApiOrigin(LOCAL_API_ORIGIN));

const nbaClientConfig: Omit<ApiClientConfig, 'baseUrl'> = {
  fetchOptions: WEB_FETCH_OPTIONS,
  formatError: (status, body) => `NBA API request failed (${status}): ${body.slice(0, 200)}`,
  invalidJsonMessage: null,
  lenientErrorBody: true,
};

// Server: straight to Django. Browser: same-origin /nba-api proxy route
// (app/nba-api/[...path]), which re-adds the trailing slash Django expects.
const serverClient = createApi({ baseUrl: `${SERVER_API_BASE_URL}/api/nba`, ...nbaClientConfig });
const browserClient = createApi({ baseUrl: '/nba-api', stripTrailingSlash: true, ...nbaClientConfig });

function client() {
  return typeof window !== 'undefined' ? browserClient : serverClient;
}

function buildUrl(path: string, params?: QueryParams): string {
  return client().url(path, params);
}

function fetchJson<T>(url: string): Promise<T> {
  return client().getJson<T>(url);
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

  async getGameDetail(gameId: number | string): Promise<GameDetailResponse> {
    return fetchJson<GameDetailResponse>(buildUrl(`/games/${gameId}/detail/`));
  },

  /** Compare 2–4 players side-by-side for a given season. */
  async comparePlayers(ids: number[], season?: number, season_type?: string): Promise<NBAPlayerSeasonStats[]> {
    const data = await fetchJson<unknown>(buildUrl('/players/compare/', { ids: ids.join(','), season, season_type }));
    return Array.isArray(data) ? (data as NBAPlayerSeasonStats[]) : [];
  },

  /** Roster wins-added summary for a team in a given season. */
  async getTeamRosterValue(slug: string, season?: number, season_type?: string): Promise<TeamRosterValueResponse> {
    return fetchJson<TeamRosterValueResponse>(buildUrl(`/teams/${slug}/roster-value/`, { season, season_type }));
  },

  /** All 30 teams ordered by adj_net_rating — Season Outlook list. */
  async getTeamOutlooks(): Promise<TeamSeasonOutlookSummary[]> {
    return fetchJson<TeamSeasonOutlookSummary[]>(buildUrl('/outlook/'));
  },

  /** Full outlook + editorial for one team. */
  async getTeamOutlook(slug: string): Promise<TeamSeasonOutlookDetail> {
    return fetchJson<TeamSeasonOutlookDetail>(buildUrl(`/outlook/${slug}/`));
  },
};
