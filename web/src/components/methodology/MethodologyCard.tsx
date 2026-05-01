import Link from 'next/link';
import type { MethodologyContent } from '@/lib/methodologyTypes';

interface MethodologyCardProps {
  content: MethodologyContent;
}

export function MethodologyCard({ content }: MethodologyCardProps) {
  return (
    <Link
      href={`/methodology/${content.slug}`}
      className="block group bg-ui-card border border-ui-border rounded-xl p-5 hover:border-brand/40 hover:shadow-sm transition-all"
    >
      <h3 className="text-base font-semibold text-text-primary group-hover:text-brand transition-colors mb-1">
        {content.title}
      </h3>
      <p className="text-sm text-text-muted leading-relaxed mb-3">{content.description}</p>
      <span className="inline-flex items-center gap-1 text-xs font-medium text-brand/80 bg-brand/8 border border-brand/20 rounded-full px-2.5 py-0.5">
        {content.bestUsedFor}
      </span>
    </Link>
  );
}
