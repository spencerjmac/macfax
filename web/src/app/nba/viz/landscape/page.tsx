import { Metadata } from 'next';
import { api } from '@/lib/api';
import NBAEfficiencyLandscapeChart from '@/components/NBAEfficiencyLandscapeChart';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
  title: 'Efficiency Landscape | NBA | macfax',
  description: 'NBA team efficiency landscape — Adj Off vs Adj Def with lines marking the top 7, top 10 and top 15 teams by net rating.',
};

interface Props {
  searchParams: Promise<{ season?: string }>;
}

export default async function NBALandscapePage({ searchParams }: Props) {
  const sp = await searchParams;
  const seasonYear = sp.season ? parseInt(sp.season, 10) : undefined;

  const data = await api.getNBALandscape({ season: seasonYear }).catch(() => null);

  return (
    <div>
      {/* Page header */}
      <div className="bg-surface border-b border-ui-border">
        <div className="max-w-[1240px] mx-auto px-8 py-10 pb-[34px]">
          <h1 className="font-display font-bold text-[clamp(32px,4vw,48px)] leading-none uppercase tracking-[0.005em] m-0 mb-[14px]">
            Efficiency Landscape
          </h1>
          <div className="flex items-center gap-[14px] flex-wrap">
            <p className="text-[15px] text-muted m-0">
              Adj Off vs Adj Def for all 30 teams, with lines marking the top 7, top 10 and top 15 by net rating
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
          <NBAEfficiencyLandscapeChart data={data} />
        ) : (
          <div className="text-center py-20 bg-ui-card border border-ui-border rounded-lg">
            <p className="text-text-muted">
              No ratings data available. Run <code className="bg-gray-100 px-1 rounded text-xs">nba_compute_ratings</code>
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
