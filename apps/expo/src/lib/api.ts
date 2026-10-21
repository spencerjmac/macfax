import { createApi } from '@macfax/core/api-client';
import type { SeasonInfo, TeamSeason } from '@macfax/core/types';
import type { GameDetailResponse, GameTeamRef, WPPoint } from '@macfax/core/types/games';

/** Used when EXPO_PUBLIC_API_BASE_URL is unset, so phones always reach a real host. */
const DEFAULT_API_ORIGIN = 'https://macfax.usu.edu';

/** The public website. Used for links to pages the app does not have yet. */
export const WEB_ORIGIN = 'https://macfax.usu.edu';

/**
 * EXPO_PUBLIC_ values are inlined into the bundle at build time: never secrets.
 * Must be read as a literal `process.env.EXPO_PUBLIC_*` access for Expo to inline it.
 */
export const API_ORIGIN = (process.env.EXPO_PUBLIC_API_BASE_URL || DEFAULT_API_ORIGIN).replace(/\/$/, '');

/** The origin is used as-is, so request paths carry their own /api prefix (same as web). */
export const api = createApi({ baseUrl: API_ORIGIN });

const API_RANKINGS_PATH = '/api/rankings/';
const API_SEASONS_PATH = '/api/seasons/';

/**
 * The API returns logo paths relative to the site ("/static/logos/x.png").
 * The website can use them as-is because it is served from the same host; the
 * app has no host of its own, so prefix the API origin. Null means "no logo":
 * callers draw the team's initial instead, as the web tables do.
 */
export function resolveLogoUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  if (/^https?:\/\//.test(path)) return path;
  return `${API_ORIGIN}${path.startsWith('/') ? '' : '/'}${path}`;
}

/** The TeamSeason fields the app's screens use so far. Field names match web's TeamSeason. */
export type RankingRow = Pick<
  TeamSeason,
  | 'teamId'
  | 'teamName'
  | 'conference'
  | 'record'
  | 'season'
  | 'rank'
  | 'adjEM'
  | 'adjO'
  | 'adjD'
  | 'adjTempo'
  | 'four_factor_index_100'
  | 'tournament_seed'
> & {
  /** Absolute URL, or null when the team has no logo. */
  logoUrl: string | null;
};

export interface RankingsData {
  /** Season label such as "2025-26". */
  season: string;
  /** Latest ratings timestamp across the rows, or null if the API sent none. */
  lastUpdated: string | null;
  teams: RankingRow[];
}

/**
 * DUPLICATED MAPPING: a subset of mapApiRowToTeamSeason in web/src/lib/data.ts
 * (the snake_case -> camelCase step behind getAllTeams), with the same defaults
 * except logoUrl (absolute or null here; web keeps the relative path).
 * If the web mapping changes, change this too, or move the mapping into
 * packages/core and share it.
 */
function mapApiRowToRankingRow(team: Record<string, unknown>): RankingRow {
  const num = (v: unknown): number | null => (v != null && typeof v === 'number' ? v : null);
  return {
    teamId: (team.team_slug as string) || '',
    teamName: (team.team_name as string) || '',
    conference: (team.conference as string) || 'Ind',
    record: (team.record as string) || '0-0',
    season: (team.season_display as string) || '',
    rank: (team.rank as number) ?? 0,
    adjEM: (team.adj_em as number) ?? 0,
    adjO: (team.adj_o as number) ?? 0,
    adjD: (team.adj_d as number) ?? 0,
    adjTempo: (team.adj_tempo as number) ?? 0,
    four_factor_index_100: num(team.four_factor_index_100),
    tournament_seed: (team.tournament_seed as number) ?? null,
    logoUrl: resolveLogoUrl(team.team_logo as string | null),
  };
}

// One in-flight or finished request per season, so Home, Rankings and the team
// screen share a single download. Failed requests are dropped so Retry refetches.
const rankingsCache = new Map<string, Promise<RankingsData>>();

/**
 * NCAA team rankings for a season (the current one when omitted). Unlike
 * web's getAllTeams, a failed request throws (with core's readable message)
 * so screens can show it. Pass `force` to bypass the cache.
 */
export function fetchRankings(season?: number, options: { force?: boolean } = {}): Promise<RankingsData> {
  const key = season ? String(season) : 'current';
  const cached = rankingsCache.get(key);
  if (cached && !options.force) return cached;

  const query = season ? `?season=${season}` : '';
  const request = api
    .getJson<{ results?: Record<string, unknown>[] }>(api.rawUrl(`${API_RANKINGS_PATH}${query}`))
    .then((json): RankingsData => {
      const results = json.results ?? [];
      const teams = results.map(mapApiRowToRankingRow);
      const timestamps = results
        .map((r) => (r.updated_at as string | undefined) || (r.computed_at as string | undefined))
        .filter((t): t is string => Boolean(t));
      return {
        season: teams[0]?.season || (season ? `${season - 1}-${String(season).slice(2)}` : ''),
        lastUpdated: timestamps.length ? timestamps.reduce((a, b) => (a > b ? a : b)) : null,
        teams,
      };
    });

  rankingsCache.set(key, request);
  request.catch(() => rankingsCache.delete(key));
  return request;
}

/** Seasons that have computed ratings, newest first (same call as web's getAllSeasons). */
export async function fetchSeasons(): Promise<SeasonInfo[]> {
  const json = await api.getJson<SeasonInfo[] | { results?: SeasonInfo[] }>(
    api.rawUrl(`${API_SEASONS_PATH}?has_ratings=true`),
  );
  return Array.isArray(json) ? json : (json.results ?? []);
}

/**
 * The API's season year for a label: "2025-26" -> 2026 (the ending year),
 * the same rule web's TeamPageTabs uses. Null if the label is not "YYYY-YY".
 */
export function seasonYearFromLabel(label: string): number | null {
  const start = parseInt(label.split('-')[0], 10);
  return Number.isNaN(start) ? null : start + 1;
}

/**
 * One game from /api/teams/<slug>/gamelog/. Only the fields the app shows are
 * typed; the API sends about 60 more. Percentages are percentage points
 * (64.3 means 64.3%).
 */
export interface GameLogEntry {
  id: number;
  /** Id for /ncaa/games/<game_id> on the website, when the game has a detail page. */
  game_id: number | null;
  game_date: string;
  opponent_name: string;
  opponent_slug: string | null;
  opponent_is_d1: boolean;
  home_away: 'H' | 'A' | 'N';
  result: 'W' | 'L';
  went_to_ot: boolean;
  pts: number;
  /** Team points minus opponent points; null when unknown. */
  margin: number | null;
  ortg: number | null;
  drtg: number | null;
  efg_pct: number | null;
  tov_pct: number | null;
  orb_pct: number | null;
  ftr: number | null;
}

/**
 * A team's games for one season (the API's ending-year number, e.g. 2026).
 * Same endpoint as fetchTeamGameLog in web/src/lib/api.ts; unlike web, a
 * failed request throws so the screen can offer Retry.
 */
export async function fetchTeamGameLog(teamId: string, seasonYear: number): Promise<GameLogEntry[]> {
  const json = await api.getJson<{ game_log?: GameLogEntry[] }>(
    api.rawUrl(`/api/teams/${encodeURIComponent(teamId)}/gamelog/?season=${seasonYear}`),
  );
  return json.game_log ?? [];
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
 * A recent finished game that has a win-probability curve, for the dev gate
 * screen. Game ids differ between databases, so the id is looked up rather
 * than hard-coded.
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
