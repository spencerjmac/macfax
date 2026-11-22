/**
 * Default minimum-playing-time filters for the player leaderboards, scaled to
 * how far into the season we are.
 *
 * A fixed cutoff (e.g. "min 500 possessions") hides almost everyone in week one
 * and is too loose by March. Instead the "Auto" option asks for roughly
 * 10 minutes a game over the games played so far:
 *   NCAA: 10 minutes  x games played
 *   NBA:  20 possessions (~10 minutes) x games played
 *
 * "Games played so far" is the most games any player in the data has, capped at
 * a full season so a traded NBA player with extra games can't push it up.
 *
 * NBA rows on the native scale (rating_scale 'native-1') use a minutes rule under
 * "Auto" instead: minutes >= 18 x the games of the player's team, the qualifier the
 * native rating-scale cutoffs were set on (ratingScale.ts). When the team's games are
 * unknown, the row falls back to the possessions rule.
 */
import type { RatingScale } from '../types/nba';

export const AUTO_THRESHOLD = 0; // sentinel value for the "Auto" dropdown option

const NCAA_MIN_PER_GAME = 10;
const NCAA_MAX_GAMES = 40;
const NBA_POSS_PER_GAME = 20;
const NBA_MAX_GAMES = 82;

function gamesSoFar(rows: Array<{ gp?: number | null }>, cap: number): number {
  let max = 0;
  for (const r of rows) if (r.gp != null && r.gp > max) max = r.gp;
  return Math.min(Math.max(max, 1), cap);
}

/** Round to a readable step: 5 below 100, 10 below 1000, 50 above. */
function tidy(n: number): number {
  const step = n < 100 ? 5 : n < 1000 ? 10 : 50;
  return Math.max(step, Math.round(n / step) * step);
}

export function autoNcaaMinMinutes(rows: Array<{ gp?: number | null }>): number {
  return tidy(NCAA_MIN_PER_GAME * gamesSoFar(rows, NCAA_MAX_GAMES));
}

export function autoNbaMinPoss(rows: Array<{ gp?: number | null }>): number {
  return tidy(NBA_POSS_PER_GAME * gamesSoFar(rows, NBA_MAX_GAMES));
}

export const NBA_NATIVE_MIN_PER_TEAM_GAME = 18;

/** The fields of an NBA player row that the playing-time filter reads. */
export interface NbaPlayingTimeRow {
  rating_scale?: RatingScale;
  team_slug: string | null;
  mpg: number | null;
  gp: number;
  on_court_poss: number | null;
}

/**
 * Regular-season playing-time filter for one NBA row.
 * - auto: the "Auto" option is selected.
 * - minPoss: the possessions cutoff in force (Auto's or a fixed option's).
 * - teamGames: team slug -> games played, from the team rankings of the same season.
 * Native rows under Auto need minutes >= 18 x their team's games; every other row,
 * and a native row whose team is missing from teamGames, needs minPoss possessions.
 */
export function nbaRowMeetsPlayingTime(
  row: NbaPlayingTimeRow,
  auto: boolean,
  minPoss: number,
  teamGames: Readonly<Record<string, number>>,
): boolean {
  const games = row.team_slug != null ? teamGames[row.team_slug] : undefined;
  if (auto && row.rating_scale === 'native-1' && games != null) {
    return (row.mpg ?? 0) * row.gp >= NBA_NATIVE_MIN_PER_TEAM_GAME * games;
  }
  return row.on_court_poss != null && row.on_court_poss >= minPoss;
}
