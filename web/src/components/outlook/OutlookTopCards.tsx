'use client';

import clsx from 'clsx';
import type { TeamOutlookProjection, TeamOutlookFit } from '@/types/outlook';
import { FitGradeBadge } from './FitGrade';

interface OutlookTopCardsProps {
  projection: TeamOutlookProjection;
  fit: TeamOutlookFit | null;
  /** When set, shows comparison delta badges next to main values */
  scenarioProjection?: TeamOutlookProjection | null;
  isScenarioMode?: boolean;
}

function RankCard({
  label,
  rank,
  adjValue,
  adjLow,
  adjHigh,
  prefix,
  scenarioRank,
  note,
}: {
  label: string;
  rank: number | null;
  adjValue: number | null;
  adjLow: number | null;
  adjHigh: number | null;
  prefix: string;
  scenarioRank?: number | null;
  note?: string;
}) {
  const baseRankDisplay = rank != null ? `#${rank}` : '—';
  const adjDisplay = adjValue != null ? adjValue.toFixed(1) : '—';
  const adjRangeDisplay =
    adjLow != null && adjHigh != null
      ? `${adjLow.toFixed(1)} – ${adjHigh.toFixed(1)}`
      : null;

  const hasScenario = scenarioRank != null;
  const delta = hasScenario && rank != null ? rank - scenarioRank! : null;
  const improved = delta != null && delta > 0;

  return (
    <div className="bg-ui-card border border-ui-border rounded-xl p-5 flex-1 min-w-0">
      <div className="text-xs text-text-muted font-medium uppercase tracking-wide mb-2">{label}</div>

      <div className="flex items-end gap-3 mb-1">
        {hasScenario ? (
          <>
            <div className="text-3xl font-bold font-mono text-text-primary">
              #{scenarioRank}
            </div>
            <div className="text-sm text-text-muted line-through">{baseRankDisplay}</div>
            {delta !== null && delta !== 0 && (
              <span
                className={clsx(
                  'text-sm font-mono font-semibold px-1.5 py-0.5 rounded',
                  improved ? 'text-emerald-700 bg-emerald-50' : 'text-rose-700 bg-rose-50',
                )}
              >
                {improved ? `▲ ${delta}` : `▼ ${Math.abs(delta)}`}
              </span>
            )}
          </>
        ) : (
          <div className="text-3xl font-bold font-mono text-text-primary">{baseRankDisplay}</div>
        )}
      </div>

      <div className="text-xs text-text-muted">
        {prefix} {adjDisplay}
        {adjRangeDisplay && (
          <span className="ml-1 opacity-60">({adjRangeDisplay})</span>
        )}
      </div>
      {note && (
        <div className="mt-2 text-xs text-text-muted italic opacity-70">{note}</div>
      )}
    </div>
  );
}

export function OutlookTopCards({
  projection,
  fit,
  scenarioProjection,
  isScenarioMode,
}: OutlookTopCardsProps) {
  return (
    <div className="space-y-3">
      {isScenarioMode && (
        <div className="flex items-center gap-2 text-xs font-medium text-brand bg-brand/8 rounded-lg px-3 py-2 border border-brand/20">
          <span className="w-2 h-2 rounded-full bg-brand inline-block" />
          Scenario mode — strikethrough values are baseline
        </div>
      )}

      <div className="flex gap-4 flex-wrap">
        <RankCard
          label="Projected Rank"
          rank={projection.projected_national_rank}
          adjValue={projection.projected_adj_em}
          adjLow={projection.projected_adj_em_low}
          adjHigh={projection.projected_adj_em_high}
          prefix="AdjEM"
          scenarioRank={
            (scenarioProjection as any)?.approx_national_rank ?? null
          }
        />
        <RankCard
          label="Offense Rank"
          rank={projection.projected_offense_rank}
          adjValue={projection.projected_adj_o}
          adjLow={projection.projected_adj_o_low}
          adjHigh={projection.projected_adj_o_high}
          prefix="AdjO"
          scenarioRank={scenarioProjection?.projected_offense_rank ?? null}
        />
        <RankCard
          label="Defense Rank"
          rank={projection.projected_defense_rank}
          adjValue={projection.projected_adj_d}
          adjLow={projection.projected_adj_d_low}
          adjHigh={projection.projected_adj_d_high}
          prefix="AdjD"
          scenarioRank={scenarioProjection?.projected_defense_rank ?? null}
        />
      </div>

      {/* Fit grades row */}
      {fit && (
        <div className="flex items-center gap-4 text-sm text-text-muted flex-wrap">
          <div className="flex items-center gap-2">
            <span>Offensive Fit</span>
            <FitGradeBadge grade={fit.off_grade} showLabel />
          </div>
          <div className="flex items-center gap-2">
            <span>Defensive Fit</span>
            <FitGradeBadge grade={fit.def_grade} showLabel />
          </div>
          <div className="flex-1" />
          <div className="text-xs opacity-60">
            Uncertainty: {projection.team_projection_uncertainty != null
              ? (projection.team_projection_uncertainty * 100).toFixed(0) + '%'
              : '—'}
          </div>
        </div>
      )}
    </div>
  );
}
