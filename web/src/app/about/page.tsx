import { Metadata } from 'next';
import Link from 'next/link';
import { BarChart3, Swords, ScatterChart, BookOpen, FlaskConical, TrendingUp, Users } from 'lucide-react';

export const metadata: Metadata = {
  title: 'About | MacFax',
  description: 'MacFax is an independent college basketball analytics platform — advanced efficiency metrics, four factors analysis, matchup tools, and original visualizations.',
};

export default function AboutPage() {
  return (
    <div className="container mx-auto px-4 py-12 max-w-4xl">

      {/* Hero */}
      <section className="mb-16">
        <h1 className="text-5xl font-bold mb-6">
          What is MacFax?
        </h1>
        <p className="text-xl text-text-muted leading-relaxed max-w-2xl">
          MacFax is an independent college basketball analytics platform built to give fans, analysts,
          and bracket sickos a serious edge. We combine adjusted efficiency ratings, four factors
          breakdowns, matchup forecasting, and original visualizations — all in one place, updated daily.
        </p>
      </section>

      {/* What it does */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold mb-8">What MacFax gives you</h2>
        <div className="grid md:grid-cols-2 gap-5">
          <div className="p-6 bg-ui-card border border-ui-border rounded-lg flex gap-4">
            <BarChart3 className="w-8 h-8 text-brand shrink-0 mt-0.5" strokeWidth={1.5} />
            <div>
              <h3 className="font-bold mb-1">Team Rankings</h3>
              <p className="text-text-muted text-sm">
                Adjusted efficiency ratings, four factors, and sorting across all 365 D1 teams.
                Find who's actually good, not just who has the easy schedule.
              </p>
            </div>
          </div>

          <div className="p-6 bg-ui-card border border-ui-border rounded-lg flex gap-4">
            <Swords className="w-8 h-8 text-brand shrink-0 mt-0.5" strokeWidth={1.5} />
            <div>
              <h3 className="font-bold mb-1">Matchup Tool</h3>
              <p className="text-text-muted text-sm">
                Compare any two teams head-to-head. See projected efficiency margins and
                where each team wins or loses the four-factor battle.
              </p>
            </div>
          </div>

          <div className="p-6 bg-ui-card border border-ui-border rounded-lg flex gap-4">
            <ScatterChart className="w-8 h-8 text-brand shrink-0 mt-0.5" strokeWidth={1.5} />
            <div>
              <h3 className="font-bold mb-1">Visualizations</h3>
              <p className="text-text-muted text-sm">
                The Trapezoid of Excellence, Efficiency Landscape, Kill Shot analysis, and Crystal Ball —
                original charts that tell a story beyond the box score.
              </p>
            </div>
          </div>

          <div className="p-6 bg-ui-card border border-ui-border rounded-lg flex gap-4">
            <BookOpen className="w-8 h-8 text-brand shrink-0 mt-0.5" strokeWidth={1.5} />
            <div>
              <h3 className="font-bold mb-1">Glossary</h3>
              <p className="text-text-muted text-sm">
                Plain-English definitions for every metric. No jargon walls,
                just clear explanations of what the numbers mean and why they matter.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* What makes it different */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold mb-6">What makes it different</h2>
        <div className="space-y-4">
          <div className="p-6 bg-ui-surface border border-ui-border rounded-lg">
            <div className="flex items-start gap-3">
              <FlaskConical className="w-5 h-5 text-brand shrink-0 mt-0.5" strokeWidth={1.5} />
              <div>
                <h3 className="font-semibold mb-1">Everything in one place</h3>
                <p className="text-text-muted text-sm">
                  Adjusted efficiency, four factors, shooting splits, WAB, Barthag, and schedule strength —
                  unified under one roof instead of scattered across five tabs on three different sites.
                </p>
              </div>
            </div>
          </div>

          <div className="p-6 bg-ui-surface border border-ui-border rounded-lg">
            <div className="flex items-start gap-3">
              <TrendingUp className="w-5 h-5 text-brand shrink-0 mt-0.5" strokeWidth={1.5} />
              <div>
                <h3 className="font-semibold mb-1">Original analysis, not just republished numbers</h3>
                <p className="text-text-muted text-sm">
                  MacFax builds on established efficiency frameworks to produce its own derived metrics,
                  composite ratings, and matchup projections. The goal isn't to mirror other platforms —
                  it's to say something new.
                </p>
              </div>
            </div>
          </div>

          <div className="p-6 bg-ui-surface border border-ui-border rounded-lg">
            <div className="flex items-start gap-3">
              <Users className="w-5 h-5 text-brand shrink-0 mt-0.5" strokeWidth={1.5} />
              <div>
                <h3 className="font-semibold mb-1">Built for actual fans</h3>
                <p className="text-text-muted text-sm">
                  Whether you're researching a bracket, scouting a game, or just trying to understand
                  why your team keeps losing winnable games — MacFax is designed to be useful, not academic.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Metrics Philosophy */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold mb-4">Metrics philosophy</h2>
        <p className="text-text-primary mb-4 leading-relaxed">
          MacFax is built around the idea that the four factors — shooting efficiency, turnover rate,
          rebounding, and free throw rate — explain most of what happens in a college basketball game.
          Adjusted efficiency tells you how good a team is relative to who they've played. Everything
          else is context.
        </p>
        <p className="text-text-muted leading-relaxed">
          As the site continues to evolve, MacFax will keep expanding its models, visuals, and tools
          to provide a stronger picture of team quality and game outlook.
        </p>
      </section>

      {/* Built by */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold mb-4">Built by</h2>
        <p className="text-text-primary leading-relaxed">
          MacFax is an independent project — not affiliated with any university, media company,
          or analytics service. It was built by someone who got frustrated trying to cross-reference
          five different sites every morning and decided to just build the thing they actually wanted.
        </p>
      </section>

      {/* Disclaimer */}
      <section className="mb-16">
        <div className="p-6 bg-ui-surface border-l-4 border-brand rounded-r-lg">
          <p className="text-text-primary text-sm mb-2">
            <strong>Independent platform.</strong> MacFax is not affiliated with or endorsed by
            KenPom.com, barttorvik.com, or any other analytics site. Adjusted efficiency metrics
            draw on methodologies pioneered by Ken Pomeroy and Dean Oliver — we acknowledge their
            foundational work.
          </p>
          <p className="text-text-muted text-sm">
            The platform is informed by established basketball analytics principles and exists 
            for educational, analytical, and informational purposes.
          </p>
        </div>
      </section>

      {/* CTA Links */}
      <section className="flex flex-wrap gap-4">
        <Link
          href="/ncaa/rankings"
          className="px-6 py-3 bg-brand text-white rounded-lg hover:bg-brand-hover transition-colors font-medium"
        >
          View Rankings
        </Link>
        <Link
          href="/ncaa/matchup"
          className="px-6 py-3 bg-ui-surface border border-ui-border rounded-lg hover:border-brand transition-colors"
        >
          Matchup Tool
        </Link>
        <Link
          href="/ncaa/glossary"
          className="px-6 py-3 bg-ui-surface border border-ui-border rounded-lg hover:border-brand transition-colors"
        >
          Metrics Glossary
        </Link>
      </section>

    </div>
  );
}
