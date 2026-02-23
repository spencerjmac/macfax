'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { RankingsRow, Conference } from '@/types';

type ViewMode = 'overview' | 'four-factors' | 'adjusted-four-factors' | 'shooting' | 'playmaking';

export default function RankingsPage() {
  const [data, setData] = useState<RankingsRow[]>([]);
  const [rawData, setRawData] = useState<RankingsRow[]>([]); // Store original API response
  const [conferences, setConferences] = useState<Conference[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [season] = useState(2026);
  const [lastUpdated, setLastUpdated] = useState<string>('');
  
  // View mode
  const [viewMode, setViewMode] = useState<ViewMode>('overview');
  const [showHeatmap, setShowHeatmap] = useState(true);
  
  // Filters
  const [search, setSearch] = useState('');
  const [conferenceFilter, setConferenceFilter] = useState('');
  const [rankFilter, setRankFilter] = useState<'all' | 'top25' | 'top50'>('all');
  const [sortField, setSortField] = useState('rank');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  
  // Fetch data when filters change
  useEffect(() => {
    loadData();
  }, [search, conferenceFilter]);
  
  // Apply sorting whenever sort field/direction/rank filter changes
  useEffect(() => {
    if (rawData.length > 0) {
      const needsServerSort = !isClientSideSort(sortField);
      if (needsServerSort) {
        // Need to fetch data sorted by server
        loadDataWithSort();
      } else {
        // Can sort client-side
        applySorting();
      }
    }
  }, [sortField, sortDir, rankFilter]);
  
  useEffect(() => {
    loadConferences();
  }, []);
  
  // Helper to check if a field requires client-side sorting
  const isClientSideSort = (field: string) => {
    // raw_four_factor_index_100 can be sorted server-side (maps to ffi_raw)
    // All other raw_* fields need client-side sorting
    return field.startsWith('raw_') && field !== 'raw_four_factor_index_100';
  };
  
  async function loadData() {
    try {
      setLoading(true);
      
      const response = await api.getRankings({
        season: season,
        search: search || undefined,
        conference: conferenceFilter || undefined,
        sort: 'rank',
        dir: 'asc',
      });
      
      const fetchedData = response.results || [];
      setRawData(fetchedData);
      
      // Apply current sorting/filtering
      applyFilterAndSort(fetchedData);
      
      setLastUpdated(new Date().toLocaleTimeString());
      setError(null);
    } catch (err: any) {
      console.error('Error loading data:', err);
      setError(err.message || 'Failed to load rankings');
    } finally {
      setLoading(false);
    }
  }
  
  function applySorting() {
    applyFilterAndSort(rawData);
  }
  
  function applyFilterAndSort(sourceData: RankingsRow[]) {
    let filteredData = [...sourceData];
    
    // Apply rank filter
    if (rankFilter === 'top25') {
      filteredData = filteredData.filter(r => r.rank <= 25);
    } else if (rankFilter === 'top50') {
      filteredData = filteredData.filter(r => r.rank <= 50);
    }
    
    // Apply client-side sorting if needed
    if (isClientSideSort(sortField)) {
      filteredData.sort((a, b) => {
        const aVal = (a as any)[sortField] || 0;
        const bVal = (b as any)[sortField] || 0;
        const comparison = aVal - bVal;
        return sortDir === 'desc' ? -comparison : comparison;
      });
    }
    
    setData(filteredData);
  }
  
  async function loadDataWithSort() {
    try {
      setLoading(true);
      
      const response = await api.getRankings({
        season: season,
        search: search || undefined,
        conference: conferenceFilter || undefined,
        sort: sortField,
        dir: sortDir,
      });
      
      const fetchedData = response.results || [];
      setRawData(fetchedData);
      
      // Apply filtering (server already sorted it)
      applyFilterOnly(fetchedData);
      
      setLastUpdated(new Date().toLocaleTimeString());
      setError(null);
    } catch (err: any) {
      console.error('Error loading data:', err);
      setError(err.message || 'Failed to load rankings');
    } finally {
      setLoading(false);
    }
  }
  
  function applyFilterOnly(sourceData: RankingsRow[]) {
    let filteredData = [...sourceData];
    
    // Apply rank filter
    if (rankFilter === 'top25') {
      filteredData = filteredData.filter(r => r.rank <= 25);
    } else if (rankFilter === 'top50') {
      filteredData = filteredData.filter(r => r.rank <= 50);
    }
    
    setData(filteredData);
  }
  
  async function loadConferences() {
    try {
      const confs = await api.getConferences();
      setConferences(confs);
    } catch (err) {
      console.error('Failed to load conferences:', err);
    }
  }
  
  function handleSort(field: string) {
    if (sortField === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir(field === 'rank' ? 'asc' : 'desc');
    }
  }
  
  // Compute percentiles for heatmap
  function getPercentile(value: number, field: string): number {
    if (!showHeatmap || data.length === 0) return 50;
    
    const values = data.map(d => {
      switch(field) {
        case 'adj_em': return d.adj_em;
        case 'adj_o': return d.adj_o;
        case 'adj_d': return d.adj_d;
        case 'adj_tempo': return d.adj_tempo;
        case 'efg_pct': return d.efg_pct;
        case 'tov_pct': return d.tov_pct;
        case 'orb_pct': return d.orb_pct;
        case 'ftr': return d.ftr;
        case 'efg_pct_d': return d.efg_pct_d;
        case 'tov_pct_d': return d.tov_pct_d;
        case 'orb_pct_d': return d.orb_pct_d;
        case 'ftr_d': return d.ftr_d;
        case 'efg_margin': return d.efg_margin;
        case 'tov_edge': return d.tov_edge;
        case 'reb_edge': return d.reb_edge;
        case 'ftr_margin': return d.ftr_margin;
        case 'raw_efg_pct': return d.raw_efg_pct;
        case 'raw_tov_pct': return d.raw_tov_pct;
        case 'raw_orb_pct': return d.raw_orb_pct;
        case 'raw_ftr': return d.raw_ftr;
        case 'raw_efg_pct_d': return d.raw_efg_pct_d;
        case 'raw_tov_pct_d': return d.raw_tov_pct_d;
        case 'raw_orb_pct_d': return d.raw_orb_pct_d;
        case 'raw_ftr_d': return d.raw_ftr_d;
        case 'raw_efg_margin': return d.raw_efg_margin;
        case 'raw_tov_edge': return d.raw_tov_edge;
        case 'raw_reb_edge': return d.raw_reb_edge;
        case 'raw_ftr_margin': return d.raw_ftr_margin;
        case 'four_factor_index_100': return d.four_factor_index_100 || 50;
        case 'raw_four_factor_index_100': return d.raw_four_factor_index_100 || 50;
        default: return 50;
      }
    }).filter(v => v != null) as number[];
    
    const sorted = [...values].sort((a, b) => a - b);
    const rank = sorted.filter(v => v < value).length;
    return (rank / sorted.length) * 100;
  }
  
  function getCellStyle(value: number, field: string, isDefense = false): React.CSSProperties {
    if (!showHeatmap) return {};
    
    const percentile = getPercentile(value, field);
    
    // For defense, invert the scale (lower is better)
    const effectivePercentile = isDefense ? 100 - percentile : percentile;
    
    let bgColor = 'transparent';
    if (effectivePercentile >= 80) {
      bgColor = 'rgba(34, 197, 94, 0.15)'; // green
    } else if (effectivePercentile >= 60) {
      bgColor = 'rgba(34, 197, 94, 0.08)';
    } else if (effectivePercentile <= 20) {
      bgColor = 'rgba(239, 68, 68, 0.15)'; // red
    } else if (effectivePercentile <= 40) {
      bgColor = 'rgba(239, 68, 68, 0.08)';
    }
    
    return { backgroundColor: bgColor };
  }
  
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-end justify-between mb-2">
            <h1 className="text-4xl font-bold text-gray-900">Team Rankings</h1>
            <div className="text-sm text-gray-500">
              {lastUpdated && `Last updated: ${lastUpdated}`}
            </div>
          </div>
          <p className="text-gray-600">
            Adjusted ratings based on game logs (per 100 possessions) • {season-1}-{String(season).slice(2)} Season
          </p>
        </div>

        {/* View Tabs */}
        <div className="bg-white rounded-lg shadow-md mb-6 p-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex gap-2">
              <button
                onClick={() => setViewMode('overview')}
                className={`px-4 py-2 rounded-md font-medium transition-colors ${
                  viewMode === 'overview'
                    ? 'bg-orange-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                Overview
              </button>
              <button
                onClick={() => setViewMode('four-factors')}
                className={`px-4 py-2 rounded-md font-medium transition-colors ${
                  viewMode === 'four-factors'
                    ? 'bg-orange-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                Four Factors
              </button>
              <button
                onClick={() => setViewMode('adjusted-four-factors')}
                className={`px-4 py-2 rounded-md font-medium transition-colors ${
                  viewMode === 'adjusted-four-factors'
                    ? 'bg-orange-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                Adjusted Four Factors
              </button>
            </div>
            
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={showHeatmap}
                onChange={(e) => setShowHeatmap(e.target.checked)}
                className="w-4 h-4 text-orange-600 rounded"
              />
              <span className="text-sm font-medium text-gray-700">Show heatmap</span>
            </label>
          </div>
        </div>
        
        {/* Filters */}
        <div className="bg-white rounded-lg shadow-md p-6 mb-6">
          <div className="flex flex-wrap gap-4 mb-4">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search teams..."
              className="flex-1 min-w-[200px] px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-orange-500 focus:border-orange-500"
            />
            
            <select
              value={conferenceFilter}
              onChange={(e) => setConferenceFilter(e.target.value)}
              className="px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-orange-500 focus:border-orange-500"
            >
              <option value="">All Conferences</option>
              {conferences.map((conf) => (
                <option key={conf.code} value={conf.code}>
                  {conf.name}
                </option>
              ))}
            </select>
            
            <button
              onClick={() => {
                setSearch('');
                setConferenceFilter('');
                setRankFilter('all');
                setSortField('rank');
                setSortDir('asc');
              }}
              className="px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 font-medium"
            >
              Clear
            </button>
          </div>
          
          {/* Filter Pills */}
          <div className="flex gap-2">
            <button
              onClick={() => setRankFilter('all')}
              className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
                rankFilter === 'all'
                  ? 'bg-orange-100 text-orange-700'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              All Teams
            </button>
            <button
              onClick={() => setRankFilter('top25')}
              className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
                rankFilter === 'top25'
                  ? 'bg-orange-100 text-orange-700'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              Top 25
            </button>
            <button
              onClick={() => setRankFilter('top50')}
              className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
                rankFilter === 'top50'
                  ? 'bg-orange-100 text-orange-700'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              Top 50
            </button>
          </div>
        </div>
        
        {/* Loading/Error States */}
        {loading && (
          <div className="flex justify-center items-center py-20">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-orange-600"></div>
          </div>
        )}
        
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-6 py-4 rounded-lg">
            <p className="font-bold">Error loading rankings</p>
            <p>{error}</p>
          </div>
        )}
        
        {/* Rankings Table */}
        {!loading && !error && (
          <div className="bg-white rounded-lg shadow-md overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50 sticky top-0 z-10">
                  {viewMode === 'overview' && (
                    <tr className="border-b border-gray-200">
                      <SortableHeader field="rank" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          Rank
                          <InfoTooltip text="National ranking by Adjusted Efficiency Margin" />
                        </div>
                      </SortableHeader>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider sticky left-0 bg-gray-50">
                        Team
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        Conf
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        Record
                      </th>
                      <SortableHeader field="adj_em" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          AdjEM
                          <InfoTooltip text="Adjusted Efficiency Margin (points per 100 possessions adjusted for opponent & venue)" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="adj_o" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          AdjO
                          <InfoTooltip text="Adjusted Offensive Efficiency (points scored per 100 possessions)" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="adj_d" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          AdjD
                          <InfoTooltip text="Adjusted Defensive Efficiency (points allowed per 100 possessions)" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="adj_tempo" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          Tempo
                          <InfoTooltip text="Adjusted tempo (possessions per 40 minutes)" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="four_factor_index_100" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          4FI
                          <InfoTooltip text="Four Factor Index (0-100 scale, composite of eFG%, TOV%, ORB%, FTR)" />
                        </div>
                      </SortableHeader>
                    </tr>
                  )}
                  
                  {viewMode === 'four-factors' && (
                    <tr className="border-b border-gray-200">
                      <SortableHeader field="rank" current={sortField} dir={sortDir} onClick={handleSort}>
                        Rank
                      </SortableHeader>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider sticky left-0 bg-gray-50">
                        Team
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        Conf
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        Record
                      </th>
                      <SortableHeader field="raw_efg_pct" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          eFG%
                          <InfoTooltip text="Effective Field Goal % (offense)" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="raw_efg_pct_d" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          eFG% D
                          <InfoTooltip text="Effective Field Goal % allowed (defense)" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="raw_efg_margin" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          eFG Margin
                          <InfoTooltip text="eFG% - Opponent eFG%" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="raw_tov_pct" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          TOV%
                          <InfoTooltip text="Turnover % (offense)" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="raw_tov_pct_d" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          TOV% D
                          <InfoTooltip text="Turnover % forced (defense)" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="raw_tov_edge" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          TOV Edge
                          <InfoTooltip text="Opponent TOV% - TOV%" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="raw_orb_pct" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          ORB%
                          <InfoTooltip text="Offensive Rebound %" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="raw_orb_pct_d" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          ORB% D
                          <InfoTooltip text="Opponent Offensive Rebound %" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="raw_reb_edge" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          REB Edge
                          <InfoTooltip text="ORB% - Opponent ORB%" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="raw_ftr" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          FTR
                          <InfoTooltip text="Free Throw Rate (offense)" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="raw_ftr_d" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          FTR D
                          <InfoTooltip text="Free Throw Rate allowed (defense)" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="raw_ftr_margin" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          FTR Margin
                          <InfoTooltip text="FTR - Opponent FTR" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="raw_four_factor_index_100" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          4FI
                          <InfoTooltip text="Four Factor Index (0-100 composite score)" />
                        </div>
                      </SortableHeader>
                    </tr>
                  )}
                  
                  {viewMode === 'adjusted-four-factors' && (
                    <tr className="border-b border-gray-200">
                      <SortableHeader field="rank" current={sortField} dir={sortDir} onClick={handleSort}>
                        Rank
                      </SortableHeader>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider sticky left-0 bg-gray-50">
                        Team
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        Conf
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        Record
                      </th>
                      <SortableHeader field="efg_pct" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          Adj eFG%
                          <InfoTooltip text="Adjusted Effective Field Goal % (offense)" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="efg_pct_d" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          Adj eFG% D
                          <InfoTooltip text="Adjusted Effective Field Goal % allowed (defense)" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="efg_margin" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          Adj eFG Margin
                          <InfoTooltip text="Adjusted eFG% - Opponent eFG%" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="tov_pct" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          Adj TOV%
                          <InfoTooltip text="Adjusted Turnover % (offense)" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="tov_pct_d" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          Adj TOV% D
                          <InfoTooltip text="Adjusted Turnover % forced (defense)" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="tov_edge" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          Adj TOV Edge
                          <InfoTooltip text="Adjusted Opponent TOV% - TOV%" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="orb_pct" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          Adj ORB%
                          <InfoTooltip text="Adjusted Offensive Rebound %" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="orb_pct_d" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          Adj ORB% D
                          <InfoTooltip text="Adjusted Opponent Offensive Rebound %" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="reb_edge" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          Adj REB Edge
                          <InfoTooltip text="Adjusted ORB% - Opponent ORB%" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="ftr" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          Adj FTR
                          <InfoTooltip text="Adjusted Free Throw Rate (offense)" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="ftr_d" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          Adj FTR D
                          <InfoTooltip text="Adjusted Free Throw Rate allowed (defense)" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="ftr_margin" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          Adj FTR Margin
                          <InfoTooltip text="Adjusted FTR - Opponent FTR" />
                        </div>
                      </SortableHeader>
                      <SortableHeader field="four_factor_index_100" current={sortField} dir={sortDir} onClick={handleSort}>
                        <div className="flex items-center gap-1">
                          4FI
                          <InfoTooltip text="Four Factor Index (0-100 composite score)" />
                        </div>
                      </SortableHeader>
                    </tr>
                  )}
                </thead>
                
                <tbody>
                  {data.map((row) => (
                    <tr key={row.team_slug} className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-3 font-bold text-gray-900">
                        {row.rank}
                      </td>
                      <td className="px-4 py-3 sticky left-0 bg-white hover:bg-gray-50">
                        <Link 
                          href={`/team/${row.team_slug}/stats?season=${season}`}
                          className="flex items-center gap-2 text-indigo-600 hover:text-indigo-800 font-medium"
                        >
                          {row.team_logo && (
                            <img 
                              src={row.team_logo} 
                              alt="" 
                              className="w-6 h-6 object-contain"
                              onError={(e) => e.currentTarget.style.display = 'none'}
                            />
                          )}
                          {row.team_name}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {row.conference || 'Ind'}
                      </td>
                      <td className="px-4 py-3 text-sm font-mono text-gray-700">
                        {row.record}
                      </td>
                      
                      {viewMode === 'overview' && (
                        <>
                          <td className="px-4 py-3 font-bold font-mono" style={getCellStyle(row.adj_em, 'adj_em')}>
                            {row.adj_em > 0 ? '+' : ''}{row.adj_em.toFixed(1)}
                          </td>
                          <td className="px-4 py-3 font-mono" style={getCellStyle(row.adj_o, 'adj_o')}>
                            {row.adj_o.toFixed(1)}
                          </td>
                          <td className="px-4 py-3 font-mono" style={getCellStyle(row.adj_d, 'adj_d', true)}>
                            {row.adj_d.toFixed(1)}
                          </td>
                          <td className="px-4 py-3 font-mono" style={getCellStyle(row.adj_tempo, 'adj_tempo')}>
                            {row.adj_tempo.toFixed(1)}
                          </td>
                          <td className="px-4 py-3 font-mono font-bold" style={getCellStyle(row.four_factor_index_100 || 50, 'four_factor_index_100')}>
                            <div className="flex items-center gap-2">
                              {row.four_factor_index_100?.toFixed(0) ?? '—'}
                              {row.four_factor_index_100 && row.four_factor_index_100 >= 75 && (
                                <span className="px-2 py-0.5 text-xs font-semibold bg-green-100 text-green-800 rounded">Elite</span>
                              )}
                            </div>
                          </td>
                        </>
                      )}
                      
                      {viewMode === 'four-factors' && (
                        <>
                          <td className="px-4 py-3 font-mono" style={getCellStyle(row.raw_efg_pct, 'raw_efg_pct')}>
                            {row.raw_efg_pct.toFixed(1)}%
                          </td>
                          <td className="px-4 py-3 font-mono" style={getCellStyle(row.raw_efg_pct_d, 'raw_efg_pct_d', true)}>
                            {row.raw_efg_pct_d.toFixed(1)}%
                          </td>
                          <td className="px-4 py-3 font-mono font-semibold" style={getCellStyle(row.raw_efg_margin, 'raw_efg_margin')}>
                            {row.raw_efg_margin > 0 ? '+' : ''}{row.raw_efg_margin.toFixed(1)}%
                          </td>
                          <td className="px-4 py-3 font-mono" style={getCellStyle(row.raw_tov_pct, 'raw_tov_pct', true)}>
                            {row.raw_tov_pct.toFixed(1)}%
                          </td>
                          <td className="px-4 py-3 font-mono" style={getCellStyle(row.raw_tov_pct_d, 'raw_tov_pct_d')}>
                            {row.raw_tov_pct_d.toFixed(1)}%
                          </td>
                          <td className="px-4 py-3 font-mono font-semibold" style={getCellStyle(row.raw_tov_edge, 'raw_tov_edge')}>
                            {row.raw_tov_edge > 0 ? '+' : ''}{row.raw_tov_edge.toFixed(1)}%
                          </td>
                          <td className="px-4 py-3 font-mono" style={getCellStyle(row.raw_orb_pct, 'raw_orb_pct')}>
                            {row.raw_orb_pct.toFixed(1)}%
                          </td>
                          <td className="px-4 py-3 font-mono" style={getCellStyle(row.raw_orb_pct_d, 'raw_orb_pct_d', true)}>
                            {row.raw_orb_pct_d.toFixed(1)}%
                          </td>
                          <td className="px-4 py-3 font-mono font-semibold" style={getCellStyle(row.raw_reb_edge, 'raw_reb_edge')}>
                            {row.raw_reb_edge > 0 ? '+' : ''}{row.raw_reb_edge.toFixed(1)}%
                          </td>
                          <td className="px-4 py-3 font-mono" style={getCellStyle(row.raw_ftr, 'raw_ftr')}>
                            {row.raw_ftr.toFixed(1)}
                          </td>
                          <td className="px-4 py-3 font-mono" style={getCellStyle(row.raw_ftr_d, 'raw_ftr_d', true)}>
                            {row.raw_ftr_d.toFixed(1)}
                          </td>
                          <td className="px-4 py-3 font-mono font-semibold" style={getCellStyle(row.raw_ftr_margin, 'raw_ftr_margin')}>
                            {row.raw_ftr_margin > 0 ? '+' : ''}{row.raw_ftr_margin.toFixed(1)}
                          </td>
                          <td className="px-4 py-3 font-mono font-bold" style={getCellStyle(row.raw_four_factor_index_100 || 50, 'raw_four_factor_index_100')}>
                            {row.raw_four_factor_index_100?.toFixed(0) ?? '—'}
                          </td>
                        </>
                      )}
                      
                      {viewMode === 'adjusted-four-factors' && (
                        <>
                          <td className="px-4 py-3 font-mono" style={getCellStyle(row.efg_pct, 'efg_pct')}>
                            {row.efg_pct.toFixed(1)}%
                          </td>
                          <td className="px-4 py-3 font-mono" style={getCellStyle(row.efg_pct_d, 'efg_pct_d', true)}>
                            {row.efg_pct_d.toFixed(1)}%
                          </td>
                          <td className="px-4 py-3 font-mono font-semibold" style={getCellStyle(row.efg_margin, 'efg_margin')}>
                            {row.efg_margin > 0 ? '+' : ''}{row.efg_margin.toFixed(1)}%
                          </td>
                          <td className="px-4 py-3 font-mono" style={getCellStyle(row.tov_pct, 'tov_pct', true)}>
                            {row.tov_pct.toFixed(1)}%
                          </td>
                          <td className="px-4 py-3 font-mono" style={getCellStyle(row.tov_pct_d, 'tov_pct_d')}>
                            {row.tov_pct_d.toFixed(1)}%
                          </td>
                          <td className="px-4 py-3 font-mono font-semibold" style={getCellStyle(row.tov_edge, 'tov_edge')}>
                            {row.tov_edge > 0 ? '+' : ''}{row.tov_edge.toFixed(1)}%
                          </td>
                          <td className="px-4 py-3 font-mono" style={getCellStyle(row.orb_pct, 'orb_pct')}>
                            {row.orb_pct.toFixed(1)}%
                          </td>
                          <td className="px-4 py-3 font-mono" style={getCellStyle(row.orb_pct_d, 'orb_pct_d', true)}>
                            {row.orb_pct_d.toFixed(1)}%
                          </td>
                          <td className="px-4 py-3 font-mono font-semibold" style={getCellStyle(row.reb_edge, 'reb_edge')}>
                            {row.reb_edge > 0 ? '+' : ''}{row.reb_edge.toFixed(1)}%
                          </td>
                          <td className="px-4 py-3 font-mono" style={getCellStyle(row.ftr, 'ftr')}>
                            {row.ftr.toFixed(1)}
                          </td>
                          <td className="px-4 py-3 font-mono" style={getCellStyle(row.ftr_d, 'ftr_d', true)}>
                            {row.ftr_d.toFixed(1)}
                          </td>
                          <td className="px-4 py-3 font-mono font-semibold" style={getCellStyle(row.ftr_margin, 'ftr_margin')}>
                            {row.ftr_margin > 0 ? '+' : ''}{row.ftr_margin.toFixed(1)}
                          </td>
                          <td className="px-4 py-3 font-mono font-bold" style={getCellStyle(row.four_factor_index_100 || 50, 'four_factor_index_100')}>
                            {row.four_factor_index_100?.toFixed(0) ?? '—'}
                          </td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            
            {data.length === 0 && (
              <div className="text-center py-12 text-gray-500">
                No teams found matching your filters.
              </div>
            )}
            
            {showHeatmap && data.length > 0 && (
              <div className="px-4 py-3 bg-gray-50 border-t border-gray-200 text-xs text-gray-600">
                <div className="flex items-center gap-4">
                  <span className="font-semibold">Legend:</span>
                  <div className="flex items-center gap-2">
                    <div className="w-4 h-4 bg-green-200 rounded"></div>
                    <span>Elite (80%+)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-4 h-4 bg-green-100 rounded"></div>
                    <span>Above Avg (60-80%)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-4 h-4 bg-white border border-gray-200 rounded"></div>
                    <span>Average (40-60%)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-4 h-4 bg-red-100 rounded"></div>
                    <span>Below Avg (20-40%)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-4 h-4 bg-red-200 rounded"></div>
                    <span>Poor (&lt;20%)</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function SortableHeader({
  field,
  current,
  dir,
  onClick,
  children,
}: {
  field: string;
  current: string;
  dir: 'asc' | 'desc';
  onClick: (field: string) => void;
  children: React.ReactNode;
}) {
  const isActive = current === field;
  
  return (
    <th
      onClick={() => onClick(field)}
      className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none transition-colors"
    >
      <div className="flex items-center gap-1">
        {children}
        {isActive && (
          <span className="text-orange-600 font-bold">{dir === 'asc' ? '↑' : '↓'}</span>
        )}
      </div>
    </th>
  );
}

function InfoTooltip({ text }: { text: string }) {
  return (
    <span 
      className="inline-flex items-center justify-center w-4 h-4 text-xs text-gray-400 hover:text-gray-600 cursor-help" 
      title={text}
    >
      ⓘ
    </span>
  );
}
