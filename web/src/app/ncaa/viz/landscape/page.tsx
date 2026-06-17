'use client';

import { useState, useEffect, useMemo, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import type { EfficiencyLandscapeData, Conference } from '@/types';
import SeasonSelect from '@/components/SeasonSelect';
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

export default function EfficiencyLandscapePage() {
  const router = useRouter();
  const [data, setData] = useState<EfficiencyLandscapeData | null>(null);
  const [conferences, setConferences] = useState<Conference[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Filters
  const [season, setSeason] = useState(2026);
  const [conferenceFilter, setConferenceFilter] = useState('ALL');
  const [topN, setTopN] = useState(365);
  const [debouncedTopN, setDebouncedTopN] = useState(365);
  
  // Load conferences only once on mount
  useEffect(() => {
    loadConferences();
  }, []);
  
  // Debounce topN input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedTopN(topN);
    }, 500);
    return () => clearTimeout(timer);
  }, [topN]);
  
  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const result = await api.getLandscape({
        season,
        conference: conferenceFilter === 'ALL' ? undefined : conferenceFilter,
        top: debouncedTopN,
      });
      setData(result);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to load landscape data');
      console.error('Landscape error:', err);
    } finally {
      setLoading(false);
    }
  }, [season, conferenceFilter, debouncedTopN]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function loadConferences() {
    try {
      const confs = await api.getConferences();
      setConferences(confs);
    } catch (err) {
      console.error('Failed to load conferences:', err);
    }
  }
  
  function handleTeamClick(teamSlug: string) {
    router.push(`/ncaa/team/${teamSlug}`);
  }
  
  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-4xl font-bold mb-2">Efficiency Landscape</h1>
        <p className="text-gray-600">
          Adjusted Offensive vs Defensive ratings with championship tier boundaries
        </p>
      </div>
      
      {/* Filters */}
      <div className="bg-white rounded-lg shadow-md p-6 mb-6">
        <div className="flex flex-wrap gap-4 mb-4 items-center">
          <SeasonSelect value={season} onChange={(s) => { setSeason(s); setConferenceFilter('ALL'); }} />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Conference
            </label>
            <select
              value={conferenceFilter}
              onChange={(e) => setConferenceFilter(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="ALL">All Conferences</option>
              <optgroup label="NCAA Tournament">
                <option value="NCAA_TOURNAMENT">🏀 NCAA Tournament</option>
                <option value="SOUTH">↳ South Region</option>
                <option value="EAST">↳ East Region</option>
                <option value="WEST">↳ West Region</option>
                <option value="MIDWEST">↳ Midwest Region</option>
              </optgroup>
              <optgroup label="Conferences">
                {conferences.map((conf) => (
                  <option key={conf.code} value={conf.code}>
                    {conf.name} ({conf.code})
                  </option>
                ))}
              </optgroup>
            </select>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Top Teams (by Adj EM)
            </label>
            <input
              type="number"
              value={topN}
              onChange={(e) => setTopN(Math.max(1, Math.min(365, parseInt(e.target.value) || 1)))}
              min="1"
              max="365"
              className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 font-mono"
            />
          </div>
        </div>
      </div>
      
      {/* Chart */}
      <div 
        className="bg-white rounded-lg shadow-md p-6"
        role="img"
        aria-label="Efficiency Landscape scatter plot showing Adjusted Offensive Rating vs Adjusted Defensive Rating with tier boundaries"
      >
        {loading && (
          <div className="flex items-center justify-center h-[600px]">
            <div className="text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#ED713A] mx-auto mb-4"></div>
              <p className="text-gray-600">Loading visualization...</p>
            </div>
          </div>
        )}
        
        {error && (
          <div className="bg-red-100 border border-red-400 text-red-800 px-6 py-4 rounded-lg">
            <p className="font-semibold">Error</p>
            <p className="mt-2">{error}</p>
          </div>
        )}
        
        {!loading && !error && data && (
          <>
            <EfficiencyLandscapeChart
              data={data}
              onTeamClick={handleTeamClick}
            />
            
            <div className="mt-4 pt-4 border-t border-gray-200">
              <p className="text-xs text-gray-500 text-center">
                Showing {data.teams.length} teams | Season {data.season_display} | Max Adj EM: {data.max_net}
              </p>
            </div>
          </>
        )}
      </div>
      
      {/* Explanation */}
      <div className="bg-white rounded-lg shadow-md p-6 mt-6">
        <h2 className="text-2xl font-bold mb-4">About This Visualization</h2>
        <p className="mb-4">
          The <strong>Efficiency Landscape</strong> maps teams by their Adjusted Offensive and Adjusted Defensive ratings 
          computed from game-by-game logs. Diagonal tier boundaries separate championship contenders from the rest of the field.
        </p>
        
        <h3 className="text-xl font-bold mb-3">How It Works</h3>
        <ul className="list-disc list-inside space-y-2 mb-4">
          <li><strong>X-axis:</strong> Adj D (Adjusted Defensive Rating - lower is better)</li>
          <li><strong>Y-axis:</strong> Adj O (Adjusted Offensive Rating - higher is better)</li>
          <li><strong>Adj EM:</strong> Adj O - Adj D (offense minus defense = net efficiency)</li>
          <li><strong>Title Favorites:</strong> Adj EM ≥ Max - 6 (top contenders)</li>
          <li><strong>Final Four Potential:</strong> Adj EM ≥ Max - 12 (strong teams)</li>
          <li><strong>Hit or Miss:</strong> Adj EM ≥ Max - 18 (bubble teams)</li>
          <li><strong>The Rest:</strong> Teams below Hit or Miss threshold</li>
        </ul>
        
        <p className="text-sm text-gray-600">
          Diagonal lines represent constant Adjusted Efficiency Margins. Teams in the upper-left corner (great offense, great defense) 
          are championship-caliber. Click any team logo to view their detailed profile.
        </p>
      </div>
    </div>
  );
}

