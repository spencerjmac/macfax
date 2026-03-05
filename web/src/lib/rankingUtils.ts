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

export function getPercentileColor(percentile: number | null, better: Better, heatmap: boolean): string {
  if (!heatmap || percentile === null || percentile === undefined) return '';

  // computeRanks already accounts for direction (rank 1 = best regardless of better),
  // so percentile is always a "goodness" score (1.0 = best). No flip needed here.
  const adjusted = percentile;

  if (adjusted >= 0.9) return 'bg-emerald-100 text-emerald-900';
  if (adjusted >= 0.75) return 'bg-emerald-50 text-emerald-900';
  if (adjusted >= 0.55) return 'bg-slate-50 text-slate-900';
  if (adjusted >= 0.35) return 'bg-amber-50 text-amber-900';
  return 'bg-rose-50 text-rose-900';
}
