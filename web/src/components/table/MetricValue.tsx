'use client';

import type { CSSProperties, ReactNode } from 'react';
import type { Column } from '@tanstack/react-table';
import clsx from 'clsx';
import { valueTextClass } from './GroupedTableHead';

interface MetricValueProps {
  /** Formatted value; null or undefined renders the '-' placeholder. */
  text: string | null | undefined;
  /** Heat background from heatStyleFromPercentile ({} when the metric isn't shaded). */
  heat: CSSProperties;
  /** Rank shown as a superscript when showRank is set. */
  rank?: number | null;
  showRank?: boolean;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  column: Column<any, unknown>;
  /** 'full' = standalone metric column; 'compact' = sub-column inside a group (text-xs, centered). */
  variant?: 'full' | 'compact';
  /** Optional mark after the value (e.g. a † with a tooltip). */
  marker?: ReactNode;
}

/** Ratings-table value cell: heat background, value, optional rank superscript, '-' for missing. */
export default function MetricValue({ text, heat, rank, showRank, column, variant = 'full', marker }: MetricValueProps) {
  const compact = variant === 'compact';
  if (text == null) {
    return compact
      ? <div className="text-center text-text-muted text-xs">-</div>
      : <span className="text-text-muted">-</span>;
  }
  return (
    <div
      style={heat}
      className={compact
        ? clsx('px-1 py-0.5 rounded text-center font-mono', valueTextClass(column, 'text-xs'))
        : clsx('px-2 py-1 rounded font-mono', valueTextClass(column))}
    >
      {text}
      {marker}
      {showRank && rank && (
        <sup className={`text-[9px] ${heat.background ? 'text-slate-700' : 'text-muted'} ml-0.5 font-sans font-medium`}>{rank}</sup>
      )}
    </div>
  );
}
