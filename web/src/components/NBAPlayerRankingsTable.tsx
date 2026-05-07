'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  ColumnDef,
  flexRender,
  SortingState,
  PaginationState,
} from '@tanstack/react-table';
import clsx from 'clsx';
import HeaderWithTooltip from './HeaderWithTooltip';
import { computeRanks, getPercentileColor } from '@/lib/rankingUtils';
import {
  PLAYER_TRADITIONAL_METRICS,
  NBA_ADVANCED_METRICS,
  NBA_IMPACT_METRICS,
  formatPlayerMetric,
  type PlayerMetricMeta,
} from '@/lib/playerMetricMetadata';
import type { NBAPlayerSeasonStats } from '@/types/nba';

type TabId = 'traditional' | 'advanced' | 'impact';

interface NBAPlayerRankingsTableProps {
  data: NBAPlayerSeasonStats[];
  seasonDisplay?: string;
  seasonType?: string;
}

// Primary columns always shown — never in picker
const NBA_TRAD_PRIMARY = ['pts', 'reb', 'ast', 'stl', 'blk', 'tov', 'efg_pct', 'ts_pct', 'ast_to'];
// Secondary (pre-checked) + optional (off by default) — shown in picker
const NBA_TRAD_EXTRAS  = ['fg_pct', 'fg3_pct', 'ft_pct', 'oreb_pg', 'dreb_pg', 'fga_pg', 'fg3a_pg', 'fta_pg'];
const NBA_TRAD_SECONDARY = new Set(['fg_pct', 'fg3_pct', 'ft_pct', 'oreb_pg', 'dreb_pg']);

const NBA_ADV_PRIMARY  = ['ts_pct', 'efg_pct', 'usg_pct', 'oreb_pct', 'dreb_pct', 'ast_pct', 'tov_pct', 'ast_to', 'pie'];
const NBA_ADV_EXTRAS   = ['stl_pct', 'blk_pct'];

// Impact primary columns (excluding on-court groups which are handled separately)
const NBA_IMP_PRIMARY  = ['box_bpr', 'box_obpr', 'box_dbpr', 'mpir', 'o_mpir', 'd_mpir'];
const NBA_IMP_ADJ_KEYS = ['on_court_adj_o', 'on_court_adj_d', 'on_court_adj_em']; // secondary
const NBA_IMP_RAW_KEYS = ['on_court_ortg', 'on_court_drtg', 'on_court_net'];       // optional

const NBA_DEFAULT_EXTRAS = new Set([
  ...NBA_TRAD_SECONDARY,
  ...NBA_IMP_ADJ_KEYS, // adj on-court secondary — pre-checked
]);

const NBA_ARCHETYPE_STYLES: Record<string, string> = {
  creator:     'bg-brand/10 text-brand border-brand/20',
  scorer:      'bg-secondary/10 text-secondary border-secondary/20',
  interior:    'bg-amber-500/10 text-amber-700 border-amber-400/20',
  three_and_d: 'bg-emerald-500/10 text-emerald-700 border-emerald-400/20',
  stretch:     'bg-violet-500/10 text-violet-700 border-violet-400/20',
  connector:   'bg-ui-hover text-text-muted border-ui-border',
};

// plus_minus lives on the type but not in playerMetricMetadata — add inline
const PLUS_MINUS_META: PlayerMetricMeta = {
  key: 'plus_minus', label: '+/-', tooltip: 'Season plus/minus per game.',
  format: 'number1', better: 'higher', showRank: false, heatmap: true, tier: 'primary',
};

const PAGE_SIZE = 100;

