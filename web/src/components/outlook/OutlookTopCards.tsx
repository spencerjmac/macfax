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
  scenarioAdjValue,
  scenarioAdjLow,
  scenarioAdjHigh,
  note,
}: {
  label: string;
  rank: number | null;
  adjValue: number | null;
  adjLow: number | null;
  adjHigh: number | null;
  prefix: string;
  scenarioRank?: number | null;
  scenarioAdjValue?: number | null;
  scenarioAdjLow?: number | null;
  scenarioAdjHigh?: number | null;
  note?: string;
}) {
  const hasScenario = scenarioRank != null;

  const displayedRank = hasScenario ? scenarioRank : rank;
  const baseRankDisplay = rank != null ? `#${rank}` : '—';

  const displayedAdj = hasScenario && scenarioAdjValue != null ? scenarioAdjValue : adjValue;
  const displayedLow = hasScenario ? (scenarioAdjLow ?? null) : adjLow;
  const displayedHigh = hasScenario ? (scenarioAdjHigh ?? null) : adjHigh;

  const adjDisplay = displayedAdj != null ? displayedAdj.toFixed(1) : '—';
  const adjRangeDisplay =
    displayedLow != null && displayedHigh != null
      ? `${displayedLow.toFixed(1)} – ${displayedHigh.toFixed(1)}`
      : null;

  const delta = hasScenario && rank != null ? rank - scenarioRank! : null;
  const improved = delta != null && delta > 0;
  const rankChanged = delta !== null && delta !== 0;

  return (
    <div className="bg-ui-card border border-ui-border rounded-xl p-5 flex-1 min-w-0">
      <div className="text-xs text-text-muted font-medium uppercase tracking-wide mb-2">{label}</div>

      <div className="flex items-end gap-3 mb-1">
        <div className="text-3xl font-bold font-mono text-text-primary">
          {displayedRank != null ? `#${displayedRank}` : '—'}
        </div>
        {rankChanged && (
          <>
            <div className="text-sm text-text-muted line-through">{baseRankDisplay}</div>
            <span
              className={clsx(
                'text-sm font-mono font-semibold px-1.5 py-0.5 rounded',
                improved ? 'text-emerald-700 bg-emerald-50' : 'text-rose-700 bg-rose-50',
              )}
            >
              {improved ? `▲ ${Math.abs(delta!)}` : `▼ ${Math.abs(delta!)}`}
            </span>
          </>
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
  const sp = scenarioProjection as any;
  return (
    <div className="space-y-3">
      {isScenarioMode && (
        <div className="flex items-center gap-2 text-xs font-medium text-brand bg-brand/8 rounded-lg px-3 py-2 border border-brand/20">
          <span className="w-2 h-2 rounded-full bg-brand inline-block" />
          Scenario mode — strikethrough values show baseline when rank changes
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
          scenarioRank={sp?.approx_national_rank ?? null}
          scenarioAdjValue={sp?.projected_adj_em ?? null}
          scenarioAdjLow={sp?.projected_adj_em_low ?? null}
          scenarioAdjHigh={sp?.projected_adj_em_high ?? null}
        />
        <RankCard
          label="Offense Rank"
          rank={projection.projected_offense_rank}
          adjValue={projection.projected_adj_o}
          adjLow={projection.projected_adj_o_low}
          adjHigh={projection.projected_adj_o_high}
          prefix="AdjO"
          scenarioRank={sp?.projected_offense_rank ?? null}
          scenarioAdjValue={sp?.projected_adj_o ?? null}
          scenarioAdjLow={sp?.projected_adj_o_low ?? null}
          scenarioAdjHigh={sp?.projected_adj_o_high ?? null}
        />
        <RankCard
          label="Defense Rank"
          rank={projection.projected_defense_rank}
          adjValue={projection.projected_adj_d}
          adjLow={projection.projected_adj_d_low}
          adjHigh={projection.projected_adj_d_high}
          prefix="AdjD"
          scenarioRank={sp?.projected_defense_rank ?? null}
          scenarioAdjValue={sp?.projected_adj_d ?? null}
          scenarioAdjLow={sp?.projected_adj_d_low ?? null}
          scenarioAdjHigh={sp?.projected_adj_d_high ?? null}
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
