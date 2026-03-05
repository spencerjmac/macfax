'use client';

import { useMemo, useState } from 'react';
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
import { TeamSeason } from '@/types';
import Link from 'next/link';
import clsx from 'clsx';
import HeaderWithTooltip from './HeaderWithTooltip';
import { METRIC_DEFINITIONS, MetricMeta } from '@/lib/metricMetadata';
import { computeRanks, getPercentileColor, RankData } from '@/lib/rankingUtils';

interface RankingsTableProps {
  data: TeamSeason[];
}

type TabId = 'overview' | 'four-factors' | 'adjusted-four-factors';

interface SubColSpec {
  key: string;
  /** Short label shown in the sub-column header (e.g. "Off", "Def", "Edge") */
  label: string;
}

export default function RankingsTable({ data }: RankingsTableProps) {
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'rank', desc: false },
  ]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [globalFilter, setGlobalFilter] = useState('');
  const [conferenceFilter, setConferenceFilter] = useState<string>('all');

  const tabs = [
    { id: 'overview' as TabId, label: 'Overview' },
    { id: 'four-factors' as TabId, label: 'Four Factors' },
    { id: 'adjusted-four-factors' as TabId, label: 'Adjusted Four Factors' },
  ];

  const conferences = useMemo(() => {
    const confs = new Set(data.map((t) => t.conference).filter(Boolean));
    return Array.from(confs).sort();
  }, [data]);

  const filteredData = useMemo(() => {
    if (conferenceFilter === 'all') return data;
    return data.filter((t) => t.conference === conferenceFilter);
  }, [data, conferenceFilter]);

  // Precompute ranks for all metrics from the full D1 dataset so heatmap
  // colours stay consistent regardless of the conference filter.
  const metricRanks = useMemo(() => {
    const ranks = new Map<string, Map<string, RankData>>();
    Object.values(METRIC_DEFINITIONS).forEach((meta) => {
      const entries = data.map((t) => ({
        id: t.teamId,
        value: (t as any)[meta.key] as number | null,
      }));
      ranks.set(meta.key, computeRanks(entries, meta.better));
    });
    return ranks;
  }, [data]);

  const formatValue = (value: number | null, format: MetricMeta['format']): string => {
    if (value == null) return '-';
    switch (format) {
      case 'number1':   return value.toFixed(1);
      case 'number2':   return value.toFixed(2);
      case 'percent1':  return `${(value * 100).toFixed(1)}%`;
      case 'int':       return Math.round(value).toString();
      default:          return value.toString();
    }
  };

  const columns = useMemo(() => {
    // ── Full-width metric column (Overview tab) ──────────────────────────────
    const createMetricColumn = (metricKey: string): ColumnDef<TeamSeason> => {
      const meta = METRIC_DEFINITIONS[metricKey];
      if (!meta) return {} as ColumnDef<TeamSeason>;
      return {
        accessorKey: meta.key,
        header: () => (
          <HeaderWithTooltip label={meta.label} better={meta.better} tooltip={meta.tooltip} />
        ),
        cell: (info) => {
          const value = info.getValue<number | null>();
          const rankData = metricRanks.get(meta.key)?.get(info.row.original.teamId);
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

    // ── Compact sub-column used inside a group ────────────────────────────────
    const createSubColumn = (spec: SubColSpec): ColumnDef<TeamSeason> => {
      const meta = METRIC_DEFINITIONS[spec.key];
      if (!meta) return {} as ColumnDef<TeamSeason>;
      return {
        accessorKey: meta.key,
        header: () => (
          <HeaderWithTooltip label={spec.label} better={meta.better} tooltip={meta.tooltip} />
        ),
        cell: (info) => {
          const value = info.getValue<number | null>();
          const rankData = metricRanks.get(meta.key)?.get(info.row.original.teamId);
          if (value == null) {
            return <div className="text-center text-text-muted text-xs">-</div>;
          }
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

    // ── Factory for a 3-column group (Off / Def / Edge or Margin) ────────────
    const createGroup = (
      id: string,
      label: string,
      off: SubColSpec,
      def: SubColSpec,
      edge: SubColSpec,
    ): ColumnDef<TeamSeason> => ({
      id,
      header: label,
      columns: [createSubColumn(off), createSubColumn(def), createSubColumn(edge)],
    });

    // ── Invisible wrapper — gives leaf columns the same depth as grouped cols ─
    // Without this, TanStack puts non-grouped leaves in the bottom header row,
    // leaving the top row with only the labeled group headers floating above nothing.
    // We use meta.isInvisible (not the header string) for reliable detection at render time.
    const invisible = (id: string, cols: ColumnDef<TeamSeason>[]): ColumnDef<TeamSeason> => ({
      id,
      header: () => null,
      meta: { isInvisible: true },
      columns: cols,
    });

    // ── Base columns – full version (Overview) ────────────────────────────────
    const baseColumns: ColumnDef<TeamSeason>[] = [
      {
        accessorKey: 'rank',
        header: 'Rk',
        cell: (info) => (
          <span className="font-mono font-semibold">{info.getValue<number>()}</span>
        ),
        size: 50,
      },
      {
        accessorKey: 'teamName',
        header: 'Team',
        cell: (info) => {
          const team = info.row.original;
          return (
            <Link
              href={`/team/${team.teamId}`}
              className="flex items-center space-x-2 hover:text-brand transition-colors"
            >
              {team.logoUrl ? (
                <img
                  src={team.logoUrl}
                  alt={team.teamName}
                  className="w-6 h-6 object-contain"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = 'none';
                  }}
                />
              ) : (
                <div className="w-6 h-6 bg-ui-surface rounded-full flex items-center justify-center text-xs font-bold text-text-muted">
                  {team.teamName.charAt(0)}
                </div>
              )}
              <span className="font-medium">{team.teamName}</span>
            </Link>
          );
        },
        size: 200,
      },
      {
        accessorKey: 'conference',
        header: 'Conf',
        cell: (info) => (
          <span className="text-text-muted text-xs uppercase">{info.getValue<string>()}</span>
        ),
        size: 60,
      },
      {
        accessorKey: 'record',
        header: 'Record',
        cell: (info) => (
          <span className="font-mono text-sm">{info.getValue<string>() || '-'}</span>
        ),
        size: 70,
      },
    ];

    // ── Base columns – compact version (Four Factors tabs, no Record) ─────────
    const compactBaseColumns: ColumnDef<TeamSeason>[] = [
      {
        accessorKey: 'rank',
        header: 'Rk',
        cell: (info) => (
          <span className="font-mono font-semibold text-sm">{info.getValue<number>()}</span>
        ),
        size: 42,
      },
      {
        accessorKey: 'teamName',
        header: 'Team',
        cell: (info) => {
          const team = info.row.original;
          return (
            <Link
              href={`/team/${team.teamId}`}
              className="flex items-center space-x-2 hover:text-brand transition-colors"
            >
              {team.logoUrl ? (
                <img
                  src={team.logoUrl}
                  alt={team.teamName}
                  className="w-5 h-5 object-contain"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = 'none';
                  }}
                />
              ) : (
                <div className="w-5 h-5 bg-ui-surface rounded-full flex items-center justify-center text-xs font-bold text-text-muted">
                  {team.teamName.charAt(0)}
                </div>
              )}
              <span className="font-medium text-sm">{team.teamName}</span>
            </Link>
          );
        },
        size: 155,
      },
      {
        accessorKey: 'conference',
        header: 'Conf',
        cell: (info) => (
          <span className="text-text-muted text-xs uppercase">{info.getValue<string>()}</span>
        ),
        size: 52,
      },
    ];

    switch (activeTab) {
      case 'overview':
        return [
          ...baseColumns,
          createMetricColumn('adjEM'),
          createMetricColumn('adjO'),
          createMetricColumn('adjD'),
          createMetricColumn('adjTempo'),
          createMetricColumn('four_factor_index_100'),
        ];

      case 'four-factors':
        return [
          invisible('ff-base', compactBaseColumns),
          createGroup('ff-efg', 'FG Rate',
            { key: 'raw_eFG',         label: 'Off'    },
            { key: 'raw_eFG_d',       label: 'Def'    },
            { key: 'raw_eFG_margin',  label: 'Margin' },
          ),
          createGroup('ff-tov', 'Turnovers',
            { key: 'raw_tov',         label: 'Off'  },
            { key: 'raw_tov_d',       label: 'Def'  },
            { key: 'raw_tov_edge',    label: 'Edge' },
          ),
          createGroup('ff-reb', 'Rebounds',
            { key: 'raw_orb',         label: 'ORB'  },
            { key: 'raw_drb',         label: 'DRB'  },
            { key: 'raw_reb_edge',    label: 'Edge' },
          ),
          createGroup('ff-ftr', 'FT Rate',
            { key: 'raw_ftr',         label: 'Off'    },
            { key: 'raw_ftr_d',       label: 'Def'    },
            { key: 'raw_ftr_margin',  label: 'Margin' },
          ),
          createSubColumn({ key: 'raw_four_factor_index_100', label: 'FFI' }),
        ];

      case 'adjusted-four-factors':
        return [
          invisible('aff-base', compactBaseColumns),
          createGroup('aff-efg', 'FG Rate',
            { key: 'eFG',         label: 'Off'    },
            { key: 'eFG_d',       label: 'Def'    },
            { key: 'eFG_margin',  label: 'Margin' },
          ),
          createGroup('aff-tov', 'Turnovers',
            { key: 'tov',         label: 'Off'  },
            { key: 'tov_d',       label: 'Def'  },
            { key: 'tov_edge',    label: 'Edge' },
          ),
          createGroup('aff-reb', 'Rebounds',
            { key: 'orb',         label: 'ORB'  },
            { key: 'drb',         label: 'DRB'  },
            { key: 'reb_edge',    label: 'Edge' },
          ),
          createGroup('aff-ftr', 'FT Rate',
            { key: 'ftr',         label: 'Off'    },
            { key: 'ftr_d',       label: 'Def'    },
            { key: 'ftr_margin',  label: 'Margin' },
          ),
          createSubColumn({ key: 'four_factor_index_100', label: 'FFI' }),
        ];

      default:
        return [
          ...baseColumns,
          createMetricColumn('adjEM'),
          createMetricColumn('adjO'),
          createMetricColumn('adjD'),
          createMetricColumn('adjTempo'),
          createMetricColumn('four_factor_index_100'),
        ];
    }
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

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap gap-4 items-center">
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
            {conferences.map((conf) => (
              <option key={conf} value={conf}>
                {conf}
              </option>
            ))}
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

                  const isInvisibleGroup = !!(header.column.columnDef.meta as any)?.isInvisible;
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
                            <span>{header.column.getIsSorted() === 'desc' ? '↓' : '↑'}</span>
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
