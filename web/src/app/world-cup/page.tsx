import type { Metadata } from 'next';
import { worldCupApi } from '@/lib/worldcup-api';
import WorldCupRankingsTable from '@/components/WorldCup/RankingsTable';
import PowerPerceptionScatter from '@/components/WorldCup/PowerPerceptionScatter';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
  title: '2026 World Cup Rankings | macfax',
  description:
    '48 teams ranked by Elo rating — a predictive metric built from 150+ years of international match history.',
};

export default async function WorldCupPage() {
  const teams = await worldCupApi.getRankings().catch(() => []);

  const updatedAt = teams[0]?.updated_at
    ? new Date(teams[0].updated_at).toLocaleDateString('en-US', {
        month: 'long',
        day: 'numeric',
        year: 'numeric',
      })
    : null;

  return (
    <div>
      {/* Page header — matches NBA/NCAA pattern */}
      <div className="bg-surface border-b border-ui-border">
        <div className="max-w-[1240px] mx-auto px-8 py-10 pb-[34px]">
          <p className="kicker-sport text-brand mb-[9px]">WORLD CUP · ELO RANKINGS</p>
          <h1 className="font-display font-bold text-[clamp(32px,4vw,48px)] leading-none uppercase tracking-[0.005em] m-0 mb-[14px]">
            2026 World Cup
          </h1>
          <div className="flex items-center gap-[14px] flex-wrap">
            <p className="text-[15px] text-muted m-0">
              48 teams ranked by Elo rating — built from 150+ years of international match history
            </p>
            {updatedAt && (
              <span className="font-mono text-[12px] text-muted inline-flex items-center gap-[7px] px-[10px] py-[5px] bg-ui-surface border border-ui-border rounded-md">
                Updated {updatedAt}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="max-w-[1240px] mx-auto px-8 py-8 space-y-10">
        {teams.length === 0 ? (
          <div className="text-center py-20 bg-ui-card border border-ui-border rounded-lg">
            <p className="font-medium text-text-primary mb-2">No rankings data yet</p>
            <p className="text-sm text-text-muted">
              Run{' '}
              <code className="bg-gray-100 px-1.5 py-0.5 rounded text-xs">
                python manage.py build_elo
              </code>{' '}
              to populate rankings.
            </p>
          </div>
        ) : (
          <>
            <section>
              <PowerPerceptionScatter teams={teams} />
            </section>

            <section>
              <div className="mb-4">
                <h2 className="font-display font-bold text-[20px] uppercase tracking-[0.02em]">
                  Team Rankings
                </h2>
                <p className="text-sm text-muted mt-1">
                  Δ = FIFA rank minus Elo rank — positive means our model rates the team higher
                  than FIFA does
                </p>
              </div>
              <WorldCupRankingsTable data={teams} />
            </section>

            {/* Legend */}
            <div className="p-6 bg-ui-surface border border-ui-border rounded-lg">
              <h2 className="font-display font-bold text-[16px] uppercase tracking-[0.02em] mb-[14px]">
                How Elo Works
              </h2>
              <div className="grid md:grid-cols-2 gap-3 text-[13.5px] text-muted">
                <div>
                  <b className="font-mono font-semibold text-text-primary mr-1.5">Elo Rating</b>
                  Starting at 1500, updated after every match. Wins gain points, losses lose them.
                </div>
                <div>
                  <b className="font-mono font-semibold text-text-primary mr-1.5">K-Factor</b>
                  World Cup matches: 60. Continental championships: 40. Qualifying: 25.
                  Friendlies: 20.
                </div>
                <div>
                  <b className="font-mono font-semibold text-text-primary mr-1.5">Margin</b>
                  Goal difference multiplier rewards dominant wins but with diminishing returns.
                </div>
                <div>
                  <b className="font-mono font-semibold text-text-primary mr-1.5">Δ (Delta)</b>
                  FIFA rank minus Elo rank. Positive = model rates team higher than FIFA does.
                </div>
                <div>
                  <b className="font-mono font-semibold text-text-primary mr-1.5">Home Advantage</b>
                  Hosts receive a +100 Elo point boost when calculating win probability for their
                  home matches. This is not reflected in the base rating shown here — it&apos;s
                  applied per match.
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
