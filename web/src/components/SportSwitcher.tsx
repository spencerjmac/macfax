'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import clsx from 'clsx';

const SPORTS = [
  { id: 'ncaa', label: 'NCAA', href: '/ncaa/rankings' },
  { id: 'nba',  label: 'NBA',  href: '/nba/rankings' },
] as const;

export default function SportSwitcher() {
  const pathname = usePathname();
  const isNCAA = pathname?.startsWith('/ncaa');
  const isNBA = pathname?.startsWith('/nba');
  const activeSport = isNBA ? 'nba' : (isNCAA ? 'ncaa' : null);

  return (
    <div className="flex items-center rounded-md border border-gray-700 divide-x divide-gray-700">
      {SPORTS.map((sport, index) => (
        <Link
          key={sport.id}
          href={sport.href}
          className={clsx(
            'px-4 py-2 text-lg font-medium transition-colors',
            index === 0 && 'rounded-l-sm',
            index === SPORTS.length - 1 && 'rounded-r-sm',
            activeSport === sport.id
              ? 'bg-brand text-white'
              : 'bg-transparent text-gray-400 hover:text-white hover:bg-gray-800'
          )}
        >
          {sport.label}
        </Link>
      ))}
    </div>
  );
}
