import { Metadata } from 'next';
import { nbaApi } from '@/lib/nba-api';
import { NBAModelCalibration } from '@/types/nba';
import { AlertTriangle, CheckCircle, FlaskConical, Info } from 'lucide-react';
import clsx from 'clsx';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
  title: 'NBA Model Health | macfax',
  description: 'Phase 3 validation: prediction accuracy, empirical HCA/B2B calibration, and FFI weight regression.',
};

// ─────────────────────────────────────────────────────────────────────────────
// Small display helpers
// ─────────────────────────────────────────────────────────────────────────────

function pct(v: number | null, decimals = 1) {
  if (v == null) return '—';
  return `${v.toFixed(decimals)}%`;
}

function num(v: number | null, decimals = 3) {
  if (v == null) return '—';
  return v.toFixed(decimals);
}

function numSign(v: number | null, decimals = 2) {
  if (v == null) return '—';
  return (v >= 0 ? '+' : '') + v.toFixed(decimals);
}

function StatCard({
  label,
  value,
  sub,
  good,
}: {
  label: string;
  value: string;
  sub?: string;
  good?: boolean | null;
}) {
  return (
    <div className="bg-ui-card border border-ui-border rounded-lg p-4">
      <p className="text-xs text-text-muted uppercase tracking-wider mb-1">{label}</p>
      <p
        className={clsx(
          'text-2xl font-bold font-mono',
          good === true && 'text-green-600',
          good === false && 'text-amber-600',
          good == null && 'text-text-primary',
        )}
      >
        {value}
      </p>
      {sub && <p className="text-xs text-text-muted mt-1">{sub}</p>}
    </div>
  );
}

