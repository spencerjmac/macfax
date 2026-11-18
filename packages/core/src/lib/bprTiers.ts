/**
 * BPR Tier classification based on wins_added above replacement.
 * Earlier scale: replacement level = BPR -2.0. native-1 rows (task 5.10b): replacement
 * -1.918 and new Wins Added units, so the cutoffs come from winsAddedCutoff (same share
 * of qualified players per tier).
 */
import type { RatingScale } from '../types/nba';
import { winsAddedCutoff } from './ratingScale';

export interface BPRTier {
  label: string;
  color: string;       // Tailwind text colour
  bgColor: string;     // Tailwind bg colour for badges/bars
  barColor: string;    // Tailwind bg for horizontal bar fill
}

export function getBPRTier(winsAdded: number | null | undefined, scale?: RatingScale): BPRTier {
  if (winsAdded === null || winsAdded === undefined) {
    return { label: "—", color: "text-slate-500", bgColor: "bg-slate-800", barColor: "bg-slate-600" };
  }
  const cut = (v: number) => winsAddedCutoff(v, scale);
  if (winsAdded >= cut(8))  return { label: "MVP-tier",         color: "text-emerald-400", bgColor: "bg-emerald-950", barColor: "bg-emerald-400" };
  if (winsAdded >= cut(5))  return { label: "All-Star",          color: "text-emerald-300", bgColor: "bg-emerald-900", barColor: "bg-emerald-300" };
  if (winsAdded >= cut(2))  return { label: "Solid Starter",     color: "text-teal-400",    bgColor: "bg-teal-950",    barColor: "bg-teal-400"    };
  if (winsAdded >= cut(0))  return { label: "Rotation",          color: "text-slate-300",   bgColor: "bg-slate-800",   barColor: "bg-slate-400"   };
  return                      { label: "Below Replacement", color: "text-rose-400",    bgColor: "bg-rose-950",    barColor: "bg-rose-400"    };
}

/** Format a BPR or wins value with sign. */
export function fmtSigned(v: number | null | undefined, decimals = 1): string {
  if (v === null || v === undefined) return "—";
  return (v >= 0 ? "+" : "") + v.toFixed(decimals);
}
