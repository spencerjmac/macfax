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
} from '@tanstack/react-table';
import clsx from 'clsx';
import type { WorldCupTeam } from '@/types/worldcup';

interface RankingsTableProps {
  data: WorldCupTeam[];
}

const CONF_LABELS: Record<string, string> = {
  UEFA:     'UEFA',
  CONMEBOL: 'CONM',
  CAF:      'CAF',
  CONCACAF: 'CONC',
  AFC:      'AFC',
  OFC:      'OFC',
};

function HostBadge() {
  const [show, setShow] = useState(false);
  return (
    <span className="relative inline-block">
      <span
        className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-brand/10 text-brand border border-brand/20 cursor-help"
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
      >
        HOST
      </span>
      {show && (
        <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-3 bg-slate-900 border border-slate-600 rounded-lg shadow-2xl">
          <p className="text-xs text-slate-200 leading-relaxed">
            Home advantage (+100 Elo pts) applied to win probability calculations, not base rating.
          </p>
          <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-2 h-2 bg-slate-900 border-r border-b border-slate-600 rotate-45" />
        </div>
      )}
    </span>
  );
}

function DeltaBadge({ value }: { value: number }) {
  const label = value === 0 ? '0' : value > 0 ? `+${value}` : `${value}`;
  return (
    <span
      className={clsx(
        'font-mono text-sm font-semibold',
        value > 0 ? 'text-brand' : value < 0 ? 'text-amber-500' : 'text-muted',
      )}
    >
      {label}
    </span>
  );
}

export default function WorldCupRankingsTable({ data }: RankingsTableProps) {
  const [sorting, setSorting] = useState<SortingState>([{ id: 'elo_rank', desc: false }]);
  const [globalFilter, setGlobalFilter] = useState('');
  const [confFilter, setConfFilter] = useState('all');
  const [groupFilter, setGroupFilter] = useState('all');

  const filteredData = useMemo(() => {
    return data.filter((t) => {
      if (confFilter !== 'all' && t.confederation !== confFilter) return false;
      if (groupFilter !== 'all' && t.group !== groupFilter) return false;
      return true;
    });
  }, [data, confFilter, groupFilter]);

  const groups = useMemo(
    () => ['all', ...Array.from(new Set(data.map((t) => t.group))).sort()],
    [data],
  );

  const columns = useMemo<ColumnDef<WorldCupTeam>[]>(
    () => [
      {
        accessorKey: 'elo_rank',
        header: '#',
        cell: (info) => (
          <span className="font-mono font-semibold text-sm text-text-primary">
            {info.getValue<number>()}
          </span>
        ),
        size: 50,
      },
      {
        accessorKey: 'name',
        header: 'Team',
        cell: (info) => {
          const team = info.row.original;
          return (
            <div className="flex items-center gap-2">
              <span className="text-xl leading-none">{team.flag_emoji}</span>
              <span className="font-medium text-text-primary">{team.name}</span>
              {team.is_host && <HostBadge />}
            </div>
          );
        },
        size: 220,
      },
      {
        accessorKey: 'group',
        header: 'Grp',
        cell: (info) => (
          <span className="font-mono text-sm text-text-primary text-center block">
            {info.getValue<string>()}
          </span>
        ),
        size: 52,
      },
      {
        accessorKey: 'confederation',
        header: 'Confed',
        cell: (info) => (
          <span className="text-xs text-muted uppercase tracking-wide">
            {CONF_LABELS[info.getValue<string>()] ?? info.getValue<string>()}
          </span>
        ),
        size: 70,
        meta: { hideOnMobile: true },
      },
      {
        accessorKey: 'elo_rating',
        header: 'Elo',
        cell: (info) => (
          <span className="font-mono text-sm font-semibold text-brand">
            {info.getValue<number>().toFixed(1)}
          </span>
        ),
        size: 80,
        sortDescFirst: true,
      },
      {
        accessorKey: 'fifa_rank',
        header: 'FIFA',
        cell: (info) => (
          <span className="font-mono text-sm text-text-primary">{info.getValue<number>()}</span>
        ),
        size: 64,
      },
      {
        accessorKey: 'elo_vs_fifa',
        header: 'Δ',
        cell: (info) => <DeltaBadge value={info.getValue<number>()} />,
        size: 60,
        sortDescFirst: true,
      },
    ],
    [],
  );

  const table = useReactTable({
    data: filteredData,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <input
          type="text"
          value={globalFilter ?? ''}
          onChange={(e) => setGlobalFilter(e.target.value)}
          placeholder="Search teams..."
          className="px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/50 min-w-[180px]"
        />
        <select
          value={confFilter}
          onChange={(e) => setConfFilter(e.target.value)}
          className="px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/50"
        >
          <option value="all">All Confederations</option>
          {['UEFA', 'CONMEBOL', 'CAF', 'CONCACAF', 'AFC', 'OFC'].map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <select
          value={groupFilter}
          onChange={(e) => setGroupFilter(e.target.value)}
          className="px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/50"
        >
          {groups.map((g) => (
            <option key={g} value={g}>{g === 'all' ? 'All Groups' : `Group ${g}`}</option>
          ))}
        </select>
        <span className="text-sm text-muted ml-auto">
          {table.getFilteredRowModel().rows.length} teams
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto border border-ui-border rounded-lg">
        <table className="w-full">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b border-ink-line bg-ink">
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className={clsx(
                      'px-3 py-[13px] text-xs font-display font-semibold text-white uppercase tracking-[0.06em] text-left whitespace-nowrap align-middle',
                      header.column.getCanSort() && 'cursor-pointer select-none hover:text-brand2',
                      (header.column.columnDef.meta as { hideOnMobile?: boolean })?.hideOnMobile &&
                        'hidden sm:table-cell',
                    )}
                    style={{ width: header.column.getSize() }}
                    onClick={header.column.getToggleSortingHandler()}
                  >
                    <div className="flex items-center gap-1">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {header.column.getIsSorted() && (
                        <span className="text-brand2">
                          {header.column.getIsSorted() === 'desc' ? '▾' : '▴'}
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
                className="border-b border-ui-border hover:bg-ui-surface transition-colors"
              >
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    className={clsx(
                      'px-3 py-2 text-sm',
                      (cell.column.columnDef.meta as { hideOnMobile?: boolean })?.hideOnMobile &&
                        'hidden sm:table-cell',
                    )}
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
        <div className="text-center py-8 text-muted">No teams match your filters.</div>
      )}
    </div>
  );
}
