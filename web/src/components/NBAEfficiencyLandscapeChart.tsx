'use client';

import { useMemo, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Customized,
  useXAxisScale,
  useYAxisScale,
} from 'recharts';
import type { NBALandscapeData, NBALandscapeTeam } from '@macfax/core/types/nba';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const FINISH_BADGE: Record<string, string> = {
  Champion: '🏆',
  'Runner-Up': '🥈',
  'Conf Finals': '🥉',
};

// Line styles and captions. The ranks come from the API (lines.<key>.n); the captions are the
// calibration results for top 7 / 10 / 15 (backend/api/nba_landscape_config.py).
const LINE_STYLES: {
  key: keyof NBALandscapeData['lines'];
  label: string;
  color: string;
  strokeWidth: number;
  dash: string;
  caption: string;
}[] = [
  {
    key: 'champion', label: 'Champion', color: 'var(--brand)', strokeWidth: 3, dash: 'none',
    caption: 'Every champion since 2005 was a top-7 team by regular-season net rating.',
  },
  {
    key: 'contender', label: 'Contender', color: '#30A2DA', strokeWidth: 2, dash: '5,5',
    caption: '81 of 88 conference finalists since 2005 came from the top 10.',
  },
  {
    key: 'playoff', label: 'Playoff', color: '#999', strokeWidth: 2, dash: '5,5',
    caption: '92% of teams above this line made the playoffs. Below it: no champion, and 2 of 88 conference finalists.',
  },
];

// ---------------------------------------------------------------------------
// Pure helper — diagonal line endpoints clipped to axis bounds
// Line equation: o = d + net  (adj_off − adj_def = constant net rating)
// ---------------------------------------------------------------------------

function computeDiagonal(
  net: number,
  oLo: number, oHi: number,
  dLo: number, dHi: number,
): [number, number][] {
  const points: [number, number][] = [];

  const oAtDLo = dLo + net;
  if (oAtDLo >= oLo && oAtDLo <= oHi) points.push([oAtDLo, dLo]);

  const oAtDHi = dHi + net;
  if (oAtDHi >= oLo && oAtDHi <= oHi) points.push([oAtDHi, dHi]);

  const dAtOLo = oLo - net;
  if (dAtOLo >= dLo && dAtOLo <= dHi) points.push([oLo, dAtOLo]);

  const dAtOHi = oHi - net;
  if (dAtOHi >= dLo && dAtOHi <= dHi) points.push([oHi, dAtOHi]);

  const unique = points.filter(
    (p, i, arr) => i === 0 || p[0] !== arr[i - 1][0] || p[1] !== arr[i - 1][1],
  );
  return unique.slice(0, 2);
}

// ---------------------------------------------------------------------------
// Tier diagonal lines
// Recharts v3: Customized DOES forward extra props to component, but xAxisMap/
// yAxisMap are v2 props no longer injected. Use v3 context hooks instead.
// TierLinesBase must be defined outside the main component for hooks rules.
// ---------------------------------------------------------------------------

interface TierDef {
  net: number;
  n: number;
  label: string;
  caption: string;
  color: string;
  strokeWidth: number;
  dash: string;
}

function TierLinesBase(props: {
  tierDefs?: TierDef[];
  oLo?: number; oHi?: number; dLo?: number; dHi?: number;
  [k: string]: any;
}) {
  const xScale = useXAxisScale();
  const yScale = useYAxisScale();

  const { tierDefs, oLo, oHi, dLo, dHi } = props;
  if (!xScale || !yScale || !tierDefs) return null;
  if (oLo == null || oHi == null || dLo == null || dHi == null) return null;

  return (
    <g>
      {tierDefs.map((tier, idx) => {
        const pts = computeDiagonal(tier.net, oLo, oHi, dLo, dHi);
        if (pts.length < 2) return null;
        const [p1, p2] = pts;
        return (
          <line
            key={idx}
            x1={xScale(p1[0])} y1={yScale(p1[1])}
            x2={xScale(p2[0])} y2={yScale(p2[1])}
            stroke={tier.color}
            strokeWidth={tier.strokeWidth}
            strokeDasharray={tier.dash === 'none' ? undefined : tier.dash}
            opacity={0.8}
          />
        );
      })}
    </g>
  );
}

// ---------------------------------------------------------------------------
// Custom tooltip
// ---------------------------------------------------------------------------

