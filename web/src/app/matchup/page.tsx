'use client';

import { useState, useEffect } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import type { MatchupResult, TopDriver, Team } from '@/types';

export default function MatchupPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  
  const [teams, setTeams] = useState<Team[]>([]);
  const [teamA, setTeamA] = useState('');
  const [teamB, setTeamB] = useState('');
  const [teamAInput, setTeamAInput] = useState('');
  const [teamBInput, setTeamBInput] = useState('');
  const [showTeamADropdown, setShowTeamADropdown] = useState(false);
  const [showTeamBDropdown, setShowTeamBDropdown] = useState(false);
  const [site, setSite] = useState<'neutral' | 'home' | 'away'>('neutral');
  const [result, setResult] = useState<MatchupResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Load teams on mount
  useEffect(() => {
    async function fetchTeams() {
      try {
        console.log('Fetching teams from API...');
        const data = await api.getTeams();
        console.log('Teams loaded:', data.length, 'teams');
        console.log('Sample team:', data[0]);
        setTeams(data);
      } catch (err) {
        console.error('Failed to load teams:', err);
      }
    }
    fetchTeams();
  }, []);
  
  // Load from URL params on mount
  useEffect(() => {
    const urlTeamA = searchParams.get('teamA');
    const urlTeamB = searchParams.get('teamB');
    const urlSite = searchParams.get('site') as 'neutral' | 'home' | 'away' | null;
    
    if (urlTeamA) {
      setTeamA(urlTeamA);
      // Find team name from slug
      const team = teams.find(t => t.slug === urlTeamA);
      setTeamAInput(team ? team.name : urlTeamA);
    }
    if (urlTeamB) {
      setTeamB(urlTeamB);
      // Find team name from slug
      const team = teams.find(t => t.slug === urlTeamB);
      setTeamBInput(team ? team.name : urlTeamB);
    }
    if (urlSite && ['neutral', 'home', 'away'].includes(urlSite)) {
      setSite(urlSite);
    }
    
    // Auto-load if both teams present
    if (urlTeamA && urlTeamB) {
      loadMatchup(urlTeamA, urlTeamB, urlSite || 'neutral');
    }
  }, [searchParams, teams]);
  
  // Filter teams based on input
  function filterTeams(input: string): Team[] {
    if (!input.trim()) return [];
    
    // Safety check: ensure teams is an array
    if (!Array.isArray(teams)) {
      console.log('Teams is not an array:', typeof teams, teams);
      return [];
    }
    
    console.log('Filtering teams with input:', input);
    console.log('Total teams available:', teams.length);
    
    const searchTerm = input.toLowerCase();
    const filtered = teams
      .filter(team => {
        // Match against name
        if (team.name.toLowerCase().includes(searchTerm)) return true;
        // Match against slug
        if (team.slug.toLowerCase().includes(searchTerm)) return true;
        // Match against aliases
        if (team.aliases && team.aliases.some(alias => alias.toLowerCase().includes(searchTerm))) return true;
        return false;
      })
      .slice(0, 10); // Limit to 10 results
    
    console.log('Filtered results:', filtered.length);
    return filtered;
  }
  
  function selectTeamA(team: Team) {
    setTeamA(team.slug);
    setTeamAInput(team.name);
    setShowTeamADropdown(false);
  }
  
  function selectTeamB(team: Team) {
    setTeamB(team.slug);
    setTeamBInput(team.name);
    setShowTeamBDropdown(false);
  }
  
  async function loadMatchup(teamASlug: string, teamBSlug: string, matchSite: string) {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getMatchup(
        teamASlug,
        teamBSlug,
        matchSite as 'neutral' | 'home' | 'away'
      );
      setResult(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load matchup');
      setResult(null);
    } finally {
      setLoading(false);
    }
  }
  
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    
    if (!teamA || !teamB) {
      setError('Please select both teams from the dropdown');
      return;
    }
    
    // Update URL params
    const params = new URLSearchParams();
    params.set('teamA', teamA);
    params.set('teamB', teamB);
    params.set('site', site);
    router.push(`/matchup?${params.toString()}`);
    
    await loadMatchup(teamA, teamB, site);
  }
  
  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="text-4xl font-bold mb-8">Matchup Prediction</h1>
      
      {/* Input Form */}
      <div className="bg-white rounded-lg shadow-md p-6 mb-8">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="relative">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Team A
              </label>
              <input
                type="text"
                value={teamAInput}
                onChange={(e) => {
                  setTeamAInput(e.target.value);
                  setShowTeamADropdown(true);
                }}
                onFocus={() => setShowTeamADropdown(true)}
                onBlur={() => setTimeout(() => setShowTeamADropdown(false), 200)}
                placeholder="Type team name..."
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-primary focus:border-primary"
              />
              {showTeamADropdown && teamAInput && (
                <div className="absolute z-10 w-full mt-1 bg-white border border-gray-300 rounded-md shadow-lg max-h-60 overflow-auto">
                  {filterTeams(teamAInput).map((team) => (
                    <div
                      key={team.id}
                      onClick={() => selectTeamA(team)}
                      className="px-4 py-2 hover:bg-gray-100 cursor-pointer flex items-center gap-2"
                    >
                      {team.logo_url && (
                        <img src={team.logo_url} alt="" className="w-6 h-6" />
                      )}
                      <span>{team.name}</span>
                      <span className="text-sm text-gray-500">({team.slug})</span>
                    </div>
                  ))}
                  {filterTeams(teamAInput).length === 0 && (
                    <div className="px-4 py-2 text-gray-500 text-sm">
                      No teams found
                    </div>
                  )}
                </div>
              )}
            </div>
            
            <div className="relative">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Team B
              </label>
              <input
                type="text"
                value={teamBInput}
                onChange={(e) => {
                  setTeamBInput(e.target.value);
                  setShowTeamBDropdown(true);
                }}
                onFocus={() => setShowTeamBDropdown(true)}
                onBlur={() => setTimeout(() => setShowTeamBDropdown(false), 200)}
                placeholder="Type team name..."
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-primary focus:border-primary"
              />
              {showTeamBDropdown && teamBInput && (
                <div className="absolute z-10 w-full mt-1 bg-white border border-gray-300 rounded-md shadow-lg max-h-60 overflow-auto">
                  {filterTeams(teamBInput).map((team) => (
                    <div
                      key={team.id}
                      onClick={() => selectTeamB(team)}
                      className="px-4 py-2 hover:bg-gray-100 cursor-pointer flex items-center gap-2"
                    >
                      {team.logo_url && (
                        <img src={team.logo_url} alt="" className="w-6 h-6" />
                      )}
                      <span>{team.name}</span>
                      <span className="text-sm text-gray-500">({team.slug})</span>
                    </div>
                  ))}
                  {filterTeams(teamBInput).length === 0 && (
                    <div className="px-4 py-2 text-gray-500 text-sm">
                      No teams found
                    </div>
                  )}
                </div>
              )}
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Site
              </label>
              <select
                value={site}
                onChange={(e) => setSite(e.target.value as any)}
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-primary focus:border-primary"
              >
                <option value="neutral">Neutral Court</option>
                <option value="home">Team A Home</option>
                <option value="away">Team B Home</option>
              </select>
            </div>
          </div>
          
          <button
            type="submit"
            disabled={loading}
            className="w-full md:w-auto px-8 py-3 bg-primary text-white font-bold rounded-md hover:bg-primary-dark disabled:opacity-50 transition-colors"
          >
            {loading ? 'Loading...' : 'Predict Matchup'}
          </button>
        </form>
      </div>
      
      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-8">
          {error}
        </div>
      )}
      
      {/* Results */}
      {result && (
        <div className="space-y-6">
          {/* Forecast Section */}
          <ForecastSection result={result} />
          
          {/* Four Factor Breakdown */}
          <FourFactorSection result={result} />
          
          {/* Top Drivers */}
          <TopDriversSection drivers={result.top_drivers} teamA={result.teamA.name} teamB={result.teamB.name} />
          
          {/* Shot Profile */}
          {result.shot_profile && (
            <ShotProfileSection profile={result.shot_profile} teamA={result.teamA.name} teamB={result.teamB.name} />
          )}
          
          {/* Volatility */}
          <VolatilitySection volatility={result.volatility} />
          
          {/* Recent Form */}
          <RecentFormSection
            teamA={result.teamA}
            teamB={result.teamB}
            formA={result.recent_form_a}
            formB={result.recent_form_b}
          />
          
          {/* Metadata Footer */}
          <MetadataSection metadata={result.metadata} season={result.season} />
        </div>
      )}
    </div>
  );
}

