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
import { Search } from '@/src/components/ui/icons';
import { memo, useCallback, useMemo, useState } from 'react';
import { FlatList, Pressable, ScrollView, Text, TextInput, View, type ListRenderItemInfo } from 'react-native';

import { EmptyState } from '@/src/components/ui/StateViews';
import { ink } from '@/src/theme/tokens';

const ROW_HEIGHT = 44;
const HEADER_HEIGHT = 40;
const DEFAULT_COLUMN_WIDTH = 80;

declare module '@tanstack/react-table' {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData, TValue> {
    /** Fixed column width in px. */
    width?: number;
    align?: 'left' | 'right';
    /** This column absorbs spare width when the table is narrower than its container. */
    grow?: boolean;
    /** The cell renderer returns its own element. Otherwise its output is wrapped in a styled <Text>. */
    custom?: boolean;
  }
}

interface DataTableProps<T> {
  data: T[];
  columns: ColumnDef<T, any>[];
  getRowId: (row: T) => string;
  onRowPress?: (row: T) => void;
  initialSorting?: SortingState;
  searchPlaceholder?: string;
  /** Rendered to the left of the search box (for example a season selector). */
  toolbar?: React.ReactNode;
  emptyTitle?: string;
}

interface TableRowProps<T> {
  row: Row<T>;
  widths: Record<string, number>;
  striped: boolean;
  onRowPress?: (row: T) => void;
}

const TableRow = memo(function TableRow<T>({ row, widths, striped, onRowPress }: TableRowProps<T>) {
  const cells = row.getVisibleCells().map((cell) => {
    const meta = cell.column.columnDef.meta;
    const content = flexRender(cell.column.columnDef.cell, cell.getContext());
    return (
      <View key={cell.id} style={{ width: widths[cell.column.id] }} className="justify-center px-2">
        {meta?.custom ? (
          content
        ) : (
          <Text
            numberOfLines={1}
            className={`text-sm text-text-onDark ${meta?.align === 'right' ? 'text-right font-mono' : 'font-sans'}`}
          >
            {content}
          </Text>
        )}
      </View>
    );
  });

  const className = `flex-row border-b border-ink-line ${striped ? 'bg-ink-2' : 'bg-ink'}`;
  if (!onRowPress) {
    return (
      <View style={{ height: ROW_HEIGHT }} className={className}>
        {cells}
      </View>
    );
  }
  return (
    <Pressable
      onPress={() => onRowPress(row.original)}
      accessibilityRole="link"
      style={{ height: ROW_HEIGHT }}
      className={`${className} active:bg-ink-3`}
    >
      {cells}
    </Pressable>
  );
}) as <T>(props: TableRowProps<T>) => React.JSX.Element;

/**
 * Sortable, searchable table. Rows are virtualized vertically by FlatList;
 * columns have fixed widths and scroll horizontally together with the header,
 * which sits outside the FlatList so it stays pinned while rows scroll.
 */
export function DataTable<T>({
  data,
  columns,
  getRowId,
  onRowPress,
  initialSorting = [],
  searchPlaceholder = 'Search',
  toolbar,
  emptyTitle = 'No rows match your search.',
}: DataTableProps<T>) {
  const [sorting, setSorting] = useState<SortingState>(initialSorting);
  const [globalFilter, setGlobalFilter] = useState('');
  const [containerWidth, setContainerWidth] = useState(0);

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
  const leafColumns = table.getAllLeafColumns();

  // Fixed widths, except that one `grow` column takes up any spare room on wide screens.
  const { widths, totalWidth } = useMemo(() => {
    const base = leafColumns.map((column) => ({
      id: column.id,
      width: column.columnDef.meta?.width ?? DEFAULT_COLUMN_WIDTH,
      grow: column.columnDef.meta?.grow ?? false,
    }));
    const fixedTotal = base.reduce((sum, column) => sum + column.width, 0);
    const spare = Math.max(0, containerWidth - fixedTotal);
    const grower = base.find((column) => column.grow);
    const result: Record<string, number> = {};
    for (const column of base) result[column.id] = column.width + (column === grower ? spare : 0);
    return { widths: result, totalWidth: fixedTotal + (grower ? spare : 0) };
  }, [leafColumns, containerWidth]);

  const renderItem = useCallback(
    ({ item, index }: ListRenderItemInfo<Row<T>>) => (
      <TableRow row={item} widths={widths} striped={index % 2 === 1} onRowPress={onRowPress} />
    ),
    [widths, onRowPress],
  );
  const keyExtractor = useCallback((row: Row<T>) => row.id, []);
  const getItemLayout = useCallback(
    (_: unknown, index: number) => ({ length: ROW_HEIGHT, offset: ROW_HEIGHT * index, index }),
    [],
  );

  return (
    <View className="flex-1">
      <View className="flex-row flex-wrap items-center gap-3 pb-3">
        {toolbar}
        <View className="h-10 min-w-[160px] flex-1 flex-row items-center gap-2 rounded-lg border border-ink-line bg-ink-2 px-3">
          <Search color={ink.fg2} size={16} strokeWidth={1.5} />
          <TextInput
            value={globalFilter}
            onChangeText={setGlobalFilter}
            placeholder={searchPlaceholder}
            placeholderTextColor={ink.fg2}
            autoCapitalize="none"
            autoCorrect={false}
            clearButtonMode="while-editing"
            className="h-10 flex-1 font-sans text-base text-text-onDark outline-none"
          />
        </View>
        <Text className="font-mono text-xs text-ink-fg2">
          {rows.length} / {data.length}
        </Text>
      </View>

      <View
        className="flex-1 overflow-hidden rounded-lg border border-ink-line"
        onLayout={(event) => setContainerWidth(Math.floor(event.nativeEvent.layout.width) - 2)}
      >
        <ScrollView horizontal className="flex-1" contentContainerStyle={{ width: totalWidth }}>
          <View style={{ width: totalWidth }} className="flex-1">
            {table.getHeaderGroups().map((headerGroup) => (
              <View key={headerGroup.id} style={{ height: HEADER_HEIGHT }} className="flex-row border-b border-ink-line bg-ink-3">
                {headerGroup.headers.map((header) => {
                  const meta = header.column.columnDef.meta;
                  const sorted = header.column.getIsSorted();
                  const canSort = header.column.getCanSort();
                  return (
                    <Pressable
                      key={header.id}
                      onPress={canSort ? header.column.getToggleSortingHandler() : undefined}
                      accessibilityRole={canSort ? 'button' : undefined}
                      style={{ width: widths[header.column.id], height: HEADER_HEIGHT }}
                      className="justify-center px-2"
                    >
                      <Text
                        numberOfLines={1}
                        className={`font-display-semibold text-xs uppercase tracking-wider ${
                          sorted ? 'text-brand2' : 'text-text-onDark'
                        } ${meta?.align === 'right' ? 'text-right' : ''}`}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {sorted === 'asc' ? ' ▴' : sorted === 'desc' ? ' ▾' : ''}
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
              ListEmptyComponent={<EmptyState title={emptyTitle} />}
              className="flex-1"
            />
          </View>
        </ScrollView>
      </View>
    </View>
  );
}
