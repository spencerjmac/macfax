'use client';

import { useState, useEffect } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import TeamStatsDisplay from '@/components/TeamStatsDisplay';
import type { TeamSeasonMetrics, TeamSeasonRatings, Team } from '@/types/api';

export default function TeamStatsPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const slug = params.slug as string;
  const season = searchParams.get('season') ? parseInt(searchParams.get('season')!) : 2026;
  
  const [team, setTeam] = useState<Team | null>(null);
  const [metrics, setMetrics] = useState<TeamSeasonMetrics | null>(null);
  const [ratings, setRatings] = useState<TeamSeasonRatings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  useEffect(() => {
    loadTeamData();
  }, [slug, season]);
  
  async function loadTeamData() {
    try {
      setLoading(true);
      setError(null);
      
      const data = await api.getTeamSeasonStats(slug, season);
      
      setTeam(data.team);
      setMetrics(data.metrics);
      setRatings(data.ratings);
    } catch (err: any) {
      console.error('Error loading team data:', err);
      setError(err.message || 'Failed to load team statistics');
    } finally {
      setLoading(false);
    }
  }
  
  if (loading) {
    return (
      <div className="container mx-auto px-4 py-20">
        <div className="flex justify-center items-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
        </div>
      </div>
    );
  }
  
  if (error || !team) {
    return (
      <div className="container mx-auto px-4 py-20">
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          <p className="font-bold">Error</p>
          <p>{error || 'Team not found'}</p>
        </div>
      </div>
    );
  }
  
  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="bg-gradient-to-r from-indigo-600 to-purple-600 rounded-lg shadow-lg p-8 mb-8 text-white">
        <div className="flex items-center gap-6">
          {team.logo_url && (
            <img
              src={team.logo_url}
              alt={team.name}
              className="w-24 h-24 object-contain bg-white rounded-lg p-2"
              onError={(e) => {
                e.currentTarget.style.display = 'none';
              }}
            />
          )}
          
          <div className="flex-1">
            <h1 className="text-4xl font-bold mb-2">{team.name}</h1>
            <p className="text-xl opacity-90">
              {season - 1}-{String(season).slice(2)} Season Statistics
            </p>
            
            {metrics && (
              <div className="mt-4 flex gap-6">
                <div>
                  <p className="text-sm opacity-75">Record</p>
                  <p className="text-2xl font-bold">{metrics.games} GP</p>
                </div>
                {ratings && (
                  <>
                    <div>
                      <p className="text-sm opacity-75">National Rank</p>
                      <p className="text-2xl font-bold">#{ratings.rank_adj_em || 'N/A'}</p>
                    </div>
                    <div>
                      <p className="text-sm opacity-75">Adj Net Rating</p>
                      <p className="text-2xl font-bold">
                        {ratings.adj_em > 0 ? '+' : ''}{ratings.adj_em.toFixed(1)}
                      </p>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
      
      {/* Stats Display */}
      <TeamStatsDisplay metrics={metrics} ratings={ratings} />
      
      {/* Footer Info */}
      <div className="mt-8 p-4 bg-gray-100 rounded-lg text-sm text-gray-600">
        <p><strong>Data Source:</strong> Game log calculations aggregated from NCAA API</p>
        <p className="mt-1"><strong>Adjusted Metrics:</strong> Account for opponent strength and site factors (home/away/neutral)</p>
        {ratings && (
          <p className="mt-1 text-xs">
            Last computed: {new Date(ratings.computed_at).toLocaleString()}
          </p>
        )}
      </div>
    </div>
  );
}
