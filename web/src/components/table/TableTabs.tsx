'use client';

import clsx from 'clsx';

export interface TableTab<T extends string> {
  id: T;
  label: string;
  /** Native tooltip on the button (optional). */
  title?: string;
}

interface TableTabsProps<T extends string> {
  tabs: TableTab<T>[];
  active: T;
  onChange: (id: T) => void;
  /** 'md' = the table's view toggle; 'sm' = a secondary option row (e.g. ratings mode). */
  size?: 'md' | 'sm';
}

const SIZES = {
  md: { wrap: 'p-[3px]', pad: 'px-[14px] py-2', text: 'text-[13px]' },
  sm: { wrap: 'p-[2px]', pad: 'px-[10px] py-1', text: 'text-[11px]' },
} as const;

/** Segmented control used above the ratings tables: ink pill for the active tab, Oswald caps. */
export default function TableTabs<T extends string>({ tabs, active, onChange, size = 'md' }: TableTabsProps<T>) {
  const s = SIZES[size];
  return (
    <div className={clsx('inline-flex max-w-full overflow-x-auto no-scrollbar bg-surface border border-ui-border rounded-lg', s.wrap)}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          title={tab.title}
          onClick={() => onChange(tab.id)}
          className={clsx(
            // Class order matches the original team-table toggle so its markup is unchanged
            `shrink-0 whitespace-nowrap ${s.pad} rounded-md font-display font-semibold ${s.text} tracking-[0.06em] uppercase transition-all`,
            active === tab.id
              ? 'bg-ink text-white'
              : 'text-muted hover:text-text-primary',
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
