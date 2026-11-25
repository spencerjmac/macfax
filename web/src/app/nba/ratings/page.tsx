import { Metadata } from 'next';
import { redirect } from 'next/navigation';
import { nbaApi } from '@/lib/nba-api';
import NBARankingsTable from '@/components/NBARankingsTable';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
  title: 'NBA Team Ratings | macfax',
  description: 'NBA team ratings by adjusted offensive, defensive, and net rating with Four Factor Index.',
};

interface NBAPageProps {
  searchParams: Promise<{ season?: string; tab?: string; season_type?: string }>;
}

export default async function NBARankingsPage({ searchParams }: NBAPageProps) {
  const sp = await searchParams;

  // Player ratings moved to their own route; keep old links working
  if (sp.tab === 'players') {
    const qs = new URLSearchParams();
    if (sp.season) qs.set('season', sp.season);
    if (sp.season_type) qs.set('season_type', sp.season_type);
    const query = qs.toString();
    redirect(query ? `/nba/players?${query}` : '/nba/players');
  }

  const seasonYear = sp.season ? parseInt(sp.season, 10) : undefined;
  const seasonType = sp.season_type === 'playoffs' ? 'playoffs' : 'regular';

  const [rankings, seasons] = await Promise.all([
    nbaApi.getRankings(seasonYear, seasonType).catch(() => []),
    nbaApi.getSeasons().catch(() => []),
  ]);

  const currentSeason = seasonYear
    ? seasons.find((s) => s.year === seasonYear) ?? null
    : seasons.find((s) => s.is_current) ?? seasons[0] ?? null;

  return (
    <div>
      {/* Page header */}
      <div className="bg-surface border-b border-ui-border">
        <div className="max-w-[1240px] mx-auto px-8 py-10 pb-[34px]">
          <h1 className="font-display font-bold text-[clamp(32px,4vw,48px)] leading-none uppercase tracking-[0.005em] m-0 mb-[14px]">
            NBA Team Ratings
          </h1>
          <div className="flex items-center gap-[14px] flex-wrap">
            <p className="text-[15px] text-muted m-0">
              Opponent-adjusted efficiency for all 30 teams
            </p>
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
        <NBARankingsTable
          data={rankings}
          seasons={seasons}
          selectedSeason={currentSeason?.year}
          selectedSeasonType={seasonType}
        />

        {/* Legend */}
        <div className="mt-8 p-6 bg-ui-surface border border-ui-border rounded-lg">
          <h2 className="font-display font-bold text-[16px] uppercase tracking-[0.02em] mb-[14px]">Metric Definitions</h2>
          <div className="grid md:grid-cols-2 gap-3 text-[13.5px]">
            {[
              { k: 'Adj Net',  v: 'Opponent-adjusted net efficiency (pts/100 poss above or below average). Primary rating metric.' },
              { k: 'Adj Off',  v: 'Opponent-adjusted offensive efficiency — points scored per 100 possessions.' },
              { k: 'Adj Def',  v: 'Opponent-adjusted defensive efficiency — points allowed per 100 possessions.' },
              { k: 'Pace',     v: 'Estimated possessions per 48 minutes after opponent adjustment.' },
              { k: 'FFI',      v: 'Four Factor Index — composite of eFG%, TOV rate, rebound rate, and FT rate edges. Weights from 11-season OLS regression.' },
              { k: 'eFG%',       v: 'Effective field goal %, accounting for 3-pointer value. Off = team, Def = opponent allowed.' },
              { k: 'Turnover %', v: 'Turnovers per 100 possessions. Off = own rate (lower = better); Def = opponent rate (higher = better).' },
              { k: 'Rebounding', v: 'OREB = team offensive rebound %; Def = opponent offensive rebound % allowed (lower = better).' },
              { k: 'FT Rate',    v: 'Free throw attempts per field goal attempt. Higher Off and lower Def is better.' },
              { k: 'Net',        v: 'Team rate minus opponent rate (for turnovers and rebounding, the side that favors the team); positive is better.' },
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
