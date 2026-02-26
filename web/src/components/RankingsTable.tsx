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
  
  // Color coding helper - returns CSS class based on percentile rank
  const getColorClass = (value: number, key: string, higherIsBetter: boolean = true) => {
    const values = filteredData.map(t => (t as any)[key]).filter((v: any) => v != null);
    if (values.length === 0) return '';
    
    const sorted = [...values].sort((a, b) => higherIsBetter ? b - a : a - b);
    const percentile = sorted.indexOf(value) / sorted.length;
    
    if (percentile <= 0.10) return 'bg-green-500/25 font-semibold'; // Top 10%
    if (percentile <= 0.25) return 'bg-green-500/15'; // Top 25%
    if (percentile <= 0.50) return 'bg-yellow-500/20'; // Top 50%
    if (percentile <= 0.75) return 'bg-orange-500/20'; // Top 75%
    return 'bg-red-500/20'; // Bottom 25%
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
            className="flex items-center space-x-2 hover:text-brand-orange transition-colors"
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
  
  // Overview tab columns
  const overviewColumns: ColumnDef<TeamSeason>[] = [
    ...baseColumns,
    {
      accessorKey: 'adjEM',
      header: 'AdjEM',
      cell: (info) => {
        const value = info.getValue<number>();
        return (
          <span className={clsx('stat-number font-semibold px-2 py-1 rounded', getColorClass(value, 'adjEM', true))}>
            {value.toFixed(2)}
          </span>
        );
      },
      size: 90,
      sortDescFirst: true,
    },
    {
      accessorKey: 'adjO',
      header: 'AdjO',
      cell: (info) => {
        const value = info.getValue<number>();
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'adjO', true))}>
            {value.toFixed(1)}
          </span>
        );
      },
      size: 80,
      sortDescFirst: true,
    },
    {
      accessorKey: 'adjD',
      header: 'AdjD',
      cell: (info) => {
        const value = info.getValue<number>();
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'adjD', false))}>
            {value.toFixed(1)}
          </span>
        );
      },
      size: 80,
      sortDescFirst: false,
    },
    {
      accessorKey: 'adjTempo',
      header: 'Tempo',
      cell: (info) => {
        const value = info.getValue<number>();
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'adjTempo', true))}>
            {value.toFixed(1)}
          </span>
        );
      },
      size: 80,
    },
    {
      accessorKey: 'four_factor_index_100',
      header: 'FFI',
      cell: (info) => {
        const value = info.getValue<number>();
        if (value == null) return '-';
        return (
          <span className={clsx('stat-number font-semibold px-2 py-1 rounded', getColorClass(value, 'four_factor_index_100', true))}>
            {value.toFixed(1)}
          </span>
        );
      },
      size: 80,
      sortDescFirst: true,
    },
  ];
  
  // Raw Four Factors tab columns
  const rawFourFactorsColumns: ColumnDef<TeamSeason>[] = [
    ...baseColumns,
    // eFG% group
    {  accessorKey: 'raw_eFG',
      header: 'eFG%',
      cell: (info) => {
        const value = info.getValue<number>();
        if (value == null) return '-';
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'raw_eFG', true))}>
            {(value * 100).toFixed(1)}%
          </span>
        );
      },
      size: 80,
      sortDescFirst: true,
    },
    {
      accessorKey: 'raw_eFG_d',
      header: 'eFG%D',
      cell: (info) => {
        const value = info.getValue<number>();
        if (value == null) return '-';
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'raw_eFG_d', false))}>
            {(value * 100).toFixed(1)}%
          </span>
        );
      },
      size: 80,
      sortDescFirst: false,
    },
    {
      accessorKey: 'raw_eFG_margin',
      header: 'eFG±',
      cell: (info) => {
        const value = info.getValue<number>();
        if (value == null) return '-';
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'raw_eFG_margin', true))}>
            {value >= 0 ? '+' : ''}{(value * 100).toFixed(1)}
          </span>
        );
      },
      size: 80,
      sortDescFirst: true,
    },
    // TOV% group
    {
      accessorKey: 'raw_tov',
      header: 'TOV%',
      cell: (info) => {
        const value = info.getValue<number>();
        if (value == null) return '-';
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'raw_tov', false))}>
            {(value * 100).toFixed(1)}%
          </span>
        );
      },
      size: 80,
      sortDescFirst: false,
    },
    {
      accessorKey: 'raw_tov_d',
      header: 'TOV%D',
      cell: (info) => {
        const value = info.getValue<number>();
        if (value == null) return '-';
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'raw_tov_d', true))}>
            {(value * 100).toFixed(1)}%
          </span>
        );
      },
      size: 80,
      sortDescFirst: true,
    },
    {
      accessorKey: 'raw_tov_edge',
      header: 'TOV±',
      cell: (info) => {
        const value = info.getValue<number>();
        if (value == null) return '-';
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'raw_tov_edge', true))}>
            {value >= 0 ? '+' : ''}{(value * 100).toFixed(1)}
          </span>
        );
      },
      size: 80,
      sortDescFirst: true,
    },
    // ORB% group
    {
      accessorKey: 'raw_orb',
      header: 'ORB%',
      cell: (info) => {
        const value = info.getValue<number>();
        if (value == null) return '-';
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'raw_orb', true))}>
            {(value * 100).toFixed(1)}%
          </span>
        );
      },
      size: 80,
      sortDescFirst: true,
    },
    {
      accessorKey: 'raw_drb',
      header: 'ORB%D',
      cell: (info) => {
        const value = info.getValue<number>();
        if (value == null) return '-';
        const oppORB = (1 - value) * 100;
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'raw_drb', true))}>
            {oppORB.toFixed(1)}%
          </span>
        );
      },
      size: 80,
      sortDescFirst: true,
    },
    {
      accessorKey: 'raw_reb_edge',
      header: 'REB±',
      cell: (info) => {
        const value = info.getValue<number>();
        if (value == null) return '-';
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'raw_reb_edge', true))}>
            {value >= 0 ? '+' : ''}{(value * 100).toFixed(1)}
          </span>
        );
      },
      size: 80,
      sortDescFirst: true,
    },
    // FTR group
    {
      accessorKey: 'raw_ftr',
      header: 'FTR',
      cell: (info) => {
        const value = info.getValue<number>();
        if (value == null) return '-';
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'raw_ftr', true))}>
            {(value * 100).toFixed(1)}%
          </span>
        );
      },
      size: 80,
      sortDescFirst: true,
    },
    {
      accessorKey: 'raw_ftr_d',
      header: 'FTRD',
      cell: (info) => {
        const value = info.getValue<number>();
        if (value == null) return '-';
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'raw_ftr_d', false))}>
            {(value * 100).toFixed(1)}%
          </span>
        );
      },
      size: 80,
      sortDescFirst: false,
    },
    {
      accessorKey: 'raw_ftr_margin',
      header: 'FTR±',
      cell: (info) => {
        const value = info.getValue<number>();
        if (value == null) return '-';
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'raw_ftr_margin', true))}>
            {value >= 0 ? '+' : ''}{(value * 100).toFixed(1)}
          </span>
        );
      },
      size: 80,
      sortDescFirst: true,
    },
    // Four Factor Index
    {
      accessorKey: 'raw_four_factor_index_100',
      header: 'FFI',
      cell: (info) => {
        const value = info.getValue<number>();
        if (value == null) return '-';
        return (
          <span className={clsx('stat-number font-semibold px-2 py-1 rounded', getColorClass(value, 'raw_four_factor_index_100', true))}>
            {value.toFixed(1)}
          </span>
        );
      },
      size: 80,
      sortDescFirst: true,
    },
  ];
  
  // Adjusted Four Factors tab columns
  const adjustedFourFactorsColumns: ColumnDef<TeamSeason>[] = [
    ...baseColumns,
    // eFG% group
    {  accessorKey: 'eFG',
      header: 'eFG%',
      cell: (info) => {
        const value = info.getValue<number>();
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'eFG', true))}>
            {(value * 100).toFixed(1)}%
          </span>
        );
      },
      size: 80,
      sortDescFirst: true,
    },
    {
      accessorKey: 'eFG_d',
      header: 'eFG%D',
      cell: (info) => {
        const value = info.getValue<number>();
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'eFG_d', false))}>
            {(value * 100).toFixed(1)}%
          </span>
        );
      },
      size: 80,
      sortDescFirst: false,
    },
    {
      accessorKey: 'eFG_margin',
      header: 'eFG±',
      cell: (info) => {
        const value = info.getValue<number>();
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'eFG_margin', true))}>
            {value >= 0 ? '+' : ''}{(value * 100).toFixed(1)}
          </span>
        );
      },
      size: 80,
      sortDescFirst: true,
    },
    // TOV% group
    {
      accessorKey: 'tov',
      header: 'TOV%',
      cell: (info) => {
        const value = info.getValue<number>();
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'tov', false))}>
            {(value * 100).toFixed(1)}%
          </span>
        );
      },
      size: 80,
      sortDescFirst: false,
    },
    {
      accessorKey: 'tov_d',
      header: 'TOV%D',
      cell: (info) => {
        const value = info.getValue<number>();
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'tov_d', true))}>
            {(value * 100).toFixed(1)}%
          </span>
        );
      },
      size: 80,
      sortDescFirst: true,
    },
    {
      accessorKey: 'tov_edge',
      header: 'TOV±',
      cell: (info) => {
        const value = info.getValue<number>();
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'tov_edge', true))}>
            {value >= 0 ? '+' : ''}{(value * 100).toFixed(1)}
          </span>
        );
      },
      size: 80,
      sortDescFirst: true,
    },
    // ORB% group
    {
      accessorKey: 'orb',
      header: 'ORB%',
      cell: (info) => {
        const value = info.getValue<number>();
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'orb', true))}>
            {(value * 100).toFixed(1)}%
          </span>
        );
      },
      size: 80,
      sortDescFirst: true,
    },
    {
      accessorKey: 'drb',
      header: 'ORB%D',
      cell: (info) => {
        const value = info.getValue<number>();
        const oppORB = (1 - value) * 100;
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'drb', false))}>
            {oppORB.toFixed(1)}%
          </span>
        );
      },
      size: 80,
      sortDescFirst: false,
    },
    {
      accessorKey: 'reb_edge',
      header: 'REB±',
      cell: (info) => {
        const value = info.getValue<number>();
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'reb_edge', true))}>
            {value >= 0 ? '+' : ''}{(value * 100).toFixed(1)}
          </span>
        );
      },
      size: 80,
      sortDescFirst: true,
    },
    // FTR group
    {
      accessorKey: 'ftr',
      header: 'FTR',
      cell: (info) => {
        const value = info.getValue<number>();
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'ftr', true))}>
            {(value * 100).toFixed(1)}%
          </span>
        );
      },
      size: 80,
      sortDescFirst: true,
    },
    {
      accessorKey: 'ftr_d',
      header: 'FTRD',
      cell: (info) => {
        const value = info.getValue<number>();
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'ftr_d', false))}>
            {(value * 100).toFixed(1)}%
          </span>
        );
      },
      size: 80,
      sortDescFirst: false,
    },
    {
      accessorKey: 'ftr_margin',
      header: 'FTR±',
      cell: (info) => {
        const value = info.getValue<number>();
        return (
          <span className={clsx('stat-number px-2 py-1 rounded', getColorClass(value, 'ftr_margin', true))}>
            {value >= 0 ? '+' : ''}{(value * 100).toFixed(1)}
          </span>
        );
      },
      size: 80,
      sortDescFirst: true,
    },
    // Four Factor Index
    {
      accessorKey: 'four_factor_index_100',
      header: 'FFI',
      cell: (info) => {
        const value = info.getValue<number>();
        if (value == null) return '-';
        return (
          <span className={clsx('stat-number font-semibold px-2 py-1 rounded', getColorClass(value, 'four_factor_index_100', true))}>
            {value.toFixed(1)}
          </span>
        );
      },
      size: 80,
      sortDescFirst: true,
    },
  ];
  
  // Get columns based on active tab
  const columns = useMemo(() => {
    switch (activeTab) {
      case 'four-factors':
        return rawFourFactorsColumns;
      case 'adjusted-four-factors':
        return adjustedFourFactorsColumns;
      default:
        return overviewColumns;
    }
  }, [activeTab, filteredData]);
  
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
      {/* Tabs */}
      <div className="border-b border-ui-border">
        <div className="flex space-x-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={clsx(
                'px-6 py-3 font-medium text-sm transition-colors border-b-2',
                activeTab === tab.id
                  ? 'border-brand-orange text-brand-orange'
                  : 'border-transparent text-text-muted hover:text-text-primary hover:border-text-muted'
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>
      
      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
        {/* Search */}
        <div className="flex-1 max-w-md">
          <input
            type="text"
            placeholder="Search teams..."
            value={globalFilter ?? ''}
            onChange={(e) => setGlobalFilter(e.target.value)}
            className="w-full px-4 py-2 border border-ui-border rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-orange bg-ui-surface text-text-primary"
          />
        </div>
        
        {/* Conference Filter */}
        <div className="flex items-center gap-2">
          <label className="text-sm text-text-muted font-medium">Conference:</label>
          <select
            value={conferenceFilter}
            onChange={(e) => setConferenceFilter(e.target.value)}
            className="px-3 py-2 border border-ui-border rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-orange bg-ui-surface text-text-primary"
          >
            <option value="all">All Conferences</option>
            {conferences.map(conf => (
              <option key={conf} value={conf}>{conf}</option>
            ))}
          </select>
        </div>
        
        {/* Results count */}
        <div className="text-sm text-text-muted">
          <span className="font-mono font-semibold">
            {table.getFilteredRowModel().rows.length}
          </span>{' '}
          teams
        </div>
      </div>
      
      {/* Table */}
      <div className="border border-ui-border rounded-lg overflow-hidden bg-ui-card">
        <div className="overflow-x-auto">
          <table className="rankings-table">
            <thead>
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <th
                      key={header.id}
                      style={{ width: header.getSize() }}
                      className={clsx(
                        header.column.getCanSort() && 'cursor-pointer select-none'
                      )}
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      <div className="flex items-center gap-2">
                        {flexRender(
                          header.column.columnDef.header,
                          header.getContext()
                        )}
                        {header.column.getIsSorted() && (
                          <span className="text-brand-orange">
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
                <tr key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id}>
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext()
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
