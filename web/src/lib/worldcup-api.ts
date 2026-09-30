import type {
  WorldCupTeam,
  WorldCupMatchupResult,
  WorldCupGroupResult,
} from '@macfax/core/types/worldcup';

import { createApi } from '@macfax/core/api-client';
import { LOCAL_API_ORIGIN, WEB_FETCH_OPTIONS, stripTrailingSlash, webApiOrigin } from './api-env';

const API_BASE_URL = stripTrailingSlash(webApiOrigin(LOCAL_API_ORIGIN));

const client = createApi({
  baseUrl: `${API_BASE_URL}/api/world-cup`,
  fetchOptions: WEB_FETCH_OPTIONS,
  formatError: (status, body) => `World Cup API request failed (${status}): ${body.slice(0, 200)}`,
  invalidJsonMessage: null,
  lenientErrorBody: true,
});

export const worldCupApi = {
  async getRankings(): Promise<WorldCupTeam[]> {
    const data = await client.getJson<{ teams: WorldCupTeam[] }>(client.rawUrl('/rankings/'));
    return data.teams;
  },

  async getMatchup(teamA: string, teamB: string): Promise<WorldCupMatchupResult> {
    return client.getJson(
      client.rawUrl(`/matchup/?teamA=${encodeURIComponent(teamA)}&teamB=${encodeURIComponent(teamB)}`)
    );
  },

  async getGroup(group: string): Promise<WorldCupGroupResult> {
    return client.getJson(client.rawUrl(`/group/${encodeURIComponent(group)}/`));
  },
};
