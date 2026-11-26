'use client';

import { useMemo, useState, useEffect } from 'react';
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
import HeaderWithTooltip from './HeaderWithTooltip';
import GroupedTableHead, { cellClass, withMeta } from './table/GroupedTableHead';
import TableTabs from './table/TableTabs';
import MetricValue from './table/MetricValue';
import MetricDefinitionsCard, { type MetricDefinition } from './MetricDefinitionsCard';
import { computeRanks, heatStyleFromPercentile } from '@macfax/core/lib/rankingUtils';
import { AUTO_THRESHOLD, autoNcaaMinMinutes } from '@macfax/core/lib/playerThresholds';
import {
  PLAYER_TRADITIONAL_METRICS,
  NCAA_IMPACT_METRICS,
  NCAA_FF_METRICS,
  NCAA_ADVANCED_METRICS,
  formatPlayerMetric,
  meetsAttemptFloor,
  type PlayerMetricMeta,
} from '@macfax/core/lib/playerMetricMetadata';
import type { NCAAPlayerSeasonStats, SeasonInfo } from '@macfax/core/types';
import { FEATURES } from '@macfax/core/config/features';
import { withNullsLast } from '@/lib/nullsLast';
import { ncaaTeamHref } from '@/lib/teamLinks';
import { pickCurrentSeason } from '@macfax/core/lib/season';
import HeatLegend from './HeatLegend';

type TabId = 'traditional' | 'impact' | 'advanced' | 'fourfactors';

const BOX_ESTIMATE_NOTE = 'Box-score estimate (all or part) — not enough lineup data yet';

// W.Add lives on the row (from PlayerMarketValue) but not in playerMetricMetadata — add inline
const WINS_ADDED_META: PlayerMetricMeta = {
  key: 'wins_added', label: 'W.Add',
  tooltip: 'Wins Added to date above replacement: season marginal wins × GP / 30.',
  format: 'signed1', better: 'higher', showRank: true, heatmap: true, tier: 'primary',
};

const PLAYER_METRIC_DEFINITIONS: Record<TabId, MetricDefinition[]> = {
  impact: [
    { k: 'BPR', v: 'Bayesian Performance Rating (OBPR + DBPR): estimated total player impact in points per 100 possessions above an average D-I player.' },
    { k: 'OBPR', v: 'Offensive BPR: estimated offensive points per 100 possessions added relative to an average D-I player.' },
    { k: 'DBPR', v: 'Defensive BPR: estimated defensive points per 100 possessions prevented relative to an average D-I player; higher is better.' },
    { k: 'W.Add', v: 'Wins Added to date above a replacement-level player: the season marginal-wins rate from BPR and minutes, times games played / 30.' },
    { k: 'Poss', v: 'Offensive possessions played from lineup segments; used to qualify and stabilize player impact ratings.' },
    { k: 'Box-score estimates', v: 'Off by default, so the table lists only players rated from lineup data (RAPM). Turn it on to include players whose BPR is a box-score estimate in whole or in part; their BPR and W.Add are marked †. Players with no BPR are never listed here.' },
  ],
  traditional: [
    { k: 'GP', v: 'Games played.' },
    { k: 'MPG', v: 'Minutes per game; the minutes filter uses total minutes played.' },
    { k: 'BPR', v: 'Bayesian Performance Rating, shown for reference; see the Impact tab. † marks a box-score estimate.' },
    { k: 'PPG', v: 'Points per game.' },
    { k: 'RPG', v: 'Total rebounds per game.' },
    { k: 'APG', v: 'Assists per game.' },
    { k: 'SPG', v: 'Steals per game.' },
    { k: 'BPG', v: 'Blocks per game.' },
    { k: 'TOV', v: 'Turnovers per game; lower is better.' },
    { k: 'FG%', v: 'Field goal percentage.' },
    { k: '3P%', v: 'Three-point percentage; shaded only at 1 or more three-point attempts per game.' },
    { k: 'FT%', v: 'Free throw percentage; shaded only at 1 or more free throw attempts per game.' },
    { k: 'TS%', v: 'True Shooting %: scoring efficiency that accounts for twos, threes, and free throws.' },
  ],
  advanced: [
    { k: 'BPR', v: 'Bayesian Performance Rating, shown for reference; see the Impact tab. † marks a box-score estimate.' },
    { k: 'USG%', v: 'Usage rate: share of team plays the player uses (shots, free throws, turnovers) while on the floor.' },
    { k: 'TS%', v: 'True Shooting %: scoring efficiency that accounts for twos, threes, and free throws.' },
    { k: 'TOV%', v: 'Turnover rate: turnovers per 100 plays used; lower is better.' },
    { k: 'ORB%', v: 'Offensive rebound rate: share of available offensive rebounds grabbed while on court.' },
    { k: 'DRB%', v: 'Defensive rebound rate: share of available defensive rebounds grabbed while on court.' },
    { k: 'STL%', v: 'Steal rate: steals per 100 opponent possessions while on court.' },
    { k: 'BLK%', v: 'Block rate: share of opponent two-point attempts blocked while on court.' },
  ],
  fourfactors: [
    { k: 'BPR', v: 'Bayesian Performance Rating, shown for reference; see the Impact tab. † marks a box-score estimate.' },
    { k: 'FFII', v: 'Four Factor Impact Index: 0-100 RAPM-based estimate of how much a player moves shooting, turnovers, rebounding, and free throw rate.' },
    { k: 'Off', v: 'Estimated player effect on the team factor while on offense; positive is better.' },
    { k: 'Def', v: 'Estimated player effect on the opponent factor while defending; positive is better.' },
    { k: 'Total', v: 'Two-way factor impact: offensive impact plus defensive impact.' },
    { k: 'eFG Impact', v: 'Estimated effect on team shot efficiency and opponent shot efficiency.' },
    { k: 'TOV Impact', v: 'Estimated effect on reducing team turnovers and forcing opponent turnovers.' },
    { k: 'Rebound Impact', v: 'Estimated effect on team offensive rebounding and limiting opponent offensive rebounds.' },
    { k: 'FTR Impact', v: 'Estimated effect on getting to the line and limiting opponent free throws.' },
  ],
};

