'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import type { Team } from '@/types';
import { api } from '@/lib/api';

interface TeamSearchWidgetProps {
  currentSlug: string;
}

export function TeamSearchWidget({ currentSlug }: TeamSearchWidgetProps) {
  const router = useRouter();
  const [teams, setTeams] = useState<Team[]>([]);
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.getTeams().then(setTeams).catch(() => {});
  }, []);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const filtered = query.trim().length >= 1
    ? teams
        .filter(t => t.name.toLowerCase().includes(query.toLowerCase()))
        .slice(0, 8)
    : [];

  function handleSelect(team: Team) {
    setOpen(false);
    setQuery('');
    router.push(`/outlook/${team.slug}`);
  }

  return (
    <div ref={containerRef} className="relative mt-2">
      <input
        ref={inputRef}
        type="text"
        value={query}
        onChange={e => { setQuery(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        placeholder="Switch team…"
        className="w-48 px-3 py-1.5 rounded-lg border border-ui-border text-sm text-text-primary placeholder-text-muted bg-ui-surface focus:outline-none focus:ring-2 focus:ring-brand/40 focus:border-brand"
      />
      {open && filtered.length > 0 && (
        <div className="absolute left-0 top-full mt-1 w-64 bg-white rounded-lg border border-ui-border shadow-lg z-50 overflow-hidden">
          {filtered.map(team => (
            <button
              key={team.slug}
              onClick={() => handleSelect(team)}
              disabled={team.slug === currentSlug}
              className="w-full text-left px-4 py-2.5 text-sm hover:bg-ui-surface transition-colors border-b border-ui-border last:border-0 disabled:opacity-40 disabled:cursor-default"
            >
              {team.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
