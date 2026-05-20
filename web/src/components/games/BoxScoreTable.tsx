'use client';

import { useState, useMemo } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
} from '@tanstack/react-table';
import clsx from 'clsx';
import type { PlayerBoxRow, GameTeamRef } from '@/types/games';

interface Props {
  homeRows: PlayerBoxRow[];
  awayRows: PlayerBoxRow[];
  homeTeam: GameTeamRef;
  awayTeam: GameTeamRef;
}

const BASE_COLUMNS: ColumnDef<PlayerBoxRow>[] = [
  {
    accessorKey: 'name',
    header: 'Player',
    size: 160,
    enableSorting: false,
  },
  { accessorKey: 'min', header: 'MIN', size: 52, enableSorting: false },
  { accessorKey: 'pts', header: 'PTS', size: 48 },
  { accessorKey: 'reb', header: 'REB', size: 48 },
  { accessorKey: 'ast', header: 'AST', size: 48 },
  { accessorKey: 'stl', header: 'STL', size: 48 },
  { accessorKey: 'blk', header: 'BLK', size: 48 },
  { accessorKey: 'tov', header: 'TOV', size: 48 },
  { accessorKey: 'fg', header: 'FG', size: 60, enableSorting: false },
  { accessorKey: 'fg3', header: '3P', size: 60, enableSorting: false },
  { accessorKey: 'ft', header: 'FT', size: 60, enableSorting: false },
  { accessorKey: 'plus_minus', header: '+/-', size: 52 },
];

function TeamTable({
  rows,
  team,
  showPlusMinus,
}: {
  rows: PlayerBoxRow[];
  team: GameTeamRef;
  showPlusMinus: boolean;
}) {
  const [sorting, setSorting] = useState<SortingState>([{ id: 'pts', desc: true }]);

  const columns = useMemo(
    () =>
      showPlusMinus ? BASE_COLUMNS : BASE_COLUMNS.filter((c) => (c as { accessorKey?: string }).accessorKey !== 'plus_minus'),
    [showPlusMinus]
  );

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <div>
      <div className="mb-2 px-1 text-sm font-semibold text-text-primary">{team.name}</div>
      <div className="overflow-x-auto rounded-xl border border-ui-border">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b border-ui-border bg-ui-surface">
                {hg.headers.map((header, hi) => (
                  <th
                    key={header.id}
                    className={clsx(
                      'select-none px-2 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-text-muted',
                      header.column.getCanSort() &&
                        'cursor-pointer hover:text-text-primary transition-colors',
                      hi === 0 ? 'text-left pl-3' : 'text-right'
                    )}
                    onClick={header.column.getToggleSortingHandler()}
                  >
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    {header.column.getIsSorted() === 'asc'
                      ? ' ↑'
                      : header.column.getIsSorted() === 'desc'
                      ? ' ↓'
                      : ''}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                className="border-b border-ui-border/40 last:border-0 hover:bg-ui-surface/50 transition-colors"
              >
                {row.getVisibleCells().map((cell, ci) => (
                  <td
                    key={cell.id}
                    className={clsx(
                      'px-2 py-2',
                      ci === 0
                        ? 'pl-3 text-left font-medium text-text-primary'
                        : 'text-right font-mono text-text-secondary'
                    )}
                  >
                    {cell.getValue() == null
                      ? '—'
                      : flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function BoxScoreTable({ homeRows, awayRows, homeTeam, awayTeam }: Props) {
  // Show +/- column only when at least one player has a non-null value (NBA)
  const showPlusMinus = useMemo(
    () =>
      [...homeRows, ...awayRows].some((r) => r.plus_minus != null),
    [homeRows, awayRows]
  );

  return (
    <div className="space-y-6">
      <TeamTable rows={awayRows} team={awayTeam} showPlusMinus={showPlusMinus} />
      <TeamTable rows={homeRows} team={homeTeam} showPlusMinus={showPlusMinus} />
    </div>
  );
}
