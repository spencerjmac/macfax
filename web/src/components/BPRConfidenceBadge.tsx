"use client";

import { clsx } from "clsx";

/**
 * Source + confidence indicator for BPR values.
 *
 * Confidence is a sample-size statement, not a quality score:
 *   NCAA — possessions on court driving the RAPM component
 *   NBA  — total minutes driving the lineup component
 *
 * NCAA seasons before 2025 additionally carry a "box-era" flag: historical
 * play-by-play has no substitution data, so those ratings are driven by box
 * score + team context rather than true lineup impact.
 */

export type BprSource = "rapm" | "box_bpr" | "mixed" | "partial" | null | undefined;

export interface BPRConfidenceProps {
  source?: BprSource;
  /** NCAA: offensive possessions; NBA: pass minutes here instead */
  sample?: number | null;
  /** thresholds differ by league */
  league: "ncaa" | "nba";
  /** NCAA only: season end-year; pre-2025 gets the box-era provenance flag */
  seasonYear?: number;
  compact?: boolean;
  className?: string;
}

const SOURCE_LABEL: Record<string, string> = {
  rapm: "On-court",
  box_bpr: "Box-based",
  mixed: "Mixed",
  partial: "Partial",
};

export function bprConfidence(
  source: BprSource,
  sample: number | null | undefined,
  league: "ncaa" | "nba",
): "High" | "Medium" | "Low" {
  const s = sample ?? 0;
  const hi = league === "ncaa" ? 800 : 1500; // poss vs minutes
  const mid = league === "ncaa" ? 400 : 700;
  if (source === "rapm" && s >= hi) return "High";
  if ((source === "rapm" || source === "mixed") && s >= mid) return "Medium";
  return "Low";
}

const CONF_STYLE: Record<string, string> = {
  High: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  Medium: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  Low: "bg-slate-500/10 text-slate-400 border-slate-500/20",
};

export function BPRConfidenceBadge({
  source,
  sample,
  league,
  seasonYear,
  compact = false,
  className,
}: BPRConfidenceProps) {
  const conf = bprConfidence(source, sample, league);
  const boxEra = league === "ncaa" && seasonYear != null && seasonYear < 2025;
  const srcLabel = source ? SOURCE_LABEL[source] ?? source : "—";

  const sampleUnit = league === "ncaa" ? "poss" : "min";
  const tooltip = boxEra
    ? `Pre-2025 college play-by-play has no substitution data, so this rating is ` +
      `driven by box score and team context rather than lineup impact. ` +
      `Sample: ${Math.round(sample ?? 0)} ${sampleUnit}.`
    : `Source: ${srcLabel}. Confidence reflects sample size ` +
      `(${Math.round(sample ?? 0)} ${sampleUnit}) feeding the on-court component — ` +
      `not a judgment of the player.`;

  return (
    <span
      title={tooltip}
      className={clsx(
        "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium leading-none",
        CONF_STYLE[boxEra ? "Low" : conf],
        className,
      )}
    >
      {boxEra ? "Box era" : conf}
      {!compact && !boxEra && source && (
        <span className="opacity-70">· {srcLabel}</span>
      )}
    </span>
  );
}