// ==================== Chart Component ====================

interface EfficiencyLandscapeChartProps {
  data: EfficiencyLandscapeData;
  onTeamClick: (slug: string) => void;
}

// NCAA: XAxis=d_rate (reversed, lower d → right), YAxis=o_rate (normal, higher o → top)
// Line equation: o - d = net → o = d + net. Returns [d, o] pairs matching axis dataKeys.
function computeNCAADiagonal(
  net: number,
  dLo: number, dHi: number,
  oLo: number, oHi: number,
): [number, number][] {
  const points: [number, number][] = [];

  const oAtDLo = dLo + net;
  if (oAtDLo >= oLo && oAtDLo <= oHi) points.push([dLo, oAtDLo]);

  const oAtDHi = dHi + net;
  if (oAtDHi >= oLo && oAtDHi <= oHi) points.push([dHi, oAtDHi]);

  const dAtOLo = oLo - net;
  if (dAtOLo >= dLo && dAtOLo <= dHi) points.push([dAtOLo, oLo]);

  const dAtOHi = oHi - net;
  if (dAtOHi >= dLo && dAtOHi <= dHi) points.push([dAtOHi, oHi]);

  const unique = points.filter(
    (p, i, arr) => i === 0 || p[0] !== arr[i - 1][0] || p[1] !== arr[i - 1][1],
  );
  return unique.slice(0, 2);
}

interface NCAADef {
  net: number; label: string; color: string; strokeWidth: number; dash: string;
}

