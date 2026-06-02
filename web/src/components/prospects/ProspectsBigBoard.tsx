'use client';

import React, { useMemo, useState } from 'react';
import Image from 'next/image';
import clsx from 'clsx';
import { Prospect, ProspectsData } from '@/types/prospects';
import { ProspectCard } from './ProspectCard';

// ─── Constants ────────────────────────────────────────────────────────────────

const POSITIONS = ['ALL', 'PG', 'SG', 'SF', 'PF', 'C'] as const;
const GRADES    = ['ALL', 'S', 'A', 'D']                as const;

const GRADE_COLORS: Record<string, string> = {
  S: '#B45309', A: '#16A34A', D: '#64748B',
};

const GRADE_BADGE: Record<string, string> = {
  S: 'bg-yellow-100 text-yellow-800',
  A: 'bg-emerald-100 text-emerald-800',
  D: 'bg-slate-100 text-slate-600',
};

const GRADE_ACTIVE: Record<string, string> = {
  ALL: 'bg-brand/10 text-brand border-brand/30',
  S:   'bg-yellow-50 text-yellow-700 border-yellow-300',
  A:   'bg-emerald-50 text-emerald-700 border-emerald-300',
  D:   'bg-slate-50 text-slate-600 border-slate-300',
};

const GRADE_TIER: Record<string, string> = {
  S: 'S TIER', A: 'A TIER', D: 'THE REST',
};

const TIER_LABELS: Record<string, string> = {
  S: 'S TIER',
  A: 'A TIER',
  D: 'THE REST',
};

const POS_BADGE: Record<string, string> = {
  PG: 'bg-blue-100 text-blue-700',
  SG: 'bg-blue-100 text-blue-700',
  SF: 'bg-purple-100 text-purple-700',
  PF: 'bg-emerald-100 text-emerald-700',
  C:  'bg-emerald-100 text-emerald-700',
};

// ─── Stat coloring ────────────────────────────────────────────────────────────

type StatKey = 'bpm' | 'ppg' | 'rpg' | 'apg';

const STAT_THRESHOLDS: Record<StatKey, [number, string][]> = {
  bpm: [[14, 'text-emerald-600 font-semibold'], [10, 'text-emerald-500'], [7, 'text-text-primary'], [-99, 'text-red-500']],
  ppg: [[20, 'text-emerald-600 font-semibold'], [16, 'text-emerald-500'], [12, 'text-text-primary'], [-99, 'text-red-500']],
  rpg: [[9,  'text-emerald-600 font-semibold'], [7,  'text-emerald-500'], [5,  'text-text-primary'], [-99, 'text-red-500']],
  apg: [[6,  'text-emerald-600 font-semibold'], [4,  'text-emerald-500'], [2.5,'text-text-primary'], [-99, 'text-red-500']],
};

function statClass(key: StatKey, val: number | null): string {
  if (val == null) return 'text-text-muted';
  for (const [thresh, cls] of STAT_THRESHOLDS[key]) {
    if (val >= thresh) return cls;
  }
  return 'text-red-500';
}

function formatStat(key: StatKey, val: number | null): string {
  if (val == null) return '—';
  if (key === 'bpm') return val >= 0 ? `+${val.toFixed(1)}` : val.toFixed(1);
  return val.toFixed(1);
}

// ─── Sorting ──────────────────────────────────────────────────────────────────

type SortKey = 'rank' | 'mps' | 'bpm' | 'ppg' | 'rpg' | 'apg';

function getSortVal(p: Prospect, key: SortKey): number {
  const map: Record<SortKey, number | null> = {
    rank: p.rank, mps: p.mps, bpm: p.bpm, ppg: p.ppg, rpg: p.rpg, apg: p.apg,
  };
  return map[key] ?? -Infinity;
}

// ─── Column header ────────────────────────────────────────────────────────────

