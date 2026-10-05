import { type ColumnDef } from '@tanstack/react-table';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, Text, View } from 'react-native';

import { DataTable } from '@/src/components/DataTable';
import { API_ORIGIN, fetchRankings, type RankingRow } from '@/src/lib/api';
import { palette } from '@/src/theme/tokens';

const fixed = (digits: number) => (value: number | null) => (value == null ? '—' : value.toFixed(digits));
const signed = (value: number | null) => (value == null ? '—' : `${value >= 0 ? '+' : ''}${value.toFixed(1)}`);

const COLUMNS: ColumnDef<RankingRow, any>[] = [
  { accessorKey: 'rank', header: 'Rk', meta: { width: 52, align: 'right' } },
  { accessorKey: 'teamName', header: 'Team', meta: { width: 190 } },
  { accessorKey: 'conference', header: 'Conf', meta: { width: 68 } },
  { accessorKey: 'record', header: 'W-L', meta: { width: 72, align: 'right' }, enableSorting: false },
  { accessorKey: 'adjEM', header: 'AdjEM', cell: (c) => signed(c.getValue()), meta: { width: 84, align: 'right' } },
  { accessorKey: 'adjO', header: 'AdjO', cell: (c) => fixed(1)(c.getValue()), meta: { width: 80, align: 'right' } },
  { accessorKey: 'adjD', header: 'AdjD', cell: (c) => fixed(1)(c.getValue()), meta: { width: 80, align: 'right' } },
  { accessorKey: 'adjTempo', header: 'Tempo', cell: (c) => fixed(1)(c.getValue()), meta: { width: 80, align: 'right' } },
  { accessorKey: 'wab', header: 'WAB', cell: (c) => signed(c.getValue()), meta: { width: 76, align: 'right' } },
  { accessorKey: 'netRank', header: 'NET', cell: (c) => fixed(0)(c.getValue()), meta: { width: 64, align: 'right' } },
];

const getRowId = (row: RankingRow) => row.teamId;

type State =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; rows: RankingRow[] };

export function RankingsTable() {
  const [state, setState] = useState<State>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading' });
    fetchRankings()
      .then((rows) => {
        if (!cancelled) setState({ status: 'ready', rows });
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ status: 'error', message: error instanceof Error ? error.message : String(error) });
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  if (state.status === 'loading') {
    return (
      <View className="flex-1 items-center justify-center gap-3">
        <ActivityIndicator color={palette.brand} />
        <Text className="font-mono text-xs text-ink-fg2">{API_ORIGIN}</Text>
      </View>
    );
  }

  if (state.status === 'error') {
    return (
      <View className="flex-1 items-center justify-center gap-3 p-6">
        <Text className="font-sans-semibold text-base text-negative">Could not load rankings</Text>
        <Text className="text-center font-sans text-sm text-ink-fg">{state.message}</Text>
        <Text className="font-mono text-xs text-ink-fg2">{API_ORIGIN}</Text>
        <Pressable onPress={() => setAttempt((n) => n + 1)} className="rounded-md bg-brand px-4 py-2">
          <Text className="font-sans-semibold text-sm text-text-onDark">Retry</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View className="flex-1 pt-3">
      <DataTable data={state.rows} columns={COLUMNS} getRowId={getRowId} searchPlaceholder="Search team or conference" />
      <Text className="px-4 py-2 font-mono text-[10px] text-ink-fg2">{API_ORIGIN}</Text>
    </View>
  );
}
