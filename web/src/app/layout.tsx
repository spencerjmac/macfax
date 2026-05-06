import type { Metadata } from 'next';
import { Inter, IBM_Plex_Mono } from 'next/font/google';
import './globals.css';
import Navigation from '@/components/Navigation';
import Footer from '@/components/Footer';

const inter = Inter({ 
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
});

const ibmPlexMono = IBM_Plex_Mono({ 
  weight: ['400', '500', '600'],
  subsets: ['latin'],
  variable: '--font-ibm-plex-mono',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'macfax | College Basketball Analytics',
  description: 'College basketball analytics: efficiency, four factors, matchup forecasts, and visualizations.',
  keywords: ['college basketball', 'analytics', 'statistics', 'efficiency', 'NCAA', 'macfax'],
  icons: {
    icon: '/brand/macfax-logo-v4.png',
    shortcut: '/brand/macfax-logo-v4.png',
    apple: '/brand/macfax-logo-v4.png',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} ${ibmPlexMono.variable}`}>
      <body className="min-h-screen flex flex-col" suppressHydrationWarning>
        <Navigation />
        <main className="flex-1">
          {children}
        </main>
        <Footer />
      </body>
    </html>
  );
}
