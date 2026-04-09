'use client';

import { useMemo, useState } from 'react';
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
  NCAA_IMPACT_METRICS,
  NCAA_FF_METRICS,
  formatPlayerMetric,
  type PlayerMetricMeta,
} from '@/lib/playerMetricMetadata';
import type { NCAAPlayerSeasonStats } from '@/types';

type TabId = 'traditional' | 'impact' | 'fourfactors';

interface NCAAPlayerRankingsTableProps {
  data: NCAAPlayerSeasonStats[];
  seasonDisplay?: string;
}

const TRADITIONAL_KEYS = [
  'pts', 'reb', 'ast', 'stl', 'blk', 'tov',
  'fg_pct', 'fg3_pct', 'ft_pct',
  'efg_pct', 'ts_pct',
  'fga_pg', 'fg3a_pg', 'fta_pg',
  'oreb_pg', 'dreb_pg', 'ast_to',
];

const IMPACT_KEYS = [
  'bpr', 'obpr', 'dbpr',
  'box_bpr', 'box_obpr', 'box_dbpr',
  'mpir', 'o_mpir', 'd_mpir',
  'on_court_ortg', 'on_court_drtg', 'on_court_net',
  'on_court_pts_pg', 'on_court_def_pg', 'on_court_net_pg',
  'on_court_secs_pg',
];

const FF_KEYS = [
  'on_court_ffi',
  'on_court_efg_pct', 'on_court_tov_pct', 'on_court_orb_pct', 'on_court_ftr',
  'on_court_opp_efg_pct', 'on_court_opp_tov_pct', 'on_court_drb_pct', 'on_court_opp_ftr',
  'on_court_efg_margin', 'on_court_tov_edge', 'on_court_reb_edge', 'on_court_ftr_margin',
];

const PAGE_SIZE = 100;

