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

/** Light-surface heat fills, faintest → strongest (step 1–5). Teal = above the middle, coral = below. */
export const HEAT_ABOVE = ['#e6f9fb', '#d1f3f6', '#baeaef', '#a1e1e7', '#88d9e0'] as const;
export const HEAT_BELOW = ['#fef2ee', '#ffe5dc', '#fed5c7', '#fbc7b5', '#f7b8a2'] as const;
const HEAT_ABOVE_DARK = ['#122a2c', '#0c3639', '#024247', '#024e53', '#015a60'] as const;
const HEAT_BELOW_DARK = ['#32201a', '#42271e', '#532e21', '#653424', '#773b26'] as const;
const HEAT_BANDS = [0.6, 0.7, 0.8, 0.9, 0.95] as const;

/**
 * Maps a percentile (0–1, 1 = best) to a banded two-sided heat-map background.
 *
 * Distance from the median, d = max(p, 1 - p), picks a step:
 * d ≥ .60/.70/.80/.90/.95 → step 1–5; anything closer to the middle gets no fill.
 * Teal = above the D1 / qualified-player middle; coral = below it.
 * Coral here only means "below the middle of the pool", not "the model sees a
 * problem" — for table cells this supersedes the 2026.2 note reserving red for
 * genuinely negative values.
 *
 * computeRanks already normalises direction, so 'higher' and 'lower' both read
 * p as "1 = best". For 'neutral' metrics (e.g. PPG) being low isn't bad, so
 * nothing below the median is filled.
 *
 * `surface` picks the palette: 'light' for light table backgrounds (web),
 * 'dark' for dark surfaces (Expo).
 */
export function heatStyleFromPercentile(
  percentile: number | null,
  better: Better = 'higher',
  surface: 'light' | 'dark' = 'light',
): { background?: string } {
  if (percentile === null || percentile === undefined || Number.isNaN(percentile)) return {};
  const p = Math.max(0, Math.min(1, percentile));
  const above = p >= 0.5;
  if (!above && better === 'neutral') return {};
  const d = above ? p : 1 - p;
  let step = 0;
  for (const band of HEAT_BANDS) if (d >= band) step++;
  if (step === 0) return {};
  const palette = surface === 'dark'
    ? (above ? HEAT_ABOVE_DARK : HEAT_BELOW_DARK)
    : (above ? HEAT_ABOVE : HEAT_BELOW);
  return { background: palette[step - 1] };
}
