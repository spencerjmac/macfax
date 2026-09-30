/**
 * NCAA sport configuration — column definitions, labels, thresholds.
 *
 * This file exists so shared components (RankingsTable, etc.) can be
 * sport-aware without hard-coding NCAA assumptions.
 */

export const NCAA_SPORT_CONFIG = {
  id: 'ncaa' as const,
  label: 'NCAA Basketball',
  shortLabel: 'NCAA',
  baseRoute: '/',
  rankingsRoute: '/rankings',
  teamRoute: (slug: string) => `/team/${slug}`,
  vizRoute: '/viz',
} as const;
