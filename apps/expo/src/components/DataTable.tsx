import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type Row,
  type SortingState,
} from '@tanstack/react-table';
import { memo, useCallback, useMemo, useState } from 'react';
import { FlatList, Pressable, ScrollView, Text, TextInput, View, type ListRenderItemInfo } from 'react-native';

import { ink } from '@/src/theme/tokens';

const ROW_HEIGHT = 40;
const HEADER_HEIGHT = 36;
const DEFAULT_COLUMN_WIDTH = 80;

declare module '@tanstack/react-table' {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData, TValue> {
    /** Fixed column width in px. */
    width?: number;
    align?: 'left' | 'right';
  }
}

interface DataTableProps<T> {
  data: T[];
  columns: ColumnDef<T, any>[];
  getRowId: (row: T) => string;
  searchPlaceholder?: string;
}

function columnWidth(meta: { width?: number } | undefined): number {
  return meta?.width ?? DEFAULT_COLUMN_WIDTH;
}

const TableRow = memo(function TableRow<T>({ row, striped }: { row: Row<T>; striped: boolean }) {
  return (
    <View
      style={{ height: ROW_HEIGHT }}
      className={`flex-row items-center border-b border-ink-line ${striped ? 'bg-ink-2' : 'bg-ink'}`}
    >
      {row.getVisibleCells().map((cell) => {
        const meta = cell.column.columnDef.meta;
        return (
          <View key={cell.id} style={{ width: columnWidth(meta) }} className="px-2">
            <Text
              numberOfLines={1}
              className={`text-sm text-text-onDark ${meta?.align === 'right' ? 'text-right font-mono' : 'font-sans'}`}
            >
              {flexRender(cell.column.columnDef.cell, cell.getContext())}
            </Text>
          </View>
        );
      })}
    </View>
  );
}) as <T>(props: { row: Row<T>; striped: boolean }) => React.JSX.Element;

/**
 * Sortable, searchable table. Rows are virtualized vertically by FlatList;
 * columns have fixed widths and scroll horizontally together with the header,
 * which sits outside the FlatList so it stays pinned while rows scroll.
 */
export function DataTable<T>({ data, columns, getRowId, searchPlaceholder = 'Search' }: DataTableProps<T>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState('');

  const table = useReactTable({
    data,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getRowId,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  const rows = table.getRowModel().rows;
  const totalWidth = useMemo(
    () => columns.reduce((sum, column) => sum + columnWidth(column.meta), 0),
    [columns],
  );

  const renderItem = useCallback(
    ({ item, index }: ListRenderItemInfo<Row<T>>) => <TableRow row={item} striped={index % 2 === 1} />,
    [],
  );
  const keyExtractor = useCallback((row: Row<T>) => row.id, []);
  const getItemLayout = useCallback(
    (_: unknown, index: number) => ({ length: ROW_HEIGHT, offset: ROW_HEIGHT * index, index }),
    [],
  );

  return (
    <View className="flex-1">
      <View className="flex-row items-center gap-3 px-4 pb-3">
        <TextInput
          value={globalFilter}
          onChangeText={setGlobalFilter}
          placeholder={searchPlaceholder}
          placeholderTextColor={ink.fg2}
          autoCapitalize="none"
          autoCorrect={false}
          clearButtonMode="while-editing"
          className="h-10 flex-1 rounded-md border border-ink-line bg-ink-2 px-3 font-sans text-base text-text-onDark"
        />
        <Text className="font-mono text-xs text-ink-fg2">
          {rows.length} / {data.length}
        </Text>
      </View>

      <ScrollView horizontal className="flex-1" contentContainerStyle={{ width: totalWidth }}>
        <View style={{ width: totalWidth }} className="flex-1">
          {table.getHeaderGroups().map((headerGroup) => (
            <View
              key={headerGroup.id}
              style={{ height: HEADER_HEIGHT }}
              className="flex-row items-center border-b border-ink-line bg-ink-3"
            >
              {headerGroup.headers.map((header) => {
                const meta = header.column.columnDef.meta;
                const sorted = header.column.getIsSorted();
                return (
                  <Pressable
                    key={header.id}
                    onPress={header.column.getToggleSortingHandler()}
                    style={{ width: columnWidth(meta), height: HEADER_HEIGHT }}
                    className="justify-center px-2"
                  >
                    <Text
                      numberOfLines={1}
                      className={`font-display-semibold text-xs uppercase tracking-wider ${
                        sorted ? 'text-brand' : 'text-ink-fg'
                      } ${meta?.align === 'right' ? 'text-right' : ''}`}
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {sorted === 'asc' ? ' ▲' : sorted === 'desc' ? ' ▼' : ''}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          ))}
          <FlatList
            data={rows}
            renderItem={renderItem}
            keyExtractor={keyExtractor}
            getItemLayout={getItemLayout}
            initialNumToRender={20}
            maxToRenderPerBatch={20}
            windowSize={11}
            keyboardShouldPersistTaps="handled"
            className="flex-1"
          />
        </View>
      </ScrollView>
    </View>
  );
}