// ==================== Forecast Section ====================

function ForecastSection({ result }: { result: MatchupResult }) {
  const { forecast, teamA, teamB } = result;
  const favorite = forecast.margin > 0 ? teamA : teamB;
  
  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-2xl font-bold mb-6 text-center">Game Forecast</h2>
      
      {/* Team Headers with Logos */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="text-center">
          {teamA.logo_url && (
            <img src={teamA.logo_url} alt={teamA.name} className="w-20 h-20 mx-auto mb-2 object-contain" />
          )}
          <p className="text-lg font-bold">{teamA.name}</p>
          <p className="text-sm text-gray-600">#{teamA.rank} • {teamA.record}</p>
        </div>
        
        <div className="flex items-center justify-center">
          <div className="text-center">
            <p className="text-sm text-gray-600 mb-1">vs</p>
            <p className="text-xs text-gray-500">
              {result.site === 'home' ? `@ ${teamA.name}` : 
               result.site === 'away' ? `@ ${teamB.name}` : 
               'Neutral'}
            </p>
          </div>
        </div>
        
        <div className="text-center">
          {teamB.logo_url && (
            <img src={teamB.logo_url} alt={teamB.name} className="w-20 h-20 mx-auto mb-2 object-contain" />
          )}
          <p className="text-lg font-bold">{teamB.name}</p>
          <p className="text-sm text-gray-600">#{teamB.rank} • {teamB.record}</p>
        </div>
      </div>
      
      {/* Predicted Score */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="text-center">
          <p className="text-5xl font-bold text-blue mono">
            {forecast.pts_a.toFixed(0)}
          </p>
          <p className="text-sm text-gray-600 mt-1">Predicted Score</p>
        </div>
        
        <div className="flex items-center justify-center">
          <div className="text-center">
            <p className="text-sm text-gray-600 mb-2">Expected Margin</p>
            <p className="text-3xl font-bold mono">
              {forecast.margin > 0 ? '+' : ''}
              {forecast.margin.toFixed(1)}
            </p>
            <p className="text-xs text-gray-500 mt-2">
              95% CI: {forecast.margin_low.toFixed(1)} to {forecast.margin_high.toFixed(1)}
            </p>
          </div>
        </div>
        
        <div className="text-center">
          <p className="text-5xl font-bold text-primary mono">
            {forecast.pts_b.toFixed(0)}
          </p>
          <p className="text-sm text-gray-600 mt-1">Predicted Score</p>
        </div>
      </div>
      
      {/* Win Probability Meter */}
      <div className="mb-4">
        <div className="flex justify-between mb-2">
          <span className="text-lg font-bold">
            {(forecast.prob_a * 100).toFixed(1)}%
          </span>
          <span className="text-sm text-gray-600">Win Probability</span>
          <span className="text-lg font-bold">
            {(forecast.prob_b * 100).toFixed(1)}%
          </span>
        </div>
        <div className="w-full h-8 bg-gray-200 rounded-full overflow-hidden relative">
          <div
            className="h-full bg-gradient-to-r from-blue-500 to-blue-600 transition-all"
            style={{ width: `${forecast.prob_a * 100}%` }}
          />
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-xs font-medium text-white mix-blend-difference">
              {favorite.name} favored
            </span>
          </div>
        </div>
      </div>
      
      {/* Game Pace */}
      <div className="text-center pt-4 border-t border-gray-200">
        <p className="text-sm text-gray-600">
          Expected Pace: <span className="font-bold">{forecast.pace.toFixed(1)}</span> possessions
        </p>
      </div>
    </div>
  );
}

// ==================== Four Factor Section ====================

function FourFactorSection({ result }: { result: MatchupResult }) {
  const { four_factor_edges, points_breakdown, teamA, teamB } = result;
  
  const factors = [
    { 
      name: 'Effective FG%', 
      key: 'efg',
      edge: four_factor_edges.efg_edge,
      valueA: four_factor_edges.exp_efg_a,
      valueB: four_factor_edges.exp_efg_b,
      pointsImpact: points_breakdown.pts_from_efg
    },
    { 
      name: 'Turnover Rate', 
      key: 'tov',
      edge: four_factor_edges.tov_edge,
      valueA: four_factor_edges.exp_tov_a,
      valueB: four_factor_edges.exp_tov_b,
      pointsImpact: points_breakdown.pts_from_tov
    },
    { 
      name: 'Offensive Reb%', 
      key: 'orb',
      edge: four_factor_edges.orb_edge,
      valueA: four_factor_edges.exp_orb_a,
      valueB: four_factor_edges.exp_orb_b,
      pointsImpact: points_breakdown.pts_from_orb
    },
    { 
      name: 'Free Throw Rate', 
      key: 'ftr',
      edge: four_factor_edges.ftr_edge,
      valueA: four_factor_edges.exp_ftr_a,
      valueB: four_factor_edges.exp_ftr_b,
      pointsImpact: points_breakdown.pts_from_ftr
    },
  ];
  
  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-2xl font-bold mb-6">Four Factor Breakdown</h2>
      
      <div className="space-y-6">
        {factors.map((factor) => (
          <div key={factor.key}>
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm font-medium">{factor.name}</span>
              <span className="text-sm font-bold mono">
                Edge: {factor.edge > 0 ? '+' : ''}{factor.edge.toFixed(2)}%
              </span>
            </div>
            
            {/* Values */}
            <div className="flex justify-between text-xs text-gray-600 mb-2">
              <span>{teamA.name}: {factor.valueA.toFixed(1)}%</span>
              <span>{teamB.name}: {factor.valueB.toFixed(1)}%</span>
            </div>
            
            {/* Bar */}
            <div className="relative">
              <FactorBar value={factor.edge} />
            </div>
            
            {/* Points Impact */}
            <div className="flex justify-between text-xs text-gray-500 mt-2">
              <span className="font-bold">
                Impact: {factor.pointsImpact > 0 ? '+' : ''}{factor.pointsImpact.toFixed(1)} pts
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function FactorBar({ value }: { value: number }) {
  const percentage = Math.min(Math.abs(value) / 10 * 100, 100); // Scale: 10% edge = 100% bar
  const color = value > 0 ? 'bg-blue-500' : 'bg-orange-500';
  
  return (
    <div className="w-full h-6 bg-gray-200 rounded overflow-hidden">
      <div
        className={`h-full ${color} transition-all`}
        style={{
          width: `${percentage}%`,
          marginLeft: value < 0 ? `${100 - percentage}%` : '0',
        }}
      />
    </div>
  );
}

// ==================== Top Drivers Section ====================

function TopDriversSection({ drivers, teamA, teamB }: { drivers: TopDriver[]; teamA: string; teamB: string }) {
  // Generate description based on driver data
  const getDescription = (driver: TopDriver) => {
    const leadingTeam = driver.team === 'a' ? teamA : teamB;
    const trailingTeam = driver.team === 'a' ? teamB : teamA;
    return `${leadingTeam} has a ${Math.abs(driver.edge).toFixed(1)}% advantage in ${driver.factor}, contributing ${Math.abs(driver.points).toFixed(1)} points`;
  };
  
  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-2xl font-bold mb-4">Top 3 Key Drivers</h2>
      <p className="text-sm text-gray-600 mb-6">
        The most impactful factors in this matchup prediction
      </p>
      
      <div className="space-y-4">
        {drivers.map((driver, index) => (
          <div key={index} className="border-l-4 border-orange-500 pl-4 py-2">
            <div className="flex justify-between items-start">
              <div>
                <p className="font-bold text-lg">
                  {index + 1}. {driver.factor}
                </p>
                <p className="text-sm text-gray-700 mt-1">
                  {getDescription(driver)}
                </p>
              </div>
              <div className="text-right ml-4">
                <p className="text-2xl font-bold mono">
                  {driver.points > 0 ? '+' : ''}{driver.points.toFixed(1)}
                </p>
                <p className="text-xs text-gray-600">pts impact</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ==================== Shot Profile Section ====================

function ShotProfileSection({ profile, teamA, teamB }: { profile: any; teamA: string; teamB: string }) {
  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-2xl font-bold mb-6">Shot Profile Analysis</h2>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* 3P Rate */}
        <div>
          <p className="text-sm font-medium text-gray-700 mb-3">3-Point Attempt Rate</p>
          <div className="flex justify-between mb-2">
            <span className="text-sm">{teamA}</span>
            <span className="text-sm font-bold">{profile.fg3_rate_a.toFixed(1)}%</span>
          </div>
          <div className="flex justify-between mb-2">
            <span className="text-sm">{teamB}</span>
            <span className="text-sm font-bold">{profile.fg3_rate_b.toFixed(1)}%</span>
          </div>
          <p className="text-xs text-gray-600 mt-2">
            Edge: <span className={profile.fg3_rate_edge > 0 ? 'text-blue-600 font-bold' : 'text-orange-600 font-bold'}>
              {profile.fg3_rate_edge > 0 ? '+' : ''}{profile.fg3_rate_edge.toFixed(1)}%
            </span>
          </p>
        </div>
        
        {/* 3P% */}
        <div>
          <p className="text-sm font-medium text-gray-700 mb-3">3-Point Percentage</p>
          <div className="flex justify-between mb-2">
            <span className="text-sm">{teamA}</span>
            <span className="text-sm font-bold">{profile.fg3_pct_a.toFixed(1)}%</span>
          </div>
          <div className="flex justify-between mb-2">
            <span className="text-sm">{teamB}</span>
            <span className="text-sm font-bold">{profile.fg3_pct_b.toFixed(1)}%</span>
          </div>
          <p className="text-xs text-gray-600 mt-2">
            Edge: <span className={profile.fg3_pct_edge > 0 ? 'text-blue-600 font-bold' : 'text-orange-600 font-bold'}>
              {profile.fg3_pct_edge > 0 ? '+' : ''}{profile.fg3_pct_edge.toFixed(1)}%
            </span>
          </p>
        </div>
        
        {/* 2P% */}
        <div>
          <p className="text-sm font-medium text-gray-700 mb-3">2-Point Percentage</p>
          <div className="flex justify-between mb-2">
            <span className="text-sm">{teamA}</span>
            <span className="text-sm font-bold">{profile.fg2_pct_a.toFixed(1)}%</span>
          </div>
          <div className="flex justify-between mb-2">
            <span className="text-sm">{teamB}</span>
            <span className="text-sm font-bold">{profile.fg2_pct_b.toFixed(1)}%</span>
          </div>
          <p className="text-xs text-gray-600 mt-2">
            Edge: <span className={profile.fg2_pct_edge > 0 ? 'text-blue-600 font-bold' : 'text-orange-600 font-bold'}>
              {profile.fg2_pct_edge > 0 ? '+' : ''}{profile.fg2_pct_edge.toFixed(1)}%
            </span>
          </p>
        </div>
      </div>
    </div>
  );
}

// ==================== Volatility Section ====================

function VolatilitySection({ volatility }: { volatility: any }) {
  const getVolatilityColor = (score: number) => {
    if (score < 30) return 'text-green-600';
    if (score < 60) return 'text-yellow-600';
    if (score < 80) return 'text-orange-600';
    return 'text-red-600';
  };
  
  const getVolatilityLabel = (score: number) => {
    if (score < 30) return 'Low';
    if (score < 60) return 'Moderate';
    if (score < 80) return 'High';
    return 'Extreme';
  };
  
  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-2xl font-bold mb-4">Game Volatility</h2>
      <p className="text-sm text-gray-600 mb-6">
        Measures game unpredictability based on pace, 3-point volume, and recent variance
      </p>
      
      <div className="flex items-center justify-center mb-6">
        <div className="text-center">
          <p className={`text-6xl font-bold ${getVolatilityColor(volatility.volatility_score)}`}>
            {volatility.volatility_score.toFixed(0)}
          </p>
          <p className="text-xl font-semibold text-gray-700 mt-2">
            {getVolatilityLabel(volatility.volatility_score)} Volatility
          </p>
        </div>
      </div>
      
      {/* Volatility Meter */}
      <div className="mb-6">
        <div className="w-full h-8 rounded-full overflow-hidden relative"
             style={{
               background: 'linear-gradient(to right, #10b981 0%, #fbbf24 30%, #f59e0b 60%, #ef4444 100%)'
             }}>
          <div className="absolute inset-0 flex items-center">
            <div 
              className="w-1 h-full bg-black shadow-lg"
              style={{ marginLeft: `${volatility.volatility_score}%` }}
            />
          </div>
        </div>
        <div className="flex justify-between text-xs text-gray-600 mt-1">
          <span>Low (0)</span>
          <span>Moderate (50)</span>
          <span>Extreme (100)</span>
        </div>
      </div>
      
      {/* Component Scores */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="text-center p-3 bg-gray-50 rounded">
          <p className="text-2xl font-bold">{volatility.pace_component.toFixed(0)}</p>
          <p className="text-xs text-gray-600 mt-1">Pace</p>
        </div>
        <div className="text-center p-3 bg-gray-50 rounded">
          <p className="text-2xl font-bold">{volatility.three_pt_component.toFixed(0)}</p>
          <p className="text-xs text-gray-600 mt-1">3P Volume</p>
        </div>
        <div className="text-center p-3 bg-gray-50 rounded">
          <p className="text-2xl font-bold">{volatility.variance_component.toFixed(0)}</p>
          <p className="text-xs text-gray-600 mt-1">Variance</p>
        </div>
      </div>
      
      {/* Reasons */}
      {volatility.reasons && volatility.reasons.length > 0 && (
        <div>
          <p className="font-semibold mb-2">Key Factors:</p>
          <ul className="space-y-1">
            {volatility.reasons.map((reason: string, index: number) => (
              <li key={index} className="text-sm text-gray-700 flex items-start">
                <span className="mr-2">•</span>
                <span>{reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ==================== Recent Form Section ====================

function RecentFormSection({ teamA, teamB, formA, formB }: any) {
  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-2xl font-bold mb-6">Recent Form (Last {formA.games_analyzed} Games)</h2>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Team A */}
        <div>
          <h3 className="text-lg font-bold mb-4">{teamA.name}</h3>
          
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className="text-center p-3 bg-blue-50 rounded">
              <p className="text-xl font-bold text-blue-600">{formA.record}</p>
              <p className="text-xs text-gray-600">Record</p>
            </div>
            <div className="text-center p-3 bg-gray-50 rounded">
              <p className="text-xl font-bold">{formA.avg_margin > 0 ? '+' : ''}{formA.avg_margin.toFixed(1)}</p>
              <p className="text-xs text-gray-600">Avg Margin</p>
            </div>
            <div className="text-center p-3 bg-gray-50 rounded">
              <p className="text-xl font-bold">±{formA.variance.toFixed(1)}</p>
              <p className="text-xs text-gray-600">Variance</p>
            </div>
          </div>
          
          {formA.games && formA.games.length > 0 && (
            <div className="space-y-2">
              {formA.games.map((game: any, index: number) => (
                <div key={index} className="flex items-center justify-between text-sm border-b border-gray-100 pb-2">
                  <span className={`font-bold w-6 ${game.result === 'W' ? 'text-green-600' : 'text-red-600'}`}>
                    {game.result}
                  </span>
                  <span className="flex-1 ml-3 text-gray-700 truncate">{game.opponent}</span>
                  <span className="font-mono text-gray-600 text-xs ml-2">{game.score}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        
        {/* Team B */}
        <div>
          <h3 className="text-lg font-bold mb-4">{teamB.name}</h3>
          
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className="text-center p-3 bg-orange-50 rounded">
              <p className="text-xl font-bold text-orange-600">{formB.record}</p>
              <p className="text-xs text-gray-600">Record</p>
            </div>
            <div className="text-center p-3 bg-gray-50 rounded">
              <p className="text-xl font-bold">{formB.avg_margin > 0 ? '+' : ''}{formB.avg_margin.toFixed(1)}</p>
              <p className="text-xs text-gray-600">Avg Margin</p>
            </div>
            <div className="text-center p-3 bg-gray-50 rounded">
              <p className="text-xl font-bold">±{formB.variance.toFixed(1)}</p>
              <p className="text-xs text-gray-600">Variance</p>
            </div>
          </div>
          
          {formB.games && formB.games.length > 0 && (
            <div className="space-y-2">
              {formB.games.map((game: any, index: number) => (
                <div key={index} className="flex items-center justify-between text-sm border-b border-gray-100 pb-2">
                  <span className={`font-bold w-6 ${game.result === 'W' ? 'text-green-600' : 'text-red-600'}`}>
                    {game.result}
                  </span>
                  <span className="flex-1 ml-3 text-gray-700 truncate">{game.opponent}</span>
                  <span className="font-mono text-gray-600 text-xs ml-2">{game.score}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ==================== Metadata Footer ====================

function MetadataSection({ metadata, season }: { metadata: any; season: string }) {
  return (
    <div className="bg-gray-50 rounded-lg p-4 text-xs text-gray-600">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <p className="font-semibold">Season</p>
          <p>{season}</p>
        </div>
        <div>
          <p className="font-semibold">HCA</p>
          <p>{metadata.hca_points.toFixed(2)} points</p>
        </div>
        <div>
          <p className="font-semibold">Prediction σ</p>
          <p>{metadata.prediction_sigma.toFixed(2)} points</p>
        </div>
        <div>
          <p className="font-semibold">Model R²</p>
          <p>{metadata.coefficients.r_squared?.toFixed(3) || 'N/A'}</p>
        </div>
      </div>
    </div>
  );
}

