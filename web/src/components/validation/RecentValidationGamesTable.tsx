'use client';

import { useState, useMemo } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from '@tanstack/react-table';
import type { ValidationRecentGame } from '@/types/validation';

interface RecentValidationGamesTableProps {
  games: ValidationRecentGame[];
}

const helper = createColumnHelper<ValidationRecentGame>();

export function RecentValidationGamesTable({ games }: RecentValidationGamesTableProps) {
  const [sorting, setSorting] = useState<SortingState>([]);

  const columns = useMemo(
    () => [
      helper.accessor('game_date', {
        header: 'Date',
        cell: info => {
          const d = new Date(info.getValue() + 'T00:00:00');
          return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        },
      }),
      helper.display({
        id: 'matchup',
        header: 'Matchup',
        cell: ({ row }) => (
          <span className="text-text-primary">
            {row.original.away_team} <span className="text-text-muted">@</span> {row.original.home_team}
          </span>
        ),
      }),
      helper.display({
        id: 'predicted',
        header: 'Predicted',
        cell: ({ row }) => (
          <span className="font-mono text-sm">
            {row.original.projected_away_score.toFixed(0)}–{row.original.projected_home_score.toFixed(0)}
          </span>
        ),
      }),
      helper.display({
        id: 'actual',
        header: 'Actual',
        cell: ({ row }) => (
          <span className="font-mono text-sm font-semibold">
            {row.original.actual_away_score}–{row.original.actual_home_score}
          </span>
        ),
      }),
      helper.accessor('margin_error', {
        header: 'Margin Error',
        cell: info => {
          const v = info.getValue();
          const color = Math.abs(v) <= 5 ? 'text-green-500' : Math.abs(v) <= 10 ? 'text-yellow-500' : 'text-red-500';
          return <span className={`font-mono text-sm ${color}`}>{v > 0 ? '+' : ''}{v.toFixed(1)}</span>;
        },
      }),
      helper.accessor('home_win_probability', {
        header: 'Win Prob',
        cell: info => {
          const p = info.getValue();
          return <span className="text-sm text-text-muted">{(p * 100).toFixed(0)}%</span>;
        },
      }),
      helper.accessor('winner_correct', {
        header: 'Correct',
        cell: info => (
          <span className={`text-base font-bold ${info.getValue() ? 'text-green-500' : 'text-red-500'}`}>
            {info.getValue() ? '✓' : '✗'}
          </span>
        ),
      }),
    ],
    []
  );

  const table = useReactTable({
    data: games,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (games.length === 0) return null;

  return (
    <div className="mt-8 bg-ui-card border border-ui-border rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-ui-border">
        <h2 className="text-lg font-semibold text-text-primary">Recent Evaluated Games</h2>
        <p className="text-sm text-text-muted mt-0.5">{games.length} games shown</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map(hg => (
              <tr key={hg.id} className="border-b border-ui-border bg-ui-surface">
                {hg.headers.map(header => (
                  <th
                    key={header.id}
                    className="px-4 py-2.5 text-left text-xs font-medium text-text-muted uppercase tracking-wide cursor-pointer select-none whitespace-nowrap"
                    onClick={header.column.getToggleSortingHandler()}
                  >
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    {header.column.getIsSorted() === 'asc' ? ' ↑' : header.column.getIsSorted() === 'desc' ? ' ↓' : ''}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row, i) => (
              <tr key={row.id} className={`border-b border-ui-border last:border-0 ${i % 2 === 0 ? '' : 'bg-ui-surface/40'}`}>
                {row.getVisibleCells().map(cell => (
                  <td key={cell.id} className="px-4 py-2.5 whitespace-nowrap text-text-primary">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
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
