/**
 * Season helpers shared by web and Expo. Pure: no React, env, or DOM.
 *
 * The API labels a season by its ending year (2027 = 2026-27) and flags the
 * displayed one with `is_current`; `undefined` season params resolve to it
 * server-side, so UI state can stay `undefined` until the user picks one.
 */

export interface SeasonLike {
  year: number;
  is_current: boolean;
}

/** The season the API treats as current; falls back to the newest year. Null for an empty list. */
export function pickCurrentSeason<T extends SeasonLike>(seasons: readonly T[]): T | null {
  const flagged = seasons.find((s) => s.is_current);
  if (flagged) return flagged;
  return seasons.reduce<T | null>((best, s) => (best === null || s.year > best.year ? s : best), null);
}

/** 2027 -> "2026-27" */
export function seasonLabelFromYear(year: number): string {
  return `${year - 1}-${String(year).slice(2)}`;
}
