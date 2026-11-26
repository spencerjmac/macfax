'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  ColumnDef,
  flexRender,
  SortingState,
  PaginationState,
} from '@tanstack/react-table';
import clsx from 'clsx';
import { noDataMessage } from '@/lib/nbaNoData';
import HeaderWithTooltip from './HeaderWithTooltip';
import GroupedTableHead, { cellClass, withMeta } from './table/GroupedTableHead';
import TableTabs from './table/TableTabs';
import MetricDefinitionsCard, { type MetricDefinition } from './MetricDefinitionsCard';
import MetricValue from './table/MetricValue';
import { computeRanks, heatStyleFromPercentile } from '@macfax/core/lib/rankingUtils';
import { winsAddedFormula } from '@macfax/core/lib/ratingScale';
import {
  AUTO_THRESHOLD,
  NBA_NATIVE_MIN_PER_TEAM_GAME,
  autoNbaMinPoss,
  nbaRowMeetsPlayingTime,
} from '@macfax/core/lib/playerThresholds';
import {
  PLAYER_TRADITIONAL_METRICS,
  NBA_ADVANCED_METRICS,
  NBA_IMPACT_METRICS,
  formatPlayerMetric,
  meetsAttemptFloor,
  type PlayerMetricMeta,
} from '@macfax/core/lib/playerMetricMetadata';
import type { NBAPlayerSeasonStats, NBASeasonInfo } from '@macfax/core/types/nba';
import { withNullsLast } from '@/lib/nullsLast';
import HeatLegend from './HeatLegend';

type TabId = 'traditional' | 'advanced' | 'impact';

interface NBAPlayerRankingsTableProps {
  data: NBAPlayerSeasonStats[];
  seasonDisplay?: string;
  seasonType?: string;
  /** Team slug -> games played this season (from the team rankings); drives Auto for native rows. */
  teamGames?: Readonly<Record<string, number>>;
  seasons?: NBASeasonInfo[];
  selectedSeason?: number;
}

const NO_TEAM_GAMES: Readonly<Record<string, number>> = {};
const NO_SEASONS: NBASeasonInfo[] = [];

/** /nba/players URL for a season and season type (both optional). */
function playersHref(season: string | number | undefined, seasonType: string): string {
  const qs = new URLSearchParams();
  if (season) qs.set('season', String(season));
  if (seasonType === 'playoffs') qs.set('season_type', 'playoffs');
  const query = qs.toString();
  return query ? `/nba/players?${query}` : '/nba/players';
}

// ── Column sets ──────────────────────────────────────────────────────────────
const NBA_IMPACT_KEYS = ['bpr', 'obpr', 'dbpr', 'wins_added', 'on_court_poss'];
const NBA_TRAD_KEYS = ['pts', 'reb', 'ast', 'stl', 'blk', 'tov', 'fg_pct', 'fg3_pct', 'ft_pct', 'ts_pct'];
const NBA_ADV_KEYS = ['usg_pct', 'ts_pct', 'ast_pct', 'tov_pct', 'oreb_pct', 'dreb_pct', 'stl_pct', 'blk_pct'];

const NBA_ARCHETYPE_STYLES: Record<string, string> = {
  creator:     'bg-brand/10 text-brand border-brand/20',
  scorer:      'bg-secondary/10 text-secondary border-secondary/20',
  interior:    'bg-amber-500/10 text-amber-700 border-amber-400/20',
  three_and_d: 'bg-emerald-500/10 text-emerald-700 border-emerald-400/20',
  stretch:     'bg-violet-500/10 text-violet-700 border-violet-400/20',
  connector:   'bg-ui-hover text-text-muted border-ui-border',
};

// wins_added lives on the type but not in playerMetricMetadata — add inline
const WINS_ADDED_META: PlayerMetricMeta = {
  key: 'wins_added', label: 'W.Add', tooltip: 'Wins Added above replacement.',
  format: 'signed1', better: 'higher', showRank: true, heatmap: true, tier: 'primary',
};

