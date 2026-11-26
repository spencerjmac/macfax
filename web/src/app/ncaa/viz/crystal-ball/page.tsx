'use client';

import { useState, useEffect, useMemo } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { CrystalBallData, CrystalBallTeam, ChecklistItem } from '@macfax/core/types';
import SeasonSelect from '@/components/SeasonSelect';
import clsx from 'clsx';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function ScoreBadge({ passed, total }: { passed: number; total: number }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-sm font-bold border border-ui-border bg-ui-surface text-text-primary">
        {passed}<span className="font-normal opacity-60">/{total}</span>
      </span>
      {/* Fixed-width slot so scores line up whether or not the badge shows */}
      <span className="inline-flex w-[6.5rem] justify-start">
        {passed === total && (
          <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold uppercase tracking-wide bg-brand text-white whitespace-nowrap">
            Title Profile
          </span>
        )}
      </span>
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
                {team.tournament_finish === 'Champ' && <span title="National Champion" className="text-sm ml-1">🏆</span>}
                {team.tournament_finish === 'Runner-Up' && <span title="Runner-Up" className="text-sm ml-1">🥈</span>}
                {team.tournament_finish === 'Final Four' && <span title="Final Four" className="text-sm ml-1">🥉</span>}
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

        {/* Expand arrow */}
        <td className="px-3 py-3 text-center text-text-muted text-xs w-8">
          <span className={clsx('transition-transform inline-block', expanded ? 'rotate-90' : '')}>▶</span>
        </td>
      </tr>

      {/* Expanded checklist */}
      {expanded && (
        <tr className="border-b border-ui-border bg-ui-surface/50">
          <td colSpan={7} className="px-4 py-3">
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
  // undefined = the API's current season (is_current)
  const [season, setSeason] = useState<number | undefined>(undefined);
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

        {/* Tournament toggle — only shown once we have bracket data */}
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

      {/* Historical context (backtest 2005–2026, skip 2020) */}
      <p className="text-sm text-text-secondary">
        On average, 2–3 teams a season have passed all 15. Every champion did except three UConn teams
        (2011, 2014, 2023). Of the 55 that passed, 18 won the title and 31 reached the Final Four.
      </p>

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

