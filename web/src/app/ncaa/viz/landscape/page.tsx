'use client';

import { useState, useEffect, useMemo, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import type { EfficiencyLandscapeData, Conference } from '@/types';
import SeasonSelect from '@/components/SeasonSelect';

export default function EfficiencyLandscapePage() {
  const router = useRouter();
  const [data, setData] = useState<EfficiencyLandscapeData | null>(null);
  const [conferences, setConferences] = useState<Conference[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredTeam, setHoveredTeam] = useState<string | null>(null);
  
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
              hoveredTeam={hoveredTeam}
              onTeamHover={setHoveredTeam}
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
  hoveredTeam: string | null;
  onTeamHover: (slug: string | null) => void;
  onTeamClick: (slug: string) => void;
}

function EfficiencyLandscapeChart({ data, hoveredTeam, onTeamHover, onTeamClick }: EfficiencyLandscapeChartProps) {
  const { teams, max_net, defaults } = data;
  
  // Chart dimensions
  const width = 1000; // coordinate space — SVG scales to container via viewBox
  const height = 600;
  const margin = { top: 60, right: 100, bottom: 80, left: 80 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  
  // Compute scales and tier lines
  const { xScale, yScale, tierLines, xTicks, yTicks } = useMemo(() => {
    // Find data bounds
    const dRates = teams.map(t => t.d_rate);
    const oRates = teams.map(t => t.o_rate);
    
    const minD = Math.min(...dRates);
    const maxD = Math.max(...dRates);
    const minO = Math.min(...oRates);
    const maxO = Math.max(...oRates);
    
    // Add padding
    const dPadding = (maxD - minD) * 0.1;
    const oPadding = (maxO - minO) * 0.1;
    
    // Create linear scales
    // X-axis: Adj D - REVERSED so lower (better) defense is on the RIGHT
    const xScale = (d: number) => {
      return margin.left + plotWidth - ((d - (minD - dPadding)) / ((maxD + dPadding) - (minD - dPadding))) * plotWidth;
    };
    
    const yScale = (o: number) => {
      return margin.top + plotHeight - ((o - (minO - oPadding)) / ((maxO + oPadding) - (minO - oPadding))) * plotHeight;
    };
    
    // NATIONAL BASELINE: Use max_net from API (computed from ALL D1 teams)
    // This ensures tier lines stay constant regardless of conference filter
    // In the REVERSED X-axis, lower Adj D is on RIGHT, so slope becomes -1
    
    // Tier cutoffs based on net values (for diagonal lines: o - d = constant)
    const titleFavoritesNet = max_net - defaults.title_delta;
    const final4Net = max_net - defaults.final4_delta;
    const hitMissNet = max_net - defaults.hit_miss_delta;
    
    // Compute diagonal lines (Adj O - Adj D = constant, so Adj O = Adj D + net)
    // With reversed X-axis (lower d on right), this creates slope -1 in display space
    const computeDiagonalLine = (netValue: number) => {
      // Line equation: o = d + netValue
      // Find intersection with plot boundaries
      const points: [number, number][] = [];
      
      const dMin = minD - dPadding;
      const dMax = maxD + dPadding;
      const oMin = minO - oPadding;
      const oMax = maxO + oPadding;
      
      // Check all four edges
      // Left edge (d = dMax because axis is reversed)
      const oAtDMax = dMax + netValue;
      if (oAtDMax >= oMin && oAtDMax <= oMax) {
        points.push([dMax, oAtDMax]);
      }
      
      // Right edge (d = dMin because axis is reversed)
      const oAtDMin = dMin + netValue;
      if (oAtDMin >= oMin && oAtDMin <= oMax) {
        points.push([dMin, oAtDMin]);
      }
      
      // Bottom edge (o = oMin)
      const dAtOMin = oMin - netValue;
      if (dAtOMin >= dMin && dAtOMin <= dMax) {
        points.push([dAtOMin, oMin]);
      }
      
      // Top edge (o = oMax)
      const dAtOMax = oMax - netValue;
      if (dAtOMax >= dMin && dAtOMax <= dMax) {
        points.push([dAtOMax, oMax]);
      }
      
      // Remove duplicates and sort
      const uniquePoints = points.filter((p, i, arr) => 
        i === 0 || p[0] !== arr[i-1][0] || p[1] !== arr[i-1][1]
      );
      
      return uniquePoints.slice(0, 2); // Should be exactly 2 points
    };
    
    const tierLines = [
      { net: titleFavoritesNet, label: 'Title Favorites', color: '#ED713A', width: 3, dash: 'none' },
      { net: final4Net, label: 'Final 4', color: '#30A2DA', width: 2, dash: '5,5' },
      { net: hitMissNet, label: 'Hit or Miss', color: '#999', width: 2, dash: '5,5' },
    ].map(tier => ({
      ...tier,
      points: computeDiagonalLine(tier.net),
    }));
    
    // Generate axis ticks
    const xTicks = Array.from({ length: 7 }, (_, i) => {
      const value = minD - dPadding + ((maxD + dPadding - (minD - dPadding)) / 6) * i;
      return { value, label: value.toFixed(1) };
    });
    
    const yTicks = Array.from({ length: 7 }, (_, i) => {
      const value = minO - oPadding + ((maxO + oPadding - (minO - oPadding)) / 6) * i;
      return { value, label: value.toFixed(1) };
    });
    
    return { xScale, yScale, tierLines, xTicks, yTicks };
  }, [teams, max_net, defaults]);
  
  // Find team for tooltip
  const tooltipTeam = teams.find(t => t.team_slug === hoveredTeam);
  
  return (
    <div className="relative">
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} className="block" style={{ maxWidth: width }}>
        {/* Background */}
        <rect 
          x={margin.left} 
          y={margin.top} 
          width={plotWidth} 
          height={plotHeight} 
          fill="#f9fafb" 
          stroke="#e5e7eb" 
          strokeWidth={1}
        />
        
        {/* Grid lines */}
        {xTicks.map(tick => (
          <line
            key={`x-grid-${tick.value}`}
            x1={xScale(tick.value)}
            y1={margin.top}
            x2={xScale(tick.value)}
            y2={margin.top + plotHeight}
            stroke="#e5e7eb"
            strokeWidth={1}
            strokeDasharray="2,2"
          />
        ))}
        {yTicks.map(tick => (
          <line
            key={`y-grid-${tick.value}`}
            x1={margin.left}
            y1={yScale(tick.value)}
            x2={margin.left + plotWidth}
            y2={yScale(tick.value)}
            stroke="#e5e7eb"
            strokeWidth={1}
            strokeDasharray="2,2"
          />
        ))}
        
        {/* Average reference lines (at 0) */}
        <line
          x1={xScale(0)}
          y1={margin.top}
          x2={xScale(0)}
          y2={margin.top + plotHeight}
          stroke="#999"
          strokeWidth={1}
          strokeDasharray="3,3"
        />
        <line
          x1={margin.left}
          y1={yScale(0)}
          x2={margin.left + plotWidth}
          y2={yScale(0)}
          stroke="#999"
          strokeWidth={1}
          strokeDasharray="3,3"
        />
        
        {/* Tier diagonal lines */}
        {tierLines.map((tier, idx) => {
          if (tier.points.length < 2) return null;
          const [p1, p2] = tier.points;
          return (
            <line
              key={`tier-${idx}`}
              x1={xScale(p1[0])}
              y1={yScale(p1[1])}
              x2={xScale(p2[0])}
              y2={yScale(p2[1])}
              stroke={tier.color}
              strokeWidth={tier.width}
              strokeDasharray={tier.dash}
              opacity={0.8}
            />
          );
        })}
        
        {/* Team logos */}
        {teams.map(team => {
          const x = xScale(team.d_rate);
          const y = yScale(team.o_rate);
          const isHovered = team.team_slug === hoveredTeam;
          const logoSize = isHovered ? 32 : 24;
          
          return (
            <g key={team.team_slug}>
              {team.logo_url ? (
                <image
                  href={team.logo_url}
                  x={x - logoSize / 2}
                  y={y - logoSize / 2}
                  width={logoSize}
                  height={logoSize}
                  style={{ cursor: 'pointer' }}
                  onMouseEnter={() => onTeamHover(team.team_slug)}
                  onMouseLeave={() => onTeamHover(null)}
                  onClick={() => onTeamClick(team.team_slug)}
                  className="transition-all duration-200"
                  opacity={isHovered ? 1 : 0.85}
                />
              ) : (
                <circle
                  cx={x}
                  cy={y}
                  r={isHovered ? 8 : 6}
                  fill="#ED713A"
                  style={{ cursor: 'pointer' }}
                  onMouseEnter={() => onTeamHover(team.team_slug)}
                  onMouseLeave={() => onTeamHover(null)}
                  onClick={() => onTeamClick(team.team_slug)}
                  className="transition-all duration-200"
                  opacity={isHovered ? 1 : 0.7}
                />
              )}
            </g>
          );
        })}
        
        {/* X-axis */}
        <line
          x1={margin.left}
          y1={margin.top + plotHeight}
          x2={margin.left + plotWidth}
          y2={margin.top + plotHeight}
          stroke="#374151"
          strokeWidth={2}
        />
        {xTicks.map(tick => (
          <g key={`x-tick-${tick.value}`}>
            <line
              x1={xScale(tick.value)}
              y1={margin.top + plotHeight}
              x2={xScale(tick.value)}
              y2={margin.top + plotHeight + 6}
              stroke="#374151"
              strokeWidth={2}
            />
            <text
              x={xScale(tick.value)}
              y={margin.top + plotHeight + 20}
              textAnchor="middle"
              className="font-mono text-xs fill-gray-700"
            >
              {tick.label}
            </text>
          </g>
        ))}
        <text
          x={margin.left + plotWidth / 2}
          y={height - 20}
          textAnchor="middle"
          className="font-bold text-sm fill-gray-900"
        >
          Adj D (lower is better) →
        </text>
        
        {/* Y-axis */}
        <line
          x1={margin.left}
          y1={margin.top}
          x2={margin.left}
          y2={margin.top + plotHeight}
          stroke="#374151"
          strokeWidth={2}
        />
        {yTicks.map(tick => (
          <g key={`y-tick-${tick.value}`}>
            <line
              x1={margin.left - 6}
              y1={yScale(tick.value)}
              x2={margin.left}
              y2={yScale(tick.value)}
              stroke="#374151"
              strokeWidth={2}
            />
            <text
              x={margin.left - 10}
              y={yScale(tick.value)}
              textAnchor="end"
              alignmentBaseline="middle"
              className="font-mono text-xs fill-gray-700"
            >
              {tick.label}
            </text>
          </g>
        ))}
        <text
          x={20}
          y={margin.top + plotHeight / 2}
          textAnchor="middle"
          className="font-bold text-sm fill-gray-900"
          transform={`rotate(-90, 20, ${margin.top + plotHeight / 2})`}
        >
          ↑ Adj O (higher is better)
        </text>
        
        {/* Legend */}
        <g transform={`translate(${margin.left + plotWidth + 20}, ${margin.top})`}>
          <text className="font-bold text-sm fill-gray-900" y={0}>Tiers</text>
          {tierLines.map((tier, idx) => (
            <g key={`legend-${idx}`} transform={`translate(0, ${20 + idx * 25})`}>
              <line
                x1={0}
                y1={0}
                x2={20}
                y2={0}
                stroke={tier.color}
                strokeWidth={tier.width}
                strokeDasharray={tier.dash}
              />
              <text
                x={25}
                y={0}
                alignmentBaseline="middle"
                className="text-xs fill-gray-700"
              >
                {tier.label}
              </text>
            </g>
          ))}
        </g>
      </svg>
      
      {/* Tooltip */}
      {tooltipTeam && (
        <div className="absolute top-4 left-4 bg-white border border-gray-300 rounded-lg shadow-lg p-4 max-w-xs z-10">
          <div className="font-bold text-lg mb-1">
            {tooltipTeam.team_name}
            {tooltipTeam.tournament_finish === 'Champ' && <span title="National Champion" className="text-sm ml-1">🏆</span>}
            {tooltipTeam.tournament_finish === 'Runner-Up' && <span title="Runner-Up" className="text-sm ml-1">🥈</span>}
            {tooltipTeam.tournament_finish === 'Final Four' && <span title="Final Four" className="text-sm ml-1">🥉</span>}
          </div>
          <div className="text-sm text-gray-600 mb-2">
            {tooltipTeam.conference_name} ({tooltipTeam.conference})
          </div>
          <div className="border-t border-gray-200 pt-2 space-y-1 text-sm">
            <div className="flex justify-between">
              <span className="font-medium">Adj O:</span>
              <span className="font-mono">{tooltipTeam.o_rate.toFixed(1)}</span>
            </div>
            <div className="flex justify-between">
              <span className="font-medium">Adj D:</span>
              <span className="font-mono">{tooltipTeam.d_rate.toFixed(1)}</span>
            </div>
            <div className="flex justify-between font-bold">
              <span>Adj EM:</span>
              <span className="font-mono">{tooltipTeam.net.toFixed(1)}</span>
            </div>
            <div className="flex justify-between text-gray-600">
              <span>Rank:</span>
              <span>#{tooltipTeam.rank || 'N/A'}</span>
            </div>
            <div className="flex justify-between text-gray-600">
              <span>Record:</span>
              <span>{tooltipTeam.record}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
