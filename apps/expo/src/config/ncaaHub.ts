import { BookOpen, Gauge, ScatterChart, Sparkles, Swords, Trophy, type LucideIcon } from '@/src/components/ui/icons';

import type { LinkTarget } from '@/src/lib/links';

/**
 * Content for the Home screen. Copy is taken from NCAA_CONFIG in
 * web/src/app/ncaa/page.tsx. Links differ: only Rankings exists in the app so
 * far, so every other tool opens its page on the website.
 */

export interface HubTool {
  icon: LucideIcon;
  title: string;
  body: string;
  target: LinkTarget;
}

export interface HubViz {
  art: 'trapezoid' | 'landscape' | 'crystal';
  kick: string;
  title: string;
  body: string;
  target: LinkTarget;
}

export interface HubConfig {
  label: string;
  eyebrow: string;
  title: string;
  teamCount: number;
  lede: string;
  rankingsTarget: LinkTarget;
  secondaryCta: string;
  secondaryCtaTarget: LinkTarget;
  allVizTarget: LinkTarget;
  tools: HubTool[];
  viz: HubViz[];
}

const web = (path: string): LinkTarget => ({ kind: 'web', path });
const RANKINGS: LinkTarget = { kind: 'app', href: '/rankings' };

export const NCAA_HUB: HubConfig = {
  label: 'NCAA',
  eyebrow: 'College Basketball · Updated daily',
  title: 'College Basketball',
  teamCount: 365,
  lede: "Adjusted efficiency, four factors, player impact, and matchup projections for every Division I team — built to show how teams actually play, not just who they've beaten.",
  rankingsTarget: RANKINGS,
  secondaryCta: 'Matchup tool',
  secondaryCtaTarget: web('/ncaa/matchup'),
  allVizTarget: web('/ncaa/viz'),
  tools: [
    { icon: Trophy, title: 'Rankings', body: 'Complete NCAA team and player rankings with AdjEM, adjusted efficiency, four factors, sorting, search, season, conference, and tournament filters.', target: RANKINGS },
    { icon: Swords, title: 'Matchup', body: 'Head-to-head forecasts for any two teams, including projected score, margin, win probability, four-factor edges, key drivers, volatility, and recent form.', target: web('/ncaa/matchup') },
    { icon: Sparkles, title: 'Outlook', body: 'Next-season roster projections built from player talent, minutes, fit, continuity, uncertainty, and editable roster scenarios.', target: web('/ncaa/outlook') },
    { icon: ScatterChart, title: 'Visualizations', body: 'Interactive charts like Trapezoid of Excellence, Efficiency Landscape, Crystal Ball, Cinderella Index, Bracket Simulator, and custom scatterplots.', target: web('/ncaa/viz') },
    { icon: BookOpen, title: 'Glossary', body: 'Definitions, formulas, and interpretation notes for MacFax metrics and model concepts.', target: web('/ncaa/glossary') },
    { icon: Gauge, title: 'Model Health', body: 'Locked-prediction validation showing winner accuracy, spread error, score error, calibration, trends, and recent evaluated games.', target: web('/validation') },
  ],
  viz: [
    { art: 'trapezoid', kick: 'Efficiency', title: 'Trapezoid of Excellence', body: 'Plots every D-I team by adjusted tempo and AdjEM against a season-calibrated contender zone, showing which efficiency-tempo profiles resemble historical deep-run teams.', target: web('/ncaa/viz/trapezoid') },
    { art: 'landscape', kick: 'Big picture', title: 'Efficiency Landscape', body: 'Maps every D-I team by adjusted offense and defense with championship tier lines, separating balanced contenders from offense-first, defense-first, and lower-tier profiles.', target: web('/ncaa/viz/landscape') },
    { art: 'crystal', kick: 'Forecast', title: 'Crystal Ball', body: 'Scores every D-I team against 15 historical championship benchmarks across efficiency, four factors, resume, shooting, and poll signals to rank contender profiles.', target: web('/ncaa/viz/crystal-ball') },
  ],
};
