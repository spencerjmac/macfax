'use client';

import { useState, useMemo } from 'react';
import clsx from 'clsx';
import type { OutlookPlayer, ScenarioPlayer, RecruitmentType } from '@/types/outlook';

// ── Helpers ───────────────────────────────────────────────────────────────────

function bprColor(bpr: number | null): string {
  if (bpr == null) return 'text-text-muted';
  if (bpr >= 5) return 'text-emerald-700 font-semibold';
  if (bpr >= 3) return 'text-teal-700';
  if (bpr >= 1) return 'text-text-primary';
  if (bpr >= 0) return 'text-text-muted';
  return 'text-rose-600';
}

function uncertaintyBadge(u: number | null) {
  if (u == null) return null;
  if (u < 0.3) return { label: 'High conf', cls: 'bg-emerald-50 text-emerald-700' };
  if (u < 0.5) return { label: 'Moderate', cls: 'bg-yellow-50 text-yellow-700' };
  if (u < 0.7) return { label: 'Low conf', cls: 'bg-orange-50 text-orange-700' };
  return { label: 'Uncertain', cls: 'bg-rose-50 text-rose-700' };
}

const RECRUITMENT_COLORS: Record<RecruitmentType, string> = {
  returner: 'bg-blue-50 text-blue-700',
  transfer: 'bg-amber-50 text-amber-800',
  newcomer: 'bg-purple-50 text-purple-700',
};

const RECRUITMENT_LABELS: Record<RecruitmentType, string> = {
  returner: 'Returner',
  transfer: 'Transfer',
  newcomer: 'Newcomer',
};

function RecruitBadge({ type }: { type: RecruitmentType }) {
  return (
    <span className={clsx('text-xs px-1.5 py-0.5 rounded font-medium', RECRUITMENT_COLORS[type])}>
      {RECRUITMENT_LABELS[type]}
    </span>
  );
}

function RoleBadge({ role }: { role: string | null }) {
  if (!role) return null;
  return (
    <span className="text-xs px-1.5 py-0.5 rounded bg-ui-surface text-text-muted font-mono border border-ui-border">
      {role}
    </span>
  );
}

function ScenarioStateBadge({ state }: { state: ScenarioPlayer['scenarioState'] }) {
  if (state === 'baseline') return null;
  if (state === 'added')
    return <span className="text-xs px-1.5 py-0.5 rounded bg-brand/10 text-brand font-medium">Added</span>;
  return <span className="text-xs px-1.5 py-0.5 rounded bg-rose-50 text-rose-700 font-medium">Removed</span>;
}

function PlaceholderBadge() {
  return (
    <span className="text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 font-medium border border-slate-200">
      Archetype
    </span>
  );
}

type SortKey = 'name' | 'bpr' | 'obpr' | 'dbpr' | 'minutes' | 'rotation' | 'uncertainty';

interface PlayerOutlookTableProps {
  players: (OutlookPlayer | ScenarioPlayer)[];
  isScenarioMode?: boolean;
  /** Called when user clicks the remove/restore button */
  onTogglePlayer?: (playerId: number) => void;
  /** Whether the remove/restore button is enabled */
  canEdit?: boolean;
}

