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
import { TeamSeason, SeasonInfo } from '@macfax/core/types';
import Link from 'next/link';
import clsx from 'clsx';
import HeaderWithTooltip from './HeaderWithTooltip';
import GroupedTableHead, { cellClass, withMeta } from './table/GroupedTableHead';
import TableTabs from './table/TableTabs';
import MetricValue from './table/MetricValue';
import MetricDefinitionsCard, { type MetricDefinition } from './MetricDefinitionsCard';
import { METRIC_DEFINITIONS, MetricMeta } from '@macfax/core/lib/metricMetadata';
import { computeRanks, heatStyleFromPercentile, RankData } from '@macfax/core/lib/rankingUtils';
import { withNullsLast } from '@/lib/nullsLast';
import { ncaaTeamHref } from '@/lib/teamLinks';
import { pickCurrentSeason } from '@macfax/core/lib/season';
import HeatLegend from './HeatLegend';

interface RankingsTableProps {
  data: TeamSeason[];
  seasons?: SeasonInfo[];
  selectedSeason?: number;
  /** Sport context — defaults to 'ncaa'. Reserved for future sport-aware column config. */
  sport?: 'ncaa';
  isPreTournament?: boolean;
}

type TabId = 'overview' | 'four-factors' | 'adjusted-four-factors' | 'traditional';

interface SubColSpec {
  key: string;
  /** Short label shown in the sub-column header (e.g. "Off", "Def", "Edge") */
  label: string;
}

const TEAM_METRIC_DEFINITIONS: Record<TabId, MetricDefinition[]> = {
  overview: [
    { k: 'AdjEM', v: 'Adjusted Efficiency Margin (AdjO - AdjD): expected points per 100 possessions above or below an average D-I team on a neutral court.' },
    { k: 'AdjO', v: 'Adjusted Offensive Efficiency: points scored per 100 possessions, adjusted for opponent defense.' },
    { k: 'AdjD', v: 'Adjusted Defensive Efficiency: points allowed per 100 possessions, adjusted for opponent offense; lower is better.' },
    { k: 'Tempo', v: 'Adjusted pace: estimated possessions per 40 minutes, adjusted for opponent pace.' },
    { k: 'FFI', v: 'Four Factor Index: 0-100 composite of shooting, turnovers, rebounding, and free throw rate; 50 is average and higher is better.' },
    { k: 'WAB', v: 'Wins Above Bubble: wins beyond what a bubble-level team would expect against the same schedule; positive means a tournament-worthy resume.' },
    { k: 'SOS', v: 'Strength of schedule rank, 1 = hardest: expected win% for an average D1 team vs this schedule; teal = harder.' },
    { k: 'Luck', v: 'Games won above (+) or below (-) what our ratings expect vs this schedule; tends not to repeat, so it is not shaded.' },
  ],
  'four-factors': [
    { k: 'Raw', v: 'Unadjusted box-score four-factor rates before opponent-strength adjustments.' },
    { k: 'eFG%', v: 'Effective Field Goal %: shooting efficiency that gives made threes extra credit.' },
    { k: 'Turnover %', v: 'Turnover rate: turnovers per possession; lower is better on offense and higher is better on defense.' },
    { k: 'Rebounding', v: 'ORB%: offensive rebounding rate, the share of available offensive rebounds secured. DRB%: defensive rebounding rate, the share of opponent misses rebounded by the defense.' },
    { k: 'FT Rate', v: 'Free throw rate: free throw attempts per field goal attempt.' },
    { k: 'Net', v: 'Team rate minus opponent rate (for turnovers, opponent TOV% minus team TOV%); positive is better.' },
    { k: 'FFI', v: 'Raw Four Factor Index: 0-100 composite of raw shooting, turnovers, rebounding, and free throw rate.' },
  ],
  'adjusted-four-factors': [
    { k: 'Adjusted', v: 'Four-factor rates adjusted for opponent quality so teams can be compared across schedules.' },
    { k: 'eFG%', v: 'Adjusted effective field goal percentage: shooting efficiency with made threes receiving extra credit.' },
    { k: 'Turnover %', v: 'Adjusted turnover rate: turnovers per possession; lower is better on offense and higher is better on defense.' },
    { k: 'Rebounding', v: 'ORB%: adjusted offensive rebounding rate, the share of available offensive rebounds secured. DRB%: adjusted defensive rebounding rate, the share of opponent misses rebounded by the defense.' },
    { k: 'FT Rate', v: 'Adjusted free throw rate: free throw attempts per field goal attempt.' },
    { k: 'Net', v: 'Adjusted team advantage over opponents; positive values mean the four-factor battle favors the team.' },
    { k: 'FFI', v: 'Adjusted Four Factor Index: 0-100 composite of adjusted four-factor margins; higher is better.' },
  ],
  traditional: [
    { k: 'PTS', v: 'Points per game, from final scores.' },
    { k: 'OPP PTS', v: 'Opponent points per game, from final scores; lower is better.' },
    { k: 'FG%', v: 'Field goals made divided by field goals attempted.' },
    { k: 'OREB', v: 'Offensive rebounds per game.' },
    { k: 'DREB', v: 'Defensive rebounds per game.' },
    { k: 'REB', v: 'Total rebounds per game.' },
    { k: 'AST', v: 'Assists per game.' },
    { k: 'STL', v: 'Steals per game.' },
    { k: 'BLK', v: 'Blocks per game.' },
    { k: 'TOV', v: 'Turnovers per game; lower is better.' },
    { k: 'PF', v: 'Personal fouls committed per game; lower is better.' },
    { k: 'PFD', v: 'Personal fouls drawn per game (fouls committed by opponents).' },
  ],
};

