'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  ColumnDef,
  flexRender,
  SortingState,
  ColumnFiltersState,
} from '@tanstack/react-table';
import Link from 'next/link';
import clsx from 'clsx';
import { noDataMessage } from '@/lib/nbaNoData';
import HeaderWithTooltip from './HeaderWithTooltip';
import GroupedTableHead, { cellClass, withMeta } from './table/GroupedTableHead';
import TableTabs from './table/TableTabs';
import MetricValue from './table/MetricValue';
import { NBATeamSeasonRatings, NBASeasonInfo } from '@macfax/core/types/nba';
import { NBA_METRIC_DEFINITIONS, NBAMetricMeta } from '@macfax/core/config/nba';
import { computeRanks, heatStyleFromPercentile, RankData } from '@macfax/core/lib/rankingUtils';
import { withNullsLast } from '@/lib/nullsLast';
import HeatLegend from './HeatLegend';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

type TabId = 'overview' | 'four-factors' | 'traditional';

interface NBARankingsTableProps {
  data: NBATeamSeasonRatings[];
  seasons?: NBASeasonInfo[];
  selectedSeason?: number;
  selectedSeasonType?: string;
}

interface SubColSpec {
  key: string;
  label: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function formatValue(value: number | null, format: NBAMetricMeta['format']): string {
  if (value == null) return '-';
  switch (format) {
    case 'number1':    return value.toFixed(1);
    case 'number2':    return value.toFixed(2);
    case 'percent1':   return `${(value * 100).toFixed(1)}%`;
    case 'number1pct': return `${value.toFixed(1)}%`;
    case 'int':        return Math.round(value).toString();
    default:           return value.toString();
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────

export default function NBARankingsTable({
  data,
  seasons = [],
  selectedSeason,
  selectedSeasonType = 'regular',
}: NBARankingsTableProps) {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [sorting, setSorting] = useState<SortingState>([{ id: 'rank_adj_net', desc: false }]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [globalFilter, setGlobalFilter] = useState('');
  const [conferenceFilter, setConferenceFilter] = useState<string>('all');

  const tabs = [
    { id: 'overview' as TabId, label: 'Overview' },
    { id: 'four-factors' as TabId, label: 'Four Factors' },
    { id: 'traditional' as TabId, label: 'Traditional' },
  ];

  const filteredData = useMemo(() => {
    if (conferenceFilter === 'all') return data;
    return data.filter((t) => t.team_conference === conferenceFilter);
  }, [data, conferenceFilter]);

  // Precompute ranks from the full 30-team dataset so heatmap colours stay
  // consistent regardless of the conference filter.
  const metricRanks = useMemo(() => {
    const ranks = new Map<string, Map<string, RankData>>();
    Object.values(NBA_METRIC_DEFINITIONS).forEach((meta) => {
      const entries = data.map((t) => ({
        id: t.team_slug,
        value: (t as unknown as Record<string, unknown>)[meta.key] as number | null,
      }));
      ranks.set(meta.key, computeRanks(entries, meta.better));
    });
    return ranks;
  }, [data]);

  // Column factories (mirroring NCAA RankingsTable patterns)

  const createMetricColumn = (metricKey: string): ColumnDef<NBATeamSeasonRatings> => {
    const meta = NBA_METRIC_DEFINITIONS[metricKey];
    if (!meta) return {} as ColumnDef<NBATeamSeasonRatings>;
    return {
      accessorKey: meta.key,
      header: () => (
        <HeaderWithTooltip label={meta.label} better={meta.better} tooltip={meta.tooltip} />
      ),
      cell: (info) => {
        const value = info.getValue<number | null>();
        const rankData = metricRanks.get(meta.key)?.get(info.row.original.team_slug);
        const hs = value != null && meta.heatmap ? heatStyleFromPercentile(rankData?.percentile ?? null, meta.better) : {};
        return (
          <MetricValue
            text={value == null ? null : formatValue(value, meta.format)}
            heat={hs}
            rank={rankData?.rank}
            showRank={meta.showRank}
            column={info.column}
          />
        );
      },
      size: 100,
      sortDescFirst: meta.better === 'higher',
    };
  };

  const createSubColumn = (spec: SubColSpec): ColumnDef<NBATeamSeasonRatings> => {
    const meta = NBA_METRIC_DEFINITIONS[spec.key];
    if (!meta) return {} as ColumnDef<NBATeamSeasonRatings>;
    return {
      accessorKey: meta.key,
      header: () => (
        <HeaderWithTooltip label={spec.label} better={meta.better} tooltip={meta.tooltip} />
      ),
      cell: (info) => {
        const value = info.getValue<number | null>();
        const rankData = metricRanks.get(meta.key)?.get(info.row.original.team_slug);
        const hs = value != null && meta.heatmap ? heatStyleFromPercentile(rankData?.percentile ?? null, meta.better) : {};
        return (
          <MetricValue
            text={value == null ? null : formatValue(value, meta.format)}
            heat={hs}
            rank={rankData?.rank}
            showRank={meta.showRank}
            column={info.column} variant="compact"
          />
        );
      },
      size: 68,
      sortDescFirst: meta.better === 'higher',
    };
  };

  const createGroup = (
    id: string,
    label: string,
    off: SubColSpec,
    def_: SubColSpec,
    edge: SubColSpec,
  ): ColumnDef<NBATeamSeasonRatings> => ({
    id,
    header: label,
    columns: [
      withMeta(createSubColumn(off), { divider: true }),
      createSubColumn(def_),
      withMeta(createSubColumn(edge), { net: true }),
    ],
  });

  // Base columns

  const baseColumns: ColumnDef<NBATeamSeasonRatings>[] = [
    {
      accessorKey: 'rank_adj_net',
      header: 'Rk',
      meta: { align: 'left' },
      sortDescFirst: false,
      cell: (info) => (
        <span className="font-mono font-semibold">{info.getValue<number | null>() ?? '-'}</span>
      ),
      size: 50,
    },
    {
      accessorKey: 'team_name',
      header: 'Team',
      meta: { align: 'left' },
      cell: (info) => {
        const team = info.row.original;
        return (
          <Link
            href={`/nba/team/${team.team_slug}`}
            className="flex items-center space-x-2 hover:text-brand transition-colors"
          >
            {team.team_logo_url ? (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img
                src={team.team_logo_url}
                alt={team.team_name}
                className="w-6 h-6 object-contain"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
            ) : (
              <div className="w-6 h-6 bg-ui-surface rounded-full flex items-center justify-center text-xs font-bold text-text-muted">
                {team.team_abbreviation}
              </div>
            )}
            <span className="font-medium">{team.team_name}</span>
          </Link>
        );
      },
      size: 200,
    },
    {
      accessorKey: 'team_conference',
      header: 'Conf',
      meta: { align: 'left' },
      cell: (info) => (
        <span className="text-text-muted text-xs uppercase">{info.getValue<string>()}</span>
      ),
      size: 60,
    },
    {
      accessorKey: 'games',
      header: 'G',
      cell: (info) => (
        <span className="font-mono text-sm">{info.getValue<number>()}</span>
      ),
      size: 52,
    },
  ];

  const compactBaseColumns: ColumnDef<NBATeamSeasonRatings>[] = [
    {
      accessorKey: 'rank_adj_net',
      header: 'Rk',
      meta: { align: 'left' },
      sortDescFirst: false,
      cell: (info) => (
        <span className="font-mono font-semibold text-sm">{info.getValue<number | null>() ?? '-'}</span>
      ),
      size: 42,
    },
    {
      accessorKey: 'team_name',
      header: 'Team',
      meta: { align: 'left' },
      cell: (info) => {
        const team = info.row.original;
        return (
          <Link
            href={`/nba/team/${team.team_slug}`}
            className="flex items-center space-x-2 hover:text-brand transition-colors"
          >
            {team.team_logo_url ? (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img
                src={team.team_logo_url}
                alt={team.team_name}
                className="w-5 h-5 object-contain"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
            ) : (
              <div className="w-5 h-5 bg-ui-surface rounded-full flex items-center justify-center text-xs font-bold text-text-muted">
                {team.team_abbreviation}
              </div>
            )}
            <span className="font-medium text-sm">{team.team_name}</span>
          </Link>
        );
      },
      size: 160,
    },
    {
      accessorKey: 'team_conference',
      header: 'Conf',
      meta: { align: 'left' },
      cell: (info) => (
        <span className="text-text-muted text-xs uppercase">{info.getValue<string>()}</span>
      ),
      size: 52,
    },
  ];

  // Column sets per tab

  const columns = useMemo(() => {
    switch (activeTab) {
      case 'overview':
        return [
          ...baseColumns,
          withMeta(createMetricColumn('adj_net'), { emphasis: true }),
          createMetricColumn('adj_off'),
          createMetricColumn('adj_def'),
          createMetricColumn('pace'),
          createMetricColumn('ffi'),
        ];

      case 'four-factors':
        return [
          ...compactBaseColumns,
          createGroup('ff-efg', 'eFG%',
            { key: 'efg_pct',      label: 'Off'    },
            { key: 'opp_efg_pct', label: 'Def'    },
            { key: 'efg_margin',  label: 'Net'    },
          ),
          createGroup('ff-tov', 'Turnover %',
            { key: 'tov_rate',     label: 'Off'  },
            { key: 'opp_tov_rate', label: 'Def'  },
            { key: 'tov_edge',     label: 'Net'  },
          ),
          createGroup('ff-reb', 'Rebounding',
            { key: 'oreb_pct',     label: 'OREB' },
            { key: 'opp_oreb_pct', label: 'Def'  },
            { key: 'oreb_edge',    label: 'Net'  },
          ),
          createGroup('ff-ftr', 'FT Rate',
            { key: 'fta_rate',     label: 'Off'    },
            { key: 'opp_fta_rate', label: 'Def'    },
            { key: 'fta_margin',   label: 'Net'    },
          ),
          withMeta(createSubColumn({ key: 'ffi', label: 'FFI' }), { emphasis: true }),
        ];

      // Same columns, order and colouring as the NCAA Traditional tab
      case 'traditional':
        return [
          ...compactBaseColumns,
          createSubColumn({ key: 'gp', label: 'GP' }),
          createSubColumn({ key: 'ppg', label: 'PTS' }),
          createSubColumn({ key: 'papg', label: 'OPP PTS' }),
          createSubColumn({ key: 'fg_pct', label: 'FG%' }),
          createSubColumn({ key: 'fg2_pct', label: '2P%' }),
          createSubColumn({ key: 'fg3_pct', label: '3P%' }),
          createSubColumn({ key: 'ft_pct', label: 'FT%' }),
          createSubColumn({ key: 'orpg', label: 'OREB' }),
          createSubColumn({ key: 'drpg', label: 'DREB' }),
          createSubColumn({ key: 'rpg', label: 'REB' }),
          createSubColumn({ key: 'apg', label: 'AST' }),
          createSubColumn({ key: 'spg', label: 'STL' }),
          createSubColumn({ key: 'bpg', label: 'BLK' }),
          createSubColumn({ key: 'topg', label: 'TOV' }),
          createSubColumn({ key: 'pfpg', label: 'PF' }),
          createSubColumn({ key: 'pfdpg', label: 'PFD' }),
        ];

      default:
        return [
          ...baseColumns,
          withMeta(createMetricColumn('adj_net'), { emphasis: true }),
          createMetricColumn('adj_off'),
          createMetricColumn('adj_def'),
          createMetricColumn('pace'),
          createMetricColumn('ffi'),
        ];
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, metricRanks]);

  // Missing values sort last in both directions
  const sortedColumns = useMemo(() => withNullsLast(columns), [columns]);

  const table = useReactTable({
    data: filteredData,
    columns: sortedColumns,
    state: { sorting, columnFilters, globalFilter },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  const isGroupedTab = activeTab !== 'overview';

  // Render

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap gap-4 items-center">
        {seasons.length > 1 && (
          <div>
            <select
              value={selectedSeason ?? ''}
              onChange={(e) => {
                const val = e.target.value;
                const stParam = selectedSeasonType === 'playoffs' ? '&season_type=playoffs' : '';
                router.push(val ? `/nba/ratings?season=${val}${stParam}` : '/nba/ratings');
              }}
              className="px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/50 font-medium"
            >
              {seasons.map((s) => (
                <option key={s.year} value={s.year}>
                  {s.display_name}{s.is_current ? ' (Current)' : ''}
                </option>
              ))}
            </select>
          </div>
        )}

        <div>
          <select
            value={selectedSeasonType}
            onChange={(e) => {
              const stParam = e.target.value === 'playoffs' ? '&season_type=playoffs' : '';
              const sParam = selectedSeason ? `&season=${selectedSeason}` : '';
              router.push(`/nba/ratings?${sParam}${stParam}`.replace('?&', '?'));
            }}
            className="px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/50 font-medium"
          >
            <option value="regular">Regular Season</option>
            <option value="playoffs">Playoffs</option>
          </select>
        </div>

        <div className="flex-1 min-w-[200px]">
          <input
            type="text"
            value={globalFilter ?? ''}
            onChange={(e) => setGlobalFilter(e.target.value)}
            placeholder="Search teams..."
            className="w-full px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/50"
          />
        </div>

        <div>
          <select
            value={conferenceFilter}
            onChange={(e) => setConferenceFilter(e.target.value)}
            className="px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/50"
          >
            <option value="all">All Conferences</option>
            <optgroup label="Conferences">
              <option value="East">Eastern Conference</option>
              <option value="West">Western Conference</option>
            </optgroup>
          </select>
        </div>

        <div className="text-sm text-text-muted">
          Showing {table.getFilteredRowModel().rows.length} teams
        </div>
      </div>

      {/* Tabs */}
      {/* View toggle */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <TableTabs tabs={tabs} active={activeTab} onChange={setActiveTab} />
        <HeatLegend basis="all 30 teams" />
      </div>

      {/* Table */}
      <div className="overflow-x-auto border border-ui-border rounded-lg">
        <table className="w-full">
          <GroupedTableHead headerGroups={table.getHeaderGroups()} tone="ink" />
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                className="border-b border-ui-border hover:bg-ui-hover transition-colors"
              >
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    className={clsx('py-2 text-sm', cellClass(cell.column), isGroupedTab ? 'px-1' : 'px-3')}
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
        <div className="text-center py-8 text-text-muted">
          {data.length === 0
            ? noDataMessage(selectedSeasonType, seasons.find((s) => s.year === selectedSeason)?.display_name)
            : 'No teams found matching your search.'}
        </div>
      )}
    </div>
  );
}
