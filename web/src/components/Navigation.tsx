'use client';

import { useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { usePathname } from 'next/navigation';
import { ChevronDown } from 'lucide-react';
import clsx from 'clsx';

type NavLink = { label: string; href: string };
type NavSection = { label: string; href: string; items: NavLink[] };

const NAV_ITEMS: NavSection[] = [
  {
    label: 'NCAA',
    href: '/ncaa',
    items: [
      { label: 'Overview', href: '/ncaa' },
      { label: 'Rankings', href: '/ncaa/rankings' },
      { label: 'Matchup Tool', href: '/ncaa/matchup' },
      { label: 'Roster Outlook', href: '/ncaa/outlook' },
      { label: 'Visualizations', href: '/ncaa/viz' },
      { label: 'Glossary', href: '/ncaa/glossary' },
      { label: 'Accuracy', href: '/validation' },
    ],
  },
  {
    label: 'NBA',
    href: '/nba',
    items: [
      { label: 'Overview', href: '/nba' },
      { label: 'Rankings', href: '/nba/rankings' },
      { label: 'Team Outlooks', href: '/nba/teams' },
      { label: 'Matchup Tool', href: '/nba/matchup' },
      { label: 'Player Value', href: '/nba/player-value' },
      { label: 'Compare', href: '/nba/compare' },
      { label: 'Visualizations', href: '/nba/viz' },
      { label: 'Model Health', href: '/nba/model-health' },
    ],
  },

];

function isSectionActive(pathname: string | null, section: NavSection): boolean {
  return !!pathname?.startsWith(section.href);
}

function isSubItemActive(pathname: string | null, item: NavLink): boolean {
  if (pathname === item.href) return true;
  const segments = item.href.split('/').filter(Boolean);
  return segments.length > 1 && !!pathname?.startsWith(item.href);
}

export default function Navigation() {
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <nav className="bg-bg text-textOnDark sticky top-0 z-50 border-b-4 border-brand">
      <div className="container mx-auto px-4">
        <div className="flex items-center justify-between">
          {/* Logo */}
          <Link href="/" className="flex items-center space-x-2">
            {/* Desktop logo - using mark until wide wordmark is added */}
            <div className="hidden md:flex items-center space-x-4">
              <Image
                src="/brand/macfax-logo-v4.png"
                alt="macfax"
                width={220}
                height={220}
                priority
                className="h-20 w-auto object-contain"
              />
              <span className="text-4xl font-bold">macfax</span>
            </div>
            {/* Mobile logo */}
            <div className="md:hidden flex items-center space-x-3">
              <Image
                src="/brand/macfax-logo-v4.png"
                alt="macfax"
                width={160}
                height={160}
                priority
                className="h-14 w-auto object-contain"
              />
              <span className="text-2xl font-bold">macfax</span>
            </div>
          </Link>

          {/* Nav Links */}
          <div className="hidden md:flex items-center gap-1">
            {NAV_ITEMS.map((section) => (
              <div key={section.href} className="relative group">
                <Link
                  href={section.href}
                  className={clsx(
                    'flex items-center gap-1 px-4 py-2 rounded transition-colors font-medium text-lg',
                    isSectionActive(pathname, section)
                      ? 'bg-brand text-white'
                      : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                  )}
                >
                  {section.label}
                  <ChevronDown className="w-4 h-4" />
                </Link>

                {/* Flush against trigger (top-full, no gap) to avoid hover dead zone */}
                <div className="absolute left-0 top-full hidden group-hover:block">
                  <div className="bg-bg border border-gray-700 rounded-b-md shadow-lg py-2 min-w-[220px]">
                    {section.items.map((item) => (
                      <Link
                        key={item.href}
                        href={item.href}
                        className={clsx(
                          'block px-4 py-2 text-base transition-colors',
                          isSubItemActive(pathname, item)
                            ? 'bg-brand text-white'
                            : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                        )}
                      >
                        {item.label}
                      </Link>
                    ))}
                  </div>
                </div>
              </div>
            ))}

            {/* Global Links */}
            <div className="w-px h-6 bg-gray-700 mx-6" />
            <Link
              href="/methodology"
              className={clsx(
                'px-4 py-2 rounded transition-colors font-medium text-lg',
                pathname?.startsWith('/methodology')
                  ? 'bg-brand text-white'
                  : 'text-gray-300 hover:bg-gray-800 hover:text-white'
              )}
            >
              Methodology
            </Link>
            <Link
              href="/about"
              className={clsx(
                'px-4 py-2 rounded transition-colors font-medium text-lg',
                pathname === '/about'
                  ? 'bg-brand text-white'
                  : 'text-gray-300 hover:bg-gray-800 hover:text-white'
              )}
            >
              About
            </Link>
          </div>

          {/* Mobile navigation */}
          <button
            type="button"
            className="md:hidden p-2"
            aria-label={mobileMenuOpen ? 'Close menu' : 'Open menu'}
            aria-controls="mobile-navigation"
            aria-expanded={mobileMenuOpen}
            onClick={() => setMobileMenuOpen(open => !open)}
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
        </div>
        {mobileMenuOpen && (
          <div id="mobile-navigation" className="md:hidden pb-5 space-y-4">
            {NAV_ITEMS.map(section => (
              <div key={section.href}>
                <Link href={section.href} onClick={() => setMobileMenuOpen(false)} className="block font-bold text-brand2 py-2">{section.label}</Link>
                <div className="grid grid-cols-2 gap-2">
                  {section.items.map(item => (
                    <Link key={item.href} href={item.href} onClick={() => setMobileMenuOpen(false)} className="text-sm text-gray-200 py-1">{item.label}</Link>
                  ))}
                </div>
              </div>
            ))}
            <div className="flex gap-6 border-t border-gray-700 pt-4">
              <Link href="/methodology" onClick={() => setMobileMenuOpen(false)} className="text-sm">Methodology</Link>
              <Link href="/about" onClick={() => setMobileMenuOpen(false)} className="text-sm">About</Link>
            </div>
          </div>
        )}
      </div>
    </nav>
  );
}