function ColHeader({
  label, col, sortKey, sortDir, onSort,
  tooltip, align = 'left',
}: {
  label: string; col: SortKey | null; sortKey: SortKey; sortDir: 1 | -1;
  onSort: (k: SortKey) => void; tooltip?: string; align?: 'left' | 'right' | 'center';
}) {
  const active = col && sortKey === col;
  return (
    <th
      className={clsx(
        'px-2 py-2 text-xs font-semibold text-text-muted uppercase tracking-wider whitespace-nowrap',
        col && 'cursor-pointer select-none hover:text-text-primary transition-colors',
        align === 'right' && 'text-right',
        align === 'center' && 'text-center',
        align === 'left' && 'text-left',
      )}
      title={tooltip}
      onClick={() => col && onSort(col)}
    >
      {label}
      {col && (
        <span className="ml-1 opacity-50">
          {active ? (sortDir === 1 ? '↑' : '↓') : '↕'}
        </span>
      )}
    </th>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface Props { data: ProspectsData; }

export function ProspectsBigBoard({ data }: Props) {
  const { prospects } = data;

  const [posFilter,    setPosFilter]    = useState('ALL');
  const [gradeFilter,  setGradeFilter]  = useState('ALL');
  const [search,       setSearch]       = useState('');
  const [sortKey,      setSortKey]      = useState<SortKey>('rank');
  const [sortDir,      setSortDir]      = useState<1 | -1>(1);
  const [expandedRank, setExpandedRank] = useState<number | null>(null);

  const filtered = useMemo(() => {
    let rows = prospects;
    if (posFilter !== 'ALL')   rows = rows.filter(p => p.position === posFilter);
    if (gradeFilter !== 'ALL') rows = rows.filter(p => p.grade === gradeFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      rows = rows.filter(p =>
        p.name.toLowerCase().includes(q) ||
        p.college.toLowerCase().includes(q)
      );
    }
    return [...rows].sort((a, b) => {
      const av = getSortVal(a, sortKey);
      const bv = getSortVal(b, sortKey);
      if (av === -Infinity && bv === -Infinity) return 0;
      if (av === -Infinity) return 1;
      if (bv === -Infinity) return -1;
      return (av - bv) * sortDir;
    });
  }, [prospects, posFilter, gradeFilter, search, sortKey, sortDir]);

  const showDividers =
    gradeFilter === 'ALL' && !search.trim() && sortKey === 'rank' && sortDir === 1;

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir(d => d === 1 ? -1 : 1);
    } else {
      setSortKey(key);
      setSortDir(key === 'rank' ? 1 : -1);
    }
  }

  const gradeCounts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const p of filtered) c[p.grade] = (c[p.grade] || 0) + 1;
    return c;
  }, [filtered]);

  type Row =
    | { type: 'player'; prospect: Prospect }
    | { type: 'divider'; grade: string }
    | { type: 'expanded'; prospect: Prospect };

  const rows = useMemo((): Row[] => {
    const result: Row[] = [];
    let lastGrade = '';
    for (const p of filtered) {
      if (showDividers && p.grade !== lastGrade) {
        result.push({ type: 'divider', grade: p.grade });
        lastGrade = p.grade;
      }
      result.push({ type: 'player', prospect: p });
      if (expandedRank === p.rank) {
        result.push({ type: 'expanded', prospect: p });
      }
    }
    return result;
  }, [filtered, showDividers, expandedRank]);

  const colProps = { sortKey, sortDir, onSort: handleSort };

  return (
    <div className="container mx-auto px-4 py-8">

      {/* ── HEADER ── */}
      <div className="mb-6">
        <div className="text-xs font-semibold tracking-widest text-brand uppercase mb-1">macfax</div>
        <h1 className="text-3xl font-bold text-text-primary">2026 NBA Draft Big Board</h1>
        <p className="mt-1 text-text-muted">MacFax Prospect Score · MPS Model · 11-fold validated</p>
      </div>

      {/* ── CONTROLS ── */}
      <div className="flex flex-wrap gap-3 items-center mb-4">

        {/* Position pills */}
        <div className="flex gap-1.5 flex-wrap">
          {POSITIONS.map(pos => (
            <button
              key={pos}
              onClick={() => setPosFilter(pos)}
              className={clsx(
                'px-3 py-1 rounded-full text-xs font-semibold border transition-colors',
                posFilter === pos
                  ? 'bg-brand/10 text-brand border-brand/30'
                  : 'bg-white text-text-muted border-ui-border hover:border-brand/30',
              )}
            >
              {pos}
            </button>
          ))}
        </div>

        {/* Grade pills */}
        <div className="flex gap-1.5 flex-wrap">
          {GRADES.map(g => (
            <button
              key={g}
              onClick={() => setGradeFilter(g)}
              className={clsx(
                'px-3 py-1 rounded-full text-xs font-bold border transition-colors',
                gradeFilter === g
                  ? GRADE_ACTIVE[g]
                  : 'bg-white text-text-muted border-ui-border hover:border-ui-border',
              )}
            >
              {g === 'D' ? 'THE REST' : g}
            </button>
          ))}
        </div>

        {/* Right: count + search */}
        <div className="ml-auto flex items-center gap-3">
          <span className="text-sm text-text-muted whitespace-nowrap">
            Showing {filtered.length} of {data.totalProspects}
          </span>
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search prospects..."
            className="px-3 py-1.5 bg-ui-surface border border-ui-border rounded-lg text-sm
                       focus:outline-none focus:ring-2 focus:ring-brand/50 w-44 text-text-primary"
          />
        </div>
      </div>

      {/* ── TABLE ── */}
      {filtered.length === 0 ? (
        <div className="text-center py-20 bg-white border border-ui-border rounded-lg">
          <p className="font-medium text-text-primary mb-2">No prospects match current filters.</p>
          <button
            onClick={() => { setPosFilter('ALL'); setGradeFilter('ALL'); setSearch(''); }}
            className="text-sm text-brand hover:underline"
          >
            Clear filters →
          </button>
        </div>
      ) : (
        <div className="overflow-x-auto border border-ui-border rounded-lg">
          <table className="w-full">
            <thead>
              <tr className="border-b border-ui-border bg-ui-surface">
                <ColHeader label="RK"     col="rank" align="left"   {...colProps} />
                <ColHeader label="PLAYER" col={null} align="left"   {...colProps} />
                <ColHeader label="MPS"    col="mps"  align="center" tooltip="MacFax Prospect Score (0–100)" {...colProps} />
                <ColHeader label="BPM"    col="bpm"  align="right"  tooltip="Box Plus/Minus — #1 NBA outcome predictor (r=0.33)" {...colProps} />
                <ColHeader label="PPG"    col="ppg"  align="right"  tooltip="Points per game" {...colProps} />
                <ColHeader label="REB"    col="rpg"  align="right"  tooltip="Rebounds per game" {...colProps} />
                <ColHeader label="AST"    col="apg"  align="right"  tooltip="Assists per game" {...colProps} />
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => {

                if (row.type === 'divider') {
                  const g = row.grade;
                  return (
                    <tr key={`div-${g}`}>
                      <td colSpan={7} className="px-3 py-2 bg-slate-50 border-b border-ui-border">
                        <div className="flex items-center gap-2">
                          <span
                            className="text-xs font-bold uppercase tracking-widest"
                            style={{ color: GRADE_COLORS[g] }}
                          >
                            {TIER_LABELS[g]}
                          </span>
                          <span className="text-xs text-text-muted font-mono">
                            ({gradeCounts[g] ?? 0})
                          </span>
                          <div className="flex-1 h-px bg-ui-border" />
                        </div>
                      </td>
                    </tr>
                  );
                }

                if (row.type === 'expanded') {
                  const p = row.prospect;
                  return (
                    <tr key={`expanded-${p.rank}`}>
                      <td colSpan={7} className="p-0 border-b-2 border-brand">
                        <ProspectCard prospect={p} />
                      </td>
                    </tr>
                  );
                }

                // player row
                const p = row.prospect;
                const isExpanded = expandedRank === p.rank;

                return (
                  <tr
                    key={`player-${p.rank}`}
                    onClick={() => setExpandedRank(isExpanded ? null : p.rank)}
                    style={{ borderLeft: `3px solid ${GRADE_COLORS[p.grade]}` }}
                    className={clsx(
                      'border-b border-ui-border cursor-pointer transition-colors',
                      isExpanded ? 'bg-slate-50' : 'hover:bg-slate-50',
                    )}
                  >
                    {/* RK */}
                    <td className="px-3 py-2.5 text-sm font-mono text-text-muted w-10">
                      {p.rank}
                    </td>

                    {/* PLAYER */}
                    <td className="px-2 py-2 min-w-[220px]">
                      <div className="flex items-center gap-3">
                        {/* Headshot */}
                        <div className="w-10 h-10 rounded-full overflow-hidden bg-slate-100 flex-shrink-0 flex items-center justify-center border border-ui-border">
                          {p.headshot ? (
                            <Image
                              src={p.headshot}
                              alt={p.name}
                              width={40}
                              height={40}
                              className="object-cover object-top w-full h-full"
                              onError={(e) => {
                                (e.target as HTMLImageElement).style.display = 'none';
                              }}
                            />
                          ) : (
                            <span className="text-xs font-bold text-text-muted">
                              {p.name.split(' ').map(n => n[0]).slice(0, 2).join('')}
                            </span>
                          )}
                        </div>
                        <div className="min-w-0">
                          <div className="font-semibold text-sm text-text-primary leading-tight truncate">
                            {p.name}
                          </div>
                          <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                            <span className={clsx(
                              'text-[10px] font-bold px-1.5 py-0.5 rounded',
                              POS_BADGE[p.position] ?? 'bg-slate-100 text-slate-600',
                            )}>
                              {p.position}
                            </span>
                            <span className="text-xs text-text-muted">{p.college}</span>
                            <span className="text-xs text-text-muted font-mono">{p.age.toFixed(1)}y</span>
                          </div>
                        </div>
                      </div>
                    </td>

                    {/* MPS */}
                    <td className="px-2 py-2.5 w-28 text-center">
                      <div
                        className="text-xl font-bold font-mono leading-tight"
                        style={{ color: GRADE_COLORS[p.grade] }}
                      >
                        {p.mps.toFixed(1)}
                      </div>
                      <div className="flex items-center justify-center gap-1 mt-0.5">
                        <span className={clsx('text-[10px] font-bold px-1.5 py-0.5 rounded', GRADE_BADGE[p.grade])}>
                          {p.grade}
                        </span>
                        <span className="text-[9px] text-text-muted uppercase tracking-wide font-mono">
                          {GRADE_TIER[p.grade]}
                        </span>
                      </div>
                    </td>

                    {/* BPM */}
                    <td className={clsx('px-2 py-2.5 text-sm font-mono text-right w-16', statClass('bpm', p.bpm))}>
                      {formatStat('bpm', p.bpm)}
                    </td>

                    {/* PPG */}
                    <td className={clsx('px-2 py-2.5 text-sm font-mono text-right w-16', statClass('ppg', p.ppg))}>
                      {formatStat('ppg', p.ppg)}
                    </td>

                    {/* REB */}
                    <td className={clsx('px-2 py-2.5 text-sm font-mono text-right w-16', statClass('rpg', p.rpg))}>
                      {formatStat('rpg', p.rpg)}
                    </td>

                    {/* AST */}
                    <td className={clsx('px-2 py-2.5 text-sm font-mono text-right w-16', statClass('apg', p.apg))}>
                      {formatStat('apg', p.apg)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ── FOOTER ── */}
      <div className="mt-6 pt-4 border-t border-ui-border flex flex-wrap gap-4 justify-between items-start text-xs text-text-muted">
        <span>macfacts · NBA Draft Analytics</span>
        <span className="max-w-lg">
          MPS scores reflect college statistical production weighted by empirical NBA outcome
          correlation across 500+ historical prospects.
          Known limitations: physical projection and wing position uncertainty.
        </span>
      </div>
    </div>
  );
}
