'use client';

import Link from 'next/link';
import Image from 'next/image';
import { usePathname } from 'next/navigation';
import clsx from 'clsx';

const navItems = [
  { href: '/rankings', label: 'Rankings' },
  { href: '/matchup', label: 'Matchup' },
  { href: '/viz', label: 'Visualizations' },
  { href: '/glossary', label: 'Glossary' },
  { href: '/about', label: 'About' },
];

export default function Navigation() {
  const pathname = usePathname();
  
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
          <div className="hidden md:flex items-center space-x-1">
            {navItems.map((item) => {
              const isActive = pathname === item.href || 
                (item.href === '/viz' && pathname?.startsWith('/viz'));
              
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={clsx(
                    'px-4 py-2 rounded transition-colors font-medium text-lg',
                    isActive
                      ? 'bg-brand text-white'
                      : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>
          
          {/* Mobile menu button (placeholder) */}
          <button className="md:hidden p-2">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
        </div>
      </div>
    </nav>
  );
}
