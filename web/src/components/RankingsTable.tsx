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

export default function RankingsTable({ data }: RankingsTableProps) {
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'rank', desc: false }
  ]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [globalFilter, setGlobalFilter] = useState('');
  const [conferenceFilter, setConferenceFilter] = useState<string>('all');
  
  const tabs = [
    { id: 'overview' as TabId, label: 'Overview' },
    { id: 'four-factors' as TabId, label: 'Four Factors' },
    { id: 'adjusted-four-factors' as TabId, label: 'Adjusted Four Factors' },
  ];
  
  // Get unique conferences
  const conferences = useMemo(() => {
    const confs = new Set(data.map(t => t.conference).filter(Boolean));
    return Array.from(confs).sort();
  }, [data]);
  
  // Filter data by conference
  const filteredData = useMemo(() => {
    if (conferenceFilter === 'all') return data;
    return data.filter(t => t.conference === conferenceFilter);
  }, [data, conferenceFilter]);
  
  // Precompute ranks for all metrics based on ALL D1 data (never filtered)
  // so ranks and color coding remain consistent regardless of conference filter
  const metricRanks = useMemo(() => {
    const ranks = new Map<string, Map<string, RankData>>();
    
    // Compute ranks for each metric keyed by teamId
    Object.values(METRIC_DEFINITIONS).forEach((meta) => {
      const entries = data.map(t => ({ id: t.teamId, value: (t as any)[meta.key] as number | null }));
      ranks.set(meta.key, computeRanks(entries, meta.better));
    });
    
    return ranks;
  }, [data]);
  
  // Helper to format metric values
  const formatValue = (value: number | null, format: MetricMeta['format']): string => {
    if (value == null) return '-';
    
    switch (format) {
      case 'number1':
        return value.toFixed(1);
      case 'number2':
        return value.toFixed(2);
      case 'percent1':
        return `${(value * 100).toFixed(1)}%`;
      case 'int':
        return Math.round(value).toString();
      default:
        return value.toString();
    }
  };
  
  // Select columns based on active tab
  const columns = useMemo(() => {
    // Helper to create a metric column (inside useMemo to capture current metricRanks)
    const createMetricColumn = (metricKey: string): ColumnDef<TeamSeason> => {
      const meta = METRIC_DEFINITIONS[metricKey];
      if (!meta) {
        console.warn(`Metric ${metricKey} not found in METRIC_DEFINITIONS`);
        return {} as ColumnDef<TeamSeason>;
      }
      
      return {
        accessorKey: meta.key,
        header: () => (
          <HeaderWithTooltip
            label={meta.label}
            better={meta.better}
            tooltip={meta.tooltip}
          />
        ),
        cell: (info) => {
          const value = info.getValue<number | null>();
          const teamId = info.row.original.teamId;
          const rankData = metricRanks.get(meta.key)?.get(teamId);
          
          if (value == null) {
            return <span className="text-text-muted">-</span>;
          }
          
          const colorClass = meta.heatmap 
            ? getPercentileColor(rankData?.percentile ?? null, meta.better, true)
            : '';
          
          return (
            <div className={clsx('flex items-center justify-between gap-2 px-2 py-1 rounded', colorClass)}>
              <span className="font-mono">{formatValue(value, meta.format)}</span>
              {meta.showRank && rankData?.rank && (
                <span className="text-[11px] text-slate-900 font-bold">
                  #{rankData.rank}
                </span>
              )}
            </div>
          );
        },
        size: 100,
        sortDescFirst: meta.better === 'higher',
      };
    };
    
    // Base columns (always visible)
    const baseColumns: ColumnDef<TeamSeason>[] = [
      {
        accessorKey: 'rank',
        header: 'Rk',
        cell: (info) => (
          <span className="font-mono font-semibold">
            {info.getValue<number>()}
          </span>
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
                    const img = e.target as HTMLImageElement;
                    img.style.display = 'none';
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
          <span className="text-text-muted text-xs uppercase">
            {info.getValue<string>()}
          </span>
        ),
        size: 60,
      },
      {
        accessorKey: 'record',
        header: 'Record',
        cell: (info) => (
          <span className="font-mono text-sm">
            {info.getValue<string>() || '-'}
          </span>
        ),
        size: 70,
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
          ...baseColumns,
          createMetricColumn('raw_eFG'),
          createMetricColumn('raw_eFG_d'),
          createMetricColumn('raw_eFG_margin'),
          createMetricColumn('raw_tov'),
          createMetricColumn('raw_tov_d'),
          createMetricColumn('raw_tov_edge'),
          createMetricColumn('raw_orb'),
          createMetricColumn('raw_drb'),
          createMetricColumn('raw_reb_edge'),
          createMetricColumn('raw_ftr'),
          createMetricColumn('raw_ftr_d'),
          createMetricColumn('raw_ftr_margin'),
          createMetricColumn('raw_four_factor_index_100'),
        ];
      case 'adjusted-four-factors':
        return [
          ...baseColumns,
          createMetricColumn('eFG'),
          createMetricColumn('eFG_d'),
          createMetricColumn('eFG_margin'),
          createMetricColumn('tov'),
          createMetricColumn('tov_d'),
          createMetricColumn('tov_edge'),
          createMetricColumn('orb'),
          createMetricColumn('drb'),
          createMetricColumn('reb_edge'),
          createMetricColumn('ftr'),
          createMetricColumn('ftr_d'),
          createMetricColumn('ftr_margin'),
          createMetricColumn('four_factor_index_100'),
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
  }, [activeTab, filteredData, metricRanks]);
  
  const table = useReactTable({
    data: filteredData,
    columns,
    state: {
      sorting,
      columnFilters,
      globalFilter,
    },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap gap-4 items-center">
        {/* Search */}
        <div className="flex-1 min-w-[200px]">
          <input
            type="text"
            value={globalFilter ?? ''}
            onChange={(e) => setGlobalFilter(e.target.value)}
            placeholder="Search teams..."
            className="w-full px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/50"
          />
        </div>
        
        {/* Conference Filter */}
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
        
        {/* Results count */}
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
                  : 'text-text-muted hover:text-text-primary'
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
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b border-ui-border bg-ui-surface">
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className={clsx(
                      'px-3 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider',
                      header.column.getCanSort() && 'cursor-pointer select-none hover:bg-ui-hover'
                    )}
                    onClick={header.column.getToggleSortingHandler()}
                    style={{ width: header.column.getSize() }}
                  >
                    <div className="flex items-center space-x-1">
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                      {header.column.getIsSorted() && (
                        <span className="ml-1">
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
                    className="px-3 py-2 text-sm"
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
