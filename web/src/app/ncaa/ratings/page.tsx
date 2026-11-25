import { Metadata } from 'next';
import { redirect } from 'next/navigation';
import { getAllTeams, getAllSeasons, getMetadata } from '@/lib/data';
import RankingsTable from '@/components/RankingsTable';

// Force dynamic rendering - never cache this page
export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
  title: 'NCAA Team Ratings | macfax',
  description: 'Complete NCAA Division I men\'s basketball team ratings with adjusted efficiency metrics, four factors, and advanced statistics.',
};

interface RankingsPageProps {
  searchParams: Promise<{ season?: string; tab?: string; pre_tournament?: string }>;
}

export default async function RankingsPage({ searchParams }: RankingsPageProps) {
  const params = await searchParams;

  // Player ratings moved to their own route; keep old links working
  if (params.tab === 'players') {
    redirect(params.season ? `/ncaa/players?season=${encodeURIComponent(params.season)}` : '/ncaa/players');
  }

  const seasonYear = params.season ? parseInt(params.season, 10) : undefined;
  const isPreTournament = params.pre_tournament === 'true';

  const [teams, seasons, meta] = await Promise.all([
    getAllTeams(seasonYear, isPreTournament),
    getAllSeasons(),
    getMetadata(seasonYear, isPreTournament),
  ]);

  return (
    <div>
      {/* Page header */}
      <div className="bg-surface border-b border-ui-border">
        <div className="max-w-[1240px] mx-auto px-8 py-10 pb-[34px]">
          <h1 className="font-display font-bold text-[clamp(32px,4vw,48px)] leading-none uppercase tracking-[0.005em] m-0 mb-[14px]">
            NCAA Team Ratings
          </h1>
          <div className="flex items-center gap-[14px] flex-wrap">
            <p className="text-[15px] text-muted m-0">
              Complete team ratings powered by opponent-adjusted ratings, four factors, resume metrics, and sortable season filters.
            </p>
            <span className="font-mono text-[12px] text-muted-2 inline-flex items-center gap-[7px] px-[10px] py-[5px] bg-ui-surface border border-ui-border rounded-md">
              <span className="w-1.5 h-1.5 rounded-full bg-brand2" />
              Updated {new Date(meta.lastUpdated).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
            </span>
          </div>
        </div>
      </div>

      <div className="max-w-[1240px] mx-auto px-8 py-8">
        <RankingsTable data={teams} seasons={seasons} selectedSeason={seasonYear} isPreTournament={isPreTournament} />
      </div>
    </div>
  );
}
