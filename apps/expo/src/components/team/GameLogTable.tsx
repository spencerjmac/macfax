import { type ColumnDef } from '@tanstack/react-table';
import { useCallback } from 'react';
import { Text, View } from 'react-native';

import { DataTable } from '@/src/components/DataTable';
import type { GameLogEntry } from '@/src/lib/api';
import { openLink } from '@/src/lib/links';

const LOCATION = {
  H: { label: 'Home', className: 'bg-green-500/20 text-green-400' },
  A: { label: 'Away', className: 'bg-red-500/20 text-red-400' },
  N: { label: 'Neutral', className: 'bg-blue-500/20 text-blue-400' },
} as const;

const fixed1 = (v: number | null) => (v == null ? '—' : v.toFixed(1));
/** The API sends percentage points; web's formatPercent also accepts 0-1 fractions, so do the same. */
const percent = (v: number | null) => (v == null ? '—' : `${(Math.abs(v) <= 1 ? v * 100 : v).toFixed(1)}%`);

function formatDate(iso: string): string {
  // Dates are plain "YYYY-MM-DD"; parse as local noon so no timezone shifts the day.
  const date = new Date(`${iso}T12:00:00`);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/** Advanced columns are blank against non-D1 opponents, as on web (the API does not compute them). */
function advanced(get: (g: GameLogEntry) => number | null) {
  return (g: GameLogEntry) => (g.opponent_is_d1 === false ? null : get(g));
}

const COLUMNS: ColumnDef<GameLogEntry, any>[] = [
  {
    id: 'date',
    accessorFn: (g) => g.game_date,
    header: 'Date',
    enableGlobalFilter: false,
    meta: { width: 72 },
    cell: (c) => formatDate(c.getValue() as string),
  },
  {
    accessorKey: 'opponent_name',
    header: 'Opponent',
    meta: { width: 190, grow: true, custom: true },
    cell: (c) => {
      const game = c.row.original;
      return (
        <View className="flex-row items-center gap-2">
          <Text numberOfLines={1} className="flex-shrink font-sans-medium text-sm text-text-onDark">
            {game.opponent_name}
          </Text>
          {game.opponent_is_d1 === false ? <Text className="font-sans text-xs text-amber-500/90">(Non-D1)</Text> : null}
        </View>
      );
    },
  },
  {
    accessorKey: 'home_away',
    header: 'Loc',
    enableGlobalFilter: false,
    meta: { width: 76, custom: true },
    cell: (c) => {
      const loc = LOCATION[c.getValue() as keyof typeof LOCATION] ?? LOCATION.N;
      return (
        <View className="items-start">
          <Text className={`overflow-hidden rounded px-2 py-0.5 font-sans-medium text-xs ${loc.className}`}>{loc.label}</Text>
        </View>
      );
    },
  },
  {
    accessorKey: 'result',
    header: 'W/L',
    enableGlobalFilter: false,
    meta: { width: 52, custom: true },
    cell: (c) => {
      const game = c.row.original;
      return (
        <Text className={`font-sans-bold text-sm ${game.result === 'W' ? 'text-green-400' : 'text-red-400'}`}>
          {game.result}
          {game.went_to_ot ? <Text className="font-sans text-[10px] text-ink-fg2"> OT</Text> : null}
        </Text>
      );
    },
  },
  {
    id: 'score',
    // Same as web: opponent points = team points - margin.
    accessorFn: (g) => (g.margin != null ? `${g.pts}-${g.pts - g.margin}` : `${g.pts}`),
    header: 'Score',
    enableSorting: false,
    enableGlobalFilter: false,
    meta: { width: 76, align: 'right' },
  },
  { id: 'ortg', accessorFn: advanced((g) => g.ortg), header: 'ORtg', enableGlobalFilter: false, meta: { width: 70, align: 'right' }, cell: (c) => fixed1(c.getValue()) },
  { id: 'drtg', accessorFn: advanced((g) => g.drtg), header: 'DRtg', enableGlobalFilter: false, meta: { width: 70, align: 'right' }, cell: (c) => fixed1(c.getValue()) },
  { id: 'efg', accessorFn: advanced((g) => g.efg_pct), header: 'eFG%', enableGlobalFilter: false, meta: { width: 72, align: 'right' }, cell: (c) => percent(c.getValue()) },
  { id: 'tov', accessorFn: advanced((g) => g.tov_pct), header: 'TOV%', enableGlobalFilter: false, meta: { width: 72, align: 'right' }, cell: (c) => percent(c.getValue()) },
  { id: 'orb', accessorFn: advanced((g) => g.orb_pct), header: 'ORB%', enableGlobalFilter: false, meta: { width: 72, align: 'right' }, cell: (c) => percent(c.getValue()) },
  { id: 'ftr', accessorFn: advanced((g) => g.ftr), header: 'FTR', enableGlobalFilter: false, meta: { width: 72, align: 'right' }, cell: (c) => percent(c.getValue()) },
];

const getRowId = (g: GameLogEntry) => String(g.id);

/**
 * A team's season game by game: the Game Log tab of web's TeamPageTabs.
 * Tapping a game opens its page on the website (the app has no game screen yet).
 */
export function GameLogTable({ games }: { games: GameLogEntry[] }) {
  const openGame = useCallback((game: GameLogEntry) => {
    if (game.game_id) openLink({ kind: 'web', path: `/ncaa/games/${game.game_id}` });
  }, []);

  return (
    <DataTable
      data={games}
      columns={COLUMNS}
      getRowId={getRowId}
      onRowPress={openGame}
      initialSorting={[{ id: 'date', desc: false }]}
      searchPlaceholder="Search opponents..."
      emptyTitle="No games match your search."
    />
  );
}
