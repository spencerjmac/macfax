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

function RankRangeCard({
  label,
  rank,
  low,
  high,
  adjValue,
  adjLow,
  adjHigh,
  prefix,
  higherIsBetter,
  scenarioRank,
  scenarioLow,
  scenarioHigh,
  note,
}: {
  label: string;
  rank: number | null;
  low: number | null;
  high: number | null;
  adjValue: number | null;
  adjLow: number | null;
  adjHigh: number | null;
  prefix: string;
  higherIsBetter: boolean;
  scenarioRank?: number | null;
  scenarioLow?: number | null;
  scenarioHigh?: number | null;
  /** Footnote shown below the card — used to flag approximate/carried-over values */
  note?: string;
}) {
  const rankDisplay = rank != null ? String(rank) : '—';
  const rangeDisplay = low != null && high != null ? `${low} – ${high}` : '—';
  const adjDisplay = adjValue != null ? adjValue.toFixed(1) : '—';
  const adjRangeDisplay =
    adjLow != null && adjHigh != null
      ? `${adjLow.toFixed(1)} – ${adjHigh.toFixed(1)}`
      : null;

  const hasScenario = scenarioRank != null;
  const delta = hasScenario && rank != null ? rank - scenarioRank! : null;
  // For rank: lower is better, so positive delta = improved (scenario rank is lower)
  const improved = delta != null && delta > 0;
  const worsened = delta != null && delta < 0;

  return (
    <div className="bg-ui-card border border-ui-border rounded-xl p-5 flex-1 min-w-0">
      <div className="text-xs text-text-muted font-medium uppercase tracking-wide mb-2">{label}</div>

      <div className="flex items-end gap-3 mb-1">
        {hasScenario ? (
          <>
            <div className="text-3xl font-bold font-mono text-text-primary">
              {scenarioLow != null && scenarioHigh != null
                ? `${scenarioLow} – ${scenarioHigh}`
                : scenarioRank != null ? String(scenarioRank) : '—'}
            </div>
            <div className="text-sm text-text-muted line-through">{rangeDisplay}</div>
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
          <div className="text-3xl font-bold font-mono text-text-primary">{rangeDisplay}</div>
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
  // Build scenario rank ranges from scenario projection (using approx rank from API)
  const scenarioRankLow = scenarioProjection?.national_rank_range_low ?? null;
  const scenarioRankHigh = scenarioProjection?.national_rank_range_high ?? null;
  const scenarioOffLow = scenarioProjection?.offense_rank_range_low ?? null;
  const scenarioOffHigh = scenarioProjection?.offense_rank_range_high ?? null;
  const scenarioDefLow = scenarioProjection?.defense_rank_range_low ?? null;
  const scenarioDefHigh = scenarioProjection?.defense_rank_range_high ?? null;

  return (
    <div className="space-y-3">
      {isScenarioMode && (
        <div className="flex items-center gap-2 text-xs font-medium text-brand bg-brand/8 rounded-lg px-3 py-2 border border-brand/20">
          <span className="w-2 h-2 rounded-full bg-brand inline-block" />
          Scenario mode — strikethrough values are baseline
        </div>
      )}

      <div className="flex gap-4 flex-wrap">
        <RankRangeCard
          label="Roster Ranking Range"
          rank={projection.projected_national_rank}
          low={projection.national_rank_range_low}
          high={projection.national_rank_range_high}
          adjValue={projection.projected_adj_em}
          adjLow={projection.projected_adj_em_low}
          adjHigh={projection.projected_adj_em_high}
          prefix="AdjEM"
          higherIsBetter
          scenarioRank={
            (scenarioProjection as any)?.approx_national_rank ?? null
          }
          scenarioLow={scenarioRankLow}
          scenarioHigh={scenarioRankHigh}
        />
        <RankRangeCard
          label="Offense Range"
          rank={projection.projected_offense_rank}
          low={projection.offense_rank_range_low}
          high={projection.offense_rank_range_high}
          adjValue={projection.projected_adj_o}
          adjLow={projection.projected_adj_o_low}
          adjHigh={projection.projected_adj_o_high}
          prefix="AdjO"
          higherIsBetter
          scenarioRank={null}
          scenarioLow={scenarioOffLow}
          scenarioHigh={scenarioOffHigh}
          note={isScenarioMode ? 'Offense rank unchanged — single-team scenario' : undefined}
        />
        <RankRangeCard
          label="Defense Range"
          rank={projection.projected_defense_rank}
          low={projection.defense_rank_range_low}
          high={projection.defense_rank_range_high}
          adjValue={projection.projected_adj_d}
          adjLow={projection.projected_adj_d_low}
          adjHigh={projection.projected_adj_d_high}
          prefix="AdjD"
          higherIsBetter={false}
          scenarioRank={null}
          scenarioLow={scenarioDefLow}
          scenarioHigh={scenarioDefHigh}
          note={isScenarioMode ? 'Defense rank unchanged — single-team scenario' : undefined}
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
