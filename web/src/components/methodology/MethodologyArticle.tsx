import Link from 'next/link';
import { ChevronRight, Clock } from 'lucide-react';
import type { MethodologyContent } from '@/lib/methodologyTypes';
import { FormulaBlock } from './FormulaBlock';
import { InterpretationBand } from './InterpretationBand';
import { LimitationCallout } from './LimitationCallout';
import { ExampleCard } from './ExampleCard';
import { RelatedMetrics } from './RelatedMetrics';

interface MethodologyArticleProps {
  content: MethodologyContent;
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-lg font-semibold text-text-primary mb-3 mt-8 pb-2 border-b border-ui-border">
      {children}
    </h2>
  );
}

function WeightsTable({ weights }: { weights: NonNullable<MethodologyContent['weights']> }) {
  return (
    <div className="rounded-lg border border-ui-border overflow-hidden my-2">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-ui-surface border-b border-ui-border">
            <th className="text-left px-4 py-2 text-xs font-medium uppercase tracking-wide text-text-muted">
              Factor
            </th>
            <th className="text-right px-4 py-2 text-xs font-medium uppercase tracking-wide text-text-muted">
              Weight
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-ui-border">
          {weights.map((w) => (
            <tr key={w.label} className="bg-ui-card hover:bg-ui-surface transition-colors">
              <td className="px-4 py-3 text-text-primary font-medium">{w.label}</td>
              <td className="px-4 py-3 text-right font-mono text-brand font-semibold">{w.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function MethodologyArticle({ content }: MethodologyArticleProps) {
  return (
    <div className="container mx-auto px-4 py-8 max-w-3xl">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-1.5 text-sm text-text-muted mb-6">
        <Link href="/methodology" className="hover:text-brand transition-colors">
          Methodology
        </Link>
        <ChevronRight className="w-3.5 h-3.5" />
        <span className="text-text-primary">{content.title}</span>
      </nav>

      {/* Hero */}
      <header className="mb-8">
        <h1 className="text-4xl font-bold text-text-primary mb-2">{content.title}</h1>
        <p className="text-lg text-text-muted mb-4">{content.subtitle}</p>
        <p className="text-base text-text-secondary leading-relaxed">{content.summary}</p>
      </header>

      {/* What It Measures */}
      <section>
        <SectionHeading>What It Measures</SectionHeading>
        <p className="text-base text-text-primary leading-relaxed">{content.whatItMeasures}</p>
      </section>

      {/* Why It Matters */}
      <section>
        <SectionHeading>Why It Matters</SectionHeading>
        <p className="text-base text-text-primary leading-relaxed">{content.whyItMatters}</p>
      </section>

      {/* How to Interpret */}
      <section>
        <SectionHeading>How to Interpret</SectionHeading>
        <p className="text-base text-text-primary leading-relaxed mb-3">{content.howToInterpret}</p>
        {content.interpretationBands && content.interpretationBands.length > 0 && (
          <InterpretationBand bands={content.interpretationBands} />
        )}
      </section>

      {/* Formula */}
      {content.basicFormula && (
        <section>
          <SectionHeading>Formula</SectionHeading>
          <FormulaBlock formula={content.basicFormula} />
        </section>
      )}

      {/* Weights */}
      {content.weights && content.weights.length > 0 && (
        <section>
          <SectionHeading>Component Weights</SectionHeading>
          <WeightsTable weights={content.weights} />
        </section>
      )}

      {/* Technical Notes */}
      {content.technicalNotes.length > 0 && (
        <section>
          <SectionHeading>Technical Notes</SectionHeading>
          <ul className="space-y-2">
            {content.technicalNotes.map((note, i) => (
              <li key={i} className="flex gap-2.5 text-sm text-text-primary leading-relaxed">
                <span className="shrink-0 mt-1 w-1.5 h-1.5 rounded-full bg-brand/60 mt-1.5" />
                {note}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Known Limitations */}
      {content.knownLimitations.length > 0 && (
        <section>
          <LimitationCallout limitations={content.knownLimitations} />
        </section>
      )}

      {/* Example */}
      {content.example && (
        <section>
          <ExampleCard example={content.example} />
        </section>
      )}

      {/* Related Metrics */}
      {content.relatedMetrics && content.relatedMetrics.length > 0 && (
        <section>
          <SectionHeading>Related Methodology</SectionHeading>
          <RelatedMetrics metrics={content.relatedMetrics} />
        </section>
      )}

      {/* Footer */}
      <footer className="mt-12 pt-6 border-t border-ui-border flex items-center gap-4 text-xs text-text-muted">
        <Clock className="w-3.5 h-3.5" />
        <span>
          Last updated: {content.lastUpdated} · Version {content.methodologyVersion}
        </span>
      </footer>
    </div>
  );
}
