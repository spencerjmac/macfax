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
  lede: 'Ratings, forecasts, roster outlooks, and visual tools for Division I college basketball, built from opponent-adjusted efficiency, four factors, team strength, and matchup-level projections.',
  rankingsHref: '/ncaa/rankings',
  secondaryCta: 'Matchup tool',
  secondaryCtaHref: '/ncaa/matchup',
  tools: [
    { icon: Trophy,      title: 'Rankings',       body: 'Complete NCAA team and player rankings with AdjEM, adjusted efficiency, four factors, sorting, search, season, conference, and tournament filters.', href: '/ncaa/rankings' },
    { icon: Swords,      title: 'Matchup',        body: 'Head-to-head forecasts for any two teams, including projected score, margin, win probability, four-factor edges, key drivers, volatility, and recent form.', href: '/ncaa/matchup' },
    { icon: Sparkles,    title: 'Outlook',        body: 'Next-season roster projections built from player talent, minutes, fit, continuity, uncertainty, and editable roster scenarios.', href: '/ncaa/outlook' },
    { icon: ScatterChart,title: 'Visualizations', body: 'Interactive charts like Trapezoid of Excellence, Efficiency Landscape, Crystal Ball, Cinderella Index, Bracket Simulator, and custom scatterplots.', href: '/ncaa/viz' },
    { icon: BookOpen,    title: 'Glossary',       body: 'Definitions, formulas, and interpretation notes for MacFax metrics and model concepts.', href: '/ncaa/glossary' },
    { icon: Gauge,       title: 'Model Health',   body: 'Locked-prediction validation showing winner accuracy, spread error, score error, calibration, trends, and recent evaluated games.', href: '/validation' },
  ],
  viz: [
    { art: 'trapezoid', kick: 'Efficiency',  title: 'Trapezoid of Excellence', body: 'Plots every D-I team by adjusted tempo and AdjEM against a season-calibrated contender zone, showing which efficiency-tempo profiles resemble historical deep-run teams.', href: '/ncaa/viz/trapezoid' },
    { art: 'landscape', kick: 'Big picture', title: 'Efficiency Landscape',    body: 'Maps every D-I team by adjusted offense and defense with championship tier lines, separating balanced contenders from offense-first, defense-first, and lower-tier profiles.', href: '/ncaa/viz/landscape' },
    { art: 'crystal',   kick: 'Forecast',    title: 'Crystal Ball',            body: 'Scores every D-I team against 15 historical championship benchmarks across efficiency, four factors, resume, shooting, and poll signals to rank contender profiles.', href: '/ncaa/viz/crystal-ball' },
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
    facts: [],
  };

  return <SportHubPage config={config} teams={teams} />;
}
