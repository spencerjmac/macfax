'use client';

import { flexRender, type Column, type Header, type HeaderGroup, type RowData } from '@tanstack/react-table';
import clsx from 'clsx';

declare module '@tanstack/react-table' {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData extends RowData, TValue> {
    /** Header and cell alignment. Numeric columns leave it unset and are centered. */
    align?: 'left' | 'center';
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyColumn = Column<any, unknown>;

/** Alignment shared by a column's header and its cells: left only when the column asks for it. */
export function columnAlign(column: AnyColumn): 'left' | 'center' {
  return column.columnDef.meta?.align ?? 'center';
}

/** Tailwind text-align class for a column's cells, matching its header. */
export function alignClass(column: AnyColumn): string {
  return columnAlign(column) === 'left' ? 'text-left' : 'text-center';
}

const TONES = {
  ink: {
    th: 'px-2 py-[13px] text-xs font-display font-semibold text-white uppercase tracking-[0.06em] whitespace-nowrap border-b border-ink-line',
    leafBg: 'bg-ink',
    groupBg: 'bg-ink-2',
    groupBorder: 'border-x border-ink-line',
    sortable: 'cursor-pointer select-none hover:text-brand2',
    arrow: 'text-brand2',
    asc: '▴',
    desc: '▾',
  },
  surface: {
    th: 'px-2 py-2 text-xs font-semibold text-text-secondary uppercase tracking-wider border-b border-ui-border',
    leafBg: 'bg-ui-surface',
    groupBg: 'bg-ui-hover',
    groupBorder: 'border-x border-ui-border/50',
    sortable: 'cursor-pointer select-none hover:bg-ui-hover',
    arrow: 'text-brand',
    asc: '↑',
    desc: '↓',
  },
} as const;

export type TableHeadTone = keyof typeof TONES;

interface GroupedTableHeadProps<T> {
  headerGroups: HeaderGroup<T>[];
  /** 'ink' = dark team-table header, 'surface' = light player-table header. */
  tone: TableHeadTone;
}

/**
 * <thead> for TanStack tables that mix grouped and ungrouped columns.
 *
 * TanStack fills the rows above an ungrouped leaf with placeholder headers and puts the leaf itself
 * in the bottom row. Skipping placeholders leaves a hole in the upper rows, which shifts later group
 * labels left. Instead, in header row r:
 *   - a placeholder whose column sits at depth r is the leaf's topmost slot: render the leaf there,
 *     spanning the rows below (rowSpan = rows − r);
 *   - other placeholders render nothing (the spanned leaf covers them);
 *   - a real leaf header whose column depth is < r was already rendered above, so it is skipped.
 */
export default function GroupedTableHead<T>({ headerGroups, tone }: GroupedTableHeadProps<T>) {
  const t = TONES[tone];
  const rows = headerGroups.length;

  const renderLeaf = (header: Header<T, unknown>, rowSpan: number) => {
    const column = header.column;
    const canSort = column.getCanSort();
    const sorted = column.getIsSorted();
    const left = columnAlign(column as AnyColumn) === 'left';
    return (
      <th
        key={header.id}
        colSpan={header.colSpan}
        rowSpan={rowSpan > 1 ? rowSpan : undefined}
        className={clsx(
          t.th,
          t.leafBg,
          'align-bottom',
          left ? 'text-left' : 'text-center',
          canSort && t.sortable,
        )}
        onClick={canSort ? column.getToggleSortingHandler() : undefined}
        style={{ width: column.getSize() }}
        aria-sort={sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : undefined}
      >
        <div className={clsx('flex items-center gap-1', !left && 'justify-center')}>
          {flexRender(column.columnDef.header, header.getContext())}
          {sorted && <span className={t.arrow}>{sorted === 'desc' ? t.desc : t.asc}</span>}
        </div>
      </th>
    );
  };

  return (
    <thead>
      {headerGroups.map((headerGroup, r) => (
        <tr key={headerGroup.id}>
          {headerGroup.headers.map((header) => {
            const column = header.column;
            const isLeafColumn = column.columns.length === 0;

            if (header.isPlaceholder) {
              return isLeafColumn && column.depth === r ? renderLeaf(header, rows - r) : null;
            }
            if (isLeafColumn) {
              return column.depth < r ? null : renderLeaf(header, 1);
            }
            return (
              <th
                key={header.id}
                colSpan={header.colSpan}
                className={clsx(t.th, t.groupBg, t.groupBorder, 'align-middle text-center')}
              >
                {flexRender(column.columnDef.header, header.getContext())}
              </th>
            );
          })}
        </tr>
      ))}
    </thead>
  );
}
