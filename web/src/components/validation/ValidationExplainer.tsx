import Link from 'next/link';

export function ValidationExplainer() {
  return (
    <div className="mt-12 space-y-6">
      <h2 className="text-xl font-bold text-text-primary">How To Read These Numbers</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-ui-surface border border-ui-border rounded-xl p-5">
          <div className="font-semibold text-text-primary mb-2">Winner Accuracy</div>
          <p className="text-sm text-text-muted">
            Percentage of games where Macfax predicted the correct winner before tip-off.
            The higher-probability team is the predicted winner.
            A coin flip would give you ~50%. Good models land in the 68–74% range.
          </p>
        </div>

        <div className="bg-ui-surface border border-ui-border rounded-xl p-5">
          <div className="font-semibold text-text-primary mb-2">Spread MAE</div>
          <p className="text-sm text-text-muted">
            Mean Absolute Error of the projected point margin. A spread MAE of 9.0 means the model
            was off by 9 points on average. Vegas lines typically run 8.5–9.5 MAE on college basketball.
          </p>
        </div>

        <div className="bg-ui-surface border border-ui-border rounded-xl p-5">
          <div className="font-semibold text-text-primary mb-2">Score MAE</div>
          <p className="text-sm text-text-muted">
            Average of the absolute errors for both teams' projected scores.
            Measures how well the model forecasts raw point totals, not just margins.
          </p>
        </div>

        <div className="bg-ui-surface border border-ui-border rounded-xl p-5">
          <div className="font-semibold text-text-primary mb-2">Brier Score</div>
          <p className="text-sm text-text-muted">
            Measures probability calibration. Lower is better. A perfect model scores 0.
            A coin flip scores 0.25. Scores below 0.20 indicate well-calibrated win probabilities.
          </p>
        </div>
      </div>

      <div className="bg-ui-surface border border-ui-border rounded-xl p-5">
        <div className="font-semibold text-text-primary mb-2">About This Data</div>
        <p className="text-sm text-text-muted leading-relaxed">
          Prospective validation begins with games predicted after this system was deployed.
          Predictions are generated from Macfax's adjusted efficiency ratings before each game and
          saved as locked snapshots — they cannot be changed after the fact. Historical backtests
          may be added separately. Macfax does not claim superiority over any external ranking system.
        </p>
        <p className="text-sm text-text-muted mt-3">
          <Link href="/methodology/matchup-model" className="text-brand hover:underline">
            Learn how predictions are generated →
          </Link>
        </p>
      </div>
    </div>
  );
}
