import { Metadata } from 'next';
import { notFound } from 'next/navigation';
import type { RosterOutlookData } from '@/types/outlook';
import RosterOutlookPage from '@/components/outlook/RosterOutlookPage';
import { TeamSearchWidget } from '@/components/outlook/TeamSearchWidget';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

interface OutlookPageProps {
  params: { slug: string };
  searchParams: { season?: string };
}

async function fetchOutlook(slug: string, season?: string): Promise<RosterOutlookData | null> {
  // Build-phase guard
  if (process.env.NEXT_PHASE === 'phase-production-build') return null;

  const base = (process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
  const params = season ? `?season=${season}` : '';
  try {
    const res = await fetch(`${base}/api/outlook/${slug}/${params}`, { cache: 'no-store' });
    if (!res.ok) return null;
    return (await res.json()) as RosterOutlookData;
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: OutlookPageProps): Promise<Metadata> {
  const data = await fetchOutlook(params.slug);
  if (!data) return { title: 'Roster Outlook | macfax' };
  return {
    title: `${data.team.name} Roster Outlook ${data.season.projected_season_year} | macfax`,
    description: `${data.team.name} projected ${data.season.projected_season_year} roster outlook: rankings, player projections, fit grades, and scenario editing.`,
  };
}

export default async function OutlookPage({ params, searchParams }: OutlookPageProps) {
  const data = await fetchOutlook(params.slug, searchParams.season);

  if (!data) notFound();

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Page header */}
      <div className="mb-6 flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">
            {data.team.name} — Roster Outlook
          </h1>
          <p className="text-sm text-text-muted mt-1">
            Projected {data.season.projected_season_year} preseason outlook ·{' '}
            Based on {data.season.year} season data
          </p>
        </div>
        <TeamSearchWidget currentSlug={params.slug} />
      </div>

      <RosterOutlookPage data={data} />
    </div>
  );
}
