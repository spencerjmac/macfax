import Link from 'next/link';
import { BarChart3, Swords, ScatterChart, BookOpen, Info, Github, Activity, Users, Trophy } from 'lucide-react';

export default function HomePage() {
  return (
    <div className="container mx-auto px-4 py-12">
      {/* Hero Section */}
      <div className="text-center mb-16">
        <h1 className="text-5xl font-bold mb-4 text-text-primary">
          macfax Analytics
        </h1>
        <p className="text-xl text-text-muted max-w-2xl mx-auto">
          Advanced efficiency metrics, four factors analysis, and predictive models 
          for both NCAA Division I and the NBA.
        </p>
      </div>

      {/* Leagues Container */}
      <div className="grid lg:grid-cols-2 gap-8 mb-16">
        
        {/* NCAA Section */}
        <div className="bg-ui-surface border border-ui-border rounded-xl p-8">
          <div className="flex items-center gap-3 mb-6">
            <Trophy className="w-8 h-8 text-brand" />
            <h2 className="text-3xl font-bold">NCAA College Basketball</h2>
          </div>
          <p className="text-text-muted mb-8">
            Complete data coverage for all 365 Division I programs, focusing on opponent-adjusted 
            efficiency, resume metrics, and matchup analysis.
          </p>
          
          <div className="grid sm:grid-cols-2 gap-4">
            <Link href="/ncaa/rankings" className="block p-5 bg-ui-card border border-ui-border rounded-lg hover:border-brand hover:bg-ui-surface-dark transition-all">
              <BarChart3 className="w-6 h-6 mb-2 text-brand" />
              <h3 className="font-bold mb-1">Team Rankings</h3>
              <p className="text-sm text-text-muted">Adjusted efficiency and four factors.</p>
            </Link>
            
            <Link href="/ncaa/matchup" className="block p-5 bg-ui-card border border-ui-border rounded-lg hover:border-brand hover:bg-ui-surface-dark transition-all">
              <Swords className="w-6 h-6 mb-2 text-brand" />
              <h3 className="font-bold mb-1">Matchup Tool</h3>
              <p className="text-sm text-text-muted">Head-to-head projections and edges.</p>
            </Link>
            
            <Link href="/ncaa/viz" className="block p-5 bg-ui-card border border-ui-border rounded-lg hover:border-brand hover:bg-ui-surface-dark transition-all">
              <ScatterChart className="w-6 h-6 mb-2 text-brand" />
              <h3 className="font-bold mb-1">Visualizations</h3>
              <p className="text-sm text-text-muted">Efficiency landscapes and trends.</p>
            </Link>
            
            <Link href="/ncaa/glossary" className="block p-5 bg-ui-card border border-ui-border rounded-lg hover:border-brand hover:bg-ui-surface-dark transition-all">
              <BookOpen className="w-6 h-6 mb-2 text-brand" />
              <h3 className="font-bold mb-1">Glossary</h3>
              <p className="text-sm text-text-muted">Detailed definitions for all metrics.</p>
            </Link>
          </div>
        </div>

        {/* NBA Section */}
        <div className="bg-ui-surface border border-ui-border rounded-xl p-8">
          <div className="flex items-center gap-3 mb-6">
            <Users className="w-8 h-8 text-secondary" />
            <h2 className="text-3xl font-bold">NBA Professional Basketball</h2>
          </div>
          <p className="text-text-muted mb-8">
            Possession-level analytics for all 30 NBA teams and their rosters, 
            featuring opponent-adjusted net ratings and player-level efficiency.
          </p>
          
          <div className="grid sm:grid-cols-2 gap-4">
            <Link href="/nba/rankings" className="block p-5 bg-ui-card border border-ui-border rounded-lg hover:border-secondary hover:bg-ui-surface-dark transition-all">
              <BarChart3 className="w-6 h-6 mb-2 text-secondary" />
              <h3 className="font-bold mb-1">NBA Rankings</h3>
              <p className="text-sm text-text-muted">Adjusted net rating and pace.</p>
            </Link>
            
            <Link href="/nba/rankings?tab=players" className="block p-5 bg-ui-card border border-ui-border rounded-lg hover:border-secondary hover:bg-ui-surface-dark transition-all">
              <Users className="w-6 h-6 mb-2 text-secondary" />
              <h3 className="font-bold mb-1">Player Stats</h3>
              <p className="text-sm text-text-muted">Advanced player-level metrics.</p>
            </Link>

            <Link href="/nba/viz" className="block p-5 bg-ui-card border border-ui-border rounded-lg hover:border-secondary hover:bg-ui-surface-dark transition-all">
              <ScatterChart className="w-6 h-6 mb-2 text-secondary" />
              <h3 className="font-bold mb-1">NBA Viz</h3>
              <p className="text-sm text-text-muted">Interactive NBA landscapes.</p>
            </Link>

            <Link href="/nba/model-health" className="block p-5 bg-ui-card border border-ui-border rounded-lg hover:border-secondary hover:bg-ui-surface-dark transition-all">
              <Activity className="w-6 h-6 mb-2 text-secondary" />
              <h3 className="font-bold mb-1">Model Health</h3>
              <p className="text-sm text-text-muted">Calibration and accuracy metrics.</p>
            </Link>
          </div>
        </div>

      </div>

      {/* Global Links */}
      <div className="grid md:grid-cols-2 gap-6 mb-16">
        <Link 
          href="/about" 
          className="block p-6 bg-ui-card border border-ui-border rounded-lg hover:border-text-primary transition-all flex items-start gap-4"
        >
          <Info className="w-8 h-8 text-text-primary shrink-0 mt-1" />
          <div>
            <h2 className="text-xl font-bold mb-1">About macfax</h2>
            <p className="text-text-muted">
              Learn about our independent data sources, methodology, and how we calculate 
              our advanced metrics across both leagues.
            </p>
          </div>
        </Link>
        
        <a 
          href="https://github.com/jaym/macfax" 
          target="_blank" 
          rel="noopener noreferrer"
          className="block p-6 bg-ui-card border border-ui-border rounded-lg hover:border-text-primary transition-all flex items-start gap-4"
        >
          <Github className="w-8 h-8 text-text-primary shrink-0 mt-1" />
          <div>
            <h2 className="text-xl font-bold mb-1">Open Source</h2>
            <p className="text-text-muted">
              Built with Next.js, Django, and PostgreSQL. 
              All calculations and visualizations are transparent.
            </p>
          </div>
        </a>
      </div>
      
      {/* Quick Stats */}
      <div className="bg-ui-surface border border-ui-border rounded-lg p-8 text-center">
        <div className="grid md:grid-cols-3 gap-8">
          <div>
            <div className="text-4xl font-bold text-brand font-mono">365</div>
            <div className="text-text-muted mt-1">NCAA D1 Teams</div>
          </div>
          <div>
            <div className="text-4xl font-bold text-secondary font-mono">30</div>
            <div className="text-text-muted mt-1">NBA Teams</div>
          </div>
          <div>
            <div className="text-4xl font-bold text-text-primary font-mono">Daily</div>
            <div className="text-text-muted mt-1">Data Updates</div>
          </div>
        </div>
      </div>
    </div>
  );
}
