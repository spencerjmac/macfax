'use client';

import 'katex/dist/katex.min.css';
import { BlockMath } from 'react-katex';
import type { FormulaContent } from '@/lib/methodologyTypes';

interface FormulaBlockProps {
  formula: FormulaContent;
  label?: string;
}

export function FormulaBlock({ formula, label }: FormulaBlockProps) {
  return (
    <div className="bg-ui-surface border border-ui-border rounded-lg p-4 my-2">
      {label && (
        <div className="text-xs text-text-muted font-medium uppercase tracking-wide mb-3">
          {label}
        </div>
      )}
      {formula.latex && (
        <div className="overflow-x-auto py-1">
          <BlockMath math={formula.latex} />
        </div>
      )}
      {formula.prose && (
        <pre className="font-mono text-sm text-text-primary whitespace-pre-wrap mt-2 leading-relaxed">
          {formula.prose}
        </pre>
      )}
    </div>
  );
}
