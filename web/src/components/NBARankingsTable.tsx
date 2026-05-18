'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  ColumnDef,
  flexRender,
  SortingState,
  ColumnFiltersState,
} from '@tanstack/react-table';
import Link from 'next/link';
import clsx from 'clsx';
import HeaderWithTooltip from './HeaderWithTooltip';
import { NBATeamSeasonRatings, NBASeasonInfo } from '@/types/nba';
import { NBA_METRIC_DEFINITIONS, NBAMetricMeta } from '@/config/nba';
import { computeRanks, getPercentileColor, RankData } from '@/lib/rankingUtils';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

type TabId = 'overview' | 'four-factors';

interface NBARankingsTableProps {
  data: NBATeamSeasonRatings[];
  seasons?: NBASeasonInfo[];
  selectedSeason?: number;
  selectedSeasonType?: string;
}

interface SubColSpec {
  key: string;
  label: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function formatValue(value: number | null, format: NBAMetricMeta['format']): string {
  if (value == null) return '-';
  switch (format) {
    case 'number1':    return value.toFixed(1);
    case 'number2':    return value.toFixed(2);
    case 'percent1':   return `${(value * 100).toFixed(1)}%`;
    case 'number1pct': return `${value.toFixed(1)}%`;
    case 'int':        return Math.round(value).toString();
    default:           return value.toString();
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────

export default function NBARankingsTable({
  data,
  seasons = [],
  selectedSeason,
  selectedSeasonType = 'regular',
}: NBARankingsTableProps) {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [sorting, setSorting] = useState<SortingState>([{ id: 'rank_adj_net', desc: false }]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [globalFilter, setGlobalFilter] = useState('');
  const [conferenceFilter, setConferenceFilter] = useState<string>('all');

  const tabs = [
    { id: 'overview' as TabId, label: 'Overview' },
    { id: 'four-factors' as TabId, label: 'Four Factors' },
  ];

  const filteredData = useMemo(() => {
    if (conferenceFilter === 'all') return data;
    return data.filter((t) => t.team_conference === conferenceFilter);
  }, [data, conferenceFilter]);

  // Precompute ranks from the full 30-team dataset so heatmap colours stay
  // consistent regardless of the conference filter.
  const metricRanks = useMemo(() => {
    const ranks = new Map<string, Map<string, RankData>>();
    Object.values(NBA_METRIC_DEFINITIONS).forEach((meta) => {
      const entries = data.map((t) => ({
        id: t.team_slug,
        value: (t as unknown as Record<string, unknown>)[meta.key] as number | null,
      }));
      ranks.set(meta.key, computeRanks(entries, meta.better));
    });
    return ranks;
  }, [data]);

  // Column factories (mirroring NCAA RankingsTable patterns)

  const createMetricColumn = (metricKey: string): ColumnDef<NBATeamSeasonRatings> => {
    const meta = NBA_METRIC_DEFINITIONS[metricKey];
    if (!meta) return {} as ColumnDef<NBATeamSeasonRatings>;
    return {
      accessorKey: meta.key,
      header: () => (
        <HeaderWithTooltip label={meta.label} better={meta.better} tooltip={meta.tooltip} />
      ),
      cell: (info) => {
        const value = info.getValue<number | null>();
        const rankData = metricRanks.get(meta.key)?.get(info.row.original.team_slug);
        if (value == null) return <span className="text-text-muted">-</span>;
        const colorClass = meta.heatmap
          ? getPercentileColor(rankData?.percentile ?? null, meta.better, true)
          : '';
        return (
          <div className={clsx('flex items-center justify-between gap-2 px-2 py-1 rounded', colorClass)}>
            <span className="font-mono">{formatValue(value, meta.format)}</span>
            {meta.showRank && rankData?.rank && (
              <span className="text-[11px] text-slate-900 font-bold">#{rankData.rank}</span>
            )}
          </div>
        );
      },
      size: 100,
      sortDescFirst: meta.better === 'higher',
    };
  };

  const createSubColumn = (spec: SubColSpec): ColumnDef<NBATeamSeasonRatings> => {
    const meta = NBA_METRIC_DEFINITIONS[spec.key];
    if (!meta) return {} as ColumnDef<NBATeamSeasonRatings>;
    return {
      accessorKey: meta.key,
      header: () => (
        <HeaderWithTooltip label={spec.label} better={meta.better} tooltip={meta.tooltip} />
      ),
      cell: (info) => {
        const value = info.getValue<number | null>();
        const rankData = metricRanks.get(meta.key)?.get(info.row.original.team_slug);
        if (value == null) return <div className="text-center text-text-muted text-xs">-</div>;
        const colorClass = meta.heatmap
          ? getPercentileColor(rankData?.percentile ?? null, meta.better, true)
          : '';
        return (
          <div className={clsx('px-1 py-0.5 rounded text-center', colorClass)}>
            <div className="font-mono text-xs leading-tight">
              {formatValue(value, meta.format)}
            </div>
            {meta.showRank && rankData?.rank && (
              <div className="text-[10px] text-slate-500 leading-tight">#{rankData.rank}</div>
            )}
          </div>
        );
      },
      size: 68,
      sortDescFirst: meta.better === 'higher',
    };
  };

  const createGroup = (
    id: string,
    label: string,
    off: SubColSpec,
    def_: SubColSpec,
    edge: SubColSpec,
  ): ColumnDef<NBATeamSeasonRatings> => ({
    id,
    header: label,
    columns: [createSubColumn(off), createSubColumn(def_), createSubColumn(edge)],
  });

  // Invisible wrapper — gives leaf columns the same depth as grouped cols
  // so TanStack's header rows align properly.
  const invisible = (id: string, cols: ColumnDef<NBATeamSeasonRatings>[]): ColumnDef<NBATeamSeasonRatings> => ({
    id,
    header: () => null,
    meta: { isInvisible: true },
    columns: cols,
  });

  // Base columns

  const baseColumns: ColumnDef<NBATeamSeasonRatings>[] = [
    {
      accessorKey: 'rank_adj_net',
      header: 'Rk',
      cell: (info) => (
        <span className="font-mono font-semibold">{info.getValue<number | null>() ?? '-'}</span>
      ),
      size: 50,
    },
    {
      accessorKey: 'team_name',
      header: 'Team',
      cell: (info) => {
        const team = info.row.original;
        return (
          <Link
            href={`/nba/team/${team.team_slug}`}
            className="flex items-center space-x-2 hover:text-brand transition-colors"
          >
            {team.team_logo_url ? (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img
                src={team.team_logo_url}
                alt={team.team_name}
                className="w-6 h-6 object-contain"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
            ) : (
              <div className="w-6 h-6 bg-ui-surface rounded-full flex items-center justify-center text-xs font-bold text-text-muted">
                {team.team_abbreviation}
              </div>
            )}
            <span className="font-medium">{team.team_name}</span>
          </Link>
        );
      },
      size: 200,
    },
    {
      accessorKey: 'team_conference',
      header: 'Conf',
      cell: (info) => (
        <span className="text-text-muted text-xs uppercase">{info.getValue<string>()}</span>
      ),
      size: 60,
    },
    {
      accessorKey: 'games',
      header: 'G',
      cell: (info) => (
        <span className="font-mono text-sm">{info.getValue<number>()}</span>
      ),
      size: 52,
    },
  ];

  const compactBaseColumns: ColumnDef<NBATeamSeasonRatings>[] = [
    {
      accessorKey: 'rank_adj_net',
      header: 'Rk',
      cell: (info) => (
        <span className="font-mono font-semibold text-sm">{info.getValue<number | null>() ?? '-'}</span>
      ),
      size: 42,
    },
    {
      accessorKey: 'team_name',
      header: 'Team',
      cell: (info) => {
        const team = info.row.original;
        return (
          <Link
            href={`/nba/team/${team.team_slug}`}
            className="flex items-center space-x-2 hover:text-brand transition-colors"
          >
            {team.team_logo_url ? (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img
                src={team.team_logo_url}
                alt={team.team_name}
                className="w-5 h-5 object-contain"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
            ) : (
              <div className="w-5 h-5 bg-ui-surface rounded-full flex items-center justify-center text-xs font-bold text-text-muted">
                {team.team_abbreviation}
              </div>
            )}
            <span className="font-medium text-sm">{team.team_name}</span>
          </Link>
        );
      },
      size: 160,
    },
    {
      accessorKey: 'team_conference',
      header: 'Conf',
      cell: (info) => (
        <span className="text-text-muted text-xs uppercase">{info.getValue<string>()}</span>
      ),
      size: 52,
    },
  ];

  // Column sets per tab

  const columns = useMemo(() => {
    switch (activeTab) {
      case 'overview':
        return [
          ...baseColumns,
          createMetricColumn('adj_net'),
          createMetricColumn('adj_off'),
          createMetricColumn('adj_def'),
          createMetricColumn('pace'),
          createMetricColumn('ffi'),
        ];

      case 'four-factors':
        return [
          invisible('ff-base', compactBaseColumns),
          createGroup('ff-efg', 'EFG %',
            { key: 'efg_pct',      label: 'Off'    },
            { key: 'opp_efg_pct', label: 'Def'    },
            { key: 'efg_margin',  label: 'Margin' },
          ),
          createGroup('ff-tov', 'Turnover Rate',
            { key: 'tov_rate',     label: 'Off'  },
            { key: 'opp_tov_rate', label: 'Def'  },
            { key: 'tov_edge',     label: 'Edge' },
          ),
          createGroup('ff-reb', 'Rebound %',
            { key: 'oreb_pct',     label: 'OREB' },
            { key: 'opp_oreb_pct', label: 'Def'  },
            { key: 'oreb_edge',    label: 'Edge' },
          ),
          createGroup('ff-ftr', 'FT Rate',
            { key: 'fta_rate',     label: 'Off'    },
            { key: 'opp_fta_rate', label: 'Def'    },
            { key: 'fta_margin',   label: 'Margin' },
          ),
          createSubColumn({ key: 'ffi', label: 'FFI' }),
        ];

      default:
        return [
          ...baseColumns,
          createMetricColumn('adj_net'),
          createMetricColumn('adj_off'),
          createMetricColumn('adj_def'),
          createMetricColumn('pace'),
          createMetricColumn('ffi'),
        ];
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, metricRanks]);

  const table = useReactTable({
    data: filteredData,
    columns,
    state: { sorting, columnFilters, globalFilter },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  const isGroupedTab = activeTab !== 'overview';

  // Render

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap gap-4 items-center">
        {seasons.length > 1 && (
          <div>
            <select
              value={selectedSeason ?? ''}
              onChange={(e) => {
                const val = e.target.value;
                const stParam = selectedSeasonType === 'playoffs' ? '&season_type=playoffs' : '';
                router.push(val ? `/nba/rankings?season=${val}${stParam}` : '/nba/rankings');
              }}
              className="px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/50 font-medium"
            >
              {seasons.map((s) => (
                <option key={s.year} value={s.year}>
                  {s.display_name}{s.is_current ? ' (Current)' : ''}
                </option>
              ))}
            </select>
          </div>
        )}

        <div>
          <select
            value={selectedSeasonType}
            onChange={(e) => {
              const stParam = e.target.value === 'playoffs' ? '&season_type=playoffs' : '';
              const sParam = selectedSeason ? `&season=${selectedSeason}` : '';
              router.push(`/nba/rankings?${sParam}${stParam}`.replace('?&', '?'));
            }}
            className="px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/50 font-medium"
          >
            <option value="regular">Regular Season</option>
            <option value="playoffs">Playoffs</option>
          </select>
        </div>

        <div className="flex-1 min-w-[200px]">
          <input
            type="text"
            value={globalFilter ?? ''}
            onChange={(e) => setGlobalFilter(e.target.value)}
            placeholder="Search teams..."
            className="w-full px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/50"
          />
        </div>

        <div>
          <select
            value={conferenceFilter}
            onChange={(e) => setConferenceFilter(e.target.value)}
            className="px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/50"
          >
            <option value="all">All Conferences</option>
            <optgroup label="Conferences">
              <option value="East">Eastern Conference</option>
              <option value="West">Western Conference</option>
            </optgroup>
          </select>
        </div>

        <div className="text-sm text-text-muted">
          Showing {table.getFilteredRowModel().rows.length} teams
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-ui-border">
        <div className="flex space-x-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
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

      {/* Table */}
      <div className="overflow-x-auto border border-ui-border rounded-lg">
        <table className="w-full">
          <thead>
            {table.getHeaderGroups().map((headerGroup, groupIdx) => (
              <tr
                key={headerGroup.id}
                className={clsx(
                  'border-b border-ui-border',
                  isGroupedTab && groupIdx === 0 ? 'bg-ui-hover' : 'bg-ui-surface',
                )}
              >
                {headerGroup.headers.map((header) => {
                  if (header.isPlaceholder) return null;

                  const isInvisibleGroup = !!(header.column.columnDef.meta as { isInvisible?: boolean })?.isInvisible;
                  const isLabeledGroup = header.colSpan > 1 && !isInvisibleGroup;
                  const isLeaf = header.colSpan === 1;

                  return (
                    <th
                      key={header.id}
                      colSpan={header.colSpan}
                      className={clsx(
                        'px-2 py-2 text-xs font-semibold text-text-secondary uppercase tracking-wider align-middle',
                        isLabeledGroup && 'text-center border-x border-ui-border/50',
                        isLeaf && 'text-left',
                        isLeaf && header.column.getCanSort() &&
                          'cursor-pointer select-none hover:bg-ui-hover',
                      )}
                      onClick={isLeaf ? header.column.getToggleSortingHandler() : undefined}
                      style={isLeaf ? { width: header.column.getSize() } : undefined}
                    >
                      {isInvisibleGroup ? null : (
                        <div
                          className={clsx(
                            'flex items-center gap-1',
                            isLabeledGroup && 'justify-center',
                          )}
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {isLeaf && header.column.getIsSorted() && (
                            <span>{header.column.getIsSorted() === 'desc' ? '\u2193' : '\u2191'}</span>
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
              <tr
                key={row.id}
                className="border-b border-ui-border hover:bg-ui-hover transition-colors"
              >
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    className={clsx('py-2 text-sm', isGroupedTab ? 'px-1' : 'px-3')}
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
          No teams found matching your search.
        </div>
      )}
    </div>
  );
}
