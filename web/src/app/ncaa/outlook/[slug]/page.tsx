import { Metadata } from 'next';
import { notFound } from 'next/navigation';
import RosterOutlookPage from '@/components/outlook/RosterOutlookPage';
import { TeamSearchWidget } from '@/components/outlook/TeamSearchWidget';
import { getRosterOutlookOrNull } from '@/lib/data';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

interface OutlookPageProps {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ season?: string }>;
}

export async function generateMetadata({ params }: OutlookPageProps): Promise<Metadata> {
  const { slug } = await params;
  const data = await getRosterOutlookOrNull(slug);
  if (!data) return { title: 'Roster Outlook | macfax' };
  return {
    title: `${data.team.name} Roster Outlook ${data.season.projected_season_year} | macfax`,
    description: `${data.team.name} projected ${data.season.projected_season_year} roster outlook: rankings, player projections, fit grades, and scenario editing.`,
  };
}

export default async function OutlookPage({ params, searchParams }: OutlookPageProps) {
  const { slug } = await params;
  const { season } = await searchParams;
  const data = await getRosterOutlookOrNull(slug, season);

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
        <TeamSearchWidget currentSlug={slug} />
      </div>

      <RosterOutlookPage data={data} />
    </div>
  );
}
