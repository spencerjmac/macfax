import type { ColumnDef } from '@tanstack/react-table';

/**
 * Missing values (null / undefined) sort last in both directions.
 *
 * TanStack keeps `undefined` last with `sortUndefined: 'last'`, applied before the sort direction,
 * but it sorts `null` as the smallest value: first on an ascending sort (TOV, PF, OPP PTS…).
 * This wraps each accessor so null reads as undefined and sets `sortUndefined: 'last'`
 * (unless the column sets its own). Groups are walked; display columns pass through.
 * Cells see `undefined` instead of `null`, which `value == null` checks already cover.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function withNullsLast<T>(columns: ColumnDef<T, any>[]): ColumnDef<T, any>[] {
  return columns.map((col) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c = { ...col } as any;
    if (Array.isArray(c.columns)) {
      c.columns = withNullsLast(c.columns);
      return c;
    }
    if (typeof c.accessorKey === 'string') {
      const key: string = c.accessorKey;
      const path = key.split('.');   // TanStack reads dotted keys as nested paths
      delete c.accessorKey;
      c.id = c.id ?? key;
      c.accessorFn = (row: unknown) =>
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        path.reduce<any>((v, k) => (v == null ? undefined : v[k]), row) ?? undefined;
    } else if (typeof c.accessorFn === 'function') {
      const fn = c.accessorFn;
      c.accessorFn = (row: unknown, index: number) => fn(row, index) ?? undefined;
    } else {
      return col;
    }
    c.sortUndefined = c.sortUndefined ?? 'last';
    return c;
  });
}
