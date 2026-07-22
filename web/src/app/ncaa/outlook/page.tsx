import type { Metadata } from 'next';
import Link from 'next/link';
import { TeamSearchWidget } from '@/components/outlook/TeamSearchWidget';

export const metadata: Metadata = {
  title: 'Roster Outlook | macfax',
  description:
    'Next-season team projections built from the roster up. Player talent, minutes, fit grades, continuity, and scenario editing for every Division I program.',
};

interface TopTeam {
  rank: number;
  team_name: string;
  team_slug: string;
  logo_url: string | null;
  projected_adj_em: number;
  adj_em_low: number;
  adj_em_high: number;
}

interface TopTeamsResponse {
  season: number;
  projected_season_year: number;
  teams: TopTeam[];
}

async function fetchTopTeams(): Promise<TopTeamsResponse | null> {
  const base = (process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
  try {
    const res = await fetch(`${base}/api/outlook/top/?limit=10`, { cache: 'no-store' });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function OutlookLandingPage() {
  const top = await fetchTopTeams();
  const projectedLabel = top
    ? `${top.projected_season_year - 1}-${String(top.projected_season_year).slice(2)}`
    : null;

  return (
    <div className="container mx-auto px-4 py-16 max-w-2xl">
      <div className="text-center mb-10">
        <h1 className="text-4xl font-bold text-text-primary mb-3">Roster Outlook</h1>
        <p className="text-lg text-text-muted leading-relaxed">
          Next-season projections built player by player — talent, minutes, roster fit, and continuity
          combined into a single forward-looking efficiency forecast.
        </p>
        {projectedLabel && (
          <p className="mt-2 text-sm font-medium text-brand">Projecting {projectedLabel}</p>
        )}
      </div>

      <div className="bg-ui-card border border-ui-border rounded-2xl p-8 flex flex-col items-center gap-4">
        <p className="text-sm font-medium text-text-muted uppercase tracking-wide">Select a team to get started</p>
        <TeamSearchWidget />
      </div>

      <div className="mt-10 grid grid-cols-1 sm:grid-cols-3 gap-4 text-center">
        <a href="#projected-top-10" className="bg-ui-surface border border-ui-border rounded-xl p-5 hover:border-brand transition-colors">
          <div className="text-2xl font-bold text-brand mb-1">Rankings</div>
          <div className="text-sm text-text-muted">Projected AdjEM, AdjO, AdjD with likely ranges</div>
        </a>
        <Link href={top?.teams?.[0] ? `/ncaa/outlook/${top.teams[0].team_slug}` : '#projected-top-10'} className="bg-ui-surface border border-ui-border rounded-xl p-5 hover:border-brand transition-colors">
          <div className="text-2xl font-bold text-brand mb-1">Fit Grades</div>
          <div className="text-sm text-text-muted">Offensive and defensive roster fit scored A+ to F</div>
        </Link>
        <Link href={top?.teams?.[0] ? `/ncaa/outlook/${top.teams[0].team_slug}?tab=scenario` : '#projected-top-10'} className="bg-ui-surface border border-ui-border rounded-xl p-5 hover:border-brand transition-colors">
          <div className="text-2xl font-bold text-brand mb-1">Scenarios</div>
          <div className="text-sm text-text-muted">Edit the roster and re-run projections instantly</div>
        </Link>
      </div>

      {top && top.teams.length > 0 && (
        <div id="projected-top-10" className="mt-12">
          <div className="flex items-baseline justify-between mb-3">
            <h2 className="text-xl font-bold text-text-primary">Projected Top 10</h2>
            <span className="text-xs text-text-muted">Projecting {projectedLabel}</span>
          </div>
          <div className="bg-ui-card border border-ui-border rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-text-muted border-b border-ui-border">
                  <th className="px-4 py-2 w-10">#</th>
                  <th className="px-4 py-2">Team</th>
                  <th className="px-4 py-2 text-right">Proj. AdjEM</th>
                  <th className="px-4 py-2 text-right">Likely range</th>
                </tr>
              </thead>
              <tbody>
                {top.teams.map((t) => (
                  <tr key={t.team_slug} className="border-b border-ui-border last:border-b-0 hover:bg-ui-surface transition-colors">
                    <td className="px-4 py-2.5 font-mono text-text-muted">{t.rank}</td>
                    <td className="px-4 py-2.5">
                      <Link href={`/ncaa/outlook/${t.team_slug}`} className="font-medium text-text-primary hover:text-brand transition-colors">
                        {t.team_name}
                      </Link>
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono font-semibold">{t.projected_adj_em > 0 ? '+' : ''}{t.projected_adj_em.toFixed(1)}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-text-muted text-xs">
                      {t.adj_em_low.toFixed(1)} to {t.adj_em_high.toFixed(1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-[11px] text-text-muted">Ranges are likely ranges (~68%) from backtested projection error.</p>
        </div>
      )}
    </div>
  );
}