export default function RankingsTable({ data, seasons = [], selectedSeason, isPreTournament = false }: RankingsTableProps) {
  const router = useRouter();
  // Team links keep a past season (?season=); current season links stay plain
  const currentSeason = pickCurrentSeason(seasons)?.year ?? null;
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'rank', desc: false },
  ]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [globalFilter, setGlobalFilter] = useState('');
  const [conferenceFilter, setConferenceFilter] = useState<string>('all');

  const tabs = [
    { id: 'overview' as TabId, label: 'Efficiency' },
    { id: 'four-factors' as TabId, label: 'Four Factors' },
    { id: 'adjusted-four-factors' as TabId, label: 'Adj Four Factors' },
    { id: 'traditional' as TabId, label: 'Traditional' },
  ];

  // Tournament filters only make sense once the season has a bracket (seeds load the day after Selection Sunday).
  const hasTournament = data.some((t) => t.tournament_seed != null);
  if (!hasTournament && conferenceFilter.startsWith('ncaa_')) {
    setConferenceFilter('all');
  }

  const conferences = useMemo(() => {
    const confs = new Set(data.map((t) => t.conference).filter(Boolean));
    return Array.from(confs).sort();
  }, [data]);

  const filteredData = useMemo(() => {
    if (conferenceFilter === 'all') return data;
    if (conferenceFilter === 'ncaa_tournament') return data.filter((t) => t.tournament_seed != null);
    if (conferenceFilter === 'ncaa_south') return data.filter((t) => t.tournament_region === 'South');
    if (conferenceFilter === 'ncaa_east') return data.filter((t) => t.tournament_region === 'East');
    if (conferenceFilter === 'ncaa_west') return data.filter((t) => t.tournament_region === 'West');
    if (conferenceFilter === 'ncaa_midwest') return data.filter((t) => t.tournament_region === 'Midwest');
    return data.filter((t) => t.conference === conferenceFilter);
  }, [data, conferenceFilter]);

  // Precompute ranks for all metrics from the full D1 dataset so heatmap
  // colours stay consistent regardless of the conference filter.
  const metricRanks = useMemo(() => {
    const ranks = new Map<string, Map<string, RankData>>();
    Object.values(METRIC_DEFINITIONS).forEach((meta) => {
      const entries = data.map((t) => ({
        id: t.teamId,
        value: (t as any)[meta.key] as number | null,
      }));
      ranks.set(meta.key, computeRanks(entries, meta.better));
    });
    return ranks;
  }, [data]);

  const formatValue = (value: number | null, format: MetricMeta['format']): string => {
    if (value == null) return '-';
    switch (format) {
      case 'number1':    return value.toFixed(1);
      case 'number2':    return value.toFixed(2);
      case 'percent1':   return `${(value * 100).toFixed(1)}%`;
      case 'number1pct': return `${value.toFixed(1)}%`;
      case 'signed1':    return `${value > 0 ? '+' : ''}${value.toFixed(1)}`;
      case 'int':        return Math.round(value).toString();
      default:          return value.toString();
    }
  };

  const columns = useMemo(() => {
    // ── Full-width metric column (Overview tab) ──────────────────────────────
    const createMetricColumn = (metricKey: string): ColumnDef<TeamSeason> => {
      const meta = METRIC_DEFINITIONS[metricKey];
      if (!meta) return {} as ColumnDef<TeamSeason>;
      return {
        accessorKey: meta.key,
        header: () => (
          <HeaderWithTooltip label={meta.label} better={meta.better} tooltip={meta.tooltip} />
        ),
        cell: (info) => {
          const value = info.getValue<number | null>();
          const rankData = metricRanks.get(meta.key)?.get(info.row.original.teamId);
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
        sortDescFirst: meta.sortDescFirst ?? meta.better === 'higher',
      };
    };

    // ── Compact sub-column used inside a group ────────────────────────────────
    const createSubColumn = (spec: SubColSpec): ColumnDef<TeamSeason> => {
      const meta = METRIC_DEFINITIONS[spec.key];
      if (!meta) return {} as ColumnDef<TeamSeason>;
      return {
        accessorKey: meta.key,
        header: () => (
          <HeaderWithTooltip label={spec.label} better={meta.better} tooltip={meta.tooltip} />
        ),
        cell: (info) => {
          const value = info.getValue<number | null>();
          const rankData = metricRanks.get(meta.key)?.get(info.row.original.teamId);
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

    // ── Factory for a 3-column group (Off / Def / Net) ─────────────────────────
    const createGroup = (
      id: string,
      label: string,
      off: SubColSpec,
      def: SubColSpec,
      edge: SubColSpec,
    ): ColumnDef<TeamSeason> => ({
      id,
      header: label,
      columns: [
        withMeta(createSubColumn(off), { divider: true }),
        createSubColumn(def),
        withMeta(createSubColumn(edge), { net: true }),
      ],
    });

    // ── Base columns – full version (Overview) ────────────────────────────────
    const baseColumns: ColumnDef<TeamSeason>[] = [
      {
        accessorKey: 'rank',
        header: 'Rk',
        meta: { align: 'left' },
        sortDescFirst: false,
        cell: (info) => (
          <span className="font-mono font-semibold">{info.getValue<number>()}</span>
        ),
        size: 50,
      },
      {
        accessorKey: 'teamName',
        header: 'Team',
        meta: { align: 'left' },
        cell: (info) => {
          const team = info.row.original;
          return (
            <Link
              href={ncaaTeamHref(team.teamId, selectedSeason, currentSeason)}
              className="flex items-center space-x-2 hover:text-brand transition-colors"
            >
              {team.logoUrl ? (
                <img
                  src={team.logoUrl}
                  alt={team.teamName}
                  className="w-6 h-6 object-contain"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = 'none';
                  }}
                />
              ) : (
                <div className="w-6 h-6 bg-ui-surface rounded-full flex items-center justify-center text-xs font-bold text-text-muted">
                  {team.teamName.charAt(0)}
                </div>
              )}
              {team.tournament_seed != null && (
                <span className="text-[11px] font-bold text-brand/80 w-4 text-right shrink-0">
                  {team.tournament_seed}
                </span>
              )}
              <span className="font-medium">{team.teamName}</span>
              {team.tournament_finish === 'Champ' && <span title="National Champion" className="text-sm">🏆</span>}
              {team.tournament_finish === 'Runner-Up' && <span title="Runner-Up" className="text-sm">🥈</span>}
              {team.tournament_finish === 'Final Four' && <span title="Final Four" className="text-sm">🥉</span>}
            </Link>
          );
        },
        size: 200,
      },
      {
        accessorKey: 'conference',
        header: 'Conf',
        meta: { align: 'left' },
        cell: (info) => (
          <span className="text-text-muted text-xs uppercase">{info.getValue<string>()}</span>
        ),
        size: 60,
      },
      {
        accessorKey: 'record',
        header: 'Record',
        cell: (info) => (
          <span className="font-mono text-sm">{info.getValue<string>() || '-'}</span>
        ),
        size: 70,
      },
    ];

    // ── Base columns – compact version (Four Factors tabs, no Record) ─────────
    const compactBaseColumns: ColumnDef<TeamSeason>[] = [
      {
        accessorKey: 'rank',
        header: 'Rk',
        meta: { align: 'left' },
        sortDescFirst: false,
        cell: (info) => (
          <span className="font-mono font-semibold text-sm">{info.getValue<number>()}</span>
        ),
        size: 42,
      },
      {
        accessorKey: 'teamName',
        header: 'Team',
        meta: { align: 'left' },
        cell: (info) => {
          const team = info.row.original;
          return (
            <Link
              href={ncaaTeamHref(team.teamId, selectedSeason, currentSeason)}
              className="flex items-center space-x-2 hover:text-brand transition-colors"
            >
              {team.logoUrl ? (
                <img
                  src={team.logoUrl}
                  alt={team.teamName}
                  className="w-5 h-5 object-contain"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = 'none';
                  }}
                />
              ) : (
                <div className="w-5 h-5 bg-ui-surface rounded-full flex items-center justify-center text-xs font-bold text-text-muted">
                  {team.teamName.charAt(0)}
                </div>
              )}
              {team.tournament_seed != null && (
                <span className="text-[10px] font-bold text-brand/80 w-4 text-right shrink-0">
                  {team.tournament_seed}
                </span>
              )}
              <span className="font-medium text-sm">{team.teamName}</span>
              {team.tournament_finish === 'Champ' && <span title="National Champion" className="text-sm">🏆</span>}
              {team.tournament_finish === 'Runner-Up' && <span title="Runner-Up" className="text-sm">🥈</span>}
              {team.tournament_finish === 'Final Four' && <span title="Final Four" className="text-sm">🥉</span>}
            </Link>
          );
        },
        size: 155,
      },
      {
        accessorKey: 'conference',
        header: 'Conf',
        meta: { align: 'left' },
        cell: (info) => (
          <span className="text-text-muted text-xs uppercase">{info.getValue<string>()}</span>
        ),
        size: 52,
      },
    ];

    switch (activeTab) {
      case 'overview':
        return [
          ...baseColumns,
          withMeta(createMetricColumn('adjEM'), { emphasis: true }),
          createMetricColumn('adjO'),
          createMetricColumn('adjD'),
          createMetricColumn('adjTempo'),
          createMetricColumn('four_factor_index_100'),
          createMetricColumn('wab'),
          createMetricColumn('sos_rank'),
          createMetricColumn('luck_wins'),
        ];

      case 'four-factors':
        return [
          ...compactBaseColumns,
          createGroup('ff-efg', 'eFG%',
            { key: 'raw_eFG',         label: 'Off'    },
            { key: 'raw_eFG_d',       label: 'Def'    },
            { key: 'raw_eFG_margin',  label: 'Net'    },
          ),
          createGroup('ff-tov', 'Turnover %',
            { key: 'raw_tov',         label: 'Off'  },
            { key: 'raw_tov_d',       label: 'Def'  },
            { key: 'raw_tov_edge',    label: 'Net'  },
          ),
          createGroup('ff-reb', 'Rebounding',
            { key: 'raw_orb',         label: 'ORB'  },
            { key: 'raw_drb',         label: 'DRB'  },
            { key: 'raw_reb_edge',    label: 'Net'  },
          ),
          createGroup('ff-ftr', 'FT Rate',
            { key: 'raw_ftr',         label: 'Off'    },
            { key: 'raw_ftr_d',       label: 'Def'    },
            { key: 'raw_ftr_margin',  label: 'Net'    },
          ),
          withMeta(createSubColumn({ key: 'raw_four_factor_index_100', label: 'FFI' }), { emphasis: true }),
        ];

      case 'adjusted-four-factors':
        return [
          ...compactBaseColumns,
          createGroup('aff-efg', 'eFG%',
            { key: 'eFG',         label: 'Off'    },
            { key: 'eFG_d',       label: 'Def'    },
            { key: 'eFG_margin',  label: 'Net'    },
          ),
          createGroup('aff-tov', 'Turnover %',
            { key: 'tov',         label: 'Off'  },
            { key: 'tov_d',       label: 'Def'  },
            { key: 'tov_edge',    label: 'Net'  },
          ),
          createGroup('aff-reb', 'Rebounding',
            { key: 'orb',         label: 'ORB'  },
            { key: 'drb',         label: 'DRB'  },
            { key: 'reb_edge',    label: 'Net'  },
          ),
          createGroup('aff-ftr', 'FT Rate',
            { key: 'ftr',         label: 'Off'    },
            { key: 'ftr_d',       label: 'Def'    },
            { key: 'ftr_margin',  label: 'Net'    },
          ),
          withMeta(createSubColumn({ key: 'four_factor_index_100', label: 'FFI' }), { emphasis: true }),
        ];

      case 'traditional':
        return [
          ...compactBaseColumns,
          createSubColumn({ key: 'd1_games_played', label: 'GP' }),
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
          withMeta(createMetricColumn('adjEM'), { emphasis: true }),
          createMetricColumn('adjO'),
          createMetricColumn('adjD'),
          createMetricColumn('adjTempo'),
          createMetricColumn('four_factor_index_100'),
          createMetricColumn('wab'),
          createMetricColumn('sos_rank'),
          createMetricColumn('luck_wins'),
        ];
    }
  }, [activeTab, metricRanks, selectedSeason, currentSeason]);

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

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap gap-4 items-center">
        {/* Season selector */}
        {seasons.length > 1 && (
          <div>
            <select
              value={selectedSeason ?? ''}
              onChange={(e) => {
                const val = e.target.value;
                router.push(val ? `/ncaa/ratings?season=${val}` : '/ncaa/ratings');
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
            {hasTournament && (
              <optgroup label="NCAA Tournament">
                <option value="ncaa_tournament">🏀 NCAA Tournament</option>
                <option value="ncaa_south">↳ South Region</option>
                <option value="ncaa_east">↳ East Region</option>
                <option value="ncaa_west">↳ West Region</option>
                <option value="ncaa_midwest">↳ Midwest Region</option>
              </optgroup>
            )}
            <optgroup label="Conferences">
              {conferences.map((conf) => (
                <option key={conf} value={conf}>
                  {conf}
                </option>
              ))}
            </optgroup>
          </select>
        </div>

        <div className="text-sm text-text-muted">
          Showing {table.getFilteredRowModel().rows.length} teams
        </div>

        {/* Pre-Tournament Toggle: hidden without a bracket, unless already on so it can be turned off */}
        {(hasTournament || isPreTournament) && (
          <div className="flex items-center gap-2 ml-auto">
            <label htmlFor="preTournamentToggle" className="text-sm font-medium text-text-primary cursor-pointer">
              Pre-Tournament Only
            </label>
            <button
              id="preTournamentToggle"
              role="switch"
              aria-checked={isPreTournament}
              onClick={() => {
                const newUrl = new URL(window.location.href);
                if (!isPreTournament) {
                  newUrl.searchParams.set('pre_tournament', 'true');
                } else {
                  newUrl.searchParams.delete('pre_tournament');
                }
                router.push(newUrl.pathname + newUrl.search);
              }}
              className={clsx(
                "relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-brand focus:ring-offset-2 focus:ring-offset-surface",
                isPreTournament ? "bg-brand" : "bg-ui-border"
              )}
            >
              <span
                className={clsx(
                  "inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform",
                  isPreTournament ? "translate-x-4" : "translate-x-1"
                )}
              />
            </button>
          </div>
        )}
      </div>

      {/* View toggle */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <TableTabs tabs={tabs} active={activeTab} onChange={setActiveTab} />
        <HeatLegend basis="all D1 teams" />
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
          No teams found matching your search.
        </div>
      )}

      <MetricDefinitionsCard definitions={TEAM_METRIC_DEFINITIONS[activeTab]} />
    </div>
  );
}
