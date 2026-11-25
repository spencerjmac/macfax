import { Metadata } from 'next';
import { getAllSeasons, getMetadata } from '@/lib/data';
import { api } from '@/lib/api';
import NCAAPlayerRankingsTable from '@/components/NCAAPlayerRankingsTable';

// Force dynamic rendering - never cache this page
export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
  title: 'NCAA Player Ratings | macfax',
  description: 'NCAA Division I men\'s basketball player ratings with BPR impact, traditional production, and four-factor impact.',
};

interface PlayersPageProps {
  searchParams: Promise<{ season?: string }>;
}

export default async function NCAAPlayersPage({ searchParams }: PlayersPageProps) {
  const params = await searchParams;
  const seasonYear = params.season ? parseInt(params.season, 10) : undefined;

  const [seasons, meta, players] = await Promise.all([
    getAllSeasons(),
    getMetadata(seasonYear),
    api.getLeaguePlayers({ season: seasonYear, ordering: '-pts', min_gp: 1 }).catch(() => []),
  ]);

  return (
    <div>
      {/* Page header */}
      <div className="bg-surface border-b border-ui-border">
        <div className="max-w-[1240px] mx-auto px-8 py-10 pb-[34px]">
          <h1 className="font-display font-bold text-[clamp(32px,4vw,48px)] leading-none uppercase tracking-[0.005em] m-0 mb-[14px]">
            NCAA Player Ratings
          </h1>
          <div className="flex items-center gap-[14px] flex-wrap">
            <p className="text-[15px] text-muted m-0">
              BPR impact, box-score production, and four-factor impact for every D-I player.
            </p>
            <span className="font-mono text-[12px] text-muted-2 inline-flex items-center gap-[7px] px-[10px] py-[5px] bg-ui-surface border border-ui-border rounded-md">
              <span className="w-1.5 h-1.5 rounded-full bg-brand2" />
              Updated {new Date(meta.lastUpdated).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
            </span>
          </div>
        </div>
      </div>

      <div className="max-w-[1240px] mx-auto px-8 py-8">
        <NCAAPlayerRankingsTable data={players} selectedSeason={seasonYear} seasons={seasons} />
      </div>
    </div>
  );
}
