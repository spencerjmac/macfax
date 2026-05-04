import type { Metadata } from 'next';
import { TeamSearchWidget } from '@/components/outlook/TeamSearchWidget';

export const metadata: Metadata = {
  title: 'Roster Outlook | macfax',
  description:
    'Next-season team projections built from the roster up. Player talent, minutes, fit grades, continuity, and scenario editing for every Division I program.',
};

export default function OutlookLandingPage() {
  return (
    <div className="container mx-auto px-4 py-16 max-w-2xl">
      <div className="text-center mb-10">
        <h1 className="text-4xl font-bold text-text-primary mb-3">Roster Outlook</h1>
        <p className="text-lg text-text-muted leading-relaxed">
          Next-season projections built player by player — talent, minutes, roster fit, and continuity
          combined into a single forward-looking efficiency forecast.
        </p>
      </div>

      <div className="bg-ui-card border border-ui-border rounded-2xl p-8 flex flex-col items-center gap-4">
        <p className="text-sm font-medium text-text-muted uppercase tracking-wide">Select a team to get started</p>
        <TeamSearchWidget />
      </div>

      <div className="mt-10 grid grid-cols-1 sm:grid-cols-3 gap-4 text-center">
        <div className="bg-ui-surface border border-ui-border rounded-xl p-5">
          <div className="text-2xl font-bold text-brand mb-1">Rankings</div>
          <div className="text-sm text-text-muted">Projected AdjEM, AdjO, AdjD with uncertainty bands</div>
        </div>
        <div className="bg-ui-surface border border-ui-border rounded-xl p-5">
          <div className="text-2xl font-bold text-brand mb-1">Fit Grades</div>
          <div className="text-sm text-text-muted">Offensive and defensive roster fit scored A+ to F</div>
        </div>
        <div className="bg-ui-surface border border-ui-border rounded-xl p-5">
          <div className="text-2xl font-bold text-brand mb-1">Scenarios</div>
          <div className="text-sm text-text-muted">Edit the roster and re-run projections instantly</div>
        </div>
      </div>
    </div>
  );
}
