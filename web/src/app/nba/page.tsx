import { Metadata } from 'next';
import Link from 'next/link';
import { BarChart3, FlaskConical, ScatterChart, Users, Zap } from 'lucide-react';

export const metadata: Metadata = {
  title: 'NBA Analytics | macfax',
  description:
    'NBA team efficiency ratings, adjusted net rating, four factors analysis, and advanced analytics.',
};

const features = [
  {
    href: '/nba/rankings',
    icon: BarChart3,
    title: 'Team Rankings',
    description:
      'Sortable NBA rankings by adjusted offensive, defensive, and net rating with Four Factor Index.',
    phase: 2,
    available: true,
  },
  {
    href: '/nba/model-health',
    icon: FlaskConical,
    title: 'Model Health',
    description:
      'Prediction accuracy, empirical HCA/B2B calibration, and FFI weight regression — backtested against 2019–25.',
    phase: 3,
    available: true,
  },
  {
    href: '/nba/rankings',
    icon: Users,
    title: 'Player Analytics',
    description:
      'Per-game averages for every NBA player — points, rebounds, assists, shooting splits. Available on each team page.',
    phase: 4,
    available: true,
  },
  {
    href: '/nba/viz',
    icon: ScatterChart,
    title: 'Visualizations',
    description:
      'Efficiency Landscape, Four Factors scatter, and Contender Zone — NBA-calibrated charts.',
    phase: 5,
    available: false,
  },
  {
    href: '#',
    icon: Zap,
    title: 'Contender Zone',
    description:
      'Probabilistic contender profiles backed by adjusted ratings and four factor model.',
    phase: 5,
    available: false,
  },
];

export default function NBAHomePage() {
  return (
    <div className="container mx-auto px-4 py-12">
      {/* Hero */}
      <div className="text-center mb-16">
        <div className="inline-block bg-brand/10 text-brand text-sm font-semibold px-3 py-1 rounded-full mb-4 border border-brand/20">
          NBA — Phase 4 Complete
        </div>
        <h1 className="text-5xl font-bold mb-4">NBA Analytics</h1>
        <p className="text-xl text-text-muted max-w-2xl mx-auto">
          Opponent-adjusted team efficiency, Four Factor analysis, player game logs,
          and advanced analytics for all 30 NBA franchises.
        </p>
      </div>

      {/* Feature cards */}
      <div className="grid md:grid-cols-2 lg:grid-cols-2 gap-6 mb-16">
        {features.map((feature) => {
          const Icon = feature.icon;
          const card = (
            <div
              className={`block p-6 bg-ui-card border rounded-lg transition-colors ${
                feature.available
                  ? 'border-ui-border hover:border-brand cursor-pointer'
                  : 'border-ui-border opacity-70 cursor-default'
              }`}
            >
              <div className="flex items-start justify-between mb-3">
                <Icon className="w-10 h-10 text-brand" strokeWidth={1.5} />
                <span
                  className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                    feature.available
                      ? 'bg-green-100 text-green-800'
                      : 'bg-gray-100 text-gray-500'
                  }`}
                >
                  {feature.available ? 'Live' : `Phase ${feature.phase}`}
                </span>
              </div>
              <h2 className="text-xl font-bold mb-2">{feature.title}</h2>
              <p className="text-text-muted text-sm">{feature.description}</p>
            </div>
          );

          return feature.available ? (
            <Link key={feature.title} href={feature.href}>
              {card}
            </Link>
          ) : (
            <div key={feature.title}>{card}</div>
          );
        })}
      </div>

      {/* Architecture note */}
      <div className="max-w-2xl mx-auto p-6 bg-ui-surface border border-ui-border rounded-lg text-sm text-text-muted">
        <h3 className="font-semibold text-text-primary mb-2">Build Status</h3>
        <ul className="space-y-1">
          <li>
            <span className="text-green-600 font-medium">Phase 1 ✓</span> — app skeleton, data models, provider layer
          </li>
          <li>
            <span className="text-green-600 font-medium">Phase 2 ✓</span> — data ingestion, team profiles, rankings
          </li>
          <li>
            <span className="text-green-600 font-medium">Phase 3 ✓</span> — adjusted ratings, backtesting, model validation
          </li>
          <li>
            <span className="text-green-600 font-medium">Phase 4 ✓</span> — player game logs, per-season roster stats
          </li>
          <li>
            <span className="text-text-muted">Phase 5 (next):</span> Visualizations, contender zone, lineup analysis
          </li>
        </ul>
      </div>
    </div>
  );
}
