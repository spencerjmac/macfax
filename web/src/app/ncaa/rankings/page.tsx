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
  const seasonYear = params.season ? parseInt(params.season, 10) : undefined;
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

  return (
    <div>
      {/* Page header */}
      <div className="bg-surface border-b border-ui-border">
        <div className="max-w-[1240px] mx-auto px-8 py-10 pb-[34px]">
          <p className="kicker-sport text-brand mb-[9px]">College Basketball · {meta.season}</p>
          <h1 className="font-display font-bold text-[clamp(32px,4vw,48px)] leading-none uppercase tracking-[0.005em] m-0 mb-[14px]">
            NCAA Rankings
          </h1>
          <div className="flex items-center gap-[14px] flex-wrap">
            <p className="text-[15px] text-muted m-0">
              Complete rankings for {meta.teamCount} Division I teams
            </p>
            <span className="font-mono text-[12px] text-muted-2 inline-flex items-center gap-[7px] px-[10px] py-[5px] bg-ui-surface border border-ui-border rounded-md">
              <span className="w-1.5 h-1.5 rounded-full bg-brand2" />
              Updated {new Date(meta.lastUpdated).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
            </span>
          </div>
        </div>
      </div>

      <div className="max-w-[1240px] mx-auto px-8 py-8">
        {/* Teams / Players tab */}
        <div className="border-b border-ui-border mb-6">
          <div className="flex gap-0">
            {[
              { id: 'teams',   label: 'Team Rankings', icon: BarChart3 },
              { id: 'players', label: 'Player Stats',   icon: Users    },
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

        {activeTab === 'players' ? (
          <NCAAPlayerRankingsTable data={players} seasonDisplay={meta.season} selectedSeason={seasonYear} />
        ) : (
          <RankingsTable data={teams} seasons={seasons} selectedSeason={seasonYear} isPreTournament={isPreTournament} />
        )}

        {/* Legend */}
        <div className="mt-8 p-6 bg-ui-surface border border-ui-border rounded-lg">
          <h2 className="font-display font-bold text-[16px] uppercase tracking-[0.02em] mb-[14px]">Metric Definitions</h2>
          <div className="grid md:grid-cols-2 gap-3 text-[13.5px]">
            {[
              { k: 'AdjEM', v: 'Adjusted Efficiency Margin (AdjO − AdjD). Predicted point margin vs average team on neutral court.' },
              { k: 'AdjO',  v: 'Adjusted Offensive Efficiency — points scored per 100 possessions vs average D1 defense.' },
              { k: 'AdjD',  v: 'Adjusted Defensive Efficiency — points allowed per 100 possessions vs average D1 offense.' },
              { k: 'Tempo', v: 'Adjusted possessions per 40 minutes.' },
              { k: 'eFG%',  v: 'Effective Field Goal % — accounts for 3-pointers being worth more than 2s.' },
              { k: 'TOV%',  v: 'Turnover rate per 100 possessions.' },
              { k: 'ORB%',  v: 'Offensive rebound % of available boards.' },
              { k: 'FTR',   v: 'Free throw rate — FTA per field goal attempt.' },
            ].map(d => (
              <div key={d.k} className="text-muted">
                <b className="font-mono font-semibold text-text-primary mr-1.5">{d.k}</b>{d.v}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
