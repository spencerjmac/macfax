'use client';

import { TeamSeasonMetrics, TeamSeasonRatings } from '@/types/api';

interface TeamStatsDisplayProps {
  metrics: TeamSeasonMetrics | null;
  ratings: TeamSeasonRatings | null;
}

export default function TeamStatsDisplay({ metrics, ratings }: TeamStatsDisplayProps) {
  if (!metrics && !ratings) {
    return (
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
        <p className="text-yellow-800">No statistics available for this team yet.</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Adjusted Ratings Card */}
      {ratings && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <h2 className="text-2xl font-bold mb-6 text-indigo-600">Adjusted Ratings</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-6">
            <div className="bg-blue-50 rounded-lg p-4 text-center">
              <p className="text-sm text-gray-600 mb-1">Adjusted Offense</p>
              <p className="text-3xl font-bold text-blue-600">{ratings.adj_o.toFixed(1)}</p>
              <p className="text-xs text-gray-500 mt-1">Rank: #{ratings.rank_adj_o || 'N/A'}</p>
            </div>
            
            <div className="bg-red-50 rounded-lg p-4 text-center">
              <p className="text-sm text-gray-600 mb-1">Adjusted Defense</p>
              <p className="text-3xl font-bold text-red-600">{ratings.adj_d.toFixed(1)}</p>
              <p className="text-xs text-gray-500 mt-1">Rank: #{ratings.rank_adj_d || 'N/A'}</p>
            </div>
            
            <div className="bg-purple-50 rounded-lg p-4 text-center">
              <p className="text-sm text-gray-600 mb-1">Adjusted Net</p>
              <p className="text-3xl font-bold text-purple-600">{ratings.adj_em > 0 ? '+' : ''}{ratings.adj_em.toFixed(1)}</p>
              <p className="text-xs text-gray-500 mt-1">Rank: #{ratings.rank_adj_em || 'N/A'}</p>
            </div>
            
            <div className="bg-green-50 rounded-lg p-4 text-center">
              <p className="text-sm text-gray-600 mb-1">Adjusted Pace</p>
              <p className="text-3xl font-bold text-green-600">{ratings.adj_tempo.toFixed(1)}</p>
              <p className="text-xs text-gray-500 mt-1">poss/game</p>
            </div>
          </div>
        </div>
      )}

      {/* Four Factor Index */}
      {ratings && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <h2 className="text-2xl font-bold mb-6 text-orange-600">Four Factor Index</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-orange-50 rounded-lg p-6 text-center">
              <p className="text-sm text-gray-600 mb-2">Raw FFI</p>
              <p className="text-5xl font-bold text-orange-600">{ratings.ffi_raw.toFixed(1)}</p>
              <p className="text-xs text-gray-500 mt-2">Based on raw margins</p>
            </div>
            
            <div className="bg-orange-100 rounded-lg p-6 text-center border-2 border-orange-300">
              <p className="text-sm text-gray-600 mb-2 font-semibold">Adjusted FFI</p>
              <p className="text-5xl font-bold text-orange-700">{ratings.ffi_adj.toFixed(1)}</p>
              <p className="text-xs text-gray-500 mt-2">Opponent-adjusted (0-100)</p>
            </div>
          </div>
          
          <div className="mt-4 p-4 bg-gray-50 rounded-lg">
            <p className="text-xs text-gray-600">
              <strong>Formula:</strong> 40.69% eFG margin + 40.69% TOV edge + 14.32% REB edge + 4.28% FTR margin
            </p>
          </div>
        </div>
      )}

      {/* Raw Four Factors */}
      {metrics && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <h2 className="text-2xl font-bold mb-6">Raw Four Factors</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div>
              <h3 className="text-lg font-semibold mb-4 text-green-600">Offense</h3>
              <div className="space-y-3">
                <MetricRow label="eFG%" value={`${metrics.efg_pct.toFixed(1)}%`} />
                <MetricRow label="TOV%" value={`${metrics.tov_pct.toFixed(1)}%`} />
                <MetricRow label="ORB%" value={`${metrics.orb_pct.toFixed(1)}%`} />
                <MetricRow label="FTR" value={metrics.ftr.toFixed(1)} />
              </div>
            </div>
            
            <div>
              <h3 className="text-lg font-semibold mb-4 text-red-600">Defense</h3>
              <div className="space-y-3">
                <MetricRow label="Opp eFG%" value={`${metrics.opp_efg_pct.toFixed(1)}%`} />
                <MetricRow label="Opp TOV%" value={`${metrics.opp_tov_pct.toFixed(1)}%`} />
                <MetricRow label="DRB%" value={`${metrics.drb_pct.toFixed(1)}%`} />
                <MetricRow label="Opp FTR" value={metrics.opp_ftr.toFixed(1)} />
              </div>
            </div>
          </div>
          
          <div className="mt-6 pt-6 border-t">
            <h3 className="text-lg font-semibold mb-4">Raw Margins</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <MarginBox label="eFG Margin" value={metrics.efg_margin} />
              <MarginBox label="TOV Edge" value={metrics.tov_edge} />
              <MarginBox label="REB Edge" value={metrics.reb_edge} />
              <MarginBox label="FTR Margin" value={metrics.ftr_margin} />
            </div>
          </div>
        </div>
      )}

      {/* Adjusted Four Factors */}
      {ratings && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <h2 className="text-2xl font-bold mb-6 text-indigo-600">Adjusted Four Factors</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div>
              <h3 className="text-lg font-semibold mb-4 text-green-600">Offense (Opponent-Adjusted)</h3>
              <div className="space-y-3">
                <MetricRow label="Adj eFG%" value={`${ratings.adj_efg_pct.toFixed(1)}%`} />
                <MetricRow label="Adj TOV%" value={`${ratings.adj_tov_pct.toFixed(1)}%`} />
                <MetricRow label="Adj ORB%" value={`${ratings.adj_orb_pct.toFixed(1)}%`} />
                <MetricRow label="Adj FTR" value={ratings.adj_ftr.toFixed(1)} />
              </div>
            </div>
            
            <div>
              <h3 className="text-lg font-semibold mb-4 text-red-600">Defense (Opponent-Adjusted)</h3>
              <div className="space-y-3">
                <MetricRow label="Adj Opp eFG%" value={`${ratings.adj_opp_efg_pct.toFixed(1)}%`} />
                <MetricRow label="Adj Opp TOV%" value={`${ratings.adj_opp_tov_pct.toFixed(1)}%`} />
                <MetricRow label="Adj DRB%" value={`${ratings.adj_drb_pct.toFixed(1)}%`} />
                <MetricRow label="Adj Opp FTR" value={ratings.adj_opp_ftr.toFixed(1)} />
              </div>
            </div>
          </div>
          
          <div className="mt-6 pt-6 border-t">
            <h3 className="text-lg font-semibold mb-4">Adjusted Margins</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <MarginBox label="Adj eFG Margin" value={ratings.adj_efg_margin} />
              <MarginBox label="Adj TOV Edge" value={ratings.adj_tov_edge} />
              <MarginBox label="Adj REB Edge" value={ratings.adj_reb_edge} />
              <MarginBox label="Adj FTR Margin" value={ratings.adj_ftr_margin} />
            </div>
          </div>
        </div>
      )}

      {/* Basic Stats */}
      {metrics && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <h2 className="text-2xl font-bold mb-6">Season Averages</h2>
          
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <StatBox label="Games" value={metrics.games.toString()} />
            <StatBox label="PPG" value={metrics.ppg.toFixed(1)} />
            <StatBox label="PAPG" value={metrics.papg.toFixed(1)} />
            <StatBox label="Pace" value={metrics.pace.toFixed(1)} />
          </div>
          
          <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="text-center">
              <p className="text-sm text-gray-600 mb-1">Raw ORtg</p>
              <p className="text-2xl font-bold text-blue-600">{metrics.ortg.toFixed(1)}</p>
            </div>
            <div className="text-center">
              <p className="text-sm text-gray-600 mb-1">Raw DRtg</p>
              <p className="text-2xl font-bold text-red-600">{metrics.drtg.toFixed(1)}</p>
            </div>
            <div className="text-center">
              <p className="text-sm text-gray-600 mb-1">Raw Net</p>
              <p className="text-2xl font-bold text-purple-600">
                {metrics.net_rtg > 0 ? '+' : ''}{metrics.net_rtg.toFixed(1)}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-center py-2 border-b border-gray-100">
      <span className="text-gray-700">{label}</span>
      <span className="font-mono font-semibold text-gray-900">{value}</span>
    </div>
  );
}

function MarginBox({ label, value }: { label: string; value: number }) {
  const color = value > 0 ? 'text-green-600 bg-green-50' : value < 0 ? 'text-red-600 bg-red-50' : 'text-gray-600 bg-gray-50';
  
  return (
    <div className={`${color} p-4 rounded-lg text-center`}>
      <p className="text-xs text-gray-600 mb-1">{label}</p>
      <p className="text-2xl font-bold font-mono">
        {value > 0 ? '+' : ''}{value.toFixed(1)}
      </p>
    </div>
  );
}

function StatBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-center">
      <p className="text-sm text-gray-600 mb-1">{label}</p>
      <p className="text-2xl font-bold font-mono">{value}</p>
    </div>
  );
}
