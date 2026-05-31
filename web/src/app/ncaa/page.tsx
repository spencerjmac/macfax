import { Metadata } from 'next';
import { Trophy, Swords, Sparkles, ScatterChart, BookOpen, Gauge } from 'lucide-react';
import { getAllTeams } from '@/lib/data';
import SportHubPage, { type HubConfig, type HubTeam } from '@/components/SportHubPage';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
  title: 'NCAA College Basketball | macfax',
  description:
    'Adjusted efficiency, four factors, and matchup forecasts for all 365 Division I teams — ranked by what they actually do on the floor.',
};

const NCAA_CONFIG: Omit<HubConfig, 'facts'> = {
  label: 'NCAA',
  eyebrow: 'College Basketball · Updated daily',
  title: 'College Basketball',
  teamCount: 365,
  lede: 'Adjusted efficiency, four factors, and matchup forecasts for all 365 Division I teams — ranked by what they actually do on the floor, not their record.',
  rankingsHref: '/ncaa/rankings',
  secondaryCta: 'Matchup tool',
  secondaryCtaHref: '/ncaa/matchup',
  tools: [
    { icon: Trophy,      title: 'Rankings',       body: 'Full AdjEM table with four factors, sortable by any metric and filterable by conference.', href: '/ncaa/rankings' },
    { icon: Swords,      title: 'Matchup',        body: 'Head-to-head projections for any two teams — margin, win probability, and the four-factor edges.', href: '/ncaa/matchup' },
    { icon: Sparkles,    title: 'Outlook',        body: 'Season projections and tournament resume — where each team is trending into March.', href: '/ncaa/outlook' },
    { icon: ScatterChart,title: 'Visualizations', body: 'The Trapezoid of Excellence, Efficiency Landscape, and more — read the season at a glance.', href: '/ncaa/viz' },
    { icon: BookOpen,    title: 'Glossary',       body: 'Plain-English definitions for every metric. What the numbers mean and why they matter.', href: '/ncaa/glossary' },
    { icon: Gauge,       title: 'Model Health',   body: 'How the model is performing this season — calibration, accuracy, and recent hits.', href: '/validation' },
  ],
  viz: [
    { art: 'trapezoid', kick: 'Efficiency',  title: 'Trapezoid of Excellence', body: 'The four factors plotted as a single shape — see exactly where a team wins and loses games.', href: '/ncaa/viz/trapezoid' },
    { art: 'landscape', kick: 'Big picture', title: 'Efficiency Landscape',    body: 'Every D-I team on one offense-vs-defense plane. Elite lives in the top-right.',            href: '/ncaa/viz/landscape' },
    { art: 'crystal',   kick: 'Forecast',    title: 'Crystal Ball',            body: 'Win-probability curves for the games that matter most.',                                     href: '/ncaa/viz/crystal-ball' },
  ],
};

export default async function NCAAHubPage() {
  let teams: HubTeam[] = [];

  try {
    const raw = await getAllTeams();
    teams = [...raw]
      .sort((a, b) => a.rank - b.rank)
      .slice(0, 5)
      .map(t => ({
        id: t.teamId,
        name: t.teamName,
        logoUrl: t.logoUrl ?? '',
        conf: t.conference,
        meta: t.record ?? '',
        em: t.adjEM,
        off: t.adjO,
        def: t.adjD,
        href: `/ncaa/team/${t.teamId}`,
      }));
  } catch {
    // API down — render hub without live data
  }

  const config: HubConfig = {
    ...NCAA_CONFIG,
    facts: [
      { k: 'Teams',         v: '365' },
      { k: 'Conferences',   v: '32' },
      { k: 'Games modeled', v: '5.4', sub: 'k' },
    ],
  };

  return <SportHubPage config={config} teams={teams} />;
}
