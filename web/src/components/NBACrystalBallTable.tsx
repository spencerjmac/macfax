'use client';

import { useState } from 'react';
import Link from 'next/link';
import clsx from 'clsx';
import type { ChecklistItem } from '@/types';
import type { NBACrystalBallData, NBACrystalBallTeam } from '@/types/nba';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const FINISH_BADGE: Record<string, string> = {
  Champion: '🏆',
  'Runner-Up': '🥈',
  'Conf Finals': '🥉',
};

const TIER_COLORS: Record<string, { bg: string; text: string; label: string }> = {
  champion:  { bg: 'bg-amber-100  border-amber-400',  text: 'text-amber-900',  label: 'Championship Tier' },
  contender: { bg: 'bg-green-50   border-green-400',  text: 'text-green-900',  label: 'Contender' },
  threat:    { bg: 'bg-blue-50    border-blue-300',   text: 'text-blue-900',   label: 'Threat' },
  pretender: { bg: 'bg-slate-50   border-slate-200',  text: 'text-slate-500',  label: 'Pretender' },
};

function getTier(passed: number) {
  if (passed >= 8) return TIER_COLORS.champion;
  if (passed >= 6) return TIER_COLORS.contender;
  if (passed >= 4) return TIER_COLORS.threat;
  return TIER_COLORS.pretender;
}

function ScoreBadge({ passed, total }: { passed: number; total: number }) {
  const tier = getTier(passed);
  return (
    <span className={clsx('inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-sm font-bold border', tier.bg, tier.text)}>
      {passed}<span className="font-normal opacity-60">/{total}</span>
    </span>
  );
}

function CheckDots({ items }: { items: ChecklistItem[] }) {
  return (
    <div className="flex gap-0.5 flex-wrap">
      {items.map((item) => (
        <span
          key={item.key}
          title={`${item.label}: ${item.pass ? '✓' : '✗'} (${item.value} — threshold ${item.threshold})`}
          className={clsx(
            'w-2.5 h-2.5 rounded-full transition-all',
            item.pass ? 'bg-green-500' : 'bg-slate-300',
          )}
        />
      ))}
    </div>
  );
}

