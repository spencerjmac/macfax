import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import type { RelatedMetric } from '@/lib/methodologyTypes';

interface RelatedMetricsProps {
  metrics: RelatedMetric[];
}

export function RelatedMetrics({ metrics }: RelatedMetricsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {metrics.map((m) => (
        <Link
          key={m.slug}
          href={`/methodology/${m.slug}`}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-brand bg-ui-surface border border-ui-border hover:border-brand/40 rounded-full px-3 py-1 transition-colors"
        >
          {m.label}
          <ArrowRight className="w-3 h-3" />
        </Link>
      ))}
    </div>
  );
}
