import { MethodologyCard } from './MethodologyCard';
import { methodologyContent } from '@/lib/methodologyContent';

interface MethodologySectionGroupProps {
  id: string;
  title: string;
  slugs: string[];
}

export function MethodologySectionGroup({ title, slugs }: MethodologySectionGroupProps) {
  const items = slugs
    .map((slug) => methodologyContent.find((m) => m.slug === slug))
    .filter(Boolean) as (typeof methodologyContent)[number][];

  return (
    <section className="mb-12">
      <h2 className="text-xs text-text-muted font-medium uppercase tracking-widest mb-4 pb-2 border-b border-ui-border">
        {title}
      </h2>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {items.map((item) => (
          <MethodologyCard key={item.slug} content={item} />
        ))}
      </div>
    </section>
  );
}
