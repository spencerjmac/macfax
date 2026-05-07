'use client';

import { useState, useMemo } from 'react';
import Link from 'next/link';
import { BlockMath } from 'react-katex';
import type { GlossaryTerm, GlossaryCategory } from '@/lib/glossaryTypes';
import { CATEGORY_LABELS } from '@/lib/glossaryTypes';

interface GlossaryTableProps {
  terms: GlossaryTerm[];
}

export default function GlossaryTable({ terms }: GlossaryTableProps) {
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<GlossaryCategory | 'all'>('all');

  const categories = useMemo<GlossaryCategory[]>(() => {
    const seen = new Set<GlossaryCategory>();
    terms.forEach(t => seen.add(t.category));
    return Array.from(seen);
  }, [terms]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return terms.filter(t => {
      const matchesSearch =
        !q ||
        t.term.toLowerCase().includes(q) ||
        t.shortDefinition.toLowerCase().includes(q) ||
        t.detailedDefinition.toLowerCase().includes(q) ||
        (t.aliases ?? []).some(a => a.toLowerCase().includes(q));
      const matchesCategory = categoryFilter === 'all' || t.category === categoryFilter;
      return matchesSearch && matchesCategory;
    });
  }, [terms, search, categoryFilter]);

  return (
    <div className="space-y-6">
      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
        <input
          type="text"
          placeholder="Search metrics..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="flex-1 max-w-md px-4 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-brand"
        />
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setCategoryFilter('all')}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              categoryFilter === 'all'
                ? 'bg-brand text-white'
                : 'bg-ui-surface border border-ui-border text-text-muted hover:text-text-primary'
            }`}
          >
            All
          </button>
          {categories.map(cat => (
            <button
              key={cat}
              onClick={() => setCategoryFilter(cat)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                categoryFilter === cat
                  ? 'bg-brand text-white'
                  : 'bg-ui-surface border border-ui-border text-text-muted hover:text-text-primary'
              }`}
            >
              {CATEGORY_LABELS[cat]}
            </button>
          ))}
        </div>
      </div>

      <p className="text-xs text-text-muted">{filtered.length} term{filtered.length !== 1 ? 's' : ''}</p>

      {/* Term cards */}
      <div className="space-y-5">
        {filtered.map(term => (
          <div
            key={term.id}
            id={term.id}
            className="p-6 bg-ui-card border border-ui-border rounded-xl hover:border-brand/40 transition-colors"
          >
            {/* Header */}
            <div className="flex items-start justify-between gap-3 mb-1">
              <div>
                <h3 className="text-xl font-bold text-text-primary">{term.term}</h3>
                {term.aliases && term.aliases.length > 0 && (
                  <span className="text-xs text-text-muted font-mono">
                    {term.aliases.join(' · ')}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="text-xs px-2 py-1 rounded bg-ui-surface border border-ui-border text-text-muted uppercase tracking-wide">
                  {CATEGORY_LABELS[term.category]}
                </span>
                {term.isHigherBetter === true && (
                  <span className="text-xs px-2 py-1 rounded bg-success/10 text-success font-medium">↑ Higher</span>
                )}
                {term.isHigherBetter === false && (
                  <span className="text-xs px-2 py-1 rounded bg-secondary/10 text-secondary font-medium">↓ Lower</span>
                )}
              </div>
            </div>

            {/* Definition */}
            <p className="text-text-muted text-sm mt-3">{term.detailedDefinition}</p>

            {/* Formula */}
            {term.formula && (
              <div className="bg-ui-surface border border-ui-border rounded-lg p-4 mt-4 overflow-x-auto">
                <div className="text-xs text-text-muted font-medium mb-2 uppercase tracking-wide">Formula</div>
                <BlockMath math={term.formula.display} />
                {term.formula.prose && (
                  <p className="text-xs text-text-muted mt-2">{term.formula.prose}</p>
                )}
              </div>
            )}

            {/* Interpretation */}
            {term.howToInterpret && (
              <div className="mt-4">
                <div className="text-xs text-text-muted font-medium uppercase tracking-wide mb-1">How to Interpret</div>
                <p className="text-sm text-text-primary">{term.howToInterpret}</p>
              </div>
            )}

            {/* Footer: methodology link + related terms */}
            {(term.methodologySlug || (term.relatedTerms && term.relatedTerms.length > 0)) && (
              <div className="flex items-center justify-between mt-4 pt-3 border-t border-ui-border">
                {term.relatedTerms && term.relatedTerms.length > 0 && (
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-xs text-text-muted">Related:</span>
                    {term.relatedTerms.map(rid => (
                      <a
                        key={rid}
                        href={`#${rid}`}
                        className="text-xs px-2 py-0.5 rounded bg-ui-surface border border-ui-border text-text-muted hover:text-text-primary transition-colors"
                      >
                        {rid}
                      </a>
                    ))}
                  </div>
                )}
                {term.methodologySlug && (
                  <Link
                    href={`/methodology/${term.methodologySlug}`}
                    className="text-xs text-brand hover:underline ml-auto"
                  >
                    Full methodology →
                  </Link>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {filtered.length === 0 && (
        <div className="text-center py-12 text-text-muted">
          No terms found matching your search.
        </div>
      )}
    </div>
  );
}
