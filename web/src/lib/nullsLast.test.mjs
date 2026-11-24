// node --test --experimental-strip-types src/lib/*.test.mjs   (npm test)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createTable, getCoreRowModel, getSortedRowModel } from '@tanstack/table-core';
import { withNullsLast } from './nullsLast.ts';

const data = [
  { team: 'A', tov: 12.1, ppg: 80.0 },
  { team: 'B', tov: null, ppg: null },
  { team: 'C', tov: 9.5, ppg: 91.2 },
  { team: 'D', tov: undefined, ppg: 70.4 },
  { team: 'E', tov: 15.0, ppg: 0 },
];

function sortedTeams(columns, sorting) {
  let state = { sorting, columnPinning: { left: [], right: [] } };
  const table = createTable({
    data,
    columns,
    state,
    onStateChange: (updater) => { state = typeof updater === 'function' ? updater(state) : updater; },
    renderFallbackValue: null,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });
  return table.getSortedRowModel().rows.map((r) => r.original.team);
}

const plain = [{ accessorKey: 'team' }, { accessorKey: 'tov' }, { accessorKey: 'ppg' }];
const wrapped = withNullsLast(plain);

test('without the wrapper, null sorts first ascending (the bug)', () => {
  assert.equal(sortedTeams(plain, [{ id: 'tov', desc: false }])[0], 'B');
});

test('ascending: missing values last', () => {
  assert.deepEqual(sortedTeams(wrapped, [{ id: 'tov', desc: false }]), ['C', 'A', 'E', 'B', 'D']);
});

test('descending: missing values last', () => {
  assert.deepEqual(sortedTeams(wrapped, [{ id: 'tov', desc: true }]), ['E', 'A', 'C', 'B', 'D']);
});

test('zero is a value, not missing', () => {
  assert.deepEqual(sortedTeams(wrapped, [{ id: 'ppg', desc: false }]), ['E', 'D', 'A', 'C', 'B']);
});

test('groups are walked; ids and accessorFn columns kept', () => {
  const cols = withNullsLast([
    { id: 'grp', header: 'Group', columns: [{ accessorKey: 'tov', header: 'TOV' }] },
    { id: 'calc', accessorFn: (row) => (row.tov == null ? null : row.tov * 2) },
    { id: 'display', header: 'x' },
  ]);
  const leaf = cols[0].columns[0];
  assert.equal(leaf.id, 'tov');
  assert.equal(leaf.sortUndefined, 'last');
  assert.equal(leaf.accessorFn(data[1]), undefined);
  assert.equal(cols[1].accessorFn(data[1], 1), undefined);
  assert.equal(cols[1].accessorFn(data[0], 0), 24.2);
  assert.equal(cols[2].sortUndefined, undefined);
  assert.deepEqual(sortedTeams(cols, [{ id: 'calc', desc: false }]), ['C', 'A', 'E', 'B', 'D']);
});
