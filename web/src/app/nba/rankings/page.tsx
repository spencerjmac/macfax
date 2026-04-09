import { Metadata } from 'next';
import { BarChart3, Users } from 'lucide-react';
import Link from 'next/link';
import { nbaApi } from '@/lib/nba-api';
import NBARankingsTable from '@/components/NBARankingsTable';
import NBAPlayerRankingsTable from '@/components/NBAPlayerRankingsTable';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
  title: 'NBA Rankings | macfax',
  description: 'NBA team rankings by adjusted offensive, defensive, and net rating with Four Factor Index.',
};

interface NBAPageProps {
  searchParams: Promise<{ season?: string; tab?: string }>;
}

export default async function NBARankingsPage({ searchParams }: NBAPageProps) {
  const sp = await searchParams;
  const seasonYear = sp.season ? parseInt(sp.season, 10) : undefined;
  const activeTab = sp.tab === 'players' ? 'players' : 'teams';

  const [rankings, seasons, players] = await Promise.all([
    nbaApi.getRankings(seasonYear).catch(() => []),
    nbaApi.getSeasons().catch(() => []),
    activeTab === 'players'
      ? nbaApi.getLeaguePlayers({ season: seasonYear, ordering: '-pts', min_gp: 1 }).catch(() => [])
      : Promise.resolve([]),
  ]);

  const currentSeason = seasonYear
    ? seasons.find((s) => s.year === seasonYear) ?? null
    : seasons.find((s) => s.is_current) ?? seasons[0] ?? null;

  const seasonDisplay = currentSeason?.display_name;
  const seasonParam = seasonYear ? `&season=${seasonYear}` : '';

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-text-primary">NBA Rankings</h1>
        <p className="mt-1 text-text-muted">
          Opponent-adjusted efficiency · {currentSeason?.display_name ?? 'Current season'}
        </p>
      </div>

      {/* Tab switcher */}
      <div className="border-b border-ui-border mb-6">
        <div className="flex gap-0">
          {[
            { id: 'teams', label: 'Team Rankings', icon: BarChart3 },
            { id: 'players', label: 'Player Stats', icon: Users },
          ].map(({ id, label, icon: Icon }) => (
            <Link
              key={id}
              href={`/nba/rankings?tab=${id}${seasonParam}`}
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

      {activeTab === 'teams' && rankings.length === 0 ? (
        /* Empty state — DB not yet populated */
        <div className="text-center py-20 bg-ui-card border border-ui-border rounded-lg">
          <BarChart3 className="w-12 h-12 mx-auto mb-4 text-brand/30" strokeWidth={1} />
          <p className="font-medium text-text-primary mb-2">No rankings data yet</p>
          <p className="text-sm text-text-muted max-w-md mx-auto">
            Run the following management commands to populate rankings:
          </p>
          <div className="mt-4 flex flex-col items-center gap-2 text-sm font-mono">
            <code className="bg-gray-100 px-3 py-1 rounded">python manage.py nba_sync_teams</code>
            <code className="bg-gray-100 px-3 py-1 rounded">python manage.py nba_sync_games --season 2026</code>
            <code className="bg-gray-100 px-3 py-1 rounded">python manage.py nba_compute_ratings --season 2026</code>
          </div>
        </div>
      ) : activeTab === 'teams' ? (
        <NBARankingsTable
          data={rankings}
          seasons={seasons}
          selectedSeason={currentSeason?.year}
        />
      ) : (
        /* Players tab */
        players.length === 0 ? (
          <div className="text-center py-20 bg-ui-card border border-ui-border rounded-lg">
            <Users className="w-12 h-12 mx-auto mb-4 text-brand/30" strokeWidth={1} />
            <p className="font-medium text-text-primary mb-2">No player stats yet</p>
            <p className="text-sm text-text-muted max-w-md mx-auto">
              Run the NBA ingestion pipeline first:
            </p>
            <div className="mt-4 flex flex-col items-center gap-2 text-sm font-mono">
              <code className="bg-gray-100 px-3 py-1 rounded">python manage.py nba_sync_team_logs --season 2026</code>
              <code className="bg-gray-100 px-3 py-1 rounded">python manage.py nba_compute_player_stats --season 2026</code>
            </div>
          </div>
        ) : (
          <NBAPlayerRankingsTable data={players} seasonDisplay={seasonDisplay} />
        )
      )}

      {/* Metric glossary — mirrors NCAA rankings page layout */}
      <div className="mt-8 p-6 bg-ui-surface border border-ui-border rounded-lg">
        <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wider mb-4">
          Metric Definitions
        </h2>
        <div className="grid md:grid-cols-2 gap-4 text-sm">
          <div>
            <span className="font-semibold text-text-primary">Adj Net</span>
            <span className="text-text-muted ml-2">
              Opponent-adjusted net efficiency (points per 100 possessions above or below average).
              Primary ranking metric.
            </span>
          </div>
          <div>
            <span className="font-semibold text-text-primary">Adj Off / Adj Def</span>
            <span className="text-text-muted ml-2">
              Opponent-adjusted offensive and defensive efficiency (points per 100 possessions).
            </span>
          </div>
          <div>
            <span className="font-semibold text-text-primary">Pace</span>
            <span className="text-text-muted ml-2">
              Estimated possessions per 48 minutes after opponent adjustment.
            </span>
          </div>
          <div>
            <span className="font-semibold text-text-primary">FFI</span>
            <span className="text-text-muted ml-2">
              Four Factor Index — composite of eFG%, turnover rate, rebound rate, and FT rate edges.
              Weights are provisional pending NBA backtesting.
            </span>
          </div>
          <div>
            <span className="font-semibold text-text-primary">EFG %</span>
            <span className="text-text-muted ml-2">
              Effective field goal percentage, accounting for the extra value of 3-point makes.
              Off = offensive, Def = opponent&apos;s eFG% allowed.
            </span>
          </div>
          <div>
            <span className="font-semibold text-text-primary">Turnover Rate</span>
            <span className="text-text-muted ml-2">
              Turnovers per 100 possessions. Off = own TOV rate (lower is better);
              Def = opponent TOV rate (higher is better).
            </span>
          </div>
          <div>
            <span className="font-semibold text-text-primary">Rebound %</span>
            <span className="text-text-muted ml-2">
              Offensive rebound percentage (OREB / available rebounds).
              Higher Off and lower Def is better.
            </span>
          </div>
          <div>
            <span className="font-semibold text-text-primary">FT Rate</span>
            <span className="text-text-muted ml-2">
              Free throw attempts per field goal attempt. Higher Off and lower Def is better.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
