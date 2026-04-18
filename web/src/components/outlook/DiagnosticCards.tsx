'use client';

import clsx from 'clsx';
import type { TeamOutlookProjection, TeamOutlookFit, OutlookPlayer } from '@/types/outlook';
import { FitGradeBadge } from './FitGrade';

// ── Reusable stat bar ─────────────────────────────────────────────────────────

function StatBar({ value, max = 100, colorClass = 'bg-brand' }: { value: number; max?: number; colorClass?: string }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className="h-1.5 bg-ui-surface rounded-full overflow-hidden mt-1">
      <div className={clsx('h-full rounded-full transition-all', colorClass)} style={{ width: `${pct}%` }} />
    </div>
  );
}

// ── Continuity & stability ────────────────────────────────────────────────────

interface ContinuityCardProps {
  projection: TeamOutlookProjection;
  scenarioProjection?: TeamOutlookProjection | null;
}

function deltaSpan(base: number | null, scenario: number | null, positive: boolean = true) {
  if (base == null || scenario == null) return null;
  const delta = scenario - base;
  if (Math.abs(delta) < 0.01) return null;
  const improved = positive ? delta > 0 : delta < 0;
  return (
    <span
      className={clsx(
        'ml-2 text-xs font-mono px-1 rounded',
        improved ? 'text-emerald-700 bg-emerald-50' : 'text-rose-700 bg-rose-50',
      )}
    >
      {delta > 0 ? '+' : ''}{delta.toFixed(1)}
    </span>
  );
}

export function ContinuityCards({ projection, scenarioProjection }: ContinuityCardProps) {
  const sp = scenarioProjection;
  const returnerPct = projection.returner_minutes_fraction != null
    ? (projection.returner_minutes_fraction * 100).toFixed(0)
    : '—';
  const continuityPct = projection.continuity_score?.toFixed(0) ?? '—';

  return (
    <div className="grid grid-cols-2 gap-4">
      <div className="bg-ui-card border border-ui-border rounded-xl p-4">
        <div className="text-xs text-text-muted font-medium uppercase tracking-wide mb-1">
          Returning Min%
        </div>
        <div className="text-2xl font-bold font-mono">
          {returnerPct}%
          {sp && deltaSpan(
            projection.returner_minutes_fraction != null ? projection.returner_minutes_fraction * 100 : null,
            sp.returner_minutes_fraction != null ? sp.returner_minutes_fraction * 100 : null,
          )}
        </div>
        {projection.returner_minutes_fraction != null && (
          <StatBar value={projection.returner_minutes_fraction * 100} />
        )}
        <p className="text-xs text-text-muted mt-2">
          Fraction of projected minutes held by returners
        </p>
      </div>

      <div className="bg-ui-card border border-ui-border rounded-xl p-4">
        <div className="text-xs text-text-muted font-medium uppercase tracking-wide mb-1">
          Roster Continuity%
        </div>
        <div className="text-2xl font-bold font-mono">
          {continuityPct}%
          {sp && deltaSpan(projection.continuity_score, sp.continuity_score)}
        </div>
        {projection.continuity_score != null && (
          <StatBar value={projection.continuity_score} />
        )}
        <p className="text-xs text-text-muted mt-2">
          BPR-weighted continuity index (0–100)
        </p>
      </div>
    </div>
  );
}

// ── Transfer portal card ──────────────────────────────────────────────────────

export function PortalDeltaCard({ projection, scenarioProjection }: ContinuityCardProps) {
  const sp = scenarioProjection;
  const transferPct = projection.transfer_dependence_score?.toFixed(0) ?? '—';
  const fitRisk = projection.transfer_fit_risk_score != null
    ? (projection.transfer_fit_risk_score * 100).toFixed(0) + '%'
    : '—';

  return (
    <div className="bg-ui-card border border-ui-border rounded-xl p-4">
      <div className="text-xs text-text-muted font-medium uppercase tracking-wide mb-3">
        Portal Dependence
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="text-xs text-text-muted mb-0.5">Transfer Dep. Score</div>
          <div className="text-xl font-bold font-mono">
            {transferPct}
            {sp && deltaSpan(projection.transfer_dependence_score, sp.transfer_dependence_score, false)}
          </div>
          {projection.transfer_dependence_score != null && (
            <StatBar value={projection.transfer_dependence_score} colorClass="bg-amber-400" />
          )}
        </div>

        <div>
          <div className="text-xs text-text-muted mb-0.5">Transfer Fit Risk</div>
          <div className="text-xl font-bold font-mono">{fitRisk}</div>
          {projection.transfer_fit_risk_score != null && (
            <StatBar value={projection.transfer_fit_risk_score * 100} colorClass="bg-rose-400" />
          )}
        </div>
      </div>

      <p className="text-xs text-text-muted mt-3">
        High risk = transfer-heavy roster in a poor-fit system → wider outcome range
      </p>
    </div>
  );
}

