'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { SeasonInfo } from '@/types';

interface SeasonSelectProps {
  value: number;
  onChange: (season: number) => void;
  className?: string;
}

export default function SeasonSelect({ value, onChange, className }: SeasonSelectProps) {
  const [seasons, setSeasons] = useState<SeasonInfo[]>([]);

  useEffect(() => {
    api.getSeasons().then(setSeasons).catch(() => {});
  }, []);

  if (seasons.length <= 1) return null;

  return (
    <div className="flex items-center gap-2">
      <label className="text-sm font-medium text-text-muted">Season:</label>
      <select
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className={
          className ??
          'text-sm border border-ui-border rounded px-2 py-1.5 bg-ui-surface focus:outline-none focus:ring-2 focus:ring-brand/50'
        }
      >
        {seasons.map((s) => (
          <option key={s.year} value={s.year}>
            {s.display_name}{s.is_current ? ' (Current)' : ''}
          </option>
        ))}
      </select>
    </div>
  );
}
