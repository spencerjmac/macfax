import type {
  Team,
  MatchupResult,
  Conference,
  SeasonInfo,
  TrapezoidData,
  EfficiencyLandscapeData,
  CrystalBallData,
  CinderellaData,
  BracketData,
  VizStats,
  VizScatterData,
  NCAAPlayerSeasonStats,
} from '@/types';
import type { NBALandscapeData, NBACrystalBallData, NBALuckChartData } from '@/types/nba';
import type { GameDetailResponse } from '@/types/games';
import type {
  RosterOutlookData,
  ScenarioRequest,
  ScenarioProjectionResult,
  OutlookPlayer,
  PlayerSearchResult,
  PlaceholderListResponse,
} from '@/types/outlook';
import type {
  ValidationSummaryResponse,
  ValidationWeeklyResponse,
  ValidationRecentGamesResponse,
} from '@/types/validation';

import {
  createApi,
  defaultErrorFormatter,
  unwrapResults,
  type QueryParams,
} from './api-client';
import { LOCAL_API_ORIGIN, WEB_FETCH_OPTIONS, stripTrailingSlash, webApiOrigin } from './api-env';

const API_BASE_URL = stripTrailingSlash(webApiOrigin(LOCAL_API_ORIGIN));
const client = createApi({ baseUrl: `${API_BASE_URL}/api`, fetchOptions: WEB_FETCH_OPTIONS });

function buildUrl(path: string, params?: QueryParams): string {
  return client.url(path, params);
}

function fetchJson<T>(url: string): Promise<T> {
  return client.getJson<T>(url);
}

export const api = {
  async getTeams(): Promise<Team[]> {
    const data = await fetchJson<any>(buildUrl('/teams/'));
    return unwrapResults<Team>(data);
  },

  async getMatchup(teamA: string, teamB: string, site: 'neutral' | 'home' | 'away'): Promise<MatchupResult> {
    return fetchJson<MatchupResult>(
      buildUrl('/matchup/', { teamA, teamB, site })
    );
  },

  async getConferences(): Promise<Conference[]> {
    const data = await fetchJson<any>(buildUrl('/conferences/'));
    return unwrapResults<Conference>(data);
  },

  async getSeasons(): Promise<SeasonInfo[]> {
    const data = await fetchJson<any>(buildUrl('/seasons/', { has_ratings: 'true' }));
    return unwrapResults<SeasonInfo>(data);
  },

  async getTrapezoid(params: { season?: number; conference?: string; top?: number }): Promise<TrapezoidData> {
    return fetchJson<TrapezoidData>(
      buildUrl('/viz/trapezoid', { season: params.season, conference: params.conference, top: params.top })
    );
  },

  async getLandscape(params: { season?: number; conference?: string; top?: number }): Promise<EfficiencyLandscapeData> {
    return fetchJson<EfficiencyLandscapeData>(
      buildUrl('/viz/landscape', { season: params.season, conference: params.conference, top: params.top })
    );
  },

  async getNBALandscape(params: { season?: number }): Promise<NBALandscapeData> {
    return fetchJson<NBALandscapeData>(
      buildUrl('/viz/nba-landscape', { season: params.season })
    );
  },

  async getNBACrystalBall(params: { season?: number }): Promise<NBACrystalBallData> {
    return fetchJson<NBACrystalBallData>(
      buildUrl('/viz/nba-crystal-ball', { season: params.season })
    );
  },

  async getNBALuckChart(params: { season?: number }): Promise<NBALuckChartData> {
    return fetchJson<NBALuckChartData>(
      buildUrl('/viz/nba-luck-chart', { season: params.season })
    );
  },

  async getCrystalBall(params: { season?: number; filter?: string }): Promise<CrystalBallData> {
    return fetchJson<CrystalBallData>(
      buildUrl('/viz/crystal-ball', { season: params.season, filter: params.filter })
    );
  },

  async getCinderella(params: {
    season?: number;
    min_seed?: number;
    max_seed?: number;
    show_all?: boolean;
  }): Promise<CinderellaData> {
    return fetchJson<CinderellaData>(
      buildUrl('/viz/cinderella', {
        season: params.season,
        min_seed: params.min_seed,
        max_seed: params.max_seed,
        show_all: params.show_all,
      })
    );
  },

  async getVizStats(params: { season?: number } = {}): Promise<VizStats> {
    return fetchJson<VizStats>(buildUrl('/viz/stats', { season: params.season }));
  },

  async getBracket(params: { season?: number; n_sims?: number } = {}): Promise<BracketData> {
    return fetchJson<BracketData>(
      buildUrl('/viz/bracket', { season: params.season, n_sims: params.n_sims })
    );
  },

  async getVizScatter(params: { season?: number; x: string; y: string; colorBy?: string }): Promise<VizScatterData> {
    return fetchJson<VizScatterData>(
      buildUrl('/viz/scatter', { season: params.season, x: params.x, y: params.y, colorBy: params.colorBy })
    );
  },

  async getTeamRoster(slug: string, season?: number): Promise<NCAAPlayerSeasonStats[]> {
    return fetchJson<NCAAPlayerSeasonStats[]>(
      buildUrl(`/team/${slug}/players/`, { season })
    );
  },

  async getLeaguePlayers(params?: {
    season?: number;
    ordering?: string;
    min_gp?: number;
    conference?: string;
  }): Promise<NCAAPlayerSeasonStats[]> {
    return fetchJson<NCAAPlayerSeasonStats[]>(
      buildUrl('/players/', params)
    );
  },

  // ── Phase 7: Roster Outlook ──────────────────────────────────────────────

  async getRosterOutlook(slug: string, season?: number): Promise<RosterOutlookData> {
    return fetchJson<RosterOutlookData>(
      buildUrl(`/outlook/${slug}/`, { season })
    );
  },

  async getScenarioProjection(body: ScenarioRequest): Promise<ScenarioProjectionResult> {
    return client.postJson<ScenarioProjectionResult>(buildUrl('/outlook/scenario/'), body, {
      formatError: defaultErrorFormatter('Scenario request failed'),
      invalidJsonMessage: 'Invalid JSON in scenario response',
    });
  },

  async searchPlayers(q: string, season?: number): Promise<PlayerSearchResult[]> {
    if (q.trim().length < 2) return [];
    return fetchJson<PlayerSearchResult[]>(
      buildUrl('/outlook/player-search/', { q: q.trim(), season })
    );
  },

  async getPlaceholderArchetypes(params?: {
    role?: string;
    tier?: string;
    conf_group?: string;
  }): Promise<PlaceholderListResponse> {
    return fetchJson<PlaceholderListResponse>(
      buildUrl('/outlook/placeholders/', params)
    );
  },

  async getValidationSummary(season?: number): Promise<ValidationSummaryResponse> {
    return fetchJson<ValidationSummaryResponse>(buildUrl('/validation/summary/', { season }));
  },

  async getValidationWeekly(season?: number): Promise<ValidationWeeklyResponse> {
    return fetchJson<ValidationWeeklyResponse>(buildUrl('/validation/weekly/', { season }));
  },

  async getValidationRecentGames(season?: number, limit?: number): Promise<ValidationRecentGamesResponse> {
    return fetchJson<ValidationRecentGamesResponse>(
      buildUrl('/validation/recent-games/', { season, limit })
    );
  },

  async getGameDetail(gameId: number | string): Promise<GameDetailResponse> {
    return fetchJson<GameDetailResponse>(buildUrl(`/games/${gameId}/detail/`));
  },
};
