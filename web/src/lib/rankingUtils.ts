import type { Better } from './metricMetadata';

export interface RankData {
  rank: number | null;
  percentile: number | null;
}

export function computeRanks(values: Array<number | null>, better: Better): Map<number, RankData> {
  const entries = values
    .map((value, index) => ({ value, index }))
    .filter((entry) => typeof entry.value === 'number' && !Number.isNaN(entry.value)) as Array<{ value: number; index: number }>;

  if (entries.length === 0) {
    return new Map();
  }

  const sorted = [...entries].sort((a, b) => {
    if (better === 'lower') return a.value - b.value;
    return b.value - a.value;
  });

  const ranks = new Map<number, RankData>();
  const n = sorted.length;

  sorted.forEach((entry, idx) => {
    const rank = idx + 1;
    const percentile = n === 1 ? 1 : (n - rank) / (n - 1);
    ranks.set(entry.index, { rank, percentile });
  });

  values.forEach((value, index) => {
    if (value === null || value === undefined) {
      ranks.set(index, { rank: null, percentile: null });
    }
  });

  return ranks;
}

export function getPercentileColor(percentile: number | null, better: Better, heatmap: boolean): string {
  if (!heatmap || percentile === null || percentile === undefined) return '';

  const adjusted = better === 'lower' ? 1 - percentile : percentile;

  if (adjusted >= 0.9) return 'bg-emerald-100 text-emerald-900';
  if (adjusted >= 0.75) return 'bg-emerald-50 text-emerald-900';
  if (adjusted >= 0.55) return 'bg-slate-50 text-slate-900';
  if (adjusted >= 0.35) return 'bg-amber-50 text-amber-900';
  return 'bg-rose-50 text-rose-900';
}