export default function NCAAPlayerRankingsTable({ data, seasonDisplay }: NCAAPlayerRankingsTableProps) {
  const [activeTab, setActiveTab] = useState<TabId>('traditional');
  const [sorting, setSorting] = useState<SortingState>([{ id: 'pts', desc: true }]);
  const [globalFilter, setGlobalFilter] = useState('');
  const [minMinutes, setMinMinutes] = useState(200);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: PAGE_SIZE });

  const tabs = [
    { id: 'traditional' as TabId,  label: 'Traditional' },
    { id: 'impact' as TabId,       label: 'Impact' },
    { id: 'fourfactors' as TabId,  label: 'Four Factors' },
  ];

  // ── Filter ────────────────────────────────────────────────────────────────
  const filtered = useMemo(
    () =>
      data.filter((p) => {
        if (p.mpg * p.gp < minMinutes) return false;
        if (globalFilter) {
          const q = globalFilter.toLowerCase();
          return (
            p.player_name.toLowerCase().includes(q) ||
            p.team_name.toLowerCase().includes(q)
          );
        }
        return true;
      }),
    [data, minMinutes, globalFilter]
  );

  // ── Ranks: computed only for the active tab's metrics (avoids 3× work on load) ──
  const allMetaMaps: Record<string, PlayerMetricMeta> = useMemo(() => {
    const map: Record<string, PlayerMetricMeta> = {};
    [...PLAYER_TRADITIONAL_METRICS, ...NCAA_IMPACT_METRICS, ...NCAA_FF_METRICS].forEach((m) => {
      map[m.key] = m;
    });
    return map;
  }, []);

  const activeTabKeys = useMemo(() => {
    if (activeTab === 'traditional') return TRADITIONAL_KEYS;
    if (activeTab === 'fourfactors') return FF_KEYS;
    return IMPACT_KEYS;
  }, [activeTab]);

  const metricRanks = useMemo(() => {
    const ranks = new Map<string, ReturnType<typeof computeRanks>>();
    const rankBase = data.filter((p) => p.mpg * p.gp >= minMinutes);
    activeTabKeys.forEach((key) => {
      const meta = allMetaMaps[key];
      if (!meta) return;
      const entries = rankBase.map((p) => ({
        id: p.player_id,
        value: (p as any)[key] as number | null,
      }));
      ranks.set(key, computeRanks(entries, meta.better));
    });
    return ranks;
  }, [data, minMinutes, allMetaMaps, activeTabKeys]);

  // ── Column factories ──────────────────────────────────────────────────────
  const createMetricColumn = (key: string): ColumnDef<NCAAPlayerSeasonStats> => {
    const meta = allMetaMaps[key];
    if (!meta) return { id: key } as ColumnDef<NCAAPlayerSeasonStats>;

    // Special display for on_court_secs_pg: convert to minutes
    const isMinutes = key === 'on_court_secs_pg';

    return {
      accessorKey: key,
      header: () => (
        <HeaderWithTooltip
          label={isMinutes ? 'Min On-Ct' : meta.label}
          better={meta.better}
          tooltip={meta.tooltip}
        />
      ),
      cell: (info) => {
        const raw = info.getValue<number | null>();
        // Convert secs → minutes for display
        const value = isMinutes && raw != null ? raw / 60 : raw;
        if (value == null) return <span className="text-text-muted">—</span>;

        const rankData = metricRanks.get(key)?.get(info.row.original.player_id);
        const colorClass =
          meta.heatmap
            ? getPercentileColor(rankData?.percentile ?? null, meta.better, true)
            : '';
        return (
          <div className={clsx('flex items-center justify-between gap-1 px-2 py-1 rounded', colorClass)}>
            <span className="font-mono text-xs">
              {isMinutes ? value.toFixed(1) : formatPlayerMetric(raw, meta.format)}
            </span>
            {meta.showRank && rankData?.rank && (
              <span className="text-[10px] text-slate-900 font-bold">#{rankData.rank}</span>
            )}
          </div>
        );
      },
      sortDescFirst: meta.better !== 'lower',
    };
  };

  // ── Columns ────────────────────────────────────────────────────────────────
  const columns = useMemo((): ColumnDef<NCAAPlayerSeasonStats>[] => {
    const pageOffset = pagination.pageIndex * PAGE_SIZE;
    const baseColumns: ColumnDef<NCAAPlayerSeasonStats>[] = [
      {
        id: 'rank',
        header: 'Rk',
        cell: (info) => (
          <span className="font-mono font-semibold text-sm text-text-muted">
            {pageOffset + info.row.index + 1}
          </span>
        ),
        enableSorting: false,
        size: 44,
      },
      {
        accessorKey: 'player_name',
        header: 'Player',
        cell: (info) => {
          const p = info.row.original;
          return (
            <div className="flex items-center gap-2 min-w-0">
              {p.headshot_url && (
                <img
                  src={p.headshot_url}
                  alt={p.player_name}
                  className="w-7 h-7 rounded-full object-cover shrink-0 bg-ui-surface"
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                />
              )}
              <div className="min-w-0">
                <div className="font-medium text-sm truncate">{p.player_name}</div>
                {p.position && (
                  <div className="text-[11px] text-text-muted uppercase">{p.position}</div>
                )}
              </div>
            </div>
          );
        },
        size: 170,
      },
      {
        accessorKey: 'team_name',
        header: 'Team',
        cell: (info) => (
          <span className="text-xs text-text-muted truncate block max-w-[110px]">
            {info.getValue<string>() || '—'}
          </span>
        ),
        size: 120,
      },
      {
        accessorKey: 'gp',
        header: 'GP',
        cell: (info) => (
          <span className="font-mono text-sm">{info.getValue<number>()}</span>
        ),
        size: 44,
      },
      {
        accessorKey: 'mpg',
        header: 'MPG',
        cell: (info) => (
          <span className="font-mono text-sm">{(info.getValue<number>() ?? 0).toFixed(1)}</span>
        ),
        size: 50,
        sortDescFirst: true,
      },
    ];

    const metricCols =
      activeTab === 'traditional'
        ? TRADITIONAL_KEYS.map(createMetricColumn)
        : activeTab === 'fourfactors'
        ? FF_KEYS.map(createMetricColumn)
        : IMPACT_KEYS.map(createMetricColumn);

    return [...baseColumns, ...metricCols];
  }, [activeTab, metricRanks, pagination.pageIndex]);

  // ── Table ─────────────────────────────────────────────────────────────────
  const table = useReactTable({
    data: filtered,
    columns,
    state: { sorting, globalFilter, pagination },
    onSortingChange: (updater) => {
      setSorting(updater);
      setPagination((p) => ({ ...p, pageIndex: 0 }));
    },
    onGlobalFilterChange: setGlobalFilter,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  return (
    <div className="space-y-4">
      {/* ── Filter bar ──────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-3 items-center">
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
        <div>
          <select
            value={minMinutes}
            onChange={(e) => {
              setMinMinutes(Number(e.target.value));
              setPagination((p) => ({ ...p, pageIndex: 0 }));
            }}
            className="px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm
                       focus:outline-none focus:ring-2 focus:ring-brand/50"
          >
            {[50, 100, 200, 300, 400, 600].map((n) => (
              <option key={n} value={n}>
                Min {n} min
              </option>
            ))}
          </select>
        </div>
        <div className="text-sm text-text-muted whitespace-nowrap">
          {table.getFilteredRowModel().rows.length} players
          {seasonDisplay && <span className="ml-1">· {seasonDisplay}</span>}
        </div>
      </div>

      {/* ── Tabs ────────────────────────────────────────────────────────────── */}
      <div className="border-b border-ui-border">
        <div className="flex space-x-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => {
                setActiveTab(tab.id);
                setSorting([
                  tab.id === 'impact'
                    ? { id: 'bpr', desc: true }
                    : tab.id === 'fourfactors'
                    ? { id: 'on_court_ffi', desc: true }
                    : { id: 'pts', desc: true },
                ]);
                setPagination((p) => ({ ...p, pageIndex: 0 }));
              }}
              className={clsx(
                'px-4 py-2 text-sm font-medium transition-colors relative',
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

      {/* ── Table ───────────────────────────────────────────────────────────── */}
      <div className="overflow-x-auto border border-ui-border rounded-lg">
        <table className="w-full">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b border-ui-border bg-ui-surface">
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className={clsx(
                      'px-2 py-2 text-xs font-semibold text-text-secondary uppercase tracking-wider text-left',
                      header.column.getCanSort() && 'cursor-pointer select-none hover:bg-ui-hover',
                    )}
                    onClick={header.column.getToggleSortingHandler()}
                    style={{ width: header.column.getSize() }}
                  >
                    <div className="flex items-center gap-1">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {header.column.getIsSorted() && (
                        <span className="text-brand">
                          {header.column.getIsSorted() === 'desc' ? '↓' : '↑'}
                        </span>
                      )}
                    </div>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                className="border-b border-ui-border hover:bg-ui-hover transition-colors"
              >
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    className="px-2 py-2 text-sm"
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
        <div className="text-center py-8 text-text-muted">
          No players found. Try adjusting the filters.
        </div>
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