function WeightRow({
  label,
  proposed,
  current,
}: {
  label: string;
  proposed: number | null;
  current: number | null;
}) {
  const diff = proposed != null && current != null ? Math.abs(proposed - current) : null;
  const notable = diff != null && diff > 0.08;
  return (
    <tr className="border-b border-ui-border/50 last:border-0">
      <td className="py-2 pr-4 text-sm text-text-primary">{label}</td>
      <td className="py-2 pr-4 text-sm font-mono font-semibold text-text-primary text-right">
        {proposed != null ? (proposed * 100).toFixed(1) + '%' : '—'}
      </td>
      <td className="py-2 text-sm font-mono text-text-muted text-right">
        {current != null ? (current * 100).toFixed(1) + '%' : '—'}
      </td>
      <td className="py-2 pl-4 text-sm text-right">
        {notable ? (
          <span className="text-amber-600 font-medium">◄ notable</span>
        ) : (
          <span className="text-green-600">✓</span>
        )}
      </td>
    </tr>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────────────

export default async function NBAModelHealthPage() {
  let calibration: NBAModelCalibration | null = null;
  let fetchError = false;

  try {
    calibration = await nbaApi.getModelCalibration();
  } catch {
    fetchError = true;
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-1">
          <FlaskConical className="w-6 h-6 text-brand" />
          <h1 className="text-3xl font-bold text-text-primary">NBA Model Health</h1>
        </div>
        <p className="text-text-muted">
          Phase 3 validation — prediction accuracy, HCA/B2B calibration, FFI weight regression.
          {calibration && (
            <span className="ml-2 text-text-secondary">
              {calibration.season_display} · last run{' '}
              {new Date(calibration.computed_at).toLocaleString()}
            </span>
          )}
        </p>
      </div>

      {/* Shell notice */}
      <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800 mb-6">
        <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
        <span>
          <strong>Phase 3 — in-season evaluation only.</strong> Season-end ratings are used
          retroactively for prediction accuracy, so the accuracy figure is optimistically biased.
          True hold-out validation requires multi-season backfill (Phase 3B).
        </span>
      </div>

      {fetchError || !calibration ? (
        <div className="text-center py-20 bg-ui-card border border-ui-border rounded-lg">
          <FlaskConical className="w-12 h-12 mx-auto mb-4 text-brand/30" strokeWidth={1} />
          <p className="font-medium text-text-primary mb-2">No calibration data yet</p>
          <p className="text-sm text-text-muted mb-4">
            Run the following command to evaluate the model:
          </p>
          <code className="bg-gray-100 px-3 py-1 rounded text-sm font-mono">
            python manage.py nba_eval_model --season 2026
          </code>
        </div>
      ) : (
        <div className="space-y-8">
          {/* ── 1. Prediction Accuracy ── */}
          <section>
            <h2 className="text-lg font-semibold text-text-primary mb-1">
              1. Prediction Accuracy
            </h2>
            <p className="text-sm text-text-muted mb-4">
              Straight-up picks using season-end adj_net ± configured HCA. Retroactive — not held-out.
            </p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard
                label="Games evaluated"
                value={calibration.games_predicted?.toLocaleString() ?? '—'}
                sub="completed regular-season games"
              />
              <StatCard
                label="Straight-up accuracy"
                value={pct(calibration.straight_up_accuracy)}
                sub="correct picks"
                good={
                  calibration.straight_up_accuracy != null
                    ? calibration.straight_up_accuracy >= 65
                    : null
                }
              />
              <StatCard
                label="Brier score"
                value={num(calibration.brier_score)}
                sub="lower = better (random = 0.25)"
                good={
                  calibration.brier_score != null
                    ? calibration.brier_score < 0.22
                    : null
                }
              />
              <StatCard
                label="Log-loss"
                value={num(calibration.log_loss)}
                sub="lower = better (random = 0.693)"
                good={
                  calibration.log_loss != null
                    ? calibration.log_loss < 0.63
                    : null
                }
              />
            </div>
          </section>

          {/* ── 2+3. HCA + B2B ── */}
          <section>
            <h2 className="text-lg font-semibold text-text-primary mb-1">
              2 &amp; 3. Empirical HCA + B2B Calibration
            </h2>
            <p className="text-sm text-text-muted mb-4">
              OLS fit: <code className="text-xs bg-ui-surface px-1 py-0.5 rounded">
                home_margin ~ β₀ + β₁·adj_net_diff + β₂·home_b2b + β₃·away_b2b
              </code>.
              {calibration.ols_games != null && ` ${calibration.ols_games} games.`}
            </p>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mb-4">
              <StatCard
                label="OLS R²"
                value={num(calibration.ols_r_squared)}
                sub="explanatory power of the model"
                good={
                  calibration.ols_r_squared != null
                    ? calibration.ols_r_squared >= 0.15
                    : null
                }
              />
              <StatCard
                label="Empirical HCA"
                value={numSign(calibration.empirical_hca) + ' pts'}
                sub={`configured: ${numSign(calibration.configured_hca)} pts/100`}
                good={
                  calibration.empirical_hca != null && calibration.configured_hca != null
                    ? Math.abs(calibration.empirical_hca - calibration.configured_hca) < 1.5
                    : null
                }
              />
              <StatCard
                label="Model scale (β₁)"
                value={num(calibration.ols_model_scale)}
                sub="goal ≈ 1.0 (pts ≈ pts/100 poss)"
                good={
                  calibration.ols_model_scale != null
                    ? Math.abs(calibration.ols_model_scale - 1.0) < 0.15
                    : null
                }
              />
              <StatCard
                label="Home B2B penalty"
                value={numSign(calibration.empirical_home_b2b_penalty) + ' pts'}
                sub={`configured: −${calibration.configured_b2b_penalty?.toFixed(1)}`}
              />
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <StatCard
                label="Away B2B (home benefit)"
                value={numSign(calibration.empirical_away_b2b_penalty) + ' pts'}
                sub={`configured: +${calibration.configured_b2b_penalty?.toFixed(1)} to home`}
              />
            </div>

            {/* Calibration recommendation */}
            {calibration.empirical_hca != null && calibration.configured_hca != null &&
              Math.abs(calibration.empirical_hca - calibration.configured_hca) >= 1.5 && (
              <div className="mt-4 flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800">
                <Info className="w-4 h-4 mt-0.5 shrink-0" />
                <span>
                  Empirical HCA ({numSign(calibration.empirical_hca)} pts) differs from configured
                  ({numSign(calibration.configured_hca)} pts/100 poss) by more than 1.5 points.
                  Consider updating <code>home_court_adj</code> in{' '}
                  <code>nba/ratings_config.py</code> once the season has more games.
                </span>
              </div>
            )}
          </section>

          {/* ── 4. FFI Weights ── */}
          <section>
            <h2 className="text-lg font-semibold text-text-primary mb-1">
              4. FFI Weight Derivation
            </h2>
            <p className="text-sm text-text-muted mb-4">
              OLS: <code className="text-xs bg-ui-surface px-1 py-0.5 rounded">
                adj_net ~ w₀ + w₁·eFG_margin + w₂·TOV_edge + w₃·OREB_edge + w₄·FTA_margin
              </code> across all{' '}
              {calibration.ffi_teams_used ?? 30} teams. R² ={' '}
              <strong>{num(calibration.ffi_adj_net_r_squared)}</strong>.
            </p>

            {calibration.ffi_adj_net_r_squared != null &&
              calibration.ffi_adj_net_r_squared >= 0.5 && (
              <div className="mb-4 flex items-start gap-2 bg-green-50 border border-green-200 rounded-lg px-4 py-3 text-sm text-green-800">
                <CheckCircle className="w-4 h-4 mt-0.5 shrink-0" />
                <span>
                  High R² — four factors explain adj_net well this season. Proposed weights below
                  can be considered for <code>NBA_FFI_WEIGHTS</code> in{' '}
                  <code>nba/ratings_config.py</code> after the season concludes.
                </span>
              </div>
            )}

            <div className="overflow-x-auto border border-ui-border rounded-lg">
              <table className="w-full">
                <thead>
                  <tr className="bg-ui-surface border-b border-ui-border text-xs uppercase tracking-wider text-text-muted">
                    <th className="px-4 py-2 text-left">Four Factor</th>
                    <th className="px-4 py-2 text-right">Proposed (data-driven)</th>
                    <th className="px-4 py-2 text-right">Current (configured)</th>
                    <th className="px-4 py-2 text-right">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ui-border/50">
                  <WeightRow
                    label="EFG margin"
                    proposed={calibration.ffi_proposed_weight_efg}
                    current={calibration.ffi_current_weight_efg}
                  />
                  <WeightRow
                    label="TOV edge"
                    proposed={calibration.ffi_proposed_weight_tov}
                    current={calibration.ffi_current_weight_tov}
                  />
                  <WeightRow
                    label="OREB edge"
                    proposed={calibration.ffi_proposed_weight_oreb}
                    current={calibration.ffi_current_weight_oreb}
                  />
                  <WeightRow
                    label="FTA margin"
                    proposed={calibration.ffi_proposed_weight_fta}
                    current={calibration.ffi_current_weight_fta}
                  />
                </tbody>
              </table>
            </div>

            <p className="mt-3 text-xs text-text-muted">
              Proposed weights are derived by running OLS on the current season&apos;s 30 teams and
              normalising positive coefficients to sum to 1. They reflect within-season patterns
              only and should not be adopted until multi-season validation is complete (Phase 3B).
            </p>
          </section>

          {/* ── Methodology note ── */}
          <section className="p-6 bg-ui-surface border border-ui-border rounded-lg">
            <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wider mb-4">
              Methodology Notes
            </h2>
            <div className="grid md:grid-cols-2 gap-4 text-sm">
              <div>
                <span className="font-semibold text-text-primary">Prediction accuracy</span>
                <span className="text-text-muted ml-2">
                  Season-end adj_net ratings are used retroactively. Because these ratings
                  already incorporate the outcomes being evaluated, accuracy is optimistically
                  biased. All-else-equal, 69–72% is typical for mature rating systems.
                </span>
              </div>
              <div>
                <span className="font-semibold text-text-primary">OLS model scale</span>
                <span className="text-text-muted ml-2">
                  β₁ converts adj_net advantage (pts/100 poss) to expected raw-point margin.
                  An NBA game averages ~100 poss/team, so β₁ should approach 1.0 at season end.
                </span>
              </div>
              <div>
                <span className="font-semibold text-text-primary">Empirical HCA</span>
                <span className="text-text-muted ml-2">
                  Derived as the OLS intercept (β₀). Compared to{' '}
                  <code>home_court_adj</code> in ratings_config.py, which is in pts/100 poss.
                  At ~100 poss/game these are roughly the same scale.
                </span>
              </div>
              <div>
                <span className="font-semibold text-text-primary">FFI R²</span>
                <span className="text-text-muted ml-2">
                  The four factors are mathematically related to scoring margin, so high R² is
                  expected (≥0.95 at season end). R² here measures how well the specific four
                  factor edges predict adj_net — not whether adj_net predicts outcomes.
                </span>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
