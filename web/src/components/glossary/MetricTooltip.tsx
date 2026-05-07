'use client';

import { useState, useRef } from 'react';
import Link from 'next/link';
import { getGlossaryTerm } from '@/lib/glossaryContent';

interface MetricTooltipProps {
  termId: string;
  children: React.ReactNode;
  showLink?: boolean;
}

export function MetricTooltip({ termId, children, showLink = true }: MetricTooltipProps) {
  const term = getGlossaryTerm(termId);
  const [visible, setVisible] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  if (!term) return <>{children}</>;

  function show() {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setVisible(true);
  }

  function hide() {
    timeoutRef.current = setTimeout(() => setVisible(false), 120);
  }

  return (
    <span
      className="relative inline-block"
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      <span className="border-b border-dashed border-text-muted cursor-help">
        {children}
      </span>
      {visible && (
        <span
          className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 bg-ui-card border border-ui-border rounded-lg shadow-lg p-3 text-left pointer-events-none"
          onMouseEnter={show}
          onMouseLeave={hide}
          style={{ pointerEvents: 'auto' }}
        >
          <span className="block text-xs font-semibold text-text-primary mb-1">{term.term}</span>
          <span className="block text-xs text-text-muted leading-relaxed">{term.shortDefinition}</span>
          {showLink && (
            <Link
              href={`/ncaa/glossary#${termId}`}
              className="block mt-2 text-xs text-brand hover:underline"
              onClick={() => setVisible(false)}
            >
              Full definition →
            </Link>
          )}
        </span>
      )}
    </span>
  );
}