const BPR_REFERENCE = { k: 'MPR', v: 'Macfax Player Rating, shown for reference; see the Impact tab.' };

// Written from each column's tooltip (playerMetricMetadata.ts and the inline meta above)
const NBA_PLAYER_DEFINITIONS: Record<Exclude<TabId, 'impact'>, MetricDefinition[]> = {
  traditional: [
    { k: 'GP', v: 'Games played.' },
    { k: 'MPG', v: 'Minutes per game.' },
    BPR_REFERENCE,
    { k: 'PPG', v: 'Points per game.' },
    { k: 'RPG', v: 'Total rebounds per game.' },
    { k: 'APG', v: 'Assists per game.' },
    { k: 'SPG', v: 'Steals per game.' },
    { k: 'BPG', v: 'Blocks per game.' },
    { k: 'TOV', v: 'Turnovers per game; lower is better.' },
    { k: 'FG%', v: 'Field goal percentage.' },
    { k: '3P%', v: 'Three-point percentage; shaded only at 1 or more three-point attempts per game.' },
    { k: 'FT%', v: 'Free throw percentage; shaded only at 1 or more free throw attempts per game.' },
    { k: 'TS%', v: 'True Shooting % = PTS / (2 × (FGA + 0.44 × FTA)): the most complete single shooting-efficiency stat.' },
  ],
  advanced: [
    BPR_REFERENCE,
    { k: 'USG%', v: 'Usage rate: share of team possessions used by this player while on the floor.' },
    { k: 'TS%', v: 'True Shooting %: scoring efficiency that accounts for twos, threes, and free throws.' },
    { k: 'AST%', v: 'Assist rate: share of team field goals assisted by this player while on court.' },
    { k: 'TOV%', v: 'Turnover rate per 100 plays; lower is better.' },
    { k: 'ORB%', v: 'Offensive rebound rate while on court.' },
    { k: 'DRB%', v: 'Defensive rebound rate while on court.' },
    { k: 'STL%', v: 'Steal rate while on court.' },
    { k: 'BLK%', v: 'Block rate: share of opponent two-point attempts blocked while on court.' },
  ],
};

/** Impact definitions; W.Add's formula depends on the season's rating scale. */
function nbaImpactDefinitions(waFormula: string): MetricDefinition[] {
  return [
    { k: 'Age', v: 'Age on February 1 of the season.' },
    { k: 'MPR', v: 'Macfax Player Rating (O-MPR + D-MPR): career-stabilized box stats regularized toward single-season RAPM. Context-adjusted impact in points per 100 possessions above league average; it reflects role and team quality, not pure skill in isolation.' },
    { k: 'O-MPR', v: 'Offensive MPR: estimated offensive points per 100 possessions added above league average.' },
    { k: 'D-MPR', v: 'Defensive MPR: estimated defensive points per 100 possessions prevented above league average; higher is a better defender.' },
    { k: 'W.Add', v: `Wins Added above replacement: ${waFormula}.` },
    { k: 'Poss', v: 'Estimated possessions played on court this season.' },
    { k: 'Role', v: 'Player archetype from the box-score profile (creator, scorer, interior, 3&D, stretch, connector).' },
  ];
}

const TAB_DEFAULT_SORT: Record<TabId, SortingState> = {
  impact:      [{ id: 'bpr', desc: true }],
  traditional: [{ id: 'pts', desc: true }],
  advanced:    [{ id: 'ts_pct', desc: true }],
};

const PAGE_SIZE = 100;