export function PlayerOutlookTable({
  players,
  isScenarioMode = false,
  onTogglePlayer,
  canEdit = false,
}: PlayerOutlookTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('rotation');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortDir(key === 'name' ? 'asc' : 'desc');
    }
  }

  const sorted = useMemo(() => {
    const copy = [...players];
    const dir = sortDir === 'asc' ? 1 : -1;
    copy.sort((a, b) => {
      switch (sortKey) {
        case 'name': return dir * a.player_name.localeCompare(b.player_name);
        case 'bpr': return dir * ((a.projected_bpr ?? -999) - (b.projected_bpr ?? -999));
        case 'obpr': return dir * ((a.projected_obpr ?? -999) - (b.projected_obpr ?? -999));
        case 'dbpr': return dir * ((a.projected_dbpr ?? -999) - (b.projected_dbpr ?? -999));
        case 'minutes': return dir * ((a.minutes_share_p2 ?? 0) - (b.minutes_share_p2 ?? 0));
        case 'rotation': return dir * ((a.rotation_rank ?? 99) - (b.rotation_rank ?? 99));
        case 'uncertainty': return dir * ((a.projection_uncertainty ?? 1) - (b.projection_uncertainty ?? 1));
        default: return 0;
      }
    });
    return copy;
  }, [players, sortKey, sortDir]);

  function SortHeader({
    label,
    colKey,
    className,
  }: {
    label: string;
    colKey: SortKey;
    className?: string;
  }) {
    const active = sortKey === colKey;
    return (
      <th
        className={clsx(
          'table-header px-3 py-2 text-left cursor-pointer select-none whitespace-nowrap',
          active ? 'text-brand' : '',
          className,
        )}
        onClick={() => toggleSort(colKey)}
      >
        {label}
        <span className="ml-1 opacity-50">
          {active ? (sortDir === 'asc' ? '↑' : '↓') : '↕'}
        </span>
      </th>
    );
  }

  if (!players.length) {
    return (
      <div className="text-center py-12 text-text-muted text-sm">
        No player projections found for this team.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-ui-border">
      <table className="rankings-table w-full">
        <thead>
          <tr className="bg-ui-surface">
            <SortHeader label="Player" colKey="name" />
            <SortHeader label="OBPR*" colKey="obpr" />
            <SortHeader label="DBPR*" colKey="dbpr" />
            <SortHeader label="BPR*" colKey="bpr" />
            <th className="table-header px-3 py-2 text-left">Role</th>
            <th className="table-header px-3 py-2 text-left">Recruitment</th>
            <SortHeader label="Min%" colKey="minutes" />
            <SortHeader label="MPG" colKey="minutes" />
            <SortHeader label="Conf." colKey="uncertainty" />
            {canEdit && <th className="table-header px-3 py-2 text-left w-16" />}
          </tr>
        </thead>
        <tbody>
          {sorted.map((player) => {
            const scenarioPlayer = 'scenarioState' in player ? player : null;
            const isRemoved = scenarioPlayer?.scenarioState === 'removed';
            const isAdded = scenarioPlayer?.scenarioState === 'added';
            const badge = uncertaintyBadge(player.projection_uncertainty);
            const mpg = player.mpg_p2 != null
              ? player.mpg_p2.toFixed(1)
              : player.minutes_share_p2 != null
              ? (player.minutes_share_p2 * 40).toFixed(1)
              : '—';
            const minPct = player.minutes_share_p2 != null
              ? (player.minutes_share_p2 * 100).toFixed(0) + '%'
              : '—';

            return (
              <tr
                key={`${player.player_id}-${scenarioPlayer?.scenarioState ?? 'base'}`}
                className={clsx(
                  'border-b border-ui-border transition-colors',
                  isRemoved ? 'opacity-40 bg-rose-50/30' : 'hover:bg-ui-surface',
                )}
              >
                {/* Player name */}
                <td className="px-3 py-2.5">
                  <div className="flex items-center gap-2">
                    <div>
                      <div className="font-medium text-sm text-text-primary leading-tight">
                        {player.player_name}
                        {scenarioPlayer && scenarioPlayer.scenarioState !== 'baseline' && (
                          <span className="ml-2">
                            <ScenarioStateBadge state={scenarioPlayer.scenarioState} />
                          </span>
                        )}
                        {player.is_placeholder && (
                          <span className="ml-2">
                            <PlaceholderBadge />
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-text-muted">{player.position || '—'}</div>
                    </div>
                  </div>
                </td>

                {/* OBPR */}
                <td className={clsx('px-3 py-2.5 text-sm font-mono', bprColor(player.projected_obpr))}>
                  {player.projected_obpr != null ? player.projected_obpr.toFixed(2) : '—'}
                </td>

                {/* DBPR */}
                <td className={clsx('px-3 py-2.5 text-sm font-mono', bprColor(player.projected_dbpr))}>
                  {player.projected_dbpr != null ? player.projected_dbpr.toFixed(2) : '—'}
                </td>

                {/* BPR */}
                <td className={clsx('px-3 py-2.5 text-sm font-mono font-semibold', bprColor(player.projected_bpr))}>
                  {player.projected_bpr != null ? player.projected_bpr.toFixed(2) : '—'}
                </td>

                {/* Role */}
                <td className="px-3 py-2.5">
                  <RoleBadge role={player.role_bucket} />
                </td>

                {/* Recruitment */}
                <td className="px-3 py-2.5">
                  <RecruitBadge type={player.recruitment_type} />
                </td>

                {/* Min% */}
                <td className="px-3 py-2.5 text-sm font-mono text-text-muted">{minPct}</td>

                {/* MPG */}
                <td className="px-3 py-2.5 text-sm font-mono text-text-muted">{mpg}</td>

                {/* Confidence */}
                <td className="px-3 py-2.5">
                  {badge ? (
                    <span className={clsx('text-xs px-1.5 py-0.5 rounded', badge.cls)}>{badge.label}</span>
                  ) : (
                    <span className="text-xs text-text-muted">—</span>
                  )}
                </td>

                {/* Edit action */}
                {canEdit && (
                  <td className="px-3 py-2.5 text-center">
                    <button
                      onClick={() => onTogglePlayer?.(player.player_id)}
                      className={clsx(
                        'text-xs px-2 py-1 rounded border transition-colors',
                        isRemoved
                          ? 'border-brand text-brand hover:bg-brand/10'
                          : 'border-rose-300 text-rose-600 hover:bg-rose-50',
                      )}
                    >
                      {isRemoved ? 'Restore' : 'Remove'}
                    </button>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="px-4 py-2 bg-ui-surface text-xs text-text-muted border-t border-ui-border">
        * Projected values for next season
      </div>
    </div>
  );
}