// ── Fit detail card ───────────────────────────────────────────────────────────

export function FitDetailCard({ fit }: { fit: TeamOutlookFit | null }) {
  if (!fit) {
    return (
      <div className="bg-ui-card border border-ui-border rounded-xl p-4 text-sm text-text-muted">
        No roster fit data available.
      </div>
    );
  }

  return (
    <div className="bg-ui-card border border-ui-border rounded-xl p-4 space-y-4">
      <div className="text-xs text-text-muted font-medium uppercase tracking-wide">
        Roster Fit Detail
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-medium">Offensive Fit</span>
            <FitGradeBadge grade={fit.off_grade} />
          </div>
          {fit.adjusted_off_fit != null && <StatBar value={fit.adjusted_off_fit} />}
          {fit.offensive_strengths.length > 0 && (
            <div className="mt-1.5 text-xs text-emerald-700">
              ▲ {fit.offensive_strengths.slice(0, 2).map(s => s.replace(/_fit$/, '').replace(/_/g, ' ')).join(', ')}
            </div>
          )}
          {fit.offensive_weaknesses.length > 0 && (
            <div className="mt-0.5 text-xs text-rose-600">
              ▼ {fit.offensive_weaknesses.slice(0, 2).map(s => s.replace(/_fit$/, '').replace(/_/g, ' ')).join(', ')}
            </div>
          )}
        </div>

        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-medium">Defensive Fit</span>
            <FitGradeBadge grade={fit.def_grade} />
          </div>
          {fit.adjusted_def_fit != null && <StatBar value={fit.adjusted_def_fit} />}
          {fit.defensive_strengths.length > 0 && (
            <div className="mt-1.5 text-xs text-emerald-700">
              ▲ {fit.defensive_strengths.slice(0, 2).map(s => s.replace(/_fit$/, '').replace(/_/g, ' ')).join(', ')}
            </div>
          )}
          {fit.defensive_weaknesses.length > 0 && (
            <div className="mt-0.5 text-xs text-rose-600">
              ▼ {fit.defensive_weaknesses.slice(0, 2).map(s => s.replace(/_fit$/, '').replace(/_/g, ' ')).join(', ')}
            </div>
          )}
        </div>
      </div>

      {!fit.has_team_style_data && (
        <p className="text-xs text-text-muted bg-ui-surface rounded px-2 py-1">
          ⓘ No team style data — Phase 4 modifiers are neutral placeholders
        </p>
      )}
    </div>
  );
}

// ── Best 5-man lineup ─────────────────────────────────────────────────────────

export function BestFiveLineup({ players }: { players: OutlookPlayer[] }) {
  // Heuristic: top-5 by rotation_rank (already sorted), fallback by minutes_share_p2
  const top5 = [...players]
    .filter(p => p.minutes_share_p2 != null)
    .sort((a, b) => (a.rotation_rank ?? 99) - (b.rotation_rank ?? 99))
    .slice(0, 5);

  if (top5.length === 0) {
    return (
      <div className="bg-ui-card border border-ui-border rounded-xl p-4 text-sm text-text-muted">
        Not enough player data to compute lineup.
      </div>
    );
  }

  return (
    <div className="bg-ui-card border border-ui-border rounded-xl p-4">
      <div className="text-xs text-text-muted font-medium uppercase tracking-wide mb-3">
        Projected Starting 5
        <span className="ml-1 font-normal normal-case">(by projected minutes)</span>
      </div>

      <div className="space-y-2">
        {top5.map((player, i) => (
          <div key={player.player_id} className="flex items-center gap-3">
            <div className="w-5 h-5 rounded-full bg-brand/10 text-brand text-xs font-bold flex items-center justify-center flex-shrink-0">
              {i + 1}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-text-primary truncate">{player.player_name}</span>
                {player.role_bucket && (
                  <span className="text-xs px-1 py-0 rounded bg-ui-surface text-text-muted font-mono border border-ui-border">
                    {player.role_bucket}
                  </span>
                )}
              </div>
            </div>
            <div className="text-right flex-shrink-0">
              <div className={clsx('text-sm font-mono font-semibold',
                (player.projected_bpr ?? 0) >= 3 ? 'text-emerald-700' : 'text-text-primary'
              )}>
                {player.projected_bpr?.toFixed(2) ?? '—'}
              </div>
              <div className="text-xs text-text-muted">
                {player.mpg_p2?.toFixed(1) ?? '--'} mpg
              </div>
            </div>
          </div>
        ))}
      </div>

      <p className="text-xs text-text-muted mt-3 pt-3 border-t border-ui-border">
        ⓘ Baseline heuristic: top-5 by projected rotation rank
      </p>
    </div>
  );
}

