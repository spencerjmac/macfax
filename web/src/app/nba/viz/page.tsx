import { Metadata } from 'next';
import { nbaApi } from '@/lib/nba-api';
import NBAEfficiencyLandscape from '@/components/NBAEfficiencyLandscape';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
  title: 'NBA Visualizations | macfax',
  description: 'NBA team efficiency landscape and four factors scatter charts.',
};

interface Props {
  searchParams: Promise<{ season?: string }>;
}

export default async function NBAVizPage({ searchParams }: Props) {
  const sp = await searchParams;
  const seasonYear = sp.season ? parseInt(sp.season, 10) : undefined;

  const [rankings, seasons] = await Promise.all([
    nbaApi.getRankings(seasonYear).catch(() => []),
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
          <p className="kicker-sport text-brand mb-[9px]">NBA · {currentSeason?.display_name ?? 'Current season'}</p>
          <h1 className="font-display font-bold text-[clamp(32px,4vw,48px)] leading-none uppercase tracking-[0.005em] m-0 mb-[14px]">
            Visualizations
          </h1>
          <div className="flex items-center gap-[14px] flex-wrap">
            <p className="text-[15px] text-muted m-0">Efficiency landscape and four factors for all 30 teams</p>
            <span className="font-mono text-[12px] text-muted-2 inline-flex items-center gap-[7px] px-[10px] py-[5px] bg-ui-surface border border-ui-border rounded-md">
              <span className="w-1.5 h-1.5 rounded-full bg-brand2" />
              Updated daily
            </span>
          </div>
        </div>
      </div>

      <div className="max-w-[1240px] mx-auto px-8 py-8 pb-16">
        <NBAEfficiencyLandscape data={rankings} seasonDisplay={currentSeason?.display_name} />
      </div>
    </div>
  );
}
