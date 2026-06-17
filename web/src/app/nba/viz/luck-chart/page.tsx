import { Metadata } from 'next';
import Link from 'next/link';
import { api } from '@/lib/api';
import { nbaApi } from '@/lib/nba-api';
import NBALuckChart from '@/components/NBALuckChart';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
  title: 'Luck Chart | NBA | macfax',
  description: 'Net Rating vs. Wins Above Expected — which NBA teams are over- or under-performing their point differential.',
};

interface Props {
  searchParams: Promise<{ season?: string }>;
}

export default async function NBALuckChartPage({ searchParams }: Props) {
  const sp = await searchParams;
  const seasonYear = sp.season ? parseInt(sp.season, 10) : undefined;

  const [data, seasons] = await Promise.all([
    api.getNBALuckChart({ season: seasonYear }).catch(() => null),
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
          <p className="kicker-sport text-brand mb-[9px]">
            <Link href="/nba/viz" className="hover:underline">NBA · Visualizations</Link> · {data?.season_display ?? currentSeason?.display_name ?? 'Current season'}
          </p>
          <h1 className="font-display font-bold text-[clamp(32px,4vw,48px)] leading-none uppercase tracking-[0.005em] m-0 mb-[14px]">
            Luck Chart
          </h1>
          <div className="flex items-center gap-[14px] flex-wrap">
            <p className="text-[15px] text-muted m-0">
              Net Rating vs. Wins Above Expected — who's playing above or below their true quality
            </p>
            <span className="font-mono text-[12px] text-muted-2 inline-flex items-center gap-[7px] px-[10px] py-[5px] bg-ui-surface border border-ui-border rounded-md">
              <span className="w-1.5 h-1.5 rounded-full bg-brand2" />
              Updated daily
            </span>
          </div>
        </div>
      </div>

      <div className="max-w-[1240px] mx-auto px-8 py-8 pb-16">
        {data ? (
          <NBALuckChart data={data} />
        ) : (
          <div className="text-center py-20 bg-ui-card border border-ui-border rounded-lg">
            <p className="text-text-muted">
              No ratings data available. Run <code className="bg-gray-100 px-1 rounded text-xs">nba_compute_ratings --season {seasonYear ?? 2026}</code>
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
