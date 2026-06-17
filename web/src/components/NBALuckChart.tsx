'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  Customized,
} from 'recharts';
import clsx from 'clsx';
import type { NBALuckChartData, NBALuckChartTeam } from '@/types/nba';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const QUADRANT_LABELS: Record<NBALuckChartTeam['quadrant'], string> = {
  hot:           'Running Hot',
  overachieving: 'Overachieving',
  hidden_value:  'Hidden Value',
  struggling:    'Struggling',
};

// ---------------------------------------------------------------------------
// Custom dot — team logo as SVG image
// ---------------------------------------------------------------------------

function LogoDot(props: any) {
  const { cx, cy, payload } = props;
  if (cx == null || cy == null) return null;
  const size = 26;
  if (payload?.logo_url) {
    return (
      <image
        href={payload.logo_url}
        x={cx - size / 2}
        y={cy - size / 2}
        width={size}
        height={size}
        opacity={0.92}
        style={{ cursor: 'pointer' }}
      />
    );
  }
  return <circle cx={cx} cy={cy} r={6} fill="var(--brand)" opacity={0.85} />;
}

// ---------------------------------------------------------------------------
// Custom tooltip
// ---------------------------------------------------------------------------

function LuckTooltip({ active, payload }: { active?: boolean; payload?: any[] }) {
  if (!active || !payload?.length) return null;
  const t: NBALuckChartTeam = payload[0].payload;
  const wae = t.wins_above_expected;
  const waeStr = (wae >= 0 ? '+' : '') + wae.toFixed(1);
  return (
    <div className="bg-ink border border-ink-line rounded-lg px-4 py-3 text-sm text-white shadow-lg min-w-[200px]">
      <div className="font-bold text-base mb-1">{t.team_name}</div>
      <div className="text-ink-fg2 text-xs mb-2">{t.actual_wins}–{t.actual_losses} · {t.conference}</div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs font-mono">
        <span className="text-ink-fg2">Net Rtg</span>
        <span className={t.net_rating >= 0 ? 'text-brand' : 'text-rose-400'}>
          {t.net_rating >= 0 ? '+' : ''}{t.net_rating.toFixed(1)}
        </span>
        <span className="text-ink-fg2">Exp W</span>
        <span>{t.expected_wins.toFixed(1)}</span>
        <span className="text-ink-fg2">Wins +/-</span>
        <span className={wae > 1 ? 'text-green-400' : wae < -1 ? 'text-rose-400' : ''}>
          {waeStr}
        </span>
        <span className="text-ink-fg2">Quadrant</span>
        <span>{QUADRANT_LABELS[t.quadrant]}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Quadrant corner labels via a Customized Recharts component
// ---------------------------------------------------------------------------

function QuadrantLabels({ xAxisMap, yAxisMap }: any) {
  const xAxis = xAxisMap && Object.values(xAxisMap)[0] as any;
  const yAxis = yAxisMap && Object.values(yAxisMap)[0] as any;
  if (!xAxis || !yAxis) return null;

  const left   = xAxis.left ?? 0;
  const right  = (xAxis.left ?? 0) + (xAxis.width ?? 0);
  const top    = yAxis.top ?? 0;
  const bottom = (yAxis.top ?? 0) + (yAxis.height ?? 0);
  const pad    = 10;
  const fs     = 10;

  return (
    <g style={{ pointerEvents: 'none' }}>
      {/* Upper-left: Overachieving */}
      <text x={left + pad} y={top + pad + fs} fontSize={fs} fill="#6b7280" textAnchor="start" fontFamily="var(--font-mono)" letterSpacing="0.08em" textDecoration="none">
        OVERACHIEVING
      </text>
      {/* Upper-right: Running Hot */}
      <text x={right - pad} y={top + pad + fs} fontSize={fs} fill="var(--brand)" textAnchor="end" fontFamily="var(--font-mono)" letterSpacing="0.08em">
        RUNNING HOT
      </text>
      {/* Lower-left: Struggling */}
      <text x={left + pad} y={bottom - pad} fontSize={fs} fill="#6b7280" textAnchor="start" fontFamily="var(--font-mono)" letterSpacing="0.08em">
        STRUGGLING
      </text>
      {/* Lower-right: Hidden Value */}
      <text x={right - pad} y={bottom - pad} fontSize={fs} fill="#30A2DA" textAnchor="end" fontFamily="var(--font-mono)" letterSpacing="0.08em">
        HIDDEN VALUE
      </text>
    </g>
  );
}

// ---------------------------------------------------------------------------
// Sortable table
// ---------------------------------------------------------------------------

type SortKey = 'team_name' | 'actual_wins' | 'actual_losses' | 'net_rating' | 'expected_wins' | 'wins_above_expected' | 'quadrant';

function SortableHeader({
  label, sortKey, current, dir, onSort,
}: {
  label: string; sortKey: SortKey;
  current: SortKey; dir: 'asc' | 'desc';
  onSort: (k: SortKey) => void;
}) {
  const active = current === sortKey;
  return (
    <th
      className="px-3 py-2 text-xs font-semibold text-text-secondary uppercase tracking-wide cursor-pointer select-none hover:text-text-primary transition-colors"
      onClick={() => onSort(sortKey)}
    >
      {label}
      {active && <span className="ml-1 text-brand">{dir === 'desc' ? '↓' : '↑'}</span>}
    </th>
  );
}

function WaeCell({ wae }: { wae: number }) {
  const str = (wae >= 0 ? '+' : '') + wae.toFixed(1);
  const cls = wae > 1
    ? 'text-green-700 bg-green-50'
    : wae < -1
      ? 'text-red-700 bg-red-50'
      : 'text-text-muted';
  return (
    <td className={clsx('px-3 py-2.5 text-sm font-mono text-center rounded-sm', cls)}>
      {str}
    </td>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface Props {
  data: NBALuckChartData;
}

export default function NBALuckChart({ data }: Props) {
  const router = useRouter();
  const [conf, setConf] = useState<'All' | 'East' | 'West'>('All');
  const [sort, setSort] = useState<{ key: SortKey; dir: 'asc' | 'desc' }>({
    key: 'wins_above_expected',
    dir: 'desc',
  });

  const filteredTeams = useMemo(
    () => conf === 'All' ? data.teams : data.teams.filter((t) => t.conference === conf),
    [data.teams, conf],
  );

  const sortedTeams = useMemo(() => {
    const copy = [...filteredTeams];
    copy.sort((a, b) => {
      const av = a[sort.key] as any;
      const bv = b[sort.key] as any;
      if (av < bv) return sort.dir === 'asc' ? -1 : 1;
      if (av > bv) return sort.dir === 'asc' ? 1 : -1;
      return 0;
    });
    return copy;
  }, [filteredTeams, sort]);

  function handleSort(key: SortKey) {
    setSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === 'desc' ? 'asc' : 'desc' }
        : { key, dir: 'desc' },
    );
  }

  return (
    <div className="space-y-8">
      {/* Conference filter */}
      <div className="flex items-center gap-3">
        <span className="text-sm text-text-muted font-mono uppercase tracking-wide">Conference</span>
        <div className="flex rounded-lg overflow-hidden border border-ui-border text-sm">
          {(['All', 'East', 'West'] as const).map((c) => (
            <button
              key={c}
              onClick={() => setConf(c)}
              className={clsx(
                'px-4 py-1.5 font-medium transition-colors',
                conf === c ? 'bg-brand text-white' : 'bg-ui-surface text-text-muted hover:text-text-primary',
                c !== 'All' && 'border-l border-ui-border',
              )}
            >
              {c}
            </button>
          ))}
        </div>
        <span className="text-sm text-text-muted">{filteredTeams.length} teams</span>
      </div>

      {/* Chart */}
      <div className="bg-white border border-ui-border rounded-xl p-4">
        <ResponsiveContainer width="100%" height={500}>
          <ScatterChart margin={{ top: 30, right: 30, bottom: 50, left: 50 }}>
            <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" />

            <XAxis
              dataKey="net_rating"
              type="number"
              domain={['auto', 'auto']}
              name="Net Rating"
              tick={{ fontSize: 11, fontFamily: 'var(--font-mono)', fill: '#6b7280' }}
              label={{ value: 'Net Rating (Adj Off − Adj Def)', position: 'insideBottom', offset: -12, fontSize: 12, fill: '#374151' }}
            />
            <YAxis
              dataKey="wins_above_expected"
              type="number"
              domain={['auto', 'auto']}
              name="Wins Above Expected"
              tick={{ fontSize: 11, fontFamily: 'var(--font-mono)', fill: '#6b7280' }}
              label={{ value: 'Wins Above Expected', angle: -90, position: 'insideLeft', offset: 10, fontSize: 12, fill: '#374151' }}
            />

            <Tooltip content={<LuckTooltip />} cursor={{ strokeDasharray: '3 3', stroke: '#d1d5db' }} />

            {/* Vertical divider at true league average — NOT hardcoded 0 */}
            <ReferenceLine
              x={data.league_avg_net_rating}
              stroke="#9ca3af"
              strokeDasharray="5 4"
              strokeWidth={1.5}
              label={{ value: 'League Avg', position: 'insideTopRight', fontSize: 10, fill: '#9ca3af', fontFamily: 'var(--font-mono)' }}
            />

            {/* Horizontal divider at 0 WAE */}
            <ReferenceLine
              y={0}
              stroke="#9ca3af"
              strokeDasharray="5 4"
              strokeWidth={1.5}
            />

            {/* Quadrant labels rendered as custom SVG layer */}
            <Customized component={QuadrantLabels} />

            <Scatter
              data={filteredTeams}
              shape={<LogoDot />}
              onClick={(pt: any) => router.push(`/nba/team/${pt.team_slug}`)}
              style={{ cursor: 'pointer' }}
            />
          </ScatterChart>
        </ResponsiveContainer>

        {/* Legend note */}
        <p className="text-xs text-text-muted text-center mt-1 font-mono">
          Pythagorean expected wins (exponent 14) · Vertical line = league avg net rating ({data.league_avg_net_rating >= 0 ? '+' : ''}{data.league_avg_net_rating})
        </p>
      </div>

      {/* Sortable table */}
      <div className="overflow-x-auto border border-ui-border rounded-lg">
        <table className="w-full text-sm">
          <thead className="bg-ui-surface border-b border-ui-border">
            <tr>
              <SortableHeader label="Team"         sortKey="team_name"            current={sort.key} dir={sort.dir} onSort={handleSort} />
              <SortableHeader label="W"            sortKey="actual_wins"          current={sort.key} dir={sort.dir} onSort={handleSort} />
              <SortableHeader label="L"            sortKey="actual_losses"        current={sort.key} dir={sort.dir} onSort={handleSort} />
              <SortableHeader label="Net Rtg"      sortKey="net_rating"           current={sort.key} dir={sort.dir} onSort={handleSort} />
              <SortableHeader label="Exp W"        sortKey="expected_wins"        current={sort.key} dir={sort.dir} onSort={handleSort} />
              <SortableHeader label="Wins +/-"     sortKey="wins_above_expected"  current={sort.key} dir={sort.dir} onSort={handleSort} />
              <SortableHeader label="Quadrant"     sortKey="quadrant"             current={sort.key} dir={sort.dir} onSort={handleSort} />
            </tr>
          </thead>
          <tbody>
            {sortedTeams.map((team) => (
              <tr
                key={team.team_slug}
                className="border-b border-ui-border cursor-pointer hover:bg-ui-hover transition-colors"
                onClick={() => router.push(`/nba/team/${team.team_slug}`)}
              >
                {/* Team */}
                <td className="px-3 py-2.5">
                  <div className="flex items-center gap-2">
                    {team.logo_url && (
                      <img
                        src={team.logo_url}
                        alt={team.team_name}
                        className="w-6 h-6 object-contain shrink-0"
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                      />
                    )}
                    <span className="font-medium">{team.team_name}</span>
                    <span className="text-xs text-text-muted">{team.conference}</span>
                  </div>
                </td>
                <td className="px-3 py-2.5 text-sm font-mono text-center">{team.actual_wins}</td>
                <td className="px-3 py-2.5 text-sm font-mono text-center">{team.actual_losses}</td>
                <td className={clsx('px-3 py-2.5 text-sm font-mono font-semibold text-center', team.net_rating >= 0 ? 'text-brand' : 'text-rose-600')}>
                  {team.net_rating >= 0 ? '+' : ''}{team.net_rating.toFixed(1)}
                </td>
                <td className="px-3 py-2.5 text-sm font-mono text-center text-text-muted">
                  {team.expected_wins.toFixed(1)}
                </td>
                <WaeCell wae={team.wins_above_expected} />
                <td className="px-3 py-2.5 text-xs text-text-muted capitalize">
                  {QUADRANT_LABELS[team.quadrant]}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
