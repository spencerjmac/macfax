'use client';

import { useMemo, useState } from 'react';
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

// Traditional keys shown for NBA (subset — no NCAA-only keys like ftm_pg)
const NBA_TRAD_KEYS = [
  'pts', 'reb', 'ast', 'stl', 'blk', 'tov', 'plus_minus',
  'fg_pct', 'fg3_pct', 'ft_pct',
  'fga_pg', 'fg3a_pg', 'fta_pg',
  'oreb_pg', 'dreb_pg',
];
const NBA_ADV_KEYS  = ['ts_pct', 'efg_pct', 'usg_pct', 'oreb_pct', 'dreb_pct', 'ast_pct', 'tov_pct', 'ast_to', 'pie', 'stl_pct', 'blk_pct'];
const NBA_IMP_KEYS  = [
  'box_bpr', 'box_obpr', 'box_dbpr',
  'on_court_poss',
  'mpir', 'o_mpir', 'd_mpir',
  'on_court_adj_o', 'on_court_adj_d', 'on_court_adj_em',
  'on_court_ortg', 'on_court_drtg', 'on_court_net',
];

const NBA_ARCHETYPE_STYLES: Record<string, string> = {
  creator:     'bg-brand/10 text-brand border-brand/20',
  scorer:      'bg-secondary/10 text-secondary border-secondary/20',
  interior:    'bg-amber-500/10 text-amber-700 border-amber-400/20',
  three_and_d: 'bg-emerald-500/10 text-emerald-700 border-emerald-400/20',
  stretch:     'bg-violet-500/10 text-violet-700 border-violet-400/20',
  connector:   'bg-ui-hover text-text-muted border-ui-border',
};

// plus_minus lives on the type but not in playerMetricMetadata — add it inline
const PLUS_MINUS_META: PlayerMetricMeta = {
  key: 'plus_minus', label: '+/-', tooltip: 'Season plus/minus per game.',
  format: 'number1', better: 'higher', showRank: false, heatmap: true,
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

  const tabs = [
    { id: 'traditional' as TabId, label: 'Traditional' },
    { id: 'advanced'    as TabId, label: 'Advanced'    },
    { id: 'impact'      as TabId, label: 'Impact'      },
  ];

  const tabDefaultSort: Record<TabId, SortingState> = {
    traditional: [{ id: 'pts',     desc: true }],
    advanced:    [{ id: 'ts_pct',  desc: true }],
    impact:      [{ id: 'box_bpr', desc: true }],
  };

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
  const allKeys = [...NBA_TRAD_KEYS, ...NBA_ADV_KEYS, ...NBA_IMP_KEYS];
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
  }, [data, minPoss, allMetaMaps]);

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
        // Special colour for +/-
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

  // ── Base identity columns (excluding rank, which lives in the columns useMemo) ──
  const baseColumns: ColumnDef<NBAPlayerSeasonStats>[] = [
    {
      accessorKey: 'player_name',
      header: 'Player',
      cell: (info) => (
        <span className="font-medium text-sm">{info.getValue<string>()}</span>
      ),
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
      return [rankColumn, ...baseColumns, ...NBA_IMP_KEYS.map(createMetricColumn), archetypeCol];
    }

    const metricCols =
      activeTab === 'traditional' ? NBA_TRAD_KEYS.map(createMetricColumn)
                                  : NBA_ADV_KEYS.map(createMetricColumn);
    return [rankColumn, ...baseColumns, ...metricCols];
  }, [activeTab, metricRanks, sorting]);

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

      {/* ── Impact tab context note ──────────────────────────────────────── */}
      {activeTab === 'impact' && (
        <div className="flex items-start gap-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800">
          <span className="shrink-0 mt-0.5">ℹ</span>
          <span>
            <strong>Box BPR</strong> is a Ridge regression model predicting on-court impact from per-100-poss box stats and role archetype — Stage 1 proxy trained on MPIR targets.{' '}
            <strong>MPIR</strong> (Macfax Player Impact Rating) is NBA.com{"'"}s Bayesian-stabilised on-court efficiency recentred on league average.{' '}
            <strong>On-Ct Adj O/D/EM</strong> are opponent-adjusted team ratings while the player is on the floor.
          </span>
        </div>
      )}

      {/* ── Table ───────────────────────────────────────────────────────── */}
      <div className="overflow-x-auto border border-ui-border rounded-lg">
        <table className="w-full">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b border-ui-border bg-ui-surface">
                {hg.headers.map((header) => (
                  <th
                    key={header.id}
                    onClick={header.column.getToggleSortingHandler()}
                    className={clsx(
                      'px-2 py-2 text-xs font-semibold text-text-secondary uppercase tracking-wider text-left',
                      header.column.getCanSort() && 'cursor-pointer select-none hover:bg-ui-hover',
                    )}
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
              <tr key={row.id} className="border-b border-ui-border hover:bg-ui-hover transition-colors">
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-2 py-2 text-sm" style={{ width: cell.column.getSize() }}>
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
