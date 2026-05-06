'use client';

import { useMemo, useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
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
import { computeRanks, getPercentileColor } from '@/lib/rankingUtils';
import {
  PLAYER_TRADITIONAL_METRICS,
  NCAA_IMPACT_METRICS,
  NCAA_FF_METRICS,
  formatPlayerMetric,
  type PlayerMetricMeta,
} from '@/lib/playerMetricMetadata';
import type { NCAAPlayerSeasonStats } from '@/types';

type TabId = 'traditional' | 'impact' | 'fourfactors';
type BprMode = 'strict_bpr' | 'full_two_sided' | 'all_players';

const PLAYER_SEASONS = [2020, 2021, 2022, 2023, 2024, 2025, 2026];

interface NCAAPlayerRankingsTableProps {
  data: NCAAPlayerSeasonStats[];
  seasonDisplay?: string;
  selectedSeason?: number;
}

// ── Traditional ───────────────────────────────────────────────────────────────
// Core visible columns
const TRAD_DEFAULT_KEYS = [
  'pts', 'reb', 'ast', 'stl', 'blk', 'tov', 'ts_pct', 'efg_pct', 'ast_to',
];
// User-toggleable optional extras
const TRAD_OPTIONAL_KEYS = [
  'fg3_pct', 'ft_pct', 'fga_pg', 'fg3a_pg', 'fta_pg', 'oreb_pg', 'dreb_pg',
];

// ── Impact ────────────────────────────────────────────────────────────────────
// Flat columns (BPR family + poss) — adj_team context rendered as a group
const IMPACT_METRIC_KEYS = [
  'bpr', 'obpr', 'dbpr', 'off_poss', 'box_bpr',
];
// These become the "On-Court Context" grouped columns in the Impact tab
const IMPACT_ADJ_CTX_KEYS = ['adj_team_off_eff_on', 'adj_team_def_eff_on'];

// ── Four Factors ──────────────────────────────────────────────────────────────
const FF_ALL_KEYS = [
  // New RAPM-based impact (primary)
  'four_factor_impact_index',
  'off_efg_impact', 'def_efg_impact',
  'off_tov_impact', 'def_tov_impact',
  'off_orb_impact', 'def_reb_impact',
  'off_ftr_impact', 'def_ftr_impact',
  'efg_impact_margin', 'tov_impact_margin', 'reb_impact_margin', 'ftr_impact_margin',
  // Old on-court lineup environment (context)
  'on_court_efg_pct', 'on_court_opp_efg_pct', 'on_court_efg_margin',
  'on_court_tov_pct', 'on_court_opp_tov_pct', 'on_court_tov_edge',
  'on_court_orb_pct', 'on_court_drb_pct', 'on_court_reb_edge',
  'on_court_ftr', 'on_court_opp_ftr', 'on_court_ftr_margin',
  'on_court_ffi',
];

const BPR_SOURCE_STYLES: Record<string, string> = {
  rapm:    'bg-brand/10 text-brand border-brand/20',
  box_bpr: 'bg-brand-orange/10 text-brand-orange border-brand-orange/20',
  mixed:   'bg-secondary/10 text-secondary border-secondary/20',
  partial: 'bg-ui-hover text-text-muted border-ui-border',
};

const PAGE_SIZE = 100;

export default function NCAAPlayerRankingsTable({ data, seasonDisplay, selectedSeason }: NCAAPlayerRankingsTableProps) {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<TabId>('impact');
  const [sorting, setSorting] = useState<SortingState>([{ id: 'bpr', desc: true }]);
  const [globalFilter, setGlobalFilter] = useState('');
  const [minMinutes, setMinMinutes] = useState(200);
  const [conferenceFilter, setConferenceFilter] = useState('all');
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: PAGE_SIZE });
  const [tradOptional, setTradOptional] = useState<Set<string>>(() => {
    try {
      const saved = localStorage.getItem('ncaa-player-trad-cols');
      return saved ? new Set(JSON.parse(saved) as string[]) : new Set();
    } catch { return new Set(); }
  });

  useEffect(() => {
    localStorage.setItem('ncaa-player-trad-cols', JSON.stringify([...tradOptional]));
  }, [tradOptional]);
  const [bprMode, setBprMode] = useState<BprMode>('strict_bpr');

  const tabs: Array<{ id: TabId; label: string }> = [
    { id: 'traditional',  label: 'Traditional'  },
    { id: 'impact',       label: 'Impact'        },
    { id: 'fourfactors',  label: 'Four Factors'  },
  ];

  const switchTab = (tab: TabId) => {
    setActiveTab(tab);
    setSorting([
      tab === 'impact'      ? { id: 'bpr',         desc: true } :
      tab === 'fourfactors' ? { id: 'four_factor_impact_index', desc: true } :
                               { id: 'pts',          desc: true },
    ]);
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  };

  // ── Conference list ───────────────────────────────────────────────────────
  const conferences = useMemo(() => {
    const seen = new Set<string>();
    data.forEach((p) => { if (p.conference_name) seen.add(p.conference_name); });
    return Array.from(seen).sort();
  }, [data]);

  // ── Filter ────────────────────────────────────────────────────────────────
  const filtered = useMemo(
    () =>
      data.filter((p) => {
        if (p.mpg * p.gp < minMinutes) return false;
        if (conferenceFilter !== 'all' && p.conference_name !== conferenceFilter) return false;
        // BPR mode gate (only applied on Impact tab)
        if (activeTab === 'impact') {
          if (bprMode === 'strict_bpr' && p.bpr_source !== 'rapm') return false;
          if (bprMode === 'full_two_sided' &&
              (p.obpr == null || p.dbpr == null || p.bpr_source === 'partial')) return false;
        }
        if (globalFilter) {
          const q = globalFilter.toLowerCase();
          return (
            p.player_name.toLowerCase().includes(q) ||
            p.team_name.toLowerCase().includes(q)
          );
        }
        return true;
      }),
    [data, minMinutes, conferenceFilter, globalFilter, activeTab, bprMode]
  );

  // ── Meta map ──────────────────────────────────────────────────────────────
  const allMetaMaps: Record<string, PlayerMetricMeta> = useMemo(() => {
    const map: Record<string, PlayerMetricMeta> = {};
    [...PLAYER_TRADITIONAL_METRICS, ...NCAA_IMPACT_METRICS, ...NCAA_FF_METRICS].forEach((m) => {
      map[m.key] = m;
    });
    return map;
  }, []);

  // ── Rank base: respects current tab's mode filter ─────────────────────────
  const rankBase = useMemo(() => {
    let base = data.filter((p) => p.mpg * p.gp >= minMinutes);
    if (activeTab === 'impact') {
      if (bprMode === 'strict_bpr')
        base = base.filter((p) => p.bpr_source === 'rapm');
      else if (bprMode === 'full_two_sided')
        base = base.filter(
          (p) => p.obpr != null && p.dbpr != null && p.bpr_source !== 'partial'
        );
    }
    return base;
  }, [data, minMinutes, activeTab, bprMode]);

  const activeTabKeys = useMemo(() => {
    if (activeTab === 'traditional') return [...TRAD_DEFAULT_KEYS, ...TRAD_OPTIONAL_KEYS];
    if (activeTab === 'fourfactors') return FF_ALL_KEYS;
    return [...IMPACT_METRIC_KEYS, ...IMPACT_ADJ_CTX_KEYS];
  }, [activeTab]);

  const metricRanks = useMemo(() => {
    const ranks = new Map<string, ReturnType<typeof computeRanks>>();
    activeTabKeys.forEach((key) => {
      const meta = allMetaMaps[key];
      if (!meta) return;
      const entries = rankBase.map((p) => ({
        id: p.player_id,
        value: (p as any)[key] as number | null,
      }));
      ranks.set(key, computeRanks(entries, meta.better));
    });
    // Computed: adj_team_net_on (off - def)
    if (activeTab === 'impact') {
      const entries = rankBase.map((p) => ({
        id: p.player_id,
        value:
          p.adj_team_off_eff_on != null && p.adj_team_def_eff_on != null
            ? p.adj_team_off_eff_on - p.adj_team_def_eff_on
            : null,
      }));
      ranks.set('adj_team_net_on', computeRanks(entries, 'higher'));
    }
    return ranks;
  }, [rankBase, allMetaMaps, activeTabKeys, activeTab]);

  // ── Column factory ────────────────────────────────────────────────────────
  const createMetricColumn = (key: string): ColumnDef<NCAAPlayerSeasonStats> => {
    const meta = allMetaMaps[key];
    if (!meta) return { id: key } as ColumnDef<NCAAPlayerSeasonStats>;
    return {
      accessorKey: key,
      header: () => (
        <HeaderWithTooltip label={meta.label} better={meta.better} tooltip={meta.tooltip} />
      ),
      cell: (info) => {
        const raw = info.getValue<number | null>();
        if (raw == null) return <span className="text-text-muted">—</span>;
        const rankData = metricRanks.get(key)?.get(info.row.original.player_id);
        const colorClass = meta.heatmap
          ? getPercentileColor(rankData?.percentile ?? null, meta.better, true)
          : '';
        return (
          <div className={clsx('flex items-center justify-between gap-1 px-2 py-1 rounded', colorClass)}>
            <span className="font-mono">{formatPlayerMetric(raw, meta.format)}</span>
          </div>
        );
      },
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
      cell: (info) => {
        const p = info.row.original;
        const rank = activeSortKey
          ? metricRanks.get(activeSortKey)?.get(p.player_id)?.rank
          : undefined;
        return (
          <span className="font-mono font-semibold text-sm text-text-muted">
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
      cell: (info) => {
        const p = info.row.original;
        return (
          <div className="flex items-center gap-2 min-w-0">
            {p.headshot_url && (
              <img
                src={p.headshot_url}
                alt={p.player_name}
                className="w-6 h-6 rounded-full object-cover shrink-0 bg-ui-surface"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
            )}
            <span className="font-medium text-sm truncate">{p.player_name}</span>
          </div>
        );
      },
      size: 170,
    };

    const teamCol: ColumnDef<NCAAPlayerSeasonStats> = {
      accessorKey: 'team_name',
      header: 'Team',
      cell: (info) => (
        <span className="text-xs text-text-muted truncate block max-w-[110px]">
          {info.getValue<string>() || '—'}
        </span>
      ),
      size: 120,
    };

    const posCol: ColumnDef<NCAAPlayerSeasonStats> = {
      accessorKey: 'position',
      header: 'Pos',
      cell: (info) => (
        <span className="text-xs text-text-muted uppercase">
          {info.getValue<string | null>() || '—'}
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

    const invisible = (id: string, cols: ColumnDef<NCAAPlayerSeasonStats>[]): ColumnDef<NCAAPlayerSeasonStats> => ({
      id,
      header: () => null,
      meta: { isInvisible: true },
      columns: cols,
    });

    // ── Traditional ──
    if (activeTab === 'traditional') {
      const visibleKeys = [
        ...TRAD_DEFAULT_KEYS,
        ...TRAD_OPTIONAL_KEYS.filter((k) => tradOptional.has(k)),
      ];
      return [...base, ...visibleKeys.map(createMetricColumn)];
    }

    // ── Impact ──
    if (activeTab === 'impact') {
      const adjNetSubCol: ColumnDef<NCAAPlayerSeasonStats> = {
        id: 'adj_team_net_on',
        header: () => (
          <HeaderWithTooltip
            label="Adj Net"
            better="higher"
            tooltip="Adjusted net efficiency (Off Eff − Def Eff) in pts/100 poss while this player is on court."
          />
        ),
        accessorFn: (row) =>
          row.adj_team_off_eff_on != null && row.adj_team_def_eff_on != null
            ? row.adj_team_off_eff_on - row.adj_team_def_eff_on
            : null,
        cell: (info) => {
          const val = info.getValue<number | null>();
          if (val == null) return <div className="text-center text-text-muted text-xs">—</div>;
          const rankData = metricRanks.get('adj_team_net_on')?.get(info.row.original.player_id);
          const colorClass = getPercentileColor(rankData?.percentile ?? null, 'higher', true);
          return (
            <div className={clsx('px-1 py-0.5 rounded text-center', colorClass)}>
              <div className="font-mono text-xs leading-tight">{val.toFixed(1)}</div>
            </div>
          );
        },
        sortDescFirst: true,
        size: 68,
      };

      const adjOffSubCol: ColumnDef<NCAAPlayerSeasonStats> = {
        accessorKey: 'adj_team_off_eff_on',
        header: () => (
          <HeaderWithTooltip
            label="Adj Off"
            better="higher"
            tooltip={allMetaMaps['adj_team_off_eff_on']?.tooltip ?? ''}
          />
        ),
        cell: (info) => {
          const val = info.getValue<number | null>();
          if (val == null) return <div className="text-center text-text-muted text-xs">—</div>;
          const rankData = metricRanks.get('adj_team_off_eff_on')?.get(info.row.original.player_id);
          const colorClass = getPercentileColor(rankData?.percentile ?? null, 'higher', true);
          return (
            <div className={clsx('px-1 py-0.5 rounded text-center', colorClass)}>
              <div className="font-mono text-xs leading-tight">{val.toFixed(1)}</div>
            </div>
          );
        },
        sortDescFirst: true,
        size: 68,
      };

      const adjDefSubCol: ColumnDef<NCAAPlayerSeasonStats> = {
        accessorKey: 'adj_team_def_eff_on',
        header: () => (
          <HeaderWithTooltip
            label="Adj Def"
            better="lower"
            tooltip={allMetaMaps['adj_team_def_eff_on']?.tooltip ?? ''}
          />
        ),
        cell: (info) => {
          const val = info.getValue<number | null>();
          if (val == null) return <div className="text-center text-text-muted text-xs">—</div>;
          const rankData = metricRanks.get('adj_team_def_eff_on')?.get(info.row.original.player_id);
          const colorClass = getPercentileColor(rankData?.percentile ?? null, 'lower', true);
          return (
            <div className={clsx('px-1 py-0.5 rounded text-center', colorClass)}>
              <div className="font-mono text-xs leading-tight">{val.toFixed(1)}</div>
            </div>
          );
        },
        sortDescFirst: false,
        size: 68,
      };

      const onCtxGroup: ColumnDef<NCAAPlayerSeasonStats> = {
        id: 'impact-adj-ctx',
        header: 'On-Court Context',
        columns: [adjOffSubCol, adjDefSubCol, adjNetSubCol],
      };

      const sourceCol: ColumnDef<NCAAPlayerSeasonStats> = {
        id: 'bpr_source',
        header: 'Source',
        accessorFn: (row) => row.bpr_source ?? '',
        cell: (info) => {
          const src = info.row.original.bpr_source;
          if (!src) return <span className="text-text-muted">—</span>;
          const label = src === 'box_bpr' ? 'box' : src;
          const cls = BPR_SOURCE_STYLES[src] ?? 'text-text-muted';
          return (
            <span className={clsx('text-[11px] font-mono px-1.5 py-0.5 rounded border', cls)}>
              {label}
            </span>
          );
        },
        enableSorting: false,
        size: 60,
      };

      return [
        invisible('impact-base', base),
        ...IMPACT_METRIC_KEYS.map(createMetricColumn),
        onCtxGroup,
        sourceCol,
      ];
    }

    // ── Four Factors — grouped columns matching team rankings design ────────
    const createSubColumn = ({ key, label }: { key: string; label: string }): ColumnDef<NCAAPlayerSeasonStats> => {
      const meta = allMetaMaps[key];
      if (!meta) return { id: key } as ColumnDef<NCAAPlayerSeasonStats>;
      return {
        accessorKey: key,
        header: () => (
          <HeaderWithTooltip label={label} better={meta.better} tooltip={meta.tooltip} />
        ),
        cell: (info) => {
          const raw = info.getValue<number | null>();
          const rankData = metricRanks.get(key)?.get(info.row.original.player_id);
          if (raw == null) return <div className="text-center text-text-muted text-xs">—</div>;
          const colorClass = meta.heatmap
            ? getPercentileColor(rankData?.percentile ?? null, meta.better, true)
            : '';
          return (
            <div className={clsx('px-1 py-0.5 rounded text-center', colorClass)}>
              <div className="font-mono text-xs leading-tight">
                {formatPlayerMetric(raw, meta.format)}
              </div>
            </div>
          );
        },
        size: 68,
        sortDescFirst: meta.better !== 'lower',
      };
    };

    const createGroup = (
      id: string,
      label: string,
      ...subs: Array<{ key: string; label: string }>
    ): ColumnDef<NCAAPlayerSeasonStats> => ({
      id,
      header: label,
      columns: subs.map(createSubColumn),
    });


    return [
      invisible('ff-base', base),
      createSubColumn({ key: 'four_factor_impact_index', label: 'FFII' }),
      createGroup('ff-impact-efg', 'eFG Impact',
        { key: 'off_efg_impact',    label: 'Off' },
        { key: 'def_efg_impact',    label: 'Def' },
        { key: 'efg_impact_margin', label: 'Total' },
      ),
      createGroup('ff-impact-tov', 'TOV Impact',
        { key: 'off_tov_impact',    label: 'Off' },
        { key: 'def_tov_impact',    label: 'Def' },
        { key: 'tov_impact_margin', label: 'Total' },
      ),
      createGroup('ff-impact-reb', 'Rebound Impact',
        { key: 'off_orb_impact',    label: 'Off' },
        { key: 'def_reb_impact',    label: 'Def' },
        { key: 'reb_impact_margin', label: 'Total' },
      ),
      createGroup('ff-impact-ftr', 'FTR Impact',
        { key: 'off_ftr_impact',    label: 'Off' },
        { key: 'def_ftr_impact',    label: 'Def' },
        { key: 'ftr_impact_margin', label: 'Total' },
      ),
      createGroup('ff-lineup-efg', 'On-Court eFG%',
        { key: 'on_court_efg_pct',     label: 'Off'    },
        { key: 'on_court_opp_efg_pct', label: 'Def'    },
        { key: 'on_court_efg_margin',  label: 'Margin' },
      ),
      createGroup('ff-lineup-tov', 'On-Court TOV%',
        { key: 'on_court_tov_pct',     label: 'Off'  },
        { key: 'on_court_opp_tov_pct', label: 'Def'  },
        { key: 'on_court_tov_edge',    label: 'Edge' },
      ),
      createGroup('ff-lineup-reb', 'On-Court Reb%',
        { key: 'on_court_orb_pct',  label: 'ORB'  },
        { key: 'on_court_drb_pct',  label: 'DRB'  },
        { key: 'on_court_reb_edge', label: 'Edge' },
      ),
      createGroup('ff-lineup-ftr', 'On-Court FTR',
        { key: 'on_court_ftr',        label: 'Off'    },
        { key: 'on_court_opp_ftr',    label: 'Def'    },
        { key: 'on_court_ftr_margin', label: 'Margin' },
      ),
      createSubColumn({ key: 'on_court_ffi', label: 'On-Ct FFI' }),
    ];
  }, [activeTab, metricRanks, pagination.pageIndex, sorting, tradOptional, allMetaMaps]);

  // ── Table ─────────────────────────────────────────────────────────────────
  const table = useReactTable({
    data: filtered,
    columns,
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

  const isGroupedTab = activeTab === 'fourfactors' || activeTab === 'impact';

  return (
    <div className="space-y-4">
      {/* ── Filter bar ──────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="flex-1 min-w-[180px]">
          <input
            type="text"
            value={globalFilter}
            onChange={(e) => {
              setGlobalFilter(e.target.value);
              setPagination((p) => ({ ...p, pageIndex: 0 }));
            }}
            placeholder="Search players or teams..."
            className="w-full px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm
                       focus:outline-none focus:ring-2 focus:ring-brand/50"
          />
        </div>
        <div>
          <select
            value={minMinutes}
            onChange={(e) => {
              setMinMinutes(Number(e.target.value));
              setPagination((p) => ({ ...p, pageIndex: 0 }));
            }}
            className="px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm
                       focus:outline-none focus:ring-2 focus:ring-brand/50"
          >
            {[50, 100, 200, 300, 400, 600].map((n) => (
              <option key={n} value={n}>
                Min {n} min
              </option>
            ))}
          </select>
        </div>
        <div>
          <select
            value={conferenceFilter}
            onChange={(e) => {
              setConferenceFilter(e.target.value);
              setPagination((p) => ({ ...p, pageIndex: 0 }));
            }}
            className="px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm
                       focus:outline-none focus:ring-2 focus:ring-brand/50"
          >
            <option value="all">All Conferences</option>
            {conferences.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
        <div>
          <select
            value={selectedSeason ?? ''}
            onChange={(e) => {
              const val = e.target.value;
              router.push(val ? `/ncaa/rankings?tab=players&season=${val}` : '/ncaa/rankings?tab=players');
            }}
            className="px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm
                       focus:outline-none focus:ring-2 focus:ring-brand/50"
          >
            <option value="">All Seasons</option>
            {PLAYER_SEASONS.map((yr) => (
              <option key={yr} value={yr}>
                {yr - 1}–{String(yr).slice(2)}
              </option>
            ))}
          </select>
        </div>
        <div className="text-sm text-text-muted whitespace-nowrap">
          {table.getFilteredRowModel().rows.length} players
          {seasonDisplay && <span className="ml-1">· {seasonDisplay}</span>}
        </div>
      </div>

      {/* ── Tabs ────────────────────────────────────────────────────────────── */}
      <div className="border-b border-ui-border">
        <div className="flex space-x-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => switchTab(tab.id)}
              className={clsx(
                'px-4 py-2 text-sm font-medium transition-colors relative',
                activeTab === tab.id
                  ? 'text-brand border-b-2 border-brand'
                  : 'text-text-muted hover:text-text-primary',
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Tab sub-controls ────────────────────────────────────────────────── */}
      {activeTab === 'traditional' && (
        <div className="flex flex-wrap gap-2 items-center">
          <span className="text-xs text-text-muted font-medium">Show:</span>
          {TRAD_OPTIONAL_KEYS.map((key) => {
            const meta = allMetaMaps[key];
            if (!meta) return null;
            const on = tradOptional.has(key);
            return (
              <button
                key={key}
                onClick={() => {
                  setTradOptional((prev) => {
                    const next = new Set(prev);
                    if (next.has(key)) next.delete(key); else next.add(key);
                    return next;
                  });
                }}
                className={clsx(
                  'px-2.5 py-1 text-xs rounded border transition-colors',
                  on
                    ? 'bg-brand/10 text-brand border-brand/30 font-medium'
                    : 'bg-ui-surface text-text-muted border-ui-border hover:border-brand/30',
                )}
              >
                {meta.label}
              </button>
            );
          })}
        </div>
      )}

      {activeTab === 'impact' && (
        <div className="flex flex-wrap gap-2 items-center">
          <span className="text-xs text-text-muted font-medium">Rankings:</span>
          {(
            [
              { id: 'strict_bpr',    label: 'Strict BPR',     title: 'Only players with full RAPM on both sides' },
              { id: 'full_two_sided', label: 'Full Two-Sided', title: 'Both OBPR and DBPR present (RAPM or box)' },
              { id: 'all_players',   label: 'All Players',    title: 'Include box-only and partial fallbacks' },
            ] as const
          ).map(({ id, label, title }) => (
            <button
              key={id}
              title={title}
              onClick={() => {
                setBprMode(id);
                setPagination((p) => ({ ...p, pageIndex: 0 }));
              }}
              className={clsx(
                'px-3 py-1 text-xs rounded border transition-colors',
                bprMode === id
                  ? 'bg-brand/10 text-brand border-brand/30 font-medium'
                  : 'bg-ui-surface text-text-muted border-ui-border hover:border-brand/30',
              )}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {/* ── Table ───────────────────────────────────────────────────────────── */}
      <div className="overflow-x-auto border border-ui-border rounded-lg">
        <table className="w-full">
          <thead>
            {table.getHeaderGroups().map((headerGroup, groupIdx) => (
              <tr
                key={headerGroup.id}
                className={clsx(
                  'border-b border-ui-border',
                  isGroupedTab && groupIdx === 0 ? 'bg-ui-hover' : 'bg-ui-surface',
                )}
              >
                {headerGroup.headers.map((header) => {
                  if (header.isPlaceholder) return null;
                  const isInvisibleGroup = !!(header.column.columnDef.meta as any)?.isInvisible;
                  const isLabeledGroup = header.colSpan > 1 && !isInvisibleGroup;
                  const isLeaf = header.colSpan === 1;
                  return (
                    <th
                      key={header.id}
                      colSpan={header.colSpan}
                      className={clsx(
                        'px-2 py-2 text-xs font-semibold text-text-secondary uppercase tracking-wider align-middle',
                        isLabeledGroup && 'text-center border-x border-ui-border/50',
                        isLeaf && 'text-left',
                        isLeaf && header.column.getCanSort() && 'cursor-pointer select-none hover:bg-ui-hover',
                      )}
                      onClick={isLeaf ? header.column.getToggleSortingHandler() : undefined}
                      style={isLeaf ? { width: header.column.getSize() } : undefined}
                    >
                      {isInvisibleGroup ? null : (
                        <div className={clsx('flex items-center gap-1', isLabeledGroup && 'justify-center')}>
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {isLeaf && header.column.getIsSorted() && (
                            <span className="text-brand">
                              {header.column.getIsSorted() === 'desc' ? '↓' : '↑'}
                            </span>
                          )}
                        </div>
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                className="border-b border-ui-border hover:bg-ui-hover transition-colors"
              >
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    className={clsx('py-2 text-sm', isGroupedTab ? 'px-1' : 'px-2')}
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
    </div>
  );
}