export default function NBAPlayerRankingsTable({
  data, seasonDisplay, seasonType = 'regular', teamGames = NO_TEAM_GAMES,
  seasons = NO_SEASONS, selectedSeason,
}: NBAPlayerRankingsTableProps) {
  const router = useRouter();
  const isPlayoffs = seasonType === 'playoffs';

  // Open on Impact when BPR exists; playoffs and seasons before BPR is computed open on Traditional
  const hasBpr = useMemo(() => data.some((p) => p.bpr != null), [data]);
  const startOnImpact = !isPlayoffs && hasBpr;
  const [activeTab, setActiveTab] = useState<TabId>(startOnImpact ? 'impact' : 'traditional');
  const [sorting, setSorting] = useState<SortingState>(TAB_DEFAULT_SORT[startOnImpact ? 'impact' : 'traditional']);
  const [globalFilter, setGlobalFilter] = useState('');
  // Default "Auto" scales with games played (see playerThresholds.ts)
  const [minPossChoice, setMinPossChoice] = useState<number>(AUTO_THRESHOLD);
  const autoMinPoss = useMemo(() => autoNbaMinPoss(data), [data]);
  const isAuto = minPossChoice === AUTO_THRESHOLD;
  const minPoss = isAuto ? autoMinPoss : minPossChoice;
  // Native rows under Auto use minutes >= 18 x team games (playerThresholds.ts)
  const hasNative = useMemo(() => data.some((p) => p.rating_scale === 'native-1'), [data]);
  // Role column only when the archetype job has filled it for this season
  const hasArchetype = useMemo(() => data.some((p) => p.nba_archetype), [data]);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: PAGE_SIZE });

  // Leave Impact when switching to playoffs or to a season with no BPR yet
  useEffect(() => {
    if ((isPlayoffs || !hasBpr) && activeTab === 'impact') {
      setActiveTab('traditional');
      setSorting(TAB_DEFAULT_SORT.traditional);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPlayoffs, hasBpr]);

  const tabs = [
    ...(!isPlayoffs ? [{ id: 'impact' as TabId, label: 'Impact' }] : []),
    { id: 'traditional' as TabId, label: 'Traditional' },
    { id: 'advanced'    as TabId, label: 'Advanced'    },
  ];

  // ── Qualification (shared by displayed rows and percentile ranks) ───────
  const qualified = useMemo(
    () =>
      isPlayoffs
        ? data
        : data.filter((p) => nbaRowMeetsPlayingTime(p, isAuto, minPoss, teamGames)),
    [data, isAuto, minPoss, teamGames, isPlayoffs]
  );

  // ── Filter ──────────────────────────────────────────────────────────────
  const filtered = useMemo(() => {
    if (!globalFilter) return qualified;
    const q = globalFilter.toLowerCase();
    return qualified.filter(
      (p) =>
        p.player_name.toLowerCase().includes(q) ||
        (p.team_name ?? '').toLowerCase().includes(q)
    );
  }, [qualified, globalFilter]);

  // ── Metric lookup map ────────────────────────────────────────────────────
  const allMetaMaps = useMemo(() => {
    const map: Record<string, PlayerMetricMeta> = { wins_added: WINS_ADDED_META };
    [...PLAYER_TRADITIONAL_METRICS, ...NBA_ADVANCED_METRICS, ...NBA_IMPACT_METRICS].forEach((m) => {
      map[m.key] = m;
    });
    return map;
  }, []);

  // ── Percentile ranks ─────────────────────────────────────────────────────
  const metricRanks = useMemo(() => {
    const ranks = new Map<string, ReturnType<typeof computeRanks>>();
    new Set([...NBA_IMPACT_KEYS, ...NBA_TRAD_KEYS, ...NBA_ADV_KEYS]).forEach((key) => {
      const meta = allMetaMaps[key];
      if (!meta) return;
      // Below an attempt floor a shooting % is left out of the ranks (and so of the heat)
      const entries = qualified.map((p) => ({
        id: String(p.id),
        value: meetsAttemptFloor(p, key) ? ((p as unknown as Record<string, number | null>)[key] ?? null) : null,
      }));
      ranks.set(key, computeRanks(entries, meta.better));
    });
    return ranks;
  }, [qualified, allMetaMaps]);

  // ── Column factory ───────────────────────────────────────────────────────
  const createMetricColumn = (key: string, tooltip?: string): ColumnDef<NBAPlayerSeasonStats> => {
    const meta = allMetaMaps[key];
    if (!meta) return { id: key } as ColumnDef<NBAPlayerSeasonStats>;
    return {
      accessorKey: key,
      header: () => (
        <HeaderWithTooltip label={meta.label} better={meta.better} tooltip={tooltip ?? meta.tooltip} />
      ),
      cell: (info) => {
        const row = info.row.original;
        const value = info.getValue<number | null>();
        const graded = meetsAttemptFloor(row, key);
        const rankData = graded ? metricRanks.get(key)?.get(String(row.id)) : undefined;
        const hs = value != null && graded && meta.heatmap ? heatStyleFromPercentile(rankData?.percentile ?? null, meta.better) : {};
        return (
          <MetricValue
            text={value == null ? null : formatPlayerMetric(value, meta.format)}
            heat={hs}
            rank={rankData?.rank}
            showRank={graded && meta.showRank}
            column={info.column}
          />
        );
      },
      sortDescFirst: meta.better !== 'lower',
      size: 78,
    };
  };

  // ── Base identity columns ────────────────────────────────────────────────
  const baseColumns: ColumnDef<NBAPlayerSeasonStats>[] = [
    {
      accessorKey: 'player_name',
      header: 'Player',
      meta: { align: 'left' },
      cell: (info) => {
        const row = info.row.original;
        const headshotUrl = `https://cdn.nba.com/headshots/nba/latest/1040x760/${row.player_id}.png`;
        return (
          <div className="flex items-center gap-2 min-w-0 max-w-[190px]">
            <div className="w-6 h-6 rounded-full overflow-hidden bg-ui-surface flex-shrink-0">
              <img
                src={headshotUrl}
                alt={row.player_name}
                className="w-6 h-6 object-cover"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
            </div>
            <Link
              href={`/nba/players/${row.player_id}`}
              title={row.player_name}
              className="font-medium text-sm truncate hover:underline underline-offset-2"
            >
              {info.getValue<string>()}
            </Link>
          </div>
        );
      },
      size: 170,
    },
    {
      accessorKey: 'team_name',
      header: 'Team',
      meta: { align: 'left' },
      // Compact team cell from the team table: logo + abbreviation, linking to the team page
      cell: (info) => {
        const row = info.row.original;
        const name = info.getValue<string | null>();
        if (!name) return <span className="text-text-muted">-</span>;
        const abbr = row.team_abbreviation ?? name;
        const inner = (
          <>
            {row.team_logo_url ? (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img
                src={row.team_logo_url}
                alt={name}
                className="w-5 h-5 object-contain shrink-0"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
            ) : (
              <div className="w-5 h-5 shrink-0 bg-ui-surface rounded-full flex items-center justify-center text-[9px] font-bold text-text-muted">
                {abbr.slice(0, 3)}
              </div>
            )}
            <span className="font-medium text-sm whitespace-nowrap" title={name}>{abbr}</span>
          </>
        );
        return row.team_slug ? (
          <Link href={`/nba/team/${row.team_slug}`} className="flex items-center space-x-2 hover:text-brand transition-colors">
            {inner}
          </Link>
        ) : (
          <div className="flex items-center space-x-2">{inner}</div>
        );
      },
      size: 80,
    },
    {
      accessorKey: 'gp',
      header: 'GP',
      cell: (info) => <span className="font-mono text-sm">{info.getValue<number>()}</span>,
      size: 44,
    },
    {
      accessorKey: 'mpg',
      header: 'MPG',
      cell: (info) => (
        <span className="font-mono text-sm">{(info.getValue<number | null>() ?? 0).toFixed(1)}</span>
      ),
      size: 50,
      sortDescFirst: true,
    },
  ];

  // ── Full column set per tab ──────────────────────────────────────────────
  // native-1 rows: new Wins Added formula (task 5.10b); earlier rows keep the old text
  const wa_formula = useMemo(() => winsAddedFormula(data), [data]);

  const columns = useMemo((): ColumnDef<NBAPlayerSeasonStats>[] => {
    const activeSortKey = sorting[0]?.id;
    const rankColumn: ColumnDef<NBAPlayerSeasonStats> = {
      id: 'rank',
      header: 'Rk',
      meta: { align: 'left' },
      cell: (info) => {
        const rank = activeSortKey
          ? metricRanks.get(activeSortKey)?.get(String(info.row.original.id))?.rank
          : undefined;
        return (
          <span className="font-mono font-semibold">
            {rank ?? pagination.pageIndex * PAGE_SIZE + info.row.index + 1}
          </span>
        );
      },
      enableSorting: false,
      size: 44,
    };

    if (activeTab === 'impact') {
      const archetypeCol: ColumnDef<NBAPlayerSeasonStats> = {
        id: 'nba_archetype',
        header: 'Role',
        accessorFn: (row) => row.nba_archetype ?? '',
        cell: (info) => {
          const arch = info.row.original.nba_archetype;
          if (!arch) return <span className="text-text-muted">-</span>;
          const label = arch === 'three_and_d' ? '3&D' : arch.charAt(0).toUpperCase() + arch.slice(1);
          const cls = NBA_ARCHETYPE_STYLES[arch] ?? 'text-text-muted';
          return (
            <span className={clsx('text-[11px] font-mono px-1.5 py-0.5 rounded border', cls)}>
              {label}
            </span>
          );
        },
        enableSorting: false,
        size: 72,
      };

      const winsAddedCol = createMetricColumn('wins_added', `Wins Added above replacement · ${wa_formula}`);

      const ageCol: ColumnDef<NBAPlayerSeasonStats> = {
        accessorKey: 'age',
        header: () => <HeaderWithTooltip label="Age" better="neutral" tooltip="Age on Feb 1 of the season." />,
        cell: (info) => {
          const age = info.getValue<number | null>();
          return age == null ? <span className="text-text-muted">-</span> : <span className="font-mono text-sm">{age}</span>;
        },
        sortDescFirst: false,
        size: 48,
      };

      // BPR is the hero: first metric, larger value, widest metric column; Age sits after Team
      return [
        rankColumn,
        baseColumns[0],
        baseColumns[1],
        ageCol,
        ...baseColumns.slice(2),
        { ...withMeta(createMetricColumn('bpr'), { emphasis: true, hero: true }), size: 120 },
        createMetricColumn('obpr'),
        createMetricColumn('dbpr'),
        winsAddedCol,
        createMetricColumn('on_court_poss'),
        ...(hasArchetype ? [archetypeCol] : []),
      ];
    }

    // BPR pinned right after MPG on the other tabs, when the season has it
    const pinnedBpr = hasBpr ? [withMeta(createMetricColumn('bpr'), { divider: true })] : [];
    const keys = activeTab === 'traditional' ? NBA_TRAD_KEYS : NBA_ADV_KEYS;
    return [
      rankColumn,
      ...baseColumns,
      ...pinnedBpr,
      ...keys.map((k, i) => (i === 0 ? withMeta(createMetricColumn(k), { divider: true }) : createMetricColumn(k))),
    ];
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, metricRanks, sorting, pagination.pageIndex, wa_formula, hasArchetype, hasBpr]);

  // ── TanStack table ───────────────────────────────────────────────────────
  // Missing values sort last in both directions
  const sortedColumns = useMemo(() => withNullsLast(columns), [columns]);

  const table = useReactTable({
    data: filtered,
    columns: sortedColumns,
    state: { sorting, globalFilter, pagination },
    onSortingChange: (updater) => {
      setSorting(updater);
      setPagination((p) => ({ ...p, pageIndex: 0 }));
    },
    onGlobalFilterChange: (updater) => {
      setGlobalFilter(updater);
      setPagination((p) => ({ ...p, pageIndex: 0 }));
    },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  return (
    <div className="space-y-4">
      {/* ── Filter bar ──────────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-4 items-center">
        {seasons.length > 1 && (
          <div>
            <select
              value={selectedSeason ?? ''}
              onChange={(e) => router.push(playersHref(e.target.value, seasonType))}
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
            value={seasonType}
            onChange={(e) => router.push(playersHref(selectedSeason, e.target.value))}
            className="px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm
                       focus:outline-none focus:ring-2 focus:ring-brand/50 font-medium"
          >
            <option value="regular">Regular Season</option>
            <option value="playoffs">Playoffs</option>
          </select>
        </div>
        <div className="flex-1 min-w-[200px]">
          <input
            type="text"
            value={globalFilter}
            onChange={(e) => {
              setGlobalFilter(e.target.value);
              setPagination((p) => ({ ...p, pageIndex: 0 }));
            }}
            placeholder="Search players or teams..."
            className="w-full px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/50"
          />
        </div>
        {!isPlayoffs && (
          <div>
            <select
              value={minPossChoice}
              onChange={(e) => {
                setMinPossChoice(Number(e.target.value));
                setPagination((p) => ({ ...p, pageIndex: 0 }));
              }}
              className="px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm
                         focus:outline-none focus:ring-2 focus:ring-brand/50"
            >
              <option value={AUTO_THRESHOLD}>
                {hasNative
                  ? `Auto · min ${NBA_NATIVE_MIN_PER_TEAM_GAME} min × team games`
                  : `Auto · min ${autoMinPoss} poss`}
              </option>
              {[50, 100, 250, 500, 750, 1000, 1500, 2000].map((n) => (
                <option key={n} value={n}>Min {n} poss</option>
              ))}
            </select>
          </div>
        )}
        <div className="text-sm text-text-muted">
          Showing {table.getFilteredRowModel().rows.length} players
        </div>
      </div>

      {/* ── Tabs ────────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <TableTabs
          tabs={tabs}
          active={activeTab}
          onChange={(id) => {
            setActiveTab(id);
            setSorting(TAB_DEFAULT_SORT[id]);
            setPagination((p) => ({ ...p, pageIndex: 0 }));
          }}
        />
        <HeatLegend basis="qualified players" note="PPG/RPG/APG shade above avg only" />
      </div>

      {/* ── Table ───────────────────────────────────────────────────────── */}
      <div className="overflow-x-auto border border-ui-border rounded-lg">
        <table className="w-full">
          <GroupedTableHead headerGroups={table.getHeaderGroups()} tone="ink" />
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="border-b border-ui-border hover:bg-ui-hover transition-colors">
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    className={clsx('py-2 text-sm', cellClass(cell.column), 'px-3')}
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
            ? noDataMessage(seasonType, seasonDisplay)
            : 'No players found. Try adjusting the filters.'}
        </div>
      )}

      {/* ── Pagination ────────────────────────────────────────────────────── */}
      {table.getPageCount() > 1 && (
        <div className="flex items-center justify-between text-sm text-text-muted">
          <span>
            Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount()}
            {' · '}
            {table.getFilteredRowModel().rows.length} players total
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => table.setPageIndex(0)}
              disabled={!table.getCanPreviousPage()}
              className="px-2 py-1 rounded border border-ui-border disabled:opacity-40 hover:bg-ui-hover"
            >
              «
            </button>
            <button
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
              className="px-3 py-1 rounded border border-ui-border disabled:opacity-40 hover:bg-ui-hover"
            >
              ‹ Prev
            </button>
            <button
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
              className="px-3 py-1 rounded border border-ui-border disabled:opacity-40 hover:bg-ui-hover"
            >
              Next ›
            </button>
            <button
              onClick={() => table.setPageIndex(table.getPageCount() - 1)}
              disabled={!table.getCanNextPage()}
              className="px-2 py-1 rounded border border-ui-border disabled:opacity-40 hover:bg-ui-hover"
            >
              »
            </button>
          </div>
        </div>
      )}

      <MetricDefinitionsCard
        definitions={activeTab === 'impact'
          ? nbaImpactDefinitions(wa_formula).filter((d) => d.k !== 'Role' || hasArchetype)
          : NBA_PLAYER_DEFINITIONS[activeTab]}
      />
    </div>
  );
}
