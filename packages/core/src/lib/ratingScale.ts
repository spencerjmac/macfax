/**
 * NBA rating scale helpers (task 5.10b).
 *
 * native-1 rows carry centred BPR (league average = 0, replacement = −1.918) and
 * Wins Added = (BPR + 1.918) × minutes/48 ÷ 27.97. Rows on the earlier scale keep the
 * old tier cutoffs and formula text exactly.
 *
 * Native cutoffs: each keeps the share of qualified players (minutes ≥ 18 × team games,
 * 2022–2026 pooled, 911 player-seasons) that the old cutoff held under the pre-native
 * ratings (snapshot of 2026-11-16). NBA only.
 */
import type { RatingScale } from '../types/nba';

export function isNativeScale(scale: RatingScale | undefined): boolean {
  return scale === 'native-1';
}

/** Old BPR cutoff → native cutoff with the same share of qualified players at or above it. */
const NATIVE_BPR_CUTOFF: Record<string, number> = {
  '5': 5.7, '3': 3.2, '2': 1.9, '1.5': 1.3, '1': 0.8, '0': -0.4,
};

/**
 * Old Wins Added cutoff → native cutoff (same share of qualified players), except 0: the
 * "Below Replacement" line is a definition (Wins Added < 0 means below a replacement-level
 * player), so it stays exactly 0 on every scale (task 5.10).
 */
const NATIVE_WINS_ADDED_CUTOFF: Record<string, number> = {
  '8': 12.2, '5': 7.5, '2': 2.4, '0': 0,
};

/** BPR tier cutoff for a row's scale: the old value on the earlier scale. */
export function bprCutoff(old: number, scale: RatingScale | undefined): number {
  return isNativeScale(scale) ? (NATIVE_BPR_CUTOFF[String(old)] ?? old) : old;
}

/** Wins Added tier cutoff for a row's scale: the old value on the earlier scale. */
export function winsAddedCutoff(old: number, scale: RatingScale | undefined): number {
  return isNativeScale(scale) ? (NATIVE_WINS_ADDED_CUTOFF[String(old)] ?? old) : old;
}

export const WINS_ADDED_FORMULA_LEGACY = '(MPR + 2.0) × MPG/48 × GP/56 · Replacement level = MPR −2.0';
export const WINS_ADDED_FORMULA_NATIVE = '(MPR + 1.918) × minutes/48 ÷ 27.97 · Replacement level = MPR −1.918';

/** Wins Added formula text for a set of rows: the native formula when any row is native-1. */
export function winsAddedFormula(rows: ReadonlyArray<{ rating_scale?: RatingScale }> | undefined): string {
  return rows?.some((r) => isNativeScale(r.rating_scale)) ? WINS_ADDED_FORMULA_NATIVE : WINS_ADDED_FORMULA_LEGACY;
}

/** Replacement offset text used by "BPR adj" labels. */
export function replacementAdjustText(rows: ReadonlyArray<{ rating_scale?: RatingScale }> | undefined): string {
  return rows?.some((r) => isNativeScale(r.rating_scale))
    ? 'MPR adj = MPR + 1.918 (replacement offset)'
    : 'MPR adj = stored MPR + 2.0 (replacement offset)';
}
