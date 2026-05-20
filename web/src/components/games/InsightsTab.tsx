'use client';

import { Lightbulb } from 'lucide-react';

interface Props {
  insights: string[];
}

const BORDER_COLORS = [
  'border-l-blue-500',
  'border-l-teal-500',
  'border-l-amber-500',
];

export default function InsightsTab({ insights }: Props) {
  if (!insights.length) {
    return (
      <div className="py-12 text-center text-sm text-text-muted">
        No insights available for this game.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {insights.map((insight, i) => (
        <div
          key={i}
          className={`flex gap-3 rounded-xl border border-ui-border border-l-4 bg-ui-surface p-4 ${
            BORDER_COLORS[i % BORDER_COLORS.length]
          }`}
        >
          <Lightbulb className="mt-0.5 h-4 w-4 flex-shrink-0 text-brand" />
          <p className="text-sm leading-relaxed text-text-primary">{insight}</p>
        </div>
      ))}
      <p className="pt-1 text-right text-[11px] text-text-muted">
        AI-generated analysis · powered by Claude
      </p>
    </div>
  );
}
