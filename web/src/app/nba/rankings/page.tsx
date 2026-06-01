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
  searchParams: Promise<{ season?: string; tab?: string; season_type?: string }>;
}

export default async function NBARankingsPage({ searchParams }: NBAPageProps) {
  const sp = await searchParams;
  const seasonYear = sp.season ? parseInt(sp.season, 10) : undefined;
  const activeTab = sp.tab === 'players' ? 'players' : 'teams';
  const seasonType = sp.season_type === 'playoffs' ? 'playoffs' : 'regular';

  const [rankings, seasons, players] = await Promise.all([
    nbaApi.getRankings(seasonYear, seasonType).catch(() => []),
    nbaApi.getSeasons().catch(() => []),
    activeTab === 'players'
      ? nbaApi.getLeaguePlayers({ season: seasonYear, ordering: '-pts', min_gp: 1, season_type: seasonType }).catch(() => [])
      : Promise.resolve([]),
  ]);

  const currentSeason = seasonYear
    ? seasons.find((s) => s.year === seasonYear) ?? null
    : seasons.find((s) => s.is_current) ?? seasons[0] ?? null;

  const seasonDisplay = currentSeason?.display_name;
  const seasonParam = seasonYear ? `&season=${seasonYear}` : '';
  const seasonTypeParam = seasonType === 'playoffs' ? `&season_type=playoffs` : '';

  return (
    <div>
      {/* Page header */}
      <div className="bg-surface border-b border-ui-border">
        <div className="max-w-[1240px] mx-auto px-8 py-10 pb-[34px]">
          <p className="kicker-sport text-brand mb-[9px]">NBA · {currentSeason?.display_name ?? 'Current season'}</p>
          <h1 className="font-display font-bold text-[clamp(32px,4vw,48px)] leading-none uppercase tracking-[0.005em] m-0 mb-[14px]">
            NBA Rankings
          </h1>
          <div className="flex items-center gap-[14px] flex-wrap">
            <p className="text-[15px] text-muted m-0">Opponent-adjusted efficiency for all 30 teams</p>
            {rankings.length > 0 && (
              <span className="font-mono text-[12px] text-muted-2 inline-flex items-center gap-[7px] px-[10px] py-[5px] bg-ui-surface border border-ui-border rounded-md">
                <span className="w-1.5 h-1.5 rounded-full bg-brand2" />
                Live
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="max-w-[1240px] mx-auto px-8 py-8">
        {/* Tab switcher */}
        <div className="border-b border-ui-border mb-6">
          <div className="flex gap-0">
            {[
              { id: 'teams', label: 'Team Rankings', icon: BarChart3 },
              { id: 'players', label: 'Player Stats', icon: Users },
            ].map(({ id, label, icon: Icon }) => (
              <Link
                key={id}
                href={`/nba/rankings?tab=${id}${seasonParam}${seasonTypeParam}`}
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
          selectedSeasonType={seasonType}
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
          <NBAPlayerRankingsTable data={players} seasonDisplay={seasonDisplay} seasonType={seasonType} />
        )
      )}

        {/* Legend */}
        <div className="mt-8 p-6 bg-ui-surface border border-ui-border rounded-lg">
          <h2 className="font-display font-bold text-[16px] uppercase tracking-[0.02em] mb-[14px]">Metric Definitions</h2>
          <div className="grid md:grid-cols-2 gap-3 text-[13.5px]">
            {[
              { k: 'Adj Net',  v: 'Opponent-adjusted net efficiency (pts/100 poss above or below average). Primary ranking metric.' },
              { k: 'Adj Off',  v: 'Opponent-adjusted offensive efficiency — points scored per 100 possessions.' },
              { k: 'Adj Def',  v: 'Opponent-adjusted defensive efficiency — points allowed per 100 possessions.' },
              { k: 'Pace',     v: 'Estimated possessions per 48 minutes after opponent adjustment.' },
              { k: 'FFI',      v: 'Four Factor Index — composite of eFG%, TOV rate, rebound rate, and FT rate edges. Weights from 11-season OLS regression.' },
              { k: 'EFG %',    v: 'Effective field goal %, accounting for 3-pointer value. Off = team, Def = opponent allowed.' },
              { k: 'TOV Rate', v: 'Turnovers per 100 possessions. Off = own rate (lower = better); Def = opponent rate (higher = better).' },
              { k: 'FT Rate',  v: 'Free throw attempts per field goal attempt. Higher Off and lower Def is better.' },
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
