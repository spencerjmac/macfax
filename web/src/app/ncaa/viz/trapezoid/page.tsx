'use client';

import { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { api } from '@/lib/api';
import type { TrapezoidData, Conference } from '@/types';
import SeasonSelect from '@/components/SeasonSelect';

// Dynamically import ECharts to avoid SSR issues
const ReactECharts = dynamic(() => import('echarts-for-react'), { ssr: false });

export default function TrapezoidPage() {
  const [data, setData] = useState<TrapezoidData | null>(null);
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
  
  // Load data when filters change
  useEffect(() => {
    loadData();
  }, [season, conferenceFilter, debouncedTopN]);
  
  async function loadConferences() {
    try {
      const confs = await api.getConferences();
      setConferences(confs);
    } catch (err) {
      console.error('Failed to load conferences:', err);
    }
  }
  
  async function loadData() {
    try {
      setLoading(true);
      const result = await api.getTrapezoid({
        season,
        conference: conferenceFilter === 'ALL' ? undefined : conferenceFilter,
        top: debouncedTopN,
      });
      setData(result);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to load trapezoid data');
      console.error('Trapezoid error:', err);
    } finally {
      setLoading(false);
    }
  }
  
  function getChartOption() {
    if (!data) return {};
    
    const { trapezoid, averages, teams } = data;
    
    // Build trapezoid polygon coordinates
    const trapezoidPolygon = [
      [trapezoid.x_left_top, trapezoid.y_top],
      [trapezoid.x_right_top, trapezoid.y_top],
      [trapezoid.x_right_bot, trapezoid.y_bot],
      [trapezoid.x_left_bot, trapezoid.y_bot],
      [trapezoid.x_left_top, trapezoid.y_top], // close the shape
    ];
    
    // Prepare scatter data
    const scatterData = teams.map(team => ({
      value: [team.adj_tempo, team.adj_em],
      name: team.team_name,
      team,
    }));
    
    return {
      backgroundColor: '#fff',
      title: {
        text: 'Trapezoid of Excellence',
        subtext: 'Concept by Ryan Hammer',
        left: 'center',
        top: 20,
        textStyle: {
          fontSize: 24,
          fontWeight: 'bold',
        },
        subtextStyle: {
          fontSize: 14,
          color: '#666',
        },
      },
      tooltip: {
        trigger: 'item',
        formatter: (params: any) => {
          if (params.componentSubType === 'scatter') {
            const team = params.data.team;
            const trophy = team.tournament_finish === 'Champ' ? ' 🏆' : team.tournament_finish === 'Runner-Up' ? ' 🥈' : team.tournament_finish === 'Final Four' ? ' 🥉' : '';
              
            return `
              <div style="font-family: inherit; padding: 4px;">
                <strong style="font-size: 14px;">${team.team_name}${trophy}</strong><br/>
                <span style="color: #666; font-size: 12px;">${team.conference_name} (${team.conference})</span><br/>
                <hr style="margin: 6px 0; border: none; border-top: 1px solid #ddd;"/>
                <strong>Adj Tempo:</strong> ${team.adj_tempo}<br/>
                <strong>Adj EM:</strong> ${team.adj_em}<br/>
                <strong>Rank:</strong> ${team.rank || 'N/A'}<br/>
                <strong>Record:</strong> ${team.record}<br/>
                <strong>Inside Trapezoid:</strong> ${team.inside_trapezoid ? '<span style="color: green;">✓ Yes</span>' : '<span style="color: #999;">No</span>'}
              </div>
            `;
          }
          return '';
        },
      },
      grid: {
        left: 80,
        right: 50,
        top: 100,
        bottom: 100,
      },
      xAxis: {
        type: 'value',
        name: 'Adjusted Tempo (Pace)',
        nameLocation: 'middle',
        nameGap: 30,
        nameTextStyle: {
          fontSize: 14,
          fontWeight: 'bold',
        },
        scale: true,  // Don't force zero in the axis
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
        name: 'Adjusted Efficiency Margin (Net Rating)',
        nameLocation: 'middle',
        nameGap: 50,
        nameTextStyle: {
          fontSize: 14,
          fontWeight: 'bold',
        },
        scale: true,  // Don't force zero in the axis
        splitLine: {
          show: true,
          lineStyle: {
            type: 'dashed',
            color: '#e0e0e0',
          },
        },
      },
      series: [
        // Trapezoid polygon (background)
        {
          type: 'line',
          name: 'Trapezoid',
          data: trapezoidPolygon,
          lineStyle: {
            color: '#ff6b6b',
            width: 3,
            type: 'solid',
          },
          areaStyle: {
            color: 'rgba(255, 107, 107, 0.1)',
          },
          symbol: 'none',
          animation: false,
          silent: true,
        },
        // Average lines
        {
          type: 'line',
          name: 'Avg Tempo',
          markLine: {
            symbol: 'none',
            label: {
              show: true,
              formatter: 'Avg Tempo',
              position: 'end',
            },
            lineStyle: {
              color: '#999',
              width: 1,
              type: 'dashed',
            },
            data: [
              {
                xAxis: averages.avg_tempo,
              },
            ],
            animation: false,
            silent: true,
          },
        },
        {
          type: 'line',
          name: 'Avg EM',
          markLine: {
            symbol: 'none',
            label: {
              show: true,
              formatter: 'Avg EM',
              position: 'end',
            },
            lineStyle: {
              color: '#999',
              width: 1,
              type: 'dashed',
            },
            data: [
              {
                yAxis: averages.avg_em,
              },
            ],
            animation: false,
            silent: true,
          },
        },
        // Team scatter points with logos
        {
          type: 'scatter',
          name: 'Teams',
          data: scatterData.map(point => ({
            ...point,
            symbol: point.team.logo_url 
              ? `image://${point.team.logo_url}` 
              : 'circle',
            symbolSize: point.team.logo_url ? 30 : 10,
          })),
          itemStyle: {
            color: (params: any) => {
              const team = params.data.team;
              // Only apply color to teams without logos
              return team.logo_url ? undefined : (team.inside_trapezoid ? '#4CAF50' : '#2196F3');
            },
            opacity: 0.9,
          },
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowColor: 'rgba(0, 0, 0, 0.5)',
            },
            scale: 1.2,
          },
        },
      ],
    };
  }
  
  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="text-4xl font-bold mb-8">Trapezoid of Excellence</h1>
      
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
              className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
        </div>
      </div>
      
      {/* Chart */}
      <div 
        className="bg-white rounded-lg shadow-md p-6"
        role="img"
        aria-label="Trapezoid of Excellence scatter plot visualization showing Adjusted Tempo vs Adjusted Efficiency Margin. Concept by Ryan Hammer."
      >
        {loading && (
          <div className="flex items-center justify-center h-96">
            <div className="text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
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
            <ReactECharts 
              option={getChartOption()} 
              style={{ height: '700px', width: '100%' }}
              opts={{ renderer: 'svg' }}
            />
            
            <div className="mt-4 pt-4 border-t border-gray-200">
              <p className="text-sm text-gray-600 text-center">
                <strong>Trapezoid of Excellence</strong> concept by <strong>Ryan Hammer</strong>
              </p>
              <p className="text-xs text-gray-500 text-center mt-2">
                Showing {data.meta.total_teams} teams | Season {data.meta.season_display}
              </p>
            </div>
          </>
        )}
      </div>
      
      {/* Explanation */}
      <div className="bg-white rounded-lg shadow-md p-6 mt-6">
        <h2 className="text-2xl font-bold mb-4">About This Visualization</h2>
        <p className="mb-4">
          The <strong>Trapezoid of Excellence</strong> identifies teams that combine elite efficiency with optimal tempo. 
          Championship-caliber teams historically cluster within this dynamically-calculated region.
        </p>
        
        <h3 className="text-xl font-bold mb-3">How It Works</h3>
        <ul className="list-disc list-inside space-y-2 mb-4">
          <li><strong>X-axis:</strong> Adjusted Tempo (pace of play)</li>
          <li><strong>Y-axis:</strong> Adjusted Efficiency Margin (net rating)</li>
          <li><strong>Trapezoid Boundaries:</strong> Computed dynamically from percentiles of the filtered dataset</li>
          <li><strong>Green Points:</strong> Teams inside the trapezoid (championship-caliber profile)</li>
          <li><strong>Blue Points:</strong> Teams outside the trapezoid</li>
        </ul>
        
        <p className="text-sm text-gray-600">
          The trapezoid boundaries adjust automatically based on the current season and your selected filters 
          (Conference and Top Teams). This ensures the analysis reflects the actual distribution of teams in your view.
        </p>
      </div>
    </div>
  );
}

