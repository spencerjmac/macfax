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
  searchParams: Promise<{ season?: string; tab?: string }>;
}

export default async function RankingsPage({ searchParams }: RankingsPageProps) {
  const params = await searchParams;
  const seasonYear = params.season ? parseInt(params.season, 10) : undefined;
  const activeTab = params.tab === 'players' ? 'players' : 'teams';

  const [teams, seasons, meta, players] = await Promise.all([
    getAllTeams(seasonYear),
    getAllSeasons(),
    getMetadata(seasonYear),
    activeTab === 'players'
      ? api.getLeaguePlayers({ season: seasonYear, ordering: '-pts', min_gp: 5 }).catch(() => [])
      : Promise.resolve([]),
  ]);

  const seasonParam = seasonYear ? `&season=${seasonYear}` : '';

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-4xl font-bold mb-2">NCAA Rankings</h1>
        <p className="text-text-muted">
          Complete rankings for {meta.teamCount} NCAA Division I teams &mdash; {meta.season}
          <span className="ml-2 text-sm">
            Last updated: {new Date(meta.lastUpdated).toLocaleDateString()}
          </span>
        </p>
      </div>

      {/* Tab switcher */}
      <div className="border-b border-ui-border mb-6">
        <div className="flex gap-0">
          {[
            { id: 'teams',   label: 'Team Rankings', icon: BarChart3 },
            { id: 'players', label: 'Player Stats',   icon: Users    },
          ].map(({ id, label, icon: Icon }) => (
            <Link
              key={id}
              href={`/rankings?tab=${id}${seasonParam}`}
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

      {/* Rankings Table / Player Table */}
      {activeTab === 'players' ? (
        <NCAAPlayerRankingsTable data={players} seasonDisplay={meta.season} />
      ) : (
        <RankingsTable data={teams} seasons={seasons} selectedSeason={seasonYear} />
      )}

      {/* Legend */}
      <div className="mt-8 p-6 bg-ui-surface border border-ui-border rounded-lg">
        <h2 className="font-bold text-lg mb-4">Metric Definitions</h2>
        <div className="grid md:grid-cols-2 gap-4 text-sm">
          <div>
            <strong className="text-brand-orange">AdjEM:</strong> Adjusted Efficiency Margin 
            (AdjO - AdjD), the predicted point margin vs average team on neutral court
          </div>
          <div>
            <strong className="text-success">AdjO:</strong> Adjusted Offensive Efficiency, 
            points scored per 100 possessions vs average D1 defense
          </div>
          <div>
            <strong className="text-secondary">AdjD:</strong> Adjusted Defensive Efficiency, 
            points allowed per 100 possessions vs average D1 offense
          </div>
          <div>
            <strong>Tempo:</strong> Adjusted possessions per 40 minutes
          </div>
          <div>
            <strong>eFG%:</strong> Effective Field Goal Percentage 
            (FG% adjusted for 3-pointers being worth more)
          </div>
          <div>
            <strong>TOV%:</strong> Turnover percentage 
            (turnovers per 100 plays)
          </div>
          <div>
            <strong>ORB%:</strong> Offensive Rebound percentage 
            (% of available offensive rebounds secured)
          </div>
          <div>
            <strong>FTR:</strong> Free Throw Rate 
            (free throws attempted per field goal attempt)
          </div>
        </div>
      </div>
    </div>
  );
}