// ── Compare summary ───────────────────────────────────────────────────────────

interface CompareSummaryProps {
  baseline: TeamOutlookProjection;
  scenario: TeamOutlookProjection & { approx_national_rank?: number };
}

function DeltaRow({
  label,
  baselineVal,
  scenarioVal,
  format,
  positiveGood,
}: {
  label: string;
  baselineVal: number | null;
  scenarioVal: number | null;
  format?: (v: number) => string;
  positiveGood?: boolean;
}) {
  const fmt = format ?? ((v: number) => v.toFixed(2));
  const delta = baselineVal != null && scenarioVal != null ? scenarioVal - baselineVal : null;
  const improved = delta !== null && (positiveGood !== false ? delta > 0 : delta < 0);
  const worsened = delta !== null && (positiveGood !== false ? delta < 0 : delta > 0);

  return (
    <div className="flex items-center justify-between py-1.5 border-b border-ui-border last:border-0">
      <span className="text-sm text-text-muted">{label}</span>
      <div className="flex items-center gap-3">
        <span className="text-sm font-mono text-text-muted">{baselineVal != null ? fmt(baselineVal) : '—'}</span>
        <span className="text-text-muted">→</span>
        <span className="text-sm font-mono font-semibold">{scenarioVal != null ? fmt(scenarioVal) : '—'}</span>
        {delta !== null && (
          <span
            className={clsx(
              'text-xs px-1.5 py-0.5 rounded font-mono min-w-12 text-center',
              improved ? 'bg-emerald-50 text-emerald-700' : worsened ? 'bg-rose-50 text-rose-700' : 'bg-ui-surface text-text-muted',
            )}
          >
            {delta > 0 ? '+' : ''}{fmt(delta)}
          </span>
        )}
      </div>
    </div>
  );
}

export function CompareSummaryCard({ baseline, scenario }: CompareSummaryProps) {
  const baseRank = baseline.projected_national_rank;
  const scenRank = (scenario as any).approx_national_rank ?? scenario.projected_national_rank;

  return (
    <div className="bg-ui-card border-2 border-brand/30 rounded-xl p-4">
      <div className="text-xs text-text-muted font-medium uppercase tracking-wide mb-3">
        Scenario vs Baseline
      </div>

      <DeltaRow
        label="Proj. Rank (approx)"
        baselineVal={baseRank}
        scenarioVal={scenRank}
        format={v => `#${Math.round(v)}`}
        positiveGood={false}
      />
      <DeltaRow
        label="AdjEM"
        baselineVal={baseline.projected_adj_em}
        scenarioVal={scenario.projected_adj_em}
        positiveGood
      />
      <DeltaRow
        label="AdjO"
        baselineVal={baseline.projected_adj_o}
        scenarioVal={scenario.projected_adj_o}
        positiveGood
      />
      <DeltaRow
        label="AdjD"
        baselineVal={baseline.projected_adj_d}
        scenarioVal={scenario.projected_adj_d}
        positiveGood={false}
      />
      <DeltaRow
        label="Uncertainty"
        baselineVal={baseline.team_projection_uncertainty}
        scenarioVal={scenario.team_projection_uncertainty}
        format={v => (v * 100).toFixed(0) + '%'}
        positiveGood={false}
      />
      <DeltaRow
        label="Continuity"
        baselineVal={baseline.continuity_value_score}
        scenarioVal={scenario.continuity_value_score}
        format={v => v.toFixed(1)}
        positiveGood
      />
      <DeltaRow
        label="Transfer Dep."
        baselineVal={baseline.transfer_dependence_score}
        scenarioVal={scenario.transfer_dependence_score}
        format={v => v.toFixed(1)}
        positiveGood={false}
      />
    </div>
  );
}
