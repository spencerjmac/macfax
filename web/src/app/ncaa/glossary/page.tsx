import { Metadata } from 'next';
import { GLOSSARY_TERMS } from '@/lib/glossaryContent';
import GlossaryTable from '@/components/GlossaryTable';

export const metadata: Metadata = {
  title: 'Macfax Glossary | College Basketball Metrics',
  description:
    'Official definitions for all metrics, ratings, and visual frameworks on Macfax — including efficiency ratings, Four Factors, player ratings, resume metrics, and prediction terms.',
};

export default function GlossaryPage() {
  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      <div className="mb-8">
        <h1 className="text-4xl font-bold mb-2 text-text-primary">Macfax Glossary</h1>
        <p className="text-text-muted">
          Official definitions for all metrics, ratings, and visual frameworks used across Macfax.
          Formulas are shown for conceptual understanding — not as complete technical specifications.
        </p>
      </div>

      <GlossaryTable terms={GLOSSARY_TERMS} />
    </div>
  );
}