// First season with player-level data; later seasons come from /seasons/ so a new season needs no edit here.
const PLAYER_FIRST_SEASON = 2020;

interface NCAAPlayerRankingsTableProps {
  data: NCAAPlayerSeasonStats[];
  selectedSeason?: number;
  /** Seasons from the API (`getAllSeasons`); the dropdown lists those with player data. */
  seasons?: SeasonInfo[];
}

// ── Column sets ───────────────────────────────────────────────────────────────
const IMPACT_KEYS = ['bpr', 'obpr', 'dbpr', 'wins_added', 'off_poss'];
const TRAD_KEYS = ['pts', 'reb', 'ast', 'stl', 'blk', 'tov', 'fg_pct', 'fg3_pct', 'ft_pct', 'ts_pct'];
const ADV_KEYS = ['usg_pct', 'ts_pct', 'tov_pct', 'orb_pct', 'drb_pct', 'stl_pct', 'blk_pct'];
const FF_GROUPS: Array<{ id: string; label: string; keys: [string, string, string] }> = [
  { id: 'ff-impact-efg', label: 'eFG Impact',     keys: ['off_efg_impact', 'def_efg_impact', 'efg_impact_margin'] },
  { id: 'ff-impact-tov', label: 'TOV Impact',     keys: ['off_tov_impact', 'def_tov_impact', 'tov_impact_margin'] },
  { id: 'ff-impact-reb', label: 'Rebound Impact', keys: ['off_orb_impact', 'def_reb_impact', 'reb_impact_margin'] },
  { id: 'ff-impact-ftr', label: 'FTR Impact',     keys: ['off_ftr_impact', 'def_ftr_impact', 'ftr_impact_margin'] },
];
const FF_KEYS = ['four_factor_impact_index', ...FF_GROUPS.flatMap((g) => g.keys)];

const TAB_DEFAULT_SORT: Record<TabId, SortingState> = {
  impact:      [{ id: 'bpr', desc: true }],
  traditional: [{ id: 'pts', desc: true }],
  advanced:    [{ id: 'ts_pct', desc: true }],
  fourfactors: [{ id: 'four_factor_impact_index', desc: true }],
};

// Position filter: PG/SG count as guards, SF/PF as forwards (the last letter)
const POSITIONS: Array<{ id: string; label: string }> = [
  { id: 'all', label: 'All Positions' },
  { id: 'G', label: 'Guards' },
  { id: 'F', label: 'Forwards' },
  { id: 'C', label: 'Centers' },
];

