/** One-line empty message for NBA tables when a season / season type has no rows yet. */
export function noDataMessage(seasonType: string | undefined, seasonDisplay: string | undefined): string {
  const kind = seasonType === 'playoffs' ? 'playoff' : 'regular season';
  return `No ${kind} data for ${seasonDisplay ?? 'this season'} yet.`;
}
