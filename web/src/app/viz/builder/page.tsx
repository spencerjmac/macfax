'use client';

import { useState, useEffect } from 'react';
import { Suspense } from 'react';
import dynamicImport from 'next/dynamic';
import { useRouter, useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import type { VizStats, VizScatterData, StatMetadata } from '@/types';

export const dynamic = 'force-dynamic';

// Dynamically import ECharts to avoid SSR issues
const ReactECharts = dynamicImport(() => import('echarts-for-react'), { ssr: false });

// FiveThirtyEight-ish color palette
const CONFERENCE_COLORS: Record<string, string> = {
  'B10': '#ED713A',   // Big Ten - Primary Orange
  'B12': '#30A2DA',   // Big 12 - Secondary Blue  
  'ACC': '#FC4F30',   // ACC - Red
  'SEC': '#E5AE38',   // SEC - Gold
  'BE': '#6D904F',    // Big East - Green
  'P12': '#8B8B8B',   // Pac-12 - Gray
  'A10': '#810F7C',   // A10 - Purple
  'MWC': '#17BECF',   // MW - Cyan
  'WCC': '#BCBD22',   // WCC - Yellow-Green
  'AAC': '#FF7F0E',   // AAC - Orange
};

function VizBuilderPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  
  // Data state  
  const [stats, setStats] = useState<VizStats | null>(null);
  const [data, setData] = useState<VizScatterData | null>(null);
  const [loading, setLoading] = useState(true);
  const [dataLoading, setDataLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // UI state from URL params
  const [xStat, setXStat] = useState(searchParams.get('x') || 'adj_o');
  const [yStat, setYStat] = useState(searchParams.get('y') || 'adj_d');
  const [showRegression, setShowRegression] = useState(searchParams.get('reg') !== '0');
  const [colorByConference, setColorByConference] = useState(searchParams.get('color') !== '0');
  const [invertX, setInvertX] = useState(searchParams.get('invX') === '1');
  const [invertY, setInvertY] = useState(searchParams.get('invY') === '1');
  
  // Load stat catalog on mount
  useEffect(() => {
    loadStats();
  }, []);
  
  // Load scatter data when stats change
  useEffect(() => {
    if (xStat && yStat) {
      loadScatterData();
      updateURL();
    }
  }, [xStat, yStat]);
  
  async function loadStats() {
    try {
      setLoading(true);
      const result = await api.getVizStats();
      setStats(result);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to load stats');
      console.error('Stats error:', err);
    } finally {
      setLoading(false);
    }
  }
  
  async function loadScatterData() {
    try {
      setDataLoading(true);
      const result = await api.getVizScatter({
        x: xStat,
        y: yStat,
        colorBy: colorByConference ? 'conference' : undefined,
      });
      setData(result);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to load scatter data');
      console.error('Scatter error:', err);
    } finally {
      setDataLoading(false);
    }
  }
  
  function updateURL() {
    const params = new URLSearchParams();
    params.set('x', xStat);
    params.set('y', yStat);
    if (!showRegression) params.set('reg', '0');
    if (!colorByConference) params.set('color', '0');
    if (invertX) params.set('invX', '1');
    if (invertY) params.set('invY', '1');
    router.replace(`?${params.toString()}`, { scroll: false });
  }
  
  function swapAxes() {
    const temp = xStat;
    setXStat(yStat);
    setYStat(temp);
    // Also swap invert states
    const tempInvert = invertX;
    setInvertX(invertY);
    setInvertY(tempInvert);
  }
  
  function formatValue(value: number, format: string, decimals: number): string {
    if (format === 'percent') {
      return `${value.toFixed(decimals)}%`;
    } else if (format === 'per_game') {
      return value.toFixed(decimals);
    } else if (format === 'rating') {
      return value.toFixed(decimals);
    } else {
      return value.toFixed(decimals);
    }
  }
  
  function getChartOption() {
    if (!data) return {};
    
    const { x, y, points, stats: scatterStats } = data;
    
    // Build series
    const series: any[] = [];
    
    if (colorByConference) {
      // Group points by conference
      const confGroups: Record<string, typeof points> = {};
      points.forEach(point => {
        const conf = point.conference || 'IND';
        if (!confGroups[conf]) confGroups[conf] = [];
        confGroups[conf].push(point);
      });
      
      // Create a scatter series per conference
      Object.entries(confGroups).forEach(([conf, confPoints]) => {
        series.push({
          type: 'scatter',
          name: conf,
          data: confPoints.map(p => ({
            value: [p.x, p.y],
            name: p.team,
            point: p,
            symbol: p.logo_url ? `image://${p.logo_url}` : 'circle',
            symbolSize: p.logo_url ? 30 : 10,
          })),
          itemStyle: {
            color: CONFERENCE_COLORS[conf] || '#8B8B8B',
            opacity: 0.9,
          },
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowColor: 'rgba(0, 0, 0, 0.5)',
            },
            scale: 1.2,
          },
        });
      });
    } else {
      // Single scatter series
      series.push({
        type: 'scatter',
        name: 'Teams',
        data: points.map(p => ({
          value: [p.x, p.y],
          name: p.team,
          point: p,
          symbol: p.logo_url ? `image://${p.logo_url}` : 'circle',
          symbolSize: p.logo_url ? 30 : 10,
        })),
        itemStyle: {
          color: '#30A2DA',
          opacity: 0.9,
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowColor: 'rgba(0, 0, 0, 0.5)',
          },
          scale: 1.2,
        },
      });
    }
    
    // Add regression line if enabled
    if (showRegression && scatterStats.slope !== null && scatterStats.intercept !== null) {
      const xValues = points.map(p => p.x);
      const minX = Math.min(...xValues);
      const maxX = Math.max(...xValues);
      
      const y1 = scatterStats.slope * minX + scatterStats.intercept;
      const y2 = scatterStats.slope * maxX + scatterStats.intercept;
      
      series.push({
        type: 'line',
        name: 'Regression',
        data: [
          [minX, y1],
          [maxX, y2],
        ],
        lineStyle: {
          color: '#ED713A',
          width: 2,
          type: 'dashed',
        },
        symbol: 'none',
        tooltip: {
          show: false,
        },
      });
    }
    
    return {
      backgroundColor: '#fff',
      title: {
        text: 'Viz Builder',
        subtext: `${y.label} vs ${x.label}`,
        left: 'center',
        top: 20,
        textStyle: {
          fontSize: 24,
          fontWeight: 'bold',
          fontFamily: 'Inter, sans-serif',
        },
        subtextStyle: {
          fontSize: 14,
          color: '#666',
          fontFamily: 'Inter, sans-serif',
        },
      },
      tooltip: {
        trigger: 'item',
        formatter: (params: any) => {
          if (params.seriesType === 'scatter') {
            const point = params.data.point;
            return `
              <div style="padding: 8px; font-family: Inter, sans-serif;">
                <strong style="font-size: 14px;">${point.team}</strong><br/>
                <span style="color: #666;">${point.conference}</span><br/>
                <hr style="margin: 6px 0; border: none; border-top: 1px solid #ddd;"/>
                <strong>${x.label}:</strong> <span style="font-family: 'IBM Plex Mono', monospace;">${formatValue(point.x, x.format, x.decimals)}</span><br/>
                <strong>${y.label}:</strong> <span style="font-family: 'IBM Plex Mono', monospace;">${formatValue(point.y, y.format, y.decimals)}</span>
              </div>
            `;
          }
          return '';
        },
      },
      grid: {
        left: 100,
        right: colorByConference ? 150 : 50,
        top: 100,
        bottom: 100,
      },
      xAxis: {
        type: 'value',
        name: x.label,
        nameLocation: 'middle',
        nameGap: 35,
        nameTextStyle: {
          fontSize: 14,
          fontWeight: 'bold',
          fontFamily: 'Inter, sans-serif',
        },
        scale: true,
        inverse: invertX,
        splitLine: {
          show: true,
          lineStyle: {
            type: 'dashed',
            color: '#e0e0e0',
          },
        },
      },
      yAxis: {
        type: 'value',
        name: y.label,
        nameLocation: 'middle',
        nameGap: 60,
        nameTextStyle: {
          fontSize: 14,
          fontWeight: 'bold',
          fontFamily: 'Inter, sans-serif',
        },
        scale: true,
        inverse: invertY,
        splitLine: {
          show: true,
          lineStyle: {
            type: 'dashed',
            color: '#e0e0e0',
          },
        },
      },
      legend: colorByConference ? {
        type: 'scroll',
        orient: 'vertical',
        right: 10,
        top: 100,
        data: Array.from(new Set(points.map(p => p.conference))).sort(),
      } : undefined,
      series,
    };
  }
  
  function handleChartClick(params: any) {
    if (params.componentType === 'series' && params.seriesType === 'scatter') {
      const point = params.data.point;
      router.push(`/team/${point.slug}`);
    }
  }
  
  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 p-8">
        <div className="max-w-7xl mx-auto">
          <div className="text-center py-12">
            <div className="text-xl text-gray-600">Loading...</div>
          </div>
        </div>
      </div>
    );
  }
  
  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 p-8">
        <div className="max-w-7xl mx-auto">
          <div className="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded">
            <strong>Error:</strong> {error}
          </div>
        </div>
      </div>
    );
  }
  
  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="bg-white rounded-lg shadow-sm p-6">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Viz Builder</h1>
          <p className="text-gray-600">
            Build custom scatterplots using stats computed from our game log data
          </p>
        </div>
        
        {/* Controls */}
        <div className="bg-white rounded-lg shadow-sm p-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* X-axis selector */}
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                X-Axis
              </label>
              <select
                value={xStat}
                onChange={(e) => setXStat(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                {stats && Object.entries(stats.groups).map(([group, groupStats]) => (
                  <optgroup key={group} label={group}>
                    {groupStats.map((stat: StatMetadata) => (
                      <option key={stat.key} value={stat.key}>
                        {stat.label}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
              <label className="flex items-center space-x-2 text-sm mt-2">
                <input
                  type="checkbox"
                  checked={invertX}
                  onChange={(e) => {
                    setInvertX(e.target.checked);
                    updateURL();
                  }}
                  className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                />
                <span className="text-gray-600">Invert X-axis</span>
              </label>
            </div>
            
            {/* Y-axis selector */}
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                Y-Axis
              </label>
              <select
                value={yStat}
                onChange={(e) => setYStat(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                {stats && Object.entries(stats.groups).map(([group, groupStats]) => (
                  <optgroup key={group} label={group}>
                    {groupStats.map((stat: StatMetadata) => (
                      <option key={stat.key} value={stat.key}>
                        {stat.label}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
              <label className="flex items-center space-x-2 text-sm mt-2">
                <input
                  type="checkbox"
                  checked={invertY}
                  onChange={(e) => {
                    setInvertY(e.target.checked);
                    updateURL();
                  }}
                  className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                />
                <span className="text-gray-600">Invert Y-axis</span>
              </label>
            </div>
            
            {/* Controls */}
            <div className="space-y-3">
              <button
                onClick={swapAxes}
                className="w-full px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium rounded-md transition-colors"
              >
                ⇄ Swap X/Y
              </button>
              
              <label className="flex items-center space-x-2 text-sm">
                <input
                  type="checkbox"
                  checked={showRegression}
                  onChange={(e) => {
                    setShowRegression(e.target.checked);
                    updateURL();
                  }}
                  className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                />
                <span className="text-gray-700">Show regression line</span>
              </label>
              
              <label className="flex items-center space-x-2 text-sm">
                <input
                  type="checkbox"
                  checked={colorByConference}
                  onChange={(e) => {
                    setColorByConference(e.target.checked);
                    updateURL();
                    loadScatterData();
                  }}
                  className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                />
                <span className="text-gray-700">Color by conference</span>
              </label>
            </div>
          </div>
        </div>
        
        {/* Statistics */}
        {data && data.stats.n && (
          <div className="bg-white rounded-lg shadow-sm p-6">
            <div className="flex flex-wrap gap-6 font-['IBM_Plex_Mono',monospace] text-sm">
              <div>
                <span className="text-gray-600">n = </span>
                <span className="font-semibold text-gray-900">{data.stats.n}</span>
              </div>
              {data.stats.pearson_r !== null && (
                <>
                  <div>
                    <span className="text-gray-600">r = </span>
                    <span className="font-semibold text-gray-900">{data.stats.pearson_r.toFixed(4)}</span>
                  </div>
                  <div>
                    <span className="text-gray-600">r² = </span>
                    <span className="font-semibold text-gray-900">{data.stats.r2?.toFixed(4)}</span>
                  </div>
                  {showRegression && data.stats.slope !== null && (
                    <div>
                      <span className="text-gray-600">y = </span>
                      <span className="font-semibold text-gray-900">
                        {data.stats.slope.toFixed(4)}x + {data.stats.intercept?.toFixed(4)}
                      </span>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        )}
        
        {/* Chart */}
        <div className="bg-white rounded-lg shadow-sm p-6">
          {dataLoading ? (
            <div className="flex items-center justify-center h-96">
              <div className="text-xl text-gray-600">Loading chart...</div>
            </div>
          ) : data ? (
            <ReactECharts
              option={getChartOption()}
              style={{ height: '700px' }}
              onEvents={{
                click: handleChartClick,
              }}
            />
          ) : (
            <div className="flex items-center justify-center h-96">
              <div className="text-xl text-gray-600">Select stats to view chart</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function VizBuilderPage() {
  return (
    <Suspense fallback={<div className="container mx-auto px-4 py-8">Loading...</div>}>
      <VizBuilderPageInner />
    </Suspense>
  );
}
