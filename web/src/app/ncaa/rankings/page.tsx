import { Metadata } from 'next';
import { BarChart3, Users } from 'lucide-react';
import Link from 'next/link';
import { getAllTeams, getAllSeasons, getMetadata } from '@/lib/data';
import { api } from '@/lib/api';
import RankingsTable from '@/components/RankingsTable';
import NCAAPlayerRankingsTable from '@/components/NCAAPlayerRankingsTable';

// Force dynamic rendering - never cache this page
export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
  title: 'Rankings | macfax',
  description: 'Complete NCAA Division I men\'s basketball rankings with adjusted efficiency metrics, four factors, and advanced statistics.',
};

interface RankingsPageProps {
  searchParams: Promise<{ season?: string; tab?: string; pre_tournament?: string }>;
}

export default async function RankingsPage({ searchParams }: RankingsPageProps) {
  const params = await searchParams;
  const seasonYear = params.season ? parseInt(params.season, 10) : 2027;
  const activeTab = params.tab === 'players' ? 'players' : 'teams';
  const isPreTournament = params.pre_tournament === 'true';

  const [teams, seasons, meta, players] = await Promise.all([
    getAllTeams(seasonYear, isPreTournament),
    getAllSeasons(),
    getMetadata(seasonYear, isPreTournament),
    activeTab === 'players'
      ? api.getLeaguePlayers({ season: seasonYear, ordering: '-pts', min_gp: 5 }).catch(() => [])
      : Promise.resolve([]),
  ]);

  const seasonParam = seasonYear ? `&season=${seasonYear}` : '';
  const preTourneyParam = isPreTournament ? `&pre_tournament=true` : '';
  const displaySeason = meta.season !== 'N/A' ? meta.season : `${seasonYear - 1}-${String(seasonYear).slice(2)}`;
  const pageTitle = activeTab === 'players' ? 'NCAA Player Rankings' : 'NCAA Rankings';
  const pageSubtitle = activeTab === 'players'
    ? 'Player leaderboards across BPR impact, traditional production, and four-factor impact, with filters for season, minutes, conference, and ranking mode.'
    : 'Complete team and player rankings powered by opponent-adjusted ratings, four factors, resume metrics, and sortable season filters.';

  return (
    <div>
      {/* Page header */}
      <div className="bg-surface border-b border-ui-border">
        <div className="max-w-[1240px] mx-auto px-8 py-10 pb-[34px]">
          <p className="kicker-sport text-brand mb-[9px]">College Basketball · {displaySeason}</p>
          <h1 className="font-display font-bold text-[clamp(32px,4vw,48px)] leading-none uppercase tracking-[0.005em] m-0 mb-[14px]">
            {pageTitle}
          </h1>
          <div className="flex items-center gap-[14px] flex-wrap">
            <p className="text-[15px] text-muted m-0">
              {pageSubtitle}
            </p>
            {teams.length > 0 ? (
              <span className="font-mono text-[12px] text-muted-2 inline-flex items-center gap-[7px] px-[10px] py-[5px] bg-ui-surface border border-ui-border rounded-md">
                <span className="w-1.5 h-1.5 rounded-full bg-brand2" />
                Updated {new Date(meta.lastUpdated).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
              </span>
            ) : seasonYear === 2027 ? (
              <span className="text-sm text-text-muted">Preseason · First games Nov 2, 2026</span>
            ) : null}
          </div>
        </div>
      </div>

      <div className="max-w-[1240px] mx-auto px-8 py-8">
        {/* Teams / Players tab */}
        <div className="border-b border-ui-border mb-6">
          <div className="flex gap-0">
            {[
              { id: 'teams',   label: 'Team Rankings', icon: BarChart3 },
              { id: 'players', label: 'Player Rankings', icon: Users    },
            ].map(({ id, label, icon: Icon }) => (
              <Link
                key={id}
                href={`/ncaa/rankings?tab=${id}${seasonParam}${preTourneyParam}`}
                className={`px-5 py-3 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${
                  activeTab === id
                    ? 'border-brand text-brand'
                    : 'border-transparent text-text-muted hover:text-text-primary'
                }`}
              >
                <Icon className="w-4 h-4" />
                {label}
              </Link>
            ))}
          </div>
        </div>

        {teams.length === 0 && seasonYear === 2027 && (
          <div className="mb-6 rounded-lg border border-ui-border bg-ui-surface px-5 py-4 text-sm text-text-muted">
            2026–27 NCAA game-based ratings will be available after games begin and the data pipeline runs.
            Until then, explore the <Link href="/ncaa/outlook" className="text-brand font-semibold hover:underline">roster outlook</Link>.
          </div>
        )}

        {activeTab === 'players' ? (
          <NCAAPlayerRankingsTable data={players} seasonDisplay={displaySeason} selectedSeason={seasonYear} />
        ) : (
          <RankingsTable data={teams} seasons={seasons} selectedSeason={seasonYear} isPreTournament={isPreTournament} />
        )}
      </div>
    </div>
  );
}