/** BPR from lineup data (RAPM); anything else is a box-score or partial fallback. */
const isLineupBpr = (p: NCAAPlayerSeasonStats) => p.bpr_source === 'rapm';

const PAGE_SIZE = 100;

export default function NCAAPlayerRankingsTable({ data, selectedSeason, seasons = [] }: NCAAPlayerRankingsTableProps) {
  const router = useRouter();
  // Team-table labels and order (newest first), limited to seasons with player data
  const playerSeasons = useMemo(
    () => seasons.filter((x) => x.year >= PLAYER_FIRST_SEASON).sort((a, b) => b.year - a.year),
    [seasons],
  );
  // Team links keep a past season (?season=); current season links stay plain
  const currentSeason = pickCurrentSeason(seasons)?.year ?? null;
  // No season in the URL means the API's current season
  const seasonValue = selectedSeason ?? seasons.find((x) => x.is_current)?.year ?? '';
  // Early in a season BPR isn't computed yet; open on Traditional so the table isn't empty
  const hasBpr = useMemo(() => data.some((p) => p.bpr != null), [data]);
  // Advanced rates and W.Add are filled by later pipeline steps; hide them for seasons without
  const hasAdvanced = useMemo(() => data.some((p) => p.usg_pct != null), [data]);
  // W.Add column: behind a flag (off by default) and only for seasons with values
  const hasWinsAdded = useMemo(
    () => FEATURES.ncaaPlayerWinsAdded && data.some((p) => p.wins_added != null),
    [data],
  );
  const [activeTab, setActiveTab] = useState<TabId>(hasBpr ? 'impact' : 'traditional');
  const [sorting, setSorting] = useState<SortingState>(TAB_DEFAULT_SORT[hasBpr ? 'impact' : 'traditional']);
  const [globalFilter, setGlobalFilter] = useState('');
  // Default "Auto" scales with games played (see playerThresholds.ts)
  const [minMinutesChoice, setMinMinutesChoice] = useState<number>(AUTO_THRESHOLD);
  const autoMinMinutes = useMemo(() => autoNcaaMinMinutes(data), [data]);
  const minMinutes = minMinutesChoice === AUTO_THRESHOLD ? autoMinMinutes : minMinutesChoice;
  const [conferenceFilter, setConferenceFilter] = useState('all');
  const [positionFilter, setPositionFilter] = useState('all');
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: PAGE_SIZE });
  // Off = lineup-based (RAPM) BPR only; on = also box-score and partial estimates
  const [includeBoxEstimates, setIncludeBoxEstimates] = useState(false);

  const tabs: Array<{ id: TabId; label: string }> = [
    { id: 'impact',       label: 'Impact'       },
    { id: 'traditional',  label: 'Traditional'  },
    ...(hasAdvanced ? [{ id: 'advanced' as TabId, label: 'Advanced' }] : []),
    { id: 'fourfactors',  label: 'Four Factors' },
  ];

  const switchTab = (tab: TabId) => {
    setActiveTab(tab);
    setSorting(TAB_DEFAULT_SORT[tab]);
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  };

  // Switching to a season with no BPR yet: leave the (empty) Impact tab
  useEffect(() => {
    if (!hasBpr && activeTab === 'impact') switchTab('traditional');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasBpr]);

  // Same for a season with no advanced rates yet
  useEffect(() => {
    if (!hasAdvanced && activeTab === 'advanced') switchTab('traditional');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasAdvanced]);

  // ── Conference list ───────────────────────────────────────────────────────
  const conferences = useMemo(() => {
    const seen = new Set<string>();
    data.forEach((p) => { if (p.conference_name) seen.add(p.conference_name); });
    return Array.from(seen).sort();
  }, [data]);

  // ── Qualified pool: minutes floor, plus the box-estimate gate on Impact ───
  // Also the rank and heat base, so colors compare like with like.
  const rankBase = useMemo(() => {
    const base = data.filter((p) => p.mpg * p.gp >= minMinutes);
    if (activeTab !== 'impact') return base;
    // Off: lineup-rated (RAPM) BPR only. On: any BPR, box estimates included; never rows with no BPR.
    return base.filter(includeBoxEstimates ? (p) => p.bpr != null : isLineupBpr);
  }, [data, minMinutes, activeTab, includeBoxEstimates]);

  // ── Filter ────────────────────────────────────────────────────────────────
  const filtered = useMemo(() => {
    const q = globalFilter.toLowerCase();
    return rankBase.filter((p) => {
      if (conferenceFilter !== 'all' && p.conference_name !== conferenceFilter) return false;
      if (positionFilter !== 'all' && !(p.position ?? '').toUpperCase().endsWith(positionFilter)) return false;
      if (q) return p.player_name.toLowerCase().includes(q) || p.team_name.toLowerCase().includes(q);
      return true;
    });
  }, [rankBase, conferenceFilter, positionFilter, globalFilter]);

  // ── Meta map ──────────────────────────────────────────────────────────────
  const allMetaMaps: Record<string, PlayerMetricMeta> = useMemo(() => {
    const map: Record<string, PlayerMetricMeta> = {};
    [...PLAYER_TRADITIONAL_METRICS, ...NCAA_IMPACT_METRICS, ...NCAA_FF_METRICS, ...NCAA_ADVANCED_METRICS, WINS_ADDED_META].forEach((m) => {
      map[m.key] = m;
    });
    return map;
  }, []);

  const activeTabKeys = useMemo(() => {
    if (activeTab === 'traditional') return ['bpr', ...TRAD_KEYS];
    if (activeTab === 'advanced') return ['bpr', ...ADV_KEYS];
    if (activeTab === 'fourfactors') return ['bpr', ...FF_KEYS];
    return IMPACT_KEYS;
  }, [activeTab]);

  const metricRanks = useMemo(() => {
    const ranks = new Map<string, ReturnType<typeof computeRanks>>();
    activeTabKeys.forEach((key) => {
      const meta = allMetaMaps[key];
      if (!meta) return;
      // Below an attempt floor a shooting % is left out of the ranks (and so of the heat)
      const entries = rankBase.map((p) => ({
        id: p.player_id,
        value: meetsAttemptFloor(p, key) ? ((p as unknown as Record<string, number | null>)[key] ?? null) : null,
      }));
      ranks.set(key, computeRanks(entries, meta.better));
    });
    return ranks;
  }, [rankBase, allMetaMaps, activeTabKeys]);

  // ── Column factory ────────────────────────────────────────────────────────
  const createMetricColumn = (key: string, variant: 'full' | 'compact' = 'full', label?: string): ColumnDef<NCAAPlayerSeasonStats> => {
    const meta = allMetaMaps[key];
    if (!meta) return { id: key } as ColumnDef<NCAAPlayerSeasonStats>;
    return {
      accessorKey: key,
      header: () => (
        <HeaderWithTooltip label={label ?? meta.label} better={meta.better} tooltip={meta.tooltip} />
      ),
      cell: (info) => {
        const p = info.row.original;
        const raw = info.getValue<number | null>();
        const graded = meetsAttemptFloor(p, key);
        const rankData = graded ? metricRanks.get(key)?.get(p.player_id) : undefined;
        const hs = raw != null && graded && meta.heatmap ? heatStyleFromPercentile(rankData?.percentile ?? null, meta.better) : {};
        // BPR (and W.Add, built from it) that isn't from lineup data gets a †
        const marker = (key === 'bpr' || key === 'wins_added') && raw != null && !isLineupBpr(p)
          ? <span title={BOX_ESTIMATE_NOTE} aria-label={BOX_ESTIMATE_NOTE} className="ml-0.5 font-sans text-[10px] text-muted cursor-help">†</span>
          : undefined;
        return (
          <MetricValue
            text={raw == null ? null : formatPlayerMetric(raw, meta.format)}
            heat={hs}
            rank={rankData?.rank}
            showRank={graded && meta.showRank}
            column={info.column}
            variant={variant}
            marker={marker}
          />
        );
      },
      size: variant === 'compact' ? 68 : 78,
      sortDescFirst: meta.better !== 'lower',
    };
  };

  // ── Columns ───────────────────────────────────────────────────────────────
  const columns = useMemo((): ColumnDef<NCAAPlayerSeasonStats>[] => {
    const pageOffset = pagination.pageIndex * PAGE_SIZE;
    const activeSortKey = sorting[0]?.id;

    const rankCol: ColumnDef<NCAAPlayerSeasonStats> = {
      id: 'rank',
      header: 'Rk',
      meta: { align: 'left' },
      cell: (info) => {
        const p = info.row.original;
        const rank = activeSortKey
          ? metricRanks.get(activeSortKey)?.get(p.player_id)?.rank
          : undefined;
        return (
          <span className="font-mono font-semibold">
            {rank ?? pageOffset + info.row.index + 1}
          </span>
        );
      },
      enableSorting: false,
      size: 44,
    };

    const playerCol: ColumnDef<NCAAPlayerSeasonStats> = {
      accessorKey: 'player_name',
      header: 'Player',
      meta: { align: 'left' },
      cell: (info) => {
        const p = info.row.original;
        return (
          <div className="flex items-center gap-2 min-w-0 max-w-[190px]">
            {p.headshot_url && (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img
                src={p.headshot_url}
                alt={p.player_name}
                className="w-6 h-6 rounded-full object-cover shrink-0 bg-ui-surface"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
            )}
            <span className="font-medium text-sm truncate" title={p.player_name}>{p.player_name}</span>
          </div>
        );
      },
      size: 170,
    };

    // Compact team cell from the team table: logo + name, linking to the team page
    const teamCol: ColumnDef<NCAAPlayerSeasonStats> = {
      accessorKey: 'team_name',
      header: 'Team',
      meta: { align: 'left' },
      cell: (info) => {
        const p = info.row.original;
        if (!p.team_name) return <span className="text-text-muted">-</span>;
        const inner = (
          <>
            {p.team_logo ? (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img
                src={p.team_logo}
                alt={p.team_name}
                className="w-5 h-5 object-contain shrink-0"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
            ) : (
              <div className="w-5 h-5 shrink-0 bg-ui-surface rounded-full flex items-center justify-center text-xs font-bold text-text-muted">
                {p.team_name.charAt(0)}
              </div>
            )}
            <span className="font-medium text-sm truncate" title={p.team_name}>{p.team_name}</span>
          </>
        );
        return p.team_slug ? (
          <Link
            href={ncaaTeamHref(p.team_slug, selectedSeason, currentSeason)}
            className="flex items-center space-x-2 min-w-0 max-w-[170px] hover:text-brand transition-colors"
          >
            {inner}
          </Link>
        ) : (
          <div className="flex items-center space-x-2 min-w-0 max-w-[170px]">{inner}</div>
        );
      },
      size: 170,
    };

    const posCol: ColumnDef<NCAAPlayerSeasonStats> = {
      accessorKey: 'position',
      header: 'Pos',
      cell: (info) => (
        <span className="text-xs text-text-muted uppercase">
          {info.getValue<string | null>() || '-'}
        </span>
      ),
      enableSorting: false,
      size: 42,
    };

    const gpCol: ColumnDef<NCAAPlayerSeasonStats> = {
      accessorKey: 'gp',
      header: 'GP',
      cell: (info) => <span className="font-mono text-sm">{info.getValue<number>()}</span>,
      size: 44,
    };

    const mpgCol: ColumnDef<NCAAPlayerSeasonStats> = {
      accessorKey: 'mpg',
      header: 'MPG',
      cell: (info) => (
        <span className="font-mono text-sm">{(info.getValue<number>() ?? 0).toFixed(1)}</span>
      ),
      size: 50,
      sortDescFirst: true,
    };

    const base = [rankCol, playerCol, teamCol, posCol, gpCol, mpgCol];
    // BPR pinned right after MPG on the other tabs, when the season has it
    const pinnedBpr = hasBpr ? [withMeta(createMetricColumn('bpr'), { divider: true })] : [];

    // ── Impact: BPR is the hero (first metric, larger value, widest column) ──
    if (activeTab === 'impact') {
      return [
        ...base,
        { ...withMeta(createMetricColumn('bpr'), { emphasis: true, hero: true }), size: 120 },
        createMetricColumn('obpr'),
        createMetricColumn('dbpr'),
        ...(hasWinsAdded ? [createMetricColumn('wins_added')] : []),
        createMetricColumn('off_poss'),
      ];
    }

    // ── Traditional / Advanced ──
    if (activeTab === 'traditional' || activeTab === 'advanced') {
      const keys = activeTab === 'traditional' ? TRAD_KEYS : ADV_KEYS;
      return [...base, ...pinnedBpr, ...keys.map((k, i) => (i === 0 ? withMeta(createMetricColumn(k), { divider: true }) : createMetricColumn(k)))];
    }

    // ── Four Factors: FFII + the four Off / Def / Total impact groups ──
    return [
      ...base,
      ...pinnedBpr,
      withMeta(createMetricColumn('four_factor_impact_index', 'compact', 'FFII'), { emphasis: true }),
      ...FF_GROUPS.map((g): ColumnDef<NCAAPlayerSeasonStats> => ({
        id: g.id,
        header: g.label,
        columns: g.keys.map((k, i) =>
          withMeta(createMetricColumn(k, 'compact', ['Off', 'Def', 'Total'][i]), { divider: i === 0, net: i === 2 }),
        ),
      })),
    ];
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, metricRanks, pagination.pageIndex, sorting, allMetaMaps, hasBpr, hasWinsAdded, selectedSeason, currentSeason]);

  // ── Table ─────────────────────────────────────────────────────────────────
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
    onGlobalFilterChange: setGlobalFilter,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  const isGroupedTab = activeTab === 'fourfactors';

  return (
    <div className="space-y-4">
      {/* ── Filter bar (team-table order) ──────────────────────────────────── */}
      <div className="flex flex-wrap gap-4 items-center">
        {playerSeasons.length > 1 && (
          <div>
            <select
              value={seasonValue}
              onChange={(e) => {
                const val = e.target.value;
                router.push(val ? `/ncaa/players?season=${val}` : '/ncaa/players');
              }}
              className="px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/50 font-medium"
            >
              {playerSeasons.map((x) => (
                <option key={x.year} value={x.year}>
                  {x.display_name}{x.is_current ? ' (Current)' : ''}
                </option>
              ))}
            </select>
          </div>
        )}
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
        <div>
          <select
            value={conferenceFilter}
            onChange={(e) => {
              setConferenceFilter(e.target.value);
              setPagination((p) => ({ ...p, pageIndex: 0 }));
            }}
            className="px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/50"
          >
            <option value="all">All Conferences</option>
            {conferences.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
        <div>
          <select
            value={positionFilter}
            onChange={(e) => {
              setPositionFilter(e.target.value);
              setPagination((p) => ({ ...p, pageIndex: 0 }));
            }}
            className="px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/50"
          >
            {POSITIONS.map((x) => (
              <option key={x.id} value={x.id}>{x.label}</option>
            ))}
          </select>
        </div>
        <div>
          <select
            value={minMinutesChoice}
            onChange={(e) => {
              setMinMinutesChoice(Number(e.target.value));
              setPagination((p) => ({ ...p, pageIndex: 0 }));
            }}
            className="px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/50"
          >
            <option value={AUTO_THRESHOLD}>Auto · min {autoMinMinutes} min</option>
            {[10, 25, 50, 100, 200, 300, 400, 600].map((n) => (
              <option key={n} value={n}>
                Min {n} min
              </option>
            ))}
          </select>
        </div>
        <div className="text-sm text-text-muted">
          Showing {table.getFilteredRowModel().rows.length} players
        </div>
      </div>

      {/* ── Tabs ────────────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <TableTabs tabs={tabs} active={activeTab} onChange={switchTab} />
        <HeatLegend basis="qualified players" note="PPG/RPG/APG shade above avg only" />
      </div>

      {/* ── Impact: box-score estimates toggle ─────────────────────────────── */}
      {activeTab === 'impact' && (
        <label className="inline-flex items-center gap-2 text-sm text-text-muted cursor-pointer select-none">
          <input
            type="checkbox"
            checked={includeBoxEstimates}
            onChange={(e) => {
              setIncludeBoxEstimates(e.target.checked);
              setPagination((p) => ({ ...p, pageIndex: 0 }));
            }}
            className="h-4 w-4 rounded border-ui-border accent-ink"
          />
          Include box-score-only estimates
        </label>
      )}

      {/* ── Table ───────────────────────────────────────────────────────────── */}
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
          No players found. Try adjusting the filters.
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
        definitions={PLAYER_METRIC_DEFINITIONS[activeTab].filter(
          (d) => (hasBpr || d.k !== 'BPR') && (hasWinsAdded || d.k !== 'W.Add'),
        )}
      />
    </div>
  );
}
