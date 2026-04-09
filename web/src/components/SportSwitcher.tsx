'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import clsx from 'clsx';

const SPORTS = [
  { id: 'ncaa', label: 'NCAA', href: '/' },
  { id: 'nba',  label: 'NBA',  href: '/nba' },
] as const;

export default function SportSwitcher() {
  const pathname = usePathname();
  const isNBA = pathname?.startsWith('/nba');
  const activeSport = isNBA ? 'nba' : 'ncaa';

  return (
    <div className="flex items-center bg-gray-900 rounded-md p-0.5 border border-gray-700">
      {SPORTS.map((sport) => (
        <Link
          key={sport.id}
          href={sport.href}
          className={clsx(
            'px-3 py-1 rounded text-sm font-semibold transition-colors',
            activeSport === sport.id
              ? 'bg-brand text-white'
              : 'text-gray-400 hover:text-white'
          )}
        >
          {sport.label}
        </Link>
      ))}
    </div>
  );
}
