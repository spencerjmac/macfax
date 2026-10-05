import { createApi } from '@macfax/core/api-client';
import type { GameDetailResponse, GameTeamRef, WPPoint } from '@macfax/core/types/games';

/** Used when EXPO_PUBLIC_API_BASE_URL is unset, so phones always reach a real host. */
const DEFAULT_API_ORIGIN = 'https://macfax.usu.edu';

/**
 * EXPO_PUBLIC_ values are inlined into the bundle at build time: never secrets.
 * Must be read as a literal `process.env.EXPO_PUBLIC_*` access for Expo to inline it.
 */
export const API_ORIGIN = (process.env.EXPO_PUBLIC_API_BASE_URL || DEFAULT_API_ORIGIN).replace(/\/$/, '');

/** The origin is used as-is, so request paths carry their own /api prefix (same as web). */
export const api = createApi({ baseUrl: API_ORIGIN });

const API_RANKINGS_PATH = '/api/rankings/';

/** The columns the gate screen's rankings table shows. */
export interface RankingRow {
  teamId: string;
  teamName: string;
  conference: string;
  record: string;
  rank: number;
  adjEM: number;
  adjO: number;
  adjD: number;
  adjTempo: number;
  wab: number | null;
  netRank: number | null;
}

/**
 * DUPLICATED MAPPING: a subset of mapApiRowToTeamSeason in web/src/lib/data.ts
 * (the snake_case -> camelCase step behind getAllTeams), with the same defaults.
 * Only the fields this screen needs are mapped. If the web mapping changes,
 * change this too, or move the mapping into packages/core and share it.
 */
function mapApiRowToRankingRow(team: Record<string, unknown>): RankingRow {
  const num = (v: unknown): number | null => (v != null && typeof v === 'number' ? v : null);
  return {
    teamId: (team.team_slug as string) || '',
    teamName: (team.team_name as string) || '',
    conference: (team.conference as string) || 'Ind',
    record: (team.record as string) || '0-0',
    rank: (team.rank as number) ?? 0,
    adjEM: (team.adj_em as number) ?? 0,
    adjO: (team.adj_o as number) ?? 0,
    adjD: (team.adj_d as number) ?? 0,
    adjTempo: (team.adj_tempo as number) ?? 0,
    wab: num(team.wab),
    netRank: num(team.net_rank),
  };
}

/**
 * Current-season NCAA rankings. Unlike web's getAllTeams, a failed request
 * throws (with core's readable error message) so the screen can show it.
 */
export async function fetchRankings(): Promise<RankingRow[]> {
  const json = await api.getJson<{ results?: Record<string, unknown>[] }>(api.rawUrl(API_RANKINGS_PATH));
  return (json.results ?? []).map(mapApiRowToRankingRow);
}

/** What the win-probability chart needs from /api/games/<id>/detail/. Small and serializable. */
export interface WPChartData {
  gameId: number;
  date: string;
  homeTeam: GameTeamRef;
  awayTeam: GameTeamRef;
  curve: WPPoint[];
}

const SAMPLE_GAME_CANDIDATES = 5;

/**
 * A recent finished game that has a win-probability curve, for the chart
 * experiment. Game ids differ between databases, so the id is looked up
 * rather than hard-coded.
 */
export async function fetchSampleWPChartData(): Promise<WPChartData> {
  const list = await api.getJson<{ results?: { id: number; status?: string }[] }>(api.rawUrl('/api/games/'));
  const finals = (list.results ?? []).filter((g) => g.status === 'final').slice(0, SAMPLE_GAME_CANDIDATES);
  for (const game of finals) {
    const detail = await api.getJson<GameDetailResponse>(api.rawUrl(`/api/games/${game.id}/detail/`));
    if (detail.wp_curve?.length) {
      return {
        gameId: detail.game_meta.id,
        date: detail.game_meta.date,
        homeTeam: detail.game_meta.home_team,
        awayTeam: detail.game_meta.away_team,
        curve: detail.wp_curve,
      };
    }
  }
  throw new Error('No recent game has a win-probability curve.');
}
