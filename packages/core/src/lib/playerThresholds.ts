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
 */

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
