import type { Better } from './metricMetadata';

export interface RankData {
  rank: number | null;
  percentile: number | null;
}

export function computeRanks(entries: Array<{ id: string; value: number | null }>, better: Better): Map<string, RankData> {
  const valid = entries
    .filter((e) => typeof e.value === 'number' && !Number.isNaN(e.value)) as Array<{ id: string; value: number }>;

  const ranks = new Map<string, RankData>();

  if (valid.length === 0) {
    entries.forEach((e) => ranks.set(e.id, { rank: null, percentile: null }));
    return ranks;
  }

  const sorted = [...valid].sort((a, b) => {
    if (better === 'lower') return a.value - b.value;
    return b.value - a.value;
  });

  const n = sorted.length;

  sorted.forEach((entry, idx) => {
    const rank = idx + 1;
    const percentile = n === 1 ? 1 : (n - rank) / (n - 1);
    ranks.set(entry.id, { rank, percentile });
  });

  entries.forEach((e) => {
    if (e.value === null || e.value === undefined) {
      ranks.set(e.id, { rank: null, percentile: null });
    }
  });

  return ranks;
}

/**
 * Maps a percentile (0–1, 1 = best) to the 2026 teal/slate heat-map background.
 * Above-average deepens in teal; below-average fades to faint slate.
 * computeRanks already normalises direction, so no flip needed here.
 */
export function heatStyleFromPercentile(percentile: number | null): { background?: string } {
  if (percentile === null || percentile === undefined) return {};
  const t = Math.max(0, Math.min(1, percentile));
  if (t >= 0.5) {
    const a = (t - 0.5) / 0.5;
    return { background: `rgba(64,144,128,${(0.10 + a * 0.42).toFixed(3)})` };
  }
  const a = (0.5 - t) / 0.5;
  return { background: `rgba(100,116,139,${(a * 0.14).toFixed(3)})` };
}