function LandscapeTooltip({ active, payload }: { active?: boolean; payload?: any[] }) {
  if (!active || !payload?.length) return null;
  const t: NBALandscapeTeam = payload[0].payload;
  return (
    <div className="bg-ink border border-ink-line rounded-lg px-4 py-3 text-sm text-white shadow-lg min-w-[180px]">
      <div className="font-bold text-base mb-1 flex items-center gap-1.5">
        {t.team_name}
        {t.playoff_finish && FINISH_BADGE[t.playoff_finish] && (
          <span title={t.playoff_finish}>{FINISH_BADGE[t.playoff_finish]}</span>
        )}
      </div>
      <div className="text-ink-fg2 text-xs mb-2">
        {t.conference} · {t.record}
        {t.rank != null && ` · #${t.rank}`}
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs font-mono">
        <span className="text-ink-fg2">Adj Off</span>
        <span className="text-emerald-400">{t.o_rate.toFixed(1)}</span>
        <span className="text-ink-fg2">Adj Def</span>
        <span className="text-rose-400">{t.d_rate.toFixed(1)}</span>
        <span className="text-ink-fg2">Adj Net</span>
        <span className={t.net >= 0 ? 'text-brand' : 'text-rose-400'}>
          {t.net >= 0 ? '+' : ''}{t.net.toFixed(1)}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface Props {
  data: NBALandscapeData;
}

export default function NBAEfficiencyLandscapeChart({ data }: Props) {
  const router = useRouter();
  const [hovered, setHovered] = useState<string | null>(null);
  const { teams, max_net, lines } = data;

  // Compute padded axis domain + tier defs (must match so diagonal clip is correct)
  const { oLo, oHi, dLo, dHi, tierDefs } = useMemo(() => {
    const oRates = teams.map((t) => t.o_rate);
    const dRates = teams.map((t) => t.d_rate);
    const oMin = Math.min(...oRates), oMax = Math.max(...oRates);
    const dMin = Math.min(...dRates), dMax = Math.max(...dRates);
    const oPad = (oMax - oMin) * 0.1;
    const dPad = (dMax - dMin) * 0.1;

    // A line is null when the season has N teams or fewer rated; leave it out.
    const tierDefs: TierDef[] = LINE_STYLES.flatMap(({ key, ...style }) => {
      const line = lines[key];
      return line.net == null ? [] : [{ ...style, net: line.net, n: line.n }];
    });

    return {
      oLo: oMin - oPad, oHi: oMax + oPad,
      dLo: dMin - dPad, dHi: dMax + dPad,
      tierDefs,
    };
  }, [teams, lines]);

  // Shape function closed over hover state
  const renderDot = useCallback((props: any) => {
    const { cx, cy, payload } = props;
    if (cx == null || cy == null) return null as any;
    const isHov = payload.team_slug === hovered;
    const size = isHov ? 32 : 24;
    if (payload.logo_url) {
      return (
        <image
          href={payload.logo_url}
          x={cx - size / 2} y={cy - size / 2}
          width={size} height={size}
          opacity={isHov ? 1 : 0.9}
          style={{ cursor: 'pointer' }}
          onMouseEnter={() => setHovered(payload.team_slug)}
          onMouseLeave={() => setHovered(null)}
        />
      ) as any;
    }
    return (
      <circle
        cx={cx} cy={cy} r={isHov ? 8 : 6}
        fill="var(--brand)" opacity={isHov ? 1 : 0.7}
        style={{ cursor: 'pointer' }}
        onMouseEnter={() => setHovered(payload.team_slug)}
        onMouseLeave={() => setHovered(null)}
      />
    ) as any;
  }, [hovered]);

  const handleRowClick = (team: NBALandscapeTeam) =>
    router.push(`/nba/team/${team.team_slug}`);

  return (
    <div className="space-y-6">
      {/* Chart */}
      <div className="bg-white border border-ui-border rounded-xl p-4">
        <div className="landscape-chart-height">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 20, right: 20, bottom: 50, left: 60 }}>
            <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" />

            <XAxis
              dataKey="o_rate"
              type="number"
              domain={[oLo, oHi]}
              name="Adj Off"
              tick={{ fontSize: 11, fontFamily: 'var(--font-mono)', fill: '#6b7280' }}
              tickFormatter={(v) => v.toFixed(0)}
              label={{
                value: 'Adj Off (higher is better) →',
                position: 'insideBottom',
                offset: -12,
                fontSize: 12,
                fill: '#374151',
              }}
            />
            <YAxis
              dataKey="d_rate"
              type="number"
              domain={[dLo, dHi]}
              reversed
              name="Adj Def"
              tick={{ fontSize: 11, fontFamily: 'var(--font-mono)', fill: '#6b7280' }}
              tickFormatter={(v) => v.toFixed(0)}
              label={{
                value: '↑ Adj Def (lower is better)',
                angle: -90,
                position: 'insideLeft',
                offset: 10,
                fontSize: 12,
                fill: '#374151',
              }}
            />

            <Tooltip
              content={<LandscapeTooltip />}
              cursor={{ strokeDasharray: '3 3', stroke: '#d1d5db' }}
              isAnimationActive={false}
            />

            {/* Diagonal tier lines — v3 hooks (useXAxisScale/useYAxisScale) inside TierLinesBase */}
            <Customized
              component={TierLinesBase as any}
              tierDefs={tierDefs}
              oLo={oLo} oHi={oHi} dLo={dLo} dHi={dHi}
            />

            <Scatter
              data={teams}
              shape={renderDot}
              onClick={(pt: any) => router.push(`/nba/team/${pt.team_slug}`)}
              style={{ cursor: 'pointer' }}
            />
          </ScatterChart>
        </ResponsiveContainer>
        </div>

        {/* Tier legend + max net note */}
        <div className="flex items-center justify-center gap-x-6 gap-y-1 mt-2 flex-wrap">
          {tierDefs.map((tier) => (
            <div key={tier.label} className="flex items-center gap-2 text-xs text-text-muted">
              <svg width="24" height="8" aria-hidden>
                <line
                  x1="0" y1="4" x2="24" y2="4"
                  stroke={tier.color}
                  strokeWidth={tier.strokeWidth}
                  strokeDasharray={tier.dash === 'none' ? undefined : tier.dash}
                />
              </svg>
              <span>
                {tier.label}
                <span className="ml-1 font-mono text-[10px]">(top {tier.n})</span>
              </span>
            </div>
          ))}
          <span className="text-[10px] text-text-muted font-mono">
            Max Net: {max_net >= 0 ? '+' : ''}{max_net.toFixed(1)}
          </span>
        </div>

        {/* Line captions: what each rank cutoff meant, 2005-2026 */}
        <ul className="mt-3 mx-auto max-w-[760px] space-y-1 text-xs text-text-muted">
          {tierDefs.map((tier) => (
            <li key={tier.label}>
              <span className="font-semibold text-text-primary">{tier.label} (top {tier.n}):</span>{' '}
              {tier.caption}
            </li>
          ))}
        </ul>
      </div>

      {/* Data table */}
      <div className="bg-ui-card border border-ui-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-ui-surface border-b border-ui-border">
              <th className="text-left py-2 px-4 text-xs text-text-muted font-semibold uppercase tracking-wide">Rank</th>
              <th className="text-left py-2 px-4 text-xs text-text-muted font-semibold uppercase tracking-wide">Team</th>
              <th className="text-left py-2 px-4 text-xs text-text-muted font-semibold uppercase tracking-wide">Conf</th>
              <th className="text-right py-2 px-4 text-xs text-text-muted font-semibold uppercase tracking-wide">Record</th>
              <th className="text-right py-2 px-4 text-xs text-text-muted font-semibold uppercase tracking-wide">Adj Net</th>
              <th className="text-right py-2 px-4 text-xs text-text-muted font-semibold uppercase tracking-wide">Adj Off</th>
              <th className="text-right py-2 px-4 text-xs text-text-muted font-semibold uppercase tracking-wide">Adj Def</th>
              <th className="text-left py-2 px-4 text-xs text-text-muted font-semibold uppercase tracking-wide">Playoffs</th>
            </tr>
          </thead>
          <tbody>
            {[...teams]
              .sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99))
              .map((t) => (
                <tr
                  key={t.team_slug}
                  className="border-b border-ui-border/50 hover:bg-ui-surface/50 cursor-pointer"
                  onClick={() => handleRowClick(t)}
                >
                  <td className="py-2 px-4 font-mono text-text-muted text-xs">#{t.rank ?? '—'}</td>
                  <td className="py-2 px-4 font-medium">{t.team_name}</td>
                  <td className="py-2 px-4 text-text-muted text-xs">{t.conference}</td>
                  <td className="py-2 px-4 text-right font-mono text-text-muted">{t.record}</td>
                  <td className="py-2 px-4 text-right font-mono font-semibold text-brand">
                    {t.net >= 0 ? '+' : ''}{t.net.toFixed(1)}
                  </td>
                  <td className="py-2 px-4 text-right font-mono text-emerald-700">{t.o_rate.toFixed(1)}</td>
                  <td className="py-2 px-4 text-right font-mono text-rose-700">{t.d_rate.toFixed(1)}</td>
                  <td className="py-2 px-4 text-xs text-text-muted">
                    {t.playoff_finish && (
                      <span className="inline-flex items-center gap-1">
                        {FINISH_BADGE[t.playoff_finish] && <span>{FINISH_BADGE[t.playoff_finish]}</span>}
                        {t.playoff_finish}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
