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
    <div className="container mx-auto px-4 py-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">NBA Visualizations</h1>
        <p className="text-text-muted mt-1">
          Efficiency Landscape · {currentSeason?.display_name ?? 'Current season'}
        </p>
      </div>
      <NBAEfficiencyLandscape data={rankings} seasonDisplay={currentSeason?.display_name} />
    </div>
  );
}
