import { Metadata } from 'next';
import { Trophy, ScatterChart, Gauge, Users, BookOpen } from 'lucide-react';
import { nbaApi } from '@/lib/nba-api';
import SportHubPage, { type HubConfig, type HubTeam } from '@/components/SportHubPage';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
  title: 'NBA Analytics | macfax',
  description:
    'Opponent-adjusted team efficiency, four factor analysis, and player analytics for all 30 NBA franchises.',
};

const NBA_CONFIG: Omit<HubConfig, 'facts'> = {
  label: 'NBA',
  eyebrow: 'NBA · Updated daily',
  title: 'NBA',
  teamCount: 30,
  lede: 'Adjusted efficiency, roster value, and development curves applied to all 30 NBA franchises — built to show what teams actually project to, not just what they\'ve done so far.',
  rankingsHref: '/nba/rankings',
  secondaryCta: 'Visualizations',
  secondaryCtaHref: '/nba/viz',
  tools: [
    { icon: Trophy,       title: 'Rankings',       body: 'Net-rating table for all 30 teams with offense and defense splits, sortable by any column.',      href: '/nba/rankings' },
    { icon: ScatterChart, title: 'Visualizations', body: 'Efficiency Landscape and team-trend charts built on the NBA model.',                              href: '/nba/viz' },
    { icon: Gauge,        title: 'Model Health',   body: 'Calibration and accuracy for the NBA model this season.',                                         href: '/nba/model-health' },
    { icon: Users,        title: 'Player Compare', body: 'Side-by-side player comparison across impact metrics.',                                            href: '/nba/compare', soon: true },
    { icon: BookOpen,     title: 'Glossary',       body: 'Definitions for every NBA metric — impact, efficiency, and pace.',                                 href: '/ncaa/glossary' },
  ],
  viz: [
    { art: 'landscape', kick: 'Big picture', title: 'Efficiency Landscape', body: 'All 30 teams on one offense-vs-defense plane — contenders separate from the pack.',  href: '/nba/viz' },
    { art: 'crystal',   kick: 'Forecast',    title: 'Crystal Ball',         body: "Win-probability curves for tonight's slate.",                                         href: '/nba/viz' },
    { art: 'trapezoid', kick: 'Efficiency',  title: 'Team Trends',          body: "Rolling net-rating over the season — who's heating up and who's sliding.",           href: '/nba/viz' },
  ],
};

export default async function NBAHubPage() {
  let teams: HubTeam[] = [];

  try {
    const raw = await nbaApi.getRankings();
    teams = [...raw]
      .sort((a, b) => (a.rank_adj_net ?? 999) - (b.rank_adj_net ?? 999))
      .slice(0, 5)
      .map(t => ({
        id: t.team_slug,
        name: t.team_name,
        logoUrl: t.team_logo_url ?? '',
        conf: t.team_conference,
        meta: `${t.games} GP`,
        em: t.adj_net ?? 0,
        off: t.adj_off ?? 0,
        def: t.adj_def ?? 0,
        href: `/nba/team/${t.team_slug}`,
      }));
  } catch {
    // API down — render hub without live data
  }

  const config: HubConfig = {
    ...NBA_CONFIG,
    facts: [],
  };

  return <SportHubPage config={config} teams={teams} />;
}
