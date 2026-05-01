import type { Metadata } from 'next';
import { METHODOLOGY_SECTIONS } from '@/lib/methodologyContent';
import { MethodologySectionGroup } from '@/components/methodology/MethodologySectionGroup';

export const metadata: Metadata = {
  title: 'Methodology | macfax',
  description:
    'How Macfax calculates adjusted ratings, Four Factors, player impact, matchup projections, and every metric on the site. Built around basketball logic, not black boxes.',
};

export default function MethodologyPage() {
  return (
    <div className="container mx-auto px-4 py-8 max-w-5xl">
      {/* Hero */}
      <div className="mb-12">
        <h1 className="text-4xl font-bold mb-3">Macfax Methodology</h1>
        <p className="text-lg text-text-muted max-w-2xl leading-relaxed">
          Macfax is independent, transparent, still improving, and built around basketball logic.
          These pages explain what each metric measures, how the numbers are calculated, and how to
          interpret them without overusing them.
        </p>
      </div>

      {/* Sections */}
      {METHODOLOGY_SECTIONS.map((section) => (
        <MethodologySectionGroup
          key={section.id}
          id={section.id}
          title={section.title}
          slugs={section.slugs}
        />
      ))}
    </div>
  );
}
