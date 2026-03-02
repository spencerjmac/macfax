import { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getTeamWithContext, getAllTeams } from '@/lib/data';
import TeamPageTabs from '@/components/TeamPageTabs';
import TeamHeader from '@/components/TeamHeader';

interface TeamPageProps {
  params: {
    slug: string;
  };
}

export async function generateStaticParams() {
  const teams = await getAllTeams();
  return teams.map((team) => ({
    slug: team.teamId,
  }));
}

export async function generateMetadata({ params }: TeamPageProps): Promise<Metadata> {
  const teamData = await getTeamWithContext(params.slug);
  
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

export default async function TeamPage({ params }: TeamPageProps) {
  const teamData = await getTeamWithContext(params.slug);
  
  if (!teamData) {
    notFound();
  }
  
  const { team, ranks, checklist } = teamData;
  
  return (
    <div className="container mx-auto px-4 py-8">
      <TeamHeader team={team} ranks={ranks} />
      <TeamPageTabs team={team} ranks={ranks} checklist={checklist} />
    </div>
  );
}