// Must be module-level for hooks rules. Recharts v3: useXAxisScale/useYAxisScale via context.
function TierLinesNCAA(props: {
  tierDefs?: NCAADef[];
  dLo?: number; dHi?: number; oLo?: number; oHi?: number;
  [k: string]: any;
}) {
  const xScale = useXAxisScale();
  const yScale = useYAxisScale();
  const { tierDefs, dLo, dHi, oLo, oHi } = props;
  if (!xScale || !yScale || !tierDefs) return null;
  if (dLo == null || dHi == null || oLo == null || oHi == null) return null;
  return (
    <g>
      {tierDefs.map((tier, idx) => {
        const pts = computeNCAADiagonal(tier.net, dLo, dHi, oLo, oHi);
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

function NCAALandscapeTooltip({ active, payload }: { active?: boolean; payload?: any[] }) {
  if (!active || !payload?.length) return null;
  const t = payload[0].payload;
  const badge =
    t.tournament_finish === 'Champ' ? '🏆' :
    t.tournament_finish === 'Runner-Up' ? '🥈' :
    t.tournament_finish === 'Final Four' ? '🥉' : null;
  return (
    <div className="bg-white border border-gray-300 rounded-lg shadow-lg p-4 max-w-xs text-sm">
      <div className="font-bold text-lg mb-1">
        {t.team_name}{badge && <span className="text-sm ml-1">{badge}</span>}
      </div>
      <div className="text-sm text-gray-600 mb-2">
        {t.conference_name} ({t.conference})
      </div>
      <div className="border-t border-gray-200 pt-2 space-y-1 text-sm">
        <div className="flex justify-between"><span className="font-medium">Adj O:</span><span className="font-mono">{t.o_rate.toFixed(1)}</span></div>
        <div className="flex justify-between"><span className="font-medium">Adj D:</span><span className="font-mono">{t.d_rate.toFixed(1)}</span></div>
        <div className="flex justify-between font-bold"><span>Adj EM:</span><span className="font-mono">{t.net.toFixed(1)}</span></div>
        <div className="flex justify-between text-gray-600"><span>Rank:</span><span>#{t.rank || 'N/A'}</span></div>
        <div className="flex justify-between text-gray-600"><span>Record:</span><span>{t.record}</span></div>
      </div>
    </div>
  );
}

function EfficiencyLandscapeChart({ data, onTeamClick }: EfficiencyLandscapeChartProps) {
  const { teams, max_net, defaults } = data;
  const [hovered, setHovered] = useState<string | null>(null);

  const { dLo, dHi, oLo, oHi, tierDefs } = useMemo(() => {
    const dRates = teams.map((t) => t.d_rate);
    const oRates = teams.map((t) => t.o_rate);
    const dMin = Math.min(...dRates), dMax = Math.max(...dRates);
    const oMin = Math.min(...oRates), oMax = Math.max(...oRates);
    const dPad = (dMax - dMin) * 0.1;
    const oPad = (oMax - oMin) * 0.1;

    const tierDefs: NCAADef[] = [
      { net: max_net - defaults.title_delta,  label: 'Title Favorites', color: '#ED713A', strokeWidth: 3, dash: 'none' },
      { net: max_net - defaults.final4_delta,  label: 'Final 4',         color: '#30A2DA', strokeWidth: 2, dash: '5,5' },
      { net: max_net - defaults.hit_miss_delta, label: 'Hit or Miss',     color: '#999',    strokeWidth: 2, dash: '5,5' },
    ];

    return {
      dLo: dMin - dPad, dHi: dMax + dPad,
      oLo: oMin - oPad, oHi: oMax + oPad,
      tierDefs,
    };
  }, [teams, max_net, defaults]);

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
          opacity={isHov ? 1 : 0.85}
          style={{ cursor: 'pointer' }}
          onMouseEnter={() => setHovered(payload.team_slug)}
          onMouseLeave={() => setHovered(null)}
        />
      ) as any;
    }
    return (
      <circle
        cx={cx} cy={cy} r={isHov ? 8 : 6}
        fill="#ED713A" opacity={isHov ? 1 : 0.7}
        style={{ cursor: 'pointer' }}
        onMouseEnter={() => setHovered(payload.team_slug)}
        onMouseLeave={() => setHovered(null)}
      />
    ) as any;
  }, [hovered]);

  return (
    <div>
      <ResponsiveContainer width="100%" height={600}>
        <ScatterChart margin={{ top: 20, right: 20, bottom: 50, left: 60 }}>
          <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" />
          <XAxis
            dataKey="d_rate"
            type="number"
            domain={[dLo, dHi]}
            reversed
            name="Adj D"
            tick={{ fontSize: 11, fontFamily: 'monospace', fill: '#6b7280' }}
            tickFormatter={(v) => v.toFixed(1)}
            label={{ value: 'Adj D (lower is better) →', position: 'insideBottom', offset: -12, fontSize: 12, fill: '#374151' }}
          />
          <YAxis
            dataKey="o_rate"
            type="number"
            domain={[oLo, oHi]}
            name="Adj O"
            tick={{ fontSize: 11, fontFamily: 'monospace', fill: '#6b7280' }}
            tickFormatter={(v) => v.toFixed(1)}
            label={{ value: '↑ Adj O (higher is better)', angle: -90, position: 'insideLeft', offset: 10, fontSize: 12, fill: '#374151' }}
          />
          <Tooltip content={<NCAALandscapeTooltip />} cursor={{ strokeDasharray: '3 3', stroke: '#d1d5db' }} />
          <Customized
            component={TierLinesNCAA as any}
            tierDefs={tierDefs}
            dLo={dLo} dHi={dHi} oLo={oLo} oHi={oHi}
          />
          <Scatter
            data={teams}
            shape={renderDot}
            onClick={(pt: any) => onTeamClick(pt.team_slug)}
            style={{ cursor: 'pointer' }}
          />
        </ScatterChart>
      </ResponsiveContainer>

      {/* Tier legend */}
      <div className="flex items-center justify-center gap-6 mt-2 flex-wrap">
        {tierDefs.map((tier) => (
          <div key={tier.label} className="flex items-center gap-2 text-xs text-gray-500">
            <svg width="24" height="8" aria-hidden>
              <line x1="0" y1="4" x2="24" y2="4"
                stroke={tier.color} strokeWidth={tier.strokeWidth}
                strokeDasharray={tier.dash === 'none' ? undefined : tier.dash} />
            </svg>
            <span>{tier.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
