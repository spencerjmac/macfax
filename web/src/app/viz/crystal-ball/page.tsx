'use client';

import { useState, useEffect, useMemo } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { CrystalBallData, CrystalBallTeam, ChecklistItem } from '@/types';
import SeasonSelect from '@/components/SeasonSelect';
import clsx from 'clsx';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TIER_COLORS: Record<string, { bg: string; text: string; label: string }> = {
  champion:  { bg: 'bg-amber-100  border-amber-400',  text: 'text-amber-900',  label: 'Championship Tier' },
  contender: { bg: 'bg-green-50   border-green-400',  text: 'text-green-900',  label: 'Contender' },
  threat:    { bg: 'bg-blue-50    border-blue-300',   text: 'text-blue-900',   label: 'Threat' },
  pretender: { bg: 'bg-slate-50   border-slate-200',  text: 'text-slate-500',  label: 'Pretender' },
};

function getTier(score: number) {
  if (score >= 12) return TIER_COLORS.champion;
  if (score >= 9)  return TIER_COLORS.contender;
  if (score >= 6)  return TIER_COLORS.threat;
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
          </div>
        </div>
      ))}
    </div>
  );
}

function TeamRow({ team, rank }: { team: CrystalBallTeam; rank: number }) {
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
                href={`/team/${team.team_slug}`}
                className="font-semibold text-sm hover:text-brand transition-colors"
                onClick={(e) => e.stopPropagation()}
              >
                {team.tournament_seed != null && (
                  <span className="text-[11px] font-bold text-brand/70 mr-1">
                    {team.tournament_seed}
                  </span>
                )}
                {team.team_name}
              </Link>
              <div className="text-xs text-text-muted">
                {team.conference}
                {team.tournament_region && (
                  <span className="ml-1 text-brand/60">· {team.tournament_region}</span>
                )}
              </div>
            </div>
          </div>
        </td>

        {/* Record */}
        <td className="px-3 py-3 text-sm font-mono text-center hidden sm:table-cell">
          {team.record}
        </td>

        {/* AdjEM */}
        <td className="px-3 py-3 text-sm font-mono text-center hidden md:table-cell">
          {team.adj_em > 0 ? '+' : ''}{team.adj_em.toFixed(1)}
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
          <td colSpan={8} className="px-4 py-3">
            <ChecklistDetail items={team.checklist.items} />
          </td>
        </tr>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function CrystalBallPage() {
  const [data, setData] = useState<CrystalBallData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [season, setSeason] = useState(2026);
  const [tournamentFilter, setTournamentFilter] = useState<'all' | 'tournament'>('all');
  const [search, setSearch] = useState('');

  useEffect(() => {
    load();
  }, [season, tournamentFilter]);

  async function load() {
    try {
      setLoading(true);
      setError(null);
      const result = await api.getCrystalBall({ season, filter: tournamentFilter });
      setData(result);
    } catch (err: any) {
      setError(err.message || 'Failed to load Crystal Ball data');
    } finally {
      setLoading(false);
    }
  }

  const displayTeams = useMemo(() => {
    if (!data) return [];
    if (!search.trim()) return data.teams;
    const q = search.toLowerCase();
    return data.teams.filter((t) =>
      t.team_name.toLowerCase().includes(q) ||
      t.conference.toLowerCase().includes(q) ||
      (t.tournament_region?.toLowerCase().includes(q) ?? false),
    );
  }, [data, search]);

  const hasTournamentData = data?.teams.some((t) => t.tournament_seed != null) ?? false;

  // Tier summary counts
  const tierCounts = useMemo(() => {
    if (!data) return null;
    const teams = data.teams;
    return {
      champion:  teams.filter((t) => t.checklist.passedCount >= 12).length,
      contender: teams.filter((t) => t.checklist.passedCount >= 9 && t.checklist.passedCount < 12).length,
      threat:    teams.filter((t) => t.checklist.passedCount >= 6 && t.checklist.passedCount < 9).length,
    };
  }, [data]);

  return (
    <div className="container mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3 mb-1">
          <span className="text-4xl">🔮</span>
          <h1 className="text-4xl font-bold">The Crystal Ball</h1>
        </div>
        <p className="text-text-muted mt-1">
          Every D1 team evaluated against 15 historical championship benchmarks — efficiency margins,
          Four Factors, resume, and more. Click any team to see the full breakdown.
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-4 items-end">

        <SeasonSelect value={season} onChange={setSeason} />

        {/* Tournament toggle — only shown once we have bracket data */}}
        {hasTournamentData && (
          <div className="flex rounded-lg overflow-hidden border border-ui-border text-sm">
            <button
              onClick={() => setTournamentFilter('all')}
              className={clsx(
                'px-4 py-2 font-medium transition-colors',
                tournamentFilter === 'all'
                  ? 'bg-brand text-white'
                  : 'bg-ui-surface text-text-muted hover:text-text-primary',
              )}
            >
              All Teams
            </button>
            <button
              onClick={() => setTournamentFilter('tournament')}
              className={clsx(
                'px-4 py-2 font-medium transition-colors border-l border-ui-border',
                tournamentFilter === 'tournament'
                  ? 'bg-brand text-white'
                  : 'bg-ui-surface text-text-muted hover:text-text-primary',
              )}
            >
              🏀 Tournament Teams
            </button>
          </div>
        )}

        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search team or conference..."
          className="px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/50 min-w-[220px]"
        />
      </div>

      {/* Tier legend + summary */}
      {tierCounts && (
        <div className="flex flex-wrap gap-3 text-sm">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-50 border border-amber-300">
            <span className="font-bold text-amber-800">12–15</span>
            <span className="text-amber-700">Championship Tier</span>
            <span className="font-mono font-bold text-amber-900">{tierCounts.champion}</span>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-green-50 border border-green-300">
            <span className="font-bold text-green-800">9–11</span>
            <span className="text-green-700">Contender</span>
            <span className="font-mono font-bold text-green-900">{tierCounts.contender}</span>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-50 border border-blue-300">
            <span className="font-bold text-blue-800">6–8</span>
            <span className="text-blue-700">Threat</span>
            <span className="font-mono font-bold text-blue-900">{tierCounts.threat}</span>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-300">
            <span className="font-bold text-slate-600">0–5</span>
            <span className="text-slate-600">Pretender</span>
          </div>
        </div>
      )}

      {/* Checklist key */}
      <div className="text-xs text-text-muted flex items-center gap-2">
        <span className="w-2.5 h-2.5 rounded-full bg-green-500 inline-block" />
        Pass
        <span className="w-2.5 h-2.5 rounded-full bg-slate-300 inline-block ml-2" />
        Fail
        <span className="ml-3 opacity-60">· Hover dots for details · Click any row to expand all 15 checks</span>
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-20 text-text-muted">
          <div className="text-center space-y-3">
            <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-brand mx-auto" />
            <p>Loading championship profiles…</p>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-300 text-red-800 px-4 py-3 rounded-lg">
          <p className="font-semibold">Error</p>
          <p className="text-sm mt-1">{error}</p>
        </div>
      )}

      {/* Table */}
      {!loading && !error && data && (
        <div className="overflow-x-auto border border-ui-border rounded-lg">
          <table className="w-full text-sm">
            <thead className="bg-ui-surface border-b border-ui-border">
              <tr>
                <th className="px-3 py-2 text-center text-xs font-semibold text-text-secondary uppercase tracking-wide w-12">Rk</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-text-secondary uppercase tracking-wide">Team</th>
                <th className="px-3 py-2 text-center text-xs font-semibold text-text-secondary uppercase tracking-wide hidden sm:table-cell">Record</th>
                <th className="px-3 py-2 text-center text-xs font-semibold text-text-secondary uppercase tracking-wide hidden md:table-cell">AdjEM</th>
                <th className="px-3 py-2 text-center text-xs font-semibold text-text-secondary uppercase tracking-wide">Score</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-text-secondary uppercase tracking-wide hidden lg:table-cell">Profile (15 checks)</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-text-secondary uppercase tracking-wide hidden xl:table-cell">Tier</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody>
              {displayTeams.map((team, idx) => (
                <TeamRow key={team.team_slug} team={team} rank={idx + 1} />
              ))}
            </tbody>
          </table>

          {displayTeams.length === 0 && (
            <div className="text-center py-10 text-text-muted">
              No teams found.
            </div>
          )}
        </div>
      )}

      <div className="text-xs text-text-muted pt-2">
        <Link href="/viz" className="hover:text-brand">← Back to Visualizations</Link>
      </div>
    </div>
  );
}

