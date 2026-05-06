import type { Metadata } from 'next';
import { api } from '@/lib/api';
import { ValidationHero } from '@/components/validation/ValidationHero';
import { ValidationMetricCard } from '@/components/validation/ValidationMetricCard';
import { AccuracyOverTimeChart } from '@/components/validation/AccuracyOverTimeChart';
import { RecentValidationGamesTable } from '@/components/validation/RecentValidationGamesTable';
import { ValidationExplainer } from '@/components/validation/ValidationExplainer';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
  title: 'How Accurate Is Macfax? | Validation',
  description:
    'Macfax model accuracy tracked against locked pregame predictions. Winner accuracy, spread MAE, score MAE, Brier score, and recent game results.',
};

function formatPct(v: number) {
  return `${(v * 100).toFixed(1)}%`;
}

function formatPts(v: number) {
  return `${v.toFixed(1)} pts`;
}

function formatBrier(v: number) {
  return v.toFixed(3);
}

export default async function ValidationPage() {
  const [summaryRes, weeklyRes, recentRes] = await Promise.allSettled([
    api.getValidationSummary(),
    api.getValidationWeekly(),
    api.getValidationRecentGames(undefined, 100),
  ]);

  const summary = summaryRes.status === 'fulfilled' ? summaryRes.value : null;
  const weekly = weeklyRes.status === 'fulfilled' ? weeklyRes.value : null;
  const recent = recentRes.status === 'fulfilled' ? recentRes.value : null;

  const seasonSummary = summary?.summaries.find(s => s.period_type === 'season');
  const hasData = (seasonSummary?.games_evaluated ?? 0) > 0;

  return (
    <div className="container mx-auto px-4 py-10 max-w-5xl">
      <ValidationHero />

      {!hasData ? (
        <div className="bg-ui-surface border border-ui-border rounded-xl p-6 mb-8 text-center">
          <div className="text-text-muted text-sm leading-relaxed">
            Prospective validation begins with games predicted after this system was deployed.
            <br />
            Check back once the first predictions have been locked and evaluated.
          </div>
        </div>
      ) : (
        <>
          {/* Metric cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 mb-8">
            <ValidationMetricCard
              label="Games Evaluated"
              value={String(seasonSummary!.games_evaluated)}
              description="Completed games with locked predictions"
            />
            <ValidationMetricCard
              label="Winner Accuracy"
              value={formatPct(seasonSummary!.winner_accuracy)}
              description="Correct winner predictions"
              highlight
            />
            <ValidationMetricCard
              label="Spread MAE"
              value={formatPts(seasonSummary!.spread_mae)}
              description="Avg margin error"
            />
            <ValidationMetricCard
              label="Score MAE"
              value={formatPts(seasonSummary!.score_mae)}
              description="Avg score error per team"
            />
            <ValidationMetricCard
              label="Brier Score"
              value={formatBrier(seasonSummary!.brier_score)}
              description="Probability calibration (lower = better)"
            />
          </div>

          {/* Period summary row */}
          {summary && summary.summaries.length > 1 && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-2">
              {(['last_7', 'last_30', 'season'] as const).map(pt => {
                const s = summary.summaries.find(x => x.period_type === pt);
                if (!s || s.games_evaluated === 0) return null;
                const label = pt === 'last_7' ? 'Last 7 Days' : pt === 'last_30' ? 'Last 30 Days' : 'Full Season';
                return (
                  <div key={pt} className="bg-ui-surface border border-ui-border rounded-xl px-5 py-3 flex items-center justify-between">
                    <span className="text-xs text-text-muted uppercase tracking-wide">{label}</span>
                    <div className="flex gap-4 text-sm">
                      <span>
                        <span className="font-semibold text-text-primary">{formatPct(s.winner_accuracy)}</span>
                        <span className="text-text-muted ml-1">win</span>
                      </span>
                      <span>
                        <span className="font-semibold text-text-primary">{formatPts(s.spread_mae)}</span>
                        <span className="text-text-muted ml-1">MAE</span>
                      </span>
                      <span className="text-text-muted">{s.games_evaluated}g</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      <AccuracyOverTimeChart weeks={weekly?.weeks ?? []} />
      <RecentValidationGamesTable games={recent?.games ?? []} />
      <ValidationExplainer />
    </div>
  );
}