export default function NBAPlayerRankingsTable({ data, seasonDisplay, seasonType = 'regular' }: NBAPlayerRankingsTableProps) {
  const router = useRouter();
  const isPlayoffs = seasonType === 'playoffs';

  const [activeTab, setActiveTab] = useState<TabId>('traditional');
  const [sorting, setSorting] = useState<SortingState>([{ id: 'pts', desc: true }]);
  const [globalFilter, setGlobalFilter] = useState('');
  const [minPoss, setMinPoss] = useState(500);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: PAGE_SIZE });

  const [optionalCols, setOptionalCols] = useState<Set<string>>(() => {
    try {
      const saved = localStorage.getItem('nba-player-cols-v1');
      return saved ? new Set(JSON.parse(saved) as string[]) : new Set(NBA_DEFAULT_EXTRAS);
    } catch { return new Set(NBA_DEFAULT_EXTRAS); }
  });

  useEffect(() => {
    localStorage.setItem('nba-player-cols-v1', JSON.stringify([...optionalCols]));
  }, [optionalCols]);

  const tabDefaultSort: Record<TabId, SortingState> = {
    traditional: [{ id: 'pts',     desc: true }],
    advanced:    [{ id: 'ts_pct',  desc: true }],
    impact:      [{ id: 'box_bpr', desc: true }],
  };

  // Auto-redirect away from Impact when switching to playoffs
  useEffect(() => {
    if (isPlayoffs && activeTab === 'impact') {
      setActiveTab('traditional');
      setSorting(tabDefaultSort['traditional']);
    }
  }, [isPlayoffs]);

  const tabs = [
    { id: 'traditional' as TabId, label: 'Traditional' },
    { id: 'advanced'    as TabId, label: 'Advanced'    },
    ...(!isPlayoffs ? [{ id: 'impact' as TabId, label: 'Impact' }] : []),
  ];

  // ── Filter ──────────────────────────────────────────────────────────────
  const filtered = useMemo(
    () =>
      data.filter((p) => {
        if (!isPlayoffs && (p.on_court_poss == null || p.on_court_poss < minPoss)) return false;
        if (globalFilter) {
          const q = globalFilter.toLowerCase();
          return (
            p.player_name.toLowerCase().includes(q) ||
            (p.team_name ?? '').toLowerCase().includes(q)
          );
        }
        return true;
      }),
    [data, minPoss, globalFilter, isPlayoffs]
  );

  // ── Metric lookup map ────────────────────────────────────────────────────
  const allMetaMaps = useMemo(() => {
    const map: Record<string, PlayerMetricMeta> = { plus_minus: PLUS_MINUS_META };
    [...PLAYER_TRADITIONAL_METRICS, ...NBA_ADVANCED_METRICS, ...NBA_IMPACT_METRICS].forEach((m) => {
      map[m.key] = m;
    });
    return map;
  }, []);

  // ── Percentile ranks ─────────────────────────────────────────────────────
  const allKeys = [
    ...NBA_TRAD_PRIMARY, ...NBA_TRAD_EXTRAS, 'plus_minus',
    ...NBA_ADV_PRIMARY, ...NBA_ADV_EXTRAS,
    ...NBA_IMP_PRIMARY, ...NBA_IMP_ADJ_KEYS, ...NBA_IMP_RAW_KEYS, 'on_court_poss',
  ];

  const metricRanks = useMemo(() => {
    const rankBase = isPlayoffs
      ? data
      : data.filter((p) => p.on_court_poss != null && p.on_court_poss >= minPoss);
    const ranks = new Map<string, ReturnType<typeof computeRanks>>();
    allKeys.forEach((key) => {
      const meta = allMetaMaps[key];
      if (!meta) return;
      const entries = rankBase.map((p) => ({
        id: String(p.id),
        value: (p as any)[key] as number | null,
      }));
      ranks.set(key, computeRanks(entries, meta.better));
    });
    return ranks;
  }, [data, minPoss, allMetaMaps, isPlayoffs]);

  // ── Column factory ───────────────────────────────────────────────────────
  const createMetricColumn = (key: string): ColumnDef<NBAPlayerSeasonStats> => {
    const meta = allMetaMaps[key];
    if (!meta) return { id: key } as ColumnDef<NBAPlayerSeasonStats>;
    return {
      accessorKey: key,
      header: () => (
        <HeaderWithTooltip label={meta.label} better={meta.better} tooltip={meta.tooltip} />
      ),
      cell: (info) => {
        const value = info.getValue<number | null>();
        if (value == null) return <span className="text-text-muted">—</span>;
        const rankData = metricRanks.get(key)?.get(String(info.row.original.id));
        const colorClass = meta.heatmap
          ? getPercentileColor(rankData?.percentile ?? null, meta.better, true)
          : '';
        if (key === 'plus_minus') {
          return (
            <span className={clsx('font-mono text-xs', value > 0 ? 'text-emerald-700' : value < 0 ? 'text-rose-700' : '')}>
              {value >= 0 ? '+' : ''}{value.toFixed(1)}
            </span>
          );
        }
        return (
          <div className={clsx('flex items-center justify-between gap-1 px-2 py-1 rounded', colorClass)}>
            <span className="font-mono text-xs">{formatPlayerMetric(value, meta.format)}</span>
          </div>
        );
      },
      sortDescFirst: meta.better !== 'lower',
      size: 78,
    };
  };

  const createSubColumn = (key: string, label?: string): ColumnDef<NBAPlayerSeasonStats> => {
    const meta = allMetaMaps[key];
    if (!meta) return { id: key } as ColumnDef<NBAPlayerSeasonStats>;
    const displayLabel = label ?? meta.label;
    return {
      accessorKey: key,
      header: () => (
        <HeaderWithTooltip label={displayLabel} better={meta.better} tooltip={meta.tooltip} />
      ),
      cell: (info) => {
        const value = info.getValue<number | null>();
        const rankData = metricRanks.get(key)?.get(String(info.row.original.id));
        if (value == null) return <div className="text-center text-text-muted text-xs">—</div>;
        const colorClass = meta.heatmap
          ? getPercentileColor(rankData?.percentile ?? null, meta.better, true)
          : '';
        return (
          <div className={clsx('px-1 py-0.5 rounded text-center', colorClass)}>
            <div className="font-mono text-xs leading-tight">{formatPlayerMetric(value, meta.format)}</div>
          </div>
        );
      },
      size: 72,
      sortDescFirst: meta.better !== 'lower',
    };
  };

  const createGroup = (
    id: string,
    label: string,
    keys: string[],
    labels?: string[],
  ): ColumnDef<NBAPlayerSeasonStats> => ({
    id,
    header: label,
    columns: keys.map((k, i) => createSubColumn(k, labels?.[i])),
  });

  // ── Base identity columns ────────────────────────────────────────────────
  const baseColumns: ColumnDef<NBAPlayerSeasonStats>[] = [
    {
      accessorKey: 'player_name',
      header: 'Player',
      cell: (info) => {
        const row = info.row.original;
        const headshotUrl = `https://cdn.nba.com/headshots/nba/latest/1040x760/${row.player_id}.png`;
        return (
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-full overflow-hidden bg-ui-surface flex-shrink-0">
              <img
                src={headshotUrl}
                alt={row.player_name}
                className="w-6 h-6 object-cover"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
            </div>
            <span className="font-medium text-sm">{info.getValue<string>()}</span>
          </div>
        );
      },
      size: 170,
    },
    {
      accessorKey: 'team_name',
      header: 'Team',
      cell: (info) => {
        const row = info.row.original;
        const name = info.getValue<string | null>();
        if (!name) return <span className="text-text-muted text-xs">—</span>;
        return row.team_slug ? (
          <Link href={`/nba/team/${row.team_slug}`}
            className="text-xs hover:text-brand transition-colors truncate block max-w-[110px]">
            {name}
          </Link>
        ) : (
          <span className="text-xs text-text-muted truncate block max-w-[110px]">{name}</span>
        );
      },
      size: 120,
    },
    {
      accessorKey: 'gp',
      header: 'GP',
      cell: (info) => <span className="font-mono text-sm">{info.getValue<number>()}</span>,
      size: 44,
    },
    {
      accessorKey: 'mpg',
      header: 'MPG',
      cell: (info) => (
        <span className="font-mono text-sm">{(info.getValue<number | null>() ?? 0).toFixed(1)}</span>
      ),
      size: 50,
      sortDescFirst: true,
    },
  ];

  const invisible = (id: string, cols: ColumnDef<NBAPlayerSeasonStats>[]): ColumnDef<NBAPlayerSeasonStats> => ({
    id,
    header: () => null,
    meta: { isInvisible: true },
    columns: cols,
  });

  // ── Full column set per tab ──────────────────────────────────────────────
  const columns = useMemo((): ColumnDef<NBAPlayerSeasonStats>[] => {
    const activeSortKey = sorting[0]?.id;
    const rankColumn: ColumnDef<NBAPlayerSeasonStats> = {
      id: 'rank',
      header: 'Rk',
      cell: (info) => {
        const rank = activeSortKey
          ? metricRanks.get(activeSortKey)?.get(String(info.row.original.id))?.rank
          : undefined;
        return (
          <span className="font-mono font-semibold text-sm text-text-muted">
            {rank ?? pagination.pageIndex * PAGE_SIZE + info.row.index + 1}
          </span>
        );
      },
      enableSorting: false,
      size: 44,
    };

    if (activeTab === 'impact') {
      const archetypeCol: ColumnDef<NBAPlayerSeasonStats> = {
        id: 'nba_archetype',
        header: 'Role',
        accessorFn: (row) => row.nba_archetype ?? '',
        cell: (info) => {
          const arch = info.row.original.nba_archetype;
          if (!arch) return <span className="text-text-muted">—</span>;
          const label = arch === 'three_and_d' ? '3&D' : arch.charAt(0).toUpperCase() + arch.slice(1);
          const cls = NBA_ARCHETYPE_STYLES[arch] ?? 'text-text-muted';
          return (
            <span className={clsx('text-[11px] font-mono px-1.5 py-0.5 rounded border', cls)}>
              {label}
            </span>
          );
        },
        enableSorting: false,
        size: 72,
      };

      const possCol = createMetricColumn('on_court_poss');

      const adjOnCourtVisible = NBA_IMP_ADJ_KEYS.every((k) => optionalCols.has(k));
      const rawOnCourtVisible = NBA_IMP_RAW_KEYS.every((k) => optionalCols.has(k));

      return [
        invisible('imp-base', [rankColumn, ...baseColumns, possCol]),
        createGroup('imp-bpr',  'Box BPR',  NBA_IMP_PRIMARY.slice(0, 3)),
        createGroup('imp-mpir', 'MPIR',     NBA_IMP_PRIMARY.slice(3)),
        ...(adjOnCourtVisible
          ? [createGroup('imp-adj-oc', 'Adj On-Court', NBA_IMP_ADJ_KEYS, ['Adj O', 'Adj D', 'Adj EM'])]
          : []),
        ...(rawOnCourtVisible
          ? [createGroup('imp-raw-oc', 'Raw On-Court', NBA_IMP_RAW_KEYS, ['ORtg', 'DRtg', 'Net'])]
          : []),
        archetypeCol,
      ];
    }

    const visibleExtras =
      activeTab === 'traditional'
        ? NBA_TRAD_EXTRAS.filter((k) => optionalCols.has(k))
        : NBA_ADV_EXTRAS.filter((k) => optionalCols.has(k));

    const primaryKeys =
      activeTab === 'traditional' ? [...NBA_TRAD_PRIMARY, 'plus_minus'] : NBA_ADV_PRIMARY;

    return [rankColumn, ...baseColumns, ...[...primaryKeys, ...visibleExtras].map(createMetricColumn)];
  }, [activeTab, metricRanks, sorting, pagination.pageIndex, optionalCols]);

  const isGroupedTab = activeTab === 'impact';

  // ── Extras per tab (for the column picker UI) ────────────────────────────
  const extrasForTab = activeTab === 'traditional' ? NBA_TRAD_EXTRAS
    : activeTab === 'advanced' ? NBA_ADV_EXTRAS
    : [...NBA_IMP_ADJ_KEYS, ...NBA_IMP_RAW_KEYS];

  const toggleExtra = (key: string) => {
    setOptionalCols((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  // ── TanStack table ───────────────────────────────────────────────────────
  const table = useReactTable({
    data: filtered,
    columns,
    state: { sorting, globalFilter, pagination },
    onSortingChange: (updater) => {
      setSorting(updater);
      setPagination((p) => ({ ...p, pageIndex: 0 }));
    },
    onGlobalFilterChange: (updater) => {
      setGlobalFilter(updater);
      setPagination((p) => ({ ...p, pageIndex: 0 }));
    },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  return (
    <div className="space-y-4">
      {/* ── Filter bar ──────────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-3 items-center">
        <div>
          <select
            value={seasonType}
            onChange={(e) => {
              const stParam = e.target.value === 'playoffs' ? '&season_type=playoffs' : '';
              router.push(`/nba/rankings?tab=players${stParam}`);
            }}
            className="px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm
                       focus:outline-none focus:ring-2 focus:ring-brand/50 font-medium"
          >
            <option value="regular">Regular Season</option>
            <option value="playoffs">Playoffs</option>
          </select>
        </div>
        <div className="flex-1 min-w-[180px]">
          <input
            type="text"
            value={globalFilter}
            onChange={(e) => {
              setGlobalFilter(e.target.value);
              setPagination((p) => ({ ...p, pageIndex: 0 }));
            }}
            placeholder="Search players or teams..."
            className="w-full px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm
                       focus:outline-none focus:ring-2 focus:ring-brand/50"
          />
        </div>
        {!isPlayoffs && (
          <div>
            <select
              value={minPoss}
              onChange={(e) => {
                setMinPoss(Number(e.target.value));
                setPagination((p) => ({ ...p, pageIndex: 0 }));
              }}
              className="px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm
                         focus:outline-none focus:ring-2 focus:ring-brand/50"
            >
              {[100, 250, 500, 750, 1000, 1500, 2000].map((n) => (
                <option key={n} value={n}>Min {n} poss</option>
              ))}
            </select>
          </div>
        )}
        <div className="text-sm text-text-muted whitespace-nowrap">
          {table.getFilteredRowModel().rows.length} players
          {seasonDisplay && <span className="ml-1">· {seasonDisplay}</span>}
        </div>
      </div>

      {/* ── Tabs ────────────────────────────────────────────────────────── */}
      <div className="border-b border-ui-border">
        <div className="flex space-x-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => {
                setActiveTab(tab.id);
                setSorting(tabDefaultSort[tab.id]);
                setPagination((p) => ({ ...p, pageIndex: 0 }));
              }}
              className={clsx(
                'px-4 py-2 text-sm font-medium transition-colors',
                activeTab === tab.id
                  ? 'text-brand border-b-2 border-brand'
                  : 'text-text-muted hover:text-text-primary',
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Column picker ───────────────────────────────────────────────── */}
      {extrasForTab.length > 0 && (
        <div className="flex flex-wrap gap-2 items-center">
          <span className="text-xs text-text-muted font-medium">Show:</span>
          {extrasForTab.map((key) => {
            const meta = allMetaMaps[key];
            if (!meta) return null;
            const on = optionalCols.has(key);
            return (
              <button
                key={key}
                onClick={() => toggleExtra(key)}
                className={clsx(
                  'px-2.5 py-1 text-xs rounded border transition-colors',
                  on
                    ? 'bg-brand/10 text-brand border-brand/30 font-medium'
                    : 'bg-ui-surface text-text-muted border-ui-border hover:border-brand/30',
                )}
              >
                {meta.label}
              </button>
            );
          })}
        </div>
      )}

      {/* ── Impact tab context note ──────────────────────────────────────── */}
      {activeTab === 'impact' && (
        <div className="flex items-start gap-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800">
          <span className="shrink-0 mt-0.5">ℹ</span>
          <span>
            <strong>Box BPR</strong> is a Ridge regression model predicting on-court impact from per-100-poss box stats and role archetype — Stage 1 proxy trained on MPIR targets.{' '}
            <strong>MPIR</strong> (Macfax Player Impact Rating) is NBA.com{"'"}s Bayesian-stabilised on-court efficiency recentred on league average.{' '}
            <strong>Adj On-Court</strong> are Bayesian-stabilised on-court efficiency ratings (toggle Raw On-Court for unadjusted).
          </span>
        </div>
      )}

      {/* ── Table ───────────────────────────────────────────────────────── */}
      <div className="overflow-x-auto border border-ui-border rounded-lg">
        <table className="w-full">
          <thead>
            {table.getHeaderGroups().map((hg, groupIdx) => (
              <tr
                key={hg.id}
                className={clsx(
                  'border-b border-ui-border',
                  isGroupedTab && groupIdx === 0 ? 'bg-ui-hover' : 'bg-ui-surface',
                )}
              >
                {hg.headers.map((header) => {
                  if (header.isPlaceholder) return null;
                  const isInvisibleGroup = !!(header.column.columnDef.meta as { isInvisible?: boolean })?.isInvisible;
                  const isLabeledGroup = header.colSpan > 1 && !isInvisibleGroup;
                  const isLeaf = header.colSpan === 1;
                  return (
                    <th
                      key={header.id}
                      colSpan={header.colSpan}
                      onClick={isLeaf ? header.column.getToggleSortingHandler() : undefined}
                      className={clsx(
                        'px-2 py-2 text-xs font-semibold text-text-secondary uppercase tracking-wider align-middle',
                        isLabeledGroup && 'text-center border-x border-ui-border/50',
                        isLeaf && 'text-left',
                        isLeaf && header.column.getCanSort() && 'cursor-pointer select-none hover:bg-ui-hover',
                      )}
                      style={isLeaf ? { width: header.column.getSize() } : undefined}
                    >
                      {isInvisibleGroup ? null : (
                        <div className={clsx('flex items-center gap-1', isLabeledGroup && 'justify-center')}>
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {isLeaf && header.column.getIsSorted() && (
                            <span className="text-brand">
                              {header.column.getIsSorted() === 'desc' ? '↓' : '↑'}
                            </span>
                          )}
                        </div>
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="border-b border-ui-border hover:bg-ui-hover transition-colors">
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    className={clsx('py-2 text-sm', isGroupedTab ? 'px-1' : 'px-2')}
                    style={{ width: cell.column.getSize() }}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {table.getFilteredRowModel().rows.length === 0 && (
        <div className="text-center py-8 text-text-muted">No players found. Try adjusting the filters.</div>
      )}

      {/* ── Pagination ────────────────────────────────────────────────────── */}
      {table.getPageCount() > 1 && (
        <div className="flex items-center justify-between text-sm text-text-muted">
          <span>
            Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount()}
            {' · '}
            {table.getFilteredRowModel().rows.length} players total
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => table.setPageIndex(0)}
              disabled={!table.getCanPreviousPage()}
              className="px-2 py-1 rounded border border-ui-border disabled:opacity-40 hover:bg-ui-hover"
            >
              «
            </button>
            <button
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
              className="px-3 py-1 rounded border border-ui-border disabled:opacity-40 hover:bg-ui-hover"
            >
              ‹ Prev
            </button>
            <button
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
              className="px-3 py-1 rounded border border-ui-border disabled:opacity-40 hover:bg-ui-hover"
            >
              Next ›
            </button>
            <button
              onClick={() => table.setPageIndex(table.getPageCount() - 1)}
              disabled={!table.getCanNextPage()}
              className="px-2 py-1 rounded border border-ui-border disabled:opacity-40 hover:bg-ui-hover"
            >
              »
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