function ChecklistDetail({ items }: { items: ChecklistItem[] }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 p-4 bg-ui-surface rounded-lg border border-ui-border">
      {items.map((item) => (
        <div
          key={item.key}
          className={clsx(
            'flex items-start gap-2 px-3 py-2 rounded-md border text-xs',
            item.pass
              ? 'bg-green-50 border-green-200 text-green-900'
              : 'bg-slate-50 border-slate-200 text-slate-500',
          )}
        >
          <span className={clsx('mt-0.5 shrink-0 text-base', item.pass ? 'text-green-600' : 'text-slate-300')}>
            {item.pass ? '✓' : '✗'}
          </span>
          <div>
            <div className="font-semibold leading-tight">{item.label}</div>
            <div className="font-mono mt-0.5">
              {item.value}
              <span className="text-[10px] ml-1 opacity-60">({item.threshold})</span>
            </div>
            {item.details && (
              <div className="text-[10px] mt-0.5 opacity-70">{item.details}</div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function TeamRow({ team, rank }: { team: NBACrystalBallTeam; rank: number }) {
  const [expanded, setExpanded] = useState(false);
  const tier = getTier(team.checklist.passedCount);

  return (
    <>
      <tr
        className={clsx(
          'border-b border-ui-border cursor-pointer select-none transition-colors',
          expanded ? 'bg-ui-hover' : 'hover:bg-ui-hover',
        )}
        onClick={() => setExpanded((v) => !v)}
      >
        {/* Rank */}
        <td className="px-3 py-3 text-center text-sm font-mono font-semibold text-text-muted w-12">
          {rank}
        </td>

        {/* Team */}
        <td className="px-3 py-3">
          <div className="flex items-center gap-2">
            {team.team_logo && (
              <img
                src={team.team_logo}
                alt={team.team_name}
                className="w-7 h-7 object-contain shrink-0"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
            )}
            <div>
              <Link
                href={`/nba/team/${team.team_slug}`}
                className="font-semibold text-sm hover:text-brand transition-colors"
                onClick={(e) => e.stopPropagation()}
              >
                {team.conference_seed != null && (
                  <span className="text-[11px] font-bold text-brand/70 mr-1">
                    #{team.conference_seed}
                  </span>
                )}
                {team.team_name}
                {team.playoff_finish && FINISH_BADGE[team.playoff_finish] && (
                  <span title={team.playoff_finish} className="text-sm ml-1">
                    {FINISH_BADGE[team.playoff_finish]}
                  </span>
                )}
              </Link>
              <div className="text-xs text-text-muted">{team.conference}</div>
            </div>
          </div>
        </td>

        {/* Record */}
        <td className="px-3 py-3 text-sm font-mono text-center hidden sm:table-cell">
          {team.record}
        </td>

        {/* Adj Net */}
        <td className="px-3 py-3 text-sm font-mono font-semibold text-center text-brand">
          {team.adj_net >= 0 ? '+' : ''}{team.adj_net.toFixed(1)}
        </td>

        {/* Adj Off */}
        <td className="px-3 py-3 text-sm font-mono text-center hidden md:table-cell text-emerald-700">
          {team.adj_off.toFixed(1)}
        </td>

        {/* Adj Def */}
        <td className="px-3 py-3 text-sm font-mono text-center hidden md:table-cell text-rose-700">
          {team.adj_def.toFixed(1)}
        </td>

        {/* Score */}
        <td className="px-3 py-3 text-center">
          <ScoreBadge passed={team.checklist.passedCount} total={team.checklist.totalCount} />
        </td>

        {/* Check dots */}
        <td className="px-3 py-3 hidden lg:table-cell">
          <CheckDots items={team.checklist.items} />
        </td>

        {/* Tier */}
        <td className="px-3 py-3 hidden xl:table-cell">
          <span className={clsx('text-xs font-medium', tier.text)}>{tier.label}</span>
        </td>

        {/* Expand arrow */}
        <td className="px-3 py-3 text-center text-text-muted text-xs w-8">
          <span className={clsx('transition-transform inline-block', expanded ? 'rotate-90' : '')}>▶</span>
        </td>
      </tr>

      {/* Expanded checklist */}
      {expanded && (
        <tr className="border-b border-ui-border bg-ui-surface/50">
          <td colSpan={10} className="px-4 py-3">
            <ChecklistDetail items={team.checklist.items} />
          </td>
        </tr>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Table
// ---------------------------------------------------------------------------

interface Props {
  data: NBACrystalBallData;
}

export default function NBACrystalBallTable({ data }: Props) {
  const tierCounts = {
    champion:  data.teams.filter((t) => t.checklist.passedCount >= 8).length,
    contender: data.teams.filter((t) => t.checklist.passedCount >= 6 && t.checklist.passedCount < 8).length,
    threat:    data.teams.filter((t) => t.checklist.passedCount >= 4 && t.checklist.passedCount < 6).length,
  };

  return (
    <div className="space-y-6">
      {/* Tier legend + summary */}
      <div className="flex flex-wrap gap-3 text-sm">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-50 border border-amber-300">
          <span className="font-bold text-amber-800">8–10</span>
          <span className="text-amber-700">Championship Tier</span>
          <span className="font-mono font-bold text-amber-900">{tierCounts.champion}</span>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-green-50 border border-green-300">
          <span className="font-bold text-green-800">6–7</span>
          <span className="text-green-700">Contender</span>
          <span className="font-mono font-bold text-green-900">{tierCounts.contender}</span>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-50 border border-blue-300">
          <span className="font-bold text-blue-800">4–5</span>
          <span className="text-blue-700">Threat</span>
          <span className="font-mono font-bold text-blue-900">{tierCounts.threat}</span>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-300">
          <span className="font-bold text-slate-600">0–3</span>
          <span className="text-slate-600">Pretender</span>
        </div>
      </div>

      {/* Checklist key */}
      <div className="text-xs text-text-muted flex items-center gap-2">
        <span className="w-2.5 h-2.5 rounded-full bg-green-500 inline-block" />
        Pass
        <span className="w-2.5 h-2.5 rounded-full bg-slate-300 inline-block ml-2" />
        Fail
        <span className="ml-3 opacity-60">· Hover dots for details · Click any row to expand all 10 checks</span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto border border-ui-border rounded-lg">
        <table className="w-full text-sm">
          <thead className="bg-ui-surface border-b border-ui-border">
            <tr>
              <th className="px-3 py-2 text-center text-xs font-semibold text-text-secondary uppercase tracking-wide w-12">Rk</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-secondary uppercase tracking-wide">Team</th>
              <th className="px-3 py-2 text-center text-xs font-semibold text-text-secondary uppercase tracking-wide hidden sm:table-cell">Record</th>
              <th className="px-3 py-2 text-center text-xs font-semibold text-text-secondary uppercase tracking-wide">Adj Net</th>
              <th className="px-3 py-2 text-center text-xs font-semibold text-text-secondary uppercase tracking-wide hidden md:table-cell">Adj Off</th>
              <th className="px-3 py-2 text-center text-xs font-semibold text-text-secondary uppercase tracking-wide hidden md:table-cell">Adj Def</th>
              <th className="px-3 py-2 text-center text-xs font-semibold text-text-secondary uppercase tracking-wide">Score</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-secondary uppercase tracking-wide hidden lg:table-cell">Profile (10 checks)</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-text-secondary uppercase tracking-wide hidden xl:table-cell">Tier</th>
              <th className="w-8" />
            </tr>
          </thead>
          <tbody>
            {data.teams.map((team, idx) => (
              <TeamRow key={team.team_slug} team={team} rank={idx + 1} />
            ))}
          </tbody>
        </table>

        {data.teams.length === 0 && (
          <div className="text-center py-10 text-text-muted">
            No teams found.
          </div>
        )}
      </div>
    </div>
  );
}
