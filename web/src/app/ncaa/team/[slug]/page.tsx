import { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getTeamWithContext, getAllSeasons } from '@/lib/data';
import { pickCurrentSeason } from '@macfax/core/lib/season';
import TeamPageTabs from '@/components/TeamPageTabs';
import TeamHeader from '@/components/TeamHeader';

// Force dynamic rendering
export const dynamic = 'force-dynamic';
export const revalidate = 0;

interface TeamPageProps {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ season?: string }>;
}

/** ?season=YYYY (ending year); anything else means the current season. */
function parseSeason(raw?: string): number | undefined {
  if (!raw || !/^\d{4}$/.test(raw)) return undefined;
  return parseInt(raw, 10);
}

export async function generateMetadata({ params, searchParams }: TeamPageProps): Promise<Metadata> {
  const { slug } = await params;
  const season = parseSeason((await searchParams).season);
  const teamData = await getTeamWithContext(slug, season);

  if (!teamData) {
    return {
      title: 'Team Not Found | macfax',
    };
  }

  const { team } = teamData;

  return {
    title: `${team.teamName} - ${team.season} | macfax`,
    description: `Advanced analytics and statistics for ${team.teamName} ${team.season} season. Efficiency metrics, four factors, and predictive analysis.`,
  };
}

export default async function TeamPage({ params, searchParams }: TeamPageProps) {
  const { slug } = await params;
  const season = parseSeason((await searchParams).season);
  const [teamData, seasons] = await Promise.all([getTeamWithContext(slug, season), getAllSeasons()]);

  if (!teamData) {
    notFound();
  }

  const { team, ranks, checklist, cinderella } = teamData;
  const currentYear = pickCurrentSeason(seasons)?.year;
  // Past season: an explicit ?season= that isn't the current one
  const pastSeason = season != null && currentYear != null && season !== currentYear ? season : undefined;

  return (
    <div>
      <TeamHeader team={team} pastSeason={pastSeason} />
      <TeamPageTabs team={team} ranks={ranks} checklist={checklist} cinderella={cinderella} pastSeason={pastSeason} />
    </div>
  );
}
