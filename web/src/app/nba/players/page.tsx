import { Metadata } from 'next';
import { nbaApi } from '@/lib/nba-api';
import NBAPlayerRankingsTable from '@/components/NBAPlayerRankingsTable';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
  title: 'NBA Player Ratings | macfax',
  description: 'NBA player ratings with MPR impact and traditional production by season and season type.',
};

interface NBAPlayersPageProps {
  searchParams: Promise<{ season?: string; season_type?: string }>;
}

export default async function NBAPlayersPage({ searchParams }: NBAPlayersPageProps) {
  const sp = await searchParams;
  const seasonYear = sp.season ? parseInt(sp.season, 10) : undefined;
  const seasonType = sp.season_type === 'playoffs' ? 'playoffs' : 'regular';

  const [rankings, seasons, players] = await Promise.all([
    nbaApi.getRankings(seasonYear, seasonType).catch(() => []),
    nbaApi.getSeasons().catch(() => []),
    nbaApi.getLeaguePlayers({ season: seasonYear, ordering: '-pts', min_gp: 1, season_type: seasonType }).catch(() => []),
  ]);

  // Team slug -> games played, for the Auto filter on native rows
  const teamGames: Record<string, number> = Object.fromEntries(rankings.map((r) => [r.team_slug, r.games]));

  const currentSeason = seasonYear
    ? seasons.find((s) => s.year === seasonYear) ?? null
    : seasons.find((s) => s.is_current) ?? seasons[0] ?? null;

  const seasonDisplay = currentSeason?.display_name;

  return (
    <div>
      {/* Page header */}
      <div className="bg-surface border-b border-ui-border">
        <div className="max-w-[1240px] mx-auto px-8 py-10 pb-[34px]">
          <h1 className="font-display font-bold text-[clamp(32px,4vw,48px)] leading-none uppercase tracking-[0.005em] m-0 mb-[14px]">
            NBA Player Ratings
          </h1>
          <div className="flex items-center gap-[14px] flex-wrap">
            <p className="text-[15px] text-muted m-0">
              MPR impact, box-score production, and advanced rates for every NBA player.
            </p>
            {players.length > 0 && (
              <span className="font-mono text-[12px] text-muted-2 inline-flex items-center gap-[7px] px-[10px] py-[5px] bg-ui-surface border border-ui-border rounded-md">
                <span className="w-1.5 h-1.5 rounded-full bg-brand2" />
                Live
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="max-w-[1240px] mx-auto px-8 py-8">
        <NBAPlayerRankingsTable
          data={players}
          seasonDisplay={seasonDisplay}
          seasonType={seasonType}
          teamGames={teamGames}
          seasons={seasons}
          selectedSeason={currentSeason?.year}
        />
      </div>
    </div>
  );
}
