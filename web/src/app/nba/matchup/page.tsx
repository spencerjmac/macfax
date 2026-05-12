'use client';

import { useState, useEffect, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { nbaApi } from '@/lib/nba-api';
import { getTeamColors, withOpacity, DEFAULT_A, DEFAULT_B, type TeamColors } from '@/lib/team-colors';
import { extractDominantColor } from '@/lib/color-extract';
import type { NBATeam, NBAMatchupResult, NBASeriesPrediction } from '@/types/nba';

export const dynamic = 'force-dynamic';

function MatchupPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [teams, setTeams] = useState<NBATeam[]>([]);
  const [teamA, setTeamA] = useState('');
  const [teamB, setTeamB] = useState('');
  const [teamAInput, setTeamAInput] = useState('');
  const [teamBInput, setTeamBInput] = useState('');
  const [showTeamADropdown, setShowTeamADropdown] = useState(false);
  const [showTeamBDropdown, setShowTeamBDropdown] = useState(false);
  const [site, setSite] = useState<'neutral' | 'home' | 'away'>('neutral');
  const [mode, setMode] = useState<'game' | 'series'>('game');
  const [result, setResult] = useState<NBAMatchupResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [colorA, setColorA] = useState<TeamColors>(DEFAULT_A);
  const [colorB, setColorB] = useState<TeamColors>(DEFAULT_B);

  // Apply team colors whenever result changes
  useEffect(() => {
    if (!result) {
      setColorA(DEFAULT_A);
      setColorB(DEFAULT_B);
      return;
    }

    setColorA(getTeamColors(result.teamA.slug) ?? DEFAULT_A);
    setColorB(getTeamColors(result.teamB.slug) ?? DEFAULT_B);

    let cancelled = false;

    async function fetchColor(
      teamName: string,
      teamSlug: string,
      logoUrl: string | null,
      setter: (c: TeamColors) => void,
    ) {
      try {
        const res = await fetch(
          `/api/team-colors?name=${encodeURIComponent(teamName)}&slug=${encodeURIComponent(teamSlug)}`
        );
        if (res.ok) {
          const data = await res.json() as { primary: string; secondary: string };
          if (!cancelled && data.primary) {
            setter({ primary: data.primary, secondary: data.secondary ?? data.primary });
            return;
          }
        }
      } catch { /* fall through */ }

      if (logoUrl) {
        const extracted = await extractDominantColor(logoUrl);
        if (!cancelled && extracted) {
          setter({ primary: extracted, secondary: extracted });
        }
      }
    }

    fetchColor(result.teamA.name, result.teamA.slug, result.teamA.logo_url, setColorA);
    fetchColor(result.teamB.name, result.teamB.slug, result.teamB.logo_url, setColorB);

    return () => { cancelled = true; };
  }, [result]);

  // Load teams on mount
  useEffect(() => {
    nbaApi.getTeams().then(setTeams).catch(console.error);
  }, []);

  // Load from URL params
  useEffect(() => {
    const urlTeamA = searchParams.get('teamA');
    const urlTeamB = searchParams.get('teamB');
    const urlSite = searchParams.get('site') as 'neutral' | 'home' | 'away' | null;
    const urlMode = searchParams.get('mode') as 'game' | 'series' | null;

    if (urlTeamA) {
      setTeamA(urlTeamA);
      const team = teams.find(t => t.slug === urlTeamA);
      setTeamAInput(team ? team.name : urlTeamA);
    }
    if (urlTeamB) {
      setTeamB(urlTeamB);
      const team = teams.find(t => t.slug === urlTeamB);
      setTeamBInput(team ? team.name : urlTeamB);
    }
    if (urlSite && ['neutral', 'home', 'away'].includes(urlSite)) setSite(urlSite);
    if (urlMode && ['game', 'series'].includes(urlMode)) setMode(urlMode);

    if (urlTeamA && urlTeamB) {
      loadMatchup(urlTeamA, urlTeamB, urlSite || 'neutral', urlMode || 'game');
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, teams]);

  function filterTeams(input: string): NBATeam[] {
    if (!input.trim() || !Array.isArray(teams)) return [];
    const q = input.toLowerCase();
    return teams
      .filter(t =>
        t.name.toLowerCase().includes(q) ||
        t.slug.toLowerCase().includes(q) ||
        t.abbreviation.toLowerCase().includes(q) ||
        t.city.toLowerCase().includes(q)
      )
      .slice(0, 10);
  }

  function selectTeamA(team: NBATeam) {
    setTeamA(team.slug);
    setTeamAInput(team.name);
    setShowTeamADropdown(false);
  }

  function selectTeamB(team: NBATeam) {
    setTeamB(team.slug);
    setTeamBInput(team.name);
    setShowTeamBDropdown(false);
  }

  async function loadMatchup(aSlug: string, bSlug: string, matchSite: string, matchMode: string) {
    try {
      setLoading(true);
      setError(null);
      const data = await nbaApi.getMatchup(
        aSlug, bSlug,
        matchSite as 'neutral' | 'home' | 'away',
        undefined,
        matchMode as 'game' | 'series',
      );
      setResult(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load matchup');
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!teamA || !teamB) {
      setError('Please select both teams');
      return;
    }
    const params = new URLSearchParams({ teamA, teamB, site, mode });
    router.push(`/nba/matchup?${params.toString()}`);
    await loadMatchup(teamA, teamB, site, mode);
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="text-4xl font-bold mb-8">NBA Matchup Predictor</h1>

      {/* Input Form */}
      <div className="bg-white rounded-lg shadow-md p-6 mb-8">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {/* Team A */}
            <div className="relative">
              <label className="block text-sm font-medium text-gray-700 mb-2">Team A</label>
              <input
                type="text"
                value={teamAInput}
                onChange={e => { setTeamAInput(e.target.value); setShowTeamADropdown(true); }}
                onFocus={() => setShowTeamADropdown(true)}
                onBlur={() => setTimeout(() => setShowTeamADropdown(false), 200)}
                placeholder="Search NBA team..."
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-primary focus:border-primary"
              />
              {showTeamADropdown && teamAInput && (
                <div className="absolute z-10 w-full mt-1 bg-white border border-gray-300 rounded-md shadow-lg max-h-60 overflow-auto">
                  {filterTeams(teamAInput).map(team => (
                    <div key={team.id} onClick={() => selectTeamA(team)}
                      className="px-4 py-2 hover:bg-gray-100 cursor-pointer flex items-center gap-2">
                      {team.logo_url && <img src={team.logo_url} alt="" className="w-6 h-6" />}
                      <span>{team.name}</span>
                      <span className="text-xs text-gray-400">{team.abbreviation}</span>
                    </div>
                  ))}
                  {filterTeams(teamAInput).length === 0 && (
                    <div className="px-4 py-2 text-gray-500 text-sm">No teams found</div>
                  )}
                </div>
              )}
            </div>

            {/* Team B */}
            <div className="relative">
              <label className="block text-sm font-medium text-gray-700 mb-2">Team B</label>
              <input
                type="text"
                value={teamBInput}
                onChange={e => { setTeamBInput(e.target.value); setShowTeamBDropdown(true); }}
                onFocus={() => setShowTeamBDropdown(true)}
                onBlur={() => setTimeout(() => setShowTeamBDropdown(false), 200)}
                placeholder="Search NBA team..."
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-primary focus:border-primary"
              />
              {showTeamBDropdown && teamBInput && (
                <div className="absolute z-10 w-full mt-1 bg-white border border-gray-300 rounded-md shadow-lg max-h-60 overflow-auto">
                  {filterTeams(teamBInput).map(team => (
                    <div key={team.id} onClick={() => selectTeamB(team)}
                      className="px-4 py-2 hover:bg-gray-100 cursor-pointer flex items-center gap-2">
                      {team.logo_url && <img src={team.logo_url} alt="" className="w-6 h-6" />}
                      <span>{team.name}</span>
                      <span className="text-xs text-gray-400">{team.abbreviation}</span>
                    </div>
                  ))}
                  {filterTeams(teamBInput).length === 0 && (
                    <div className="px-4 py-2 text-gray-500 text-sm">No teams found</div>
                  )}
                </div>
              )}
            </div>

            {/* Site */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Site</label>
              <select value={site} onChange={e => setSite(e.target.value as 'neutral' | 'home' | 'away')}
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-primary focus:border-primary">
                <option value="neutral">Neutral Court</option>
                <option value="home">Team A Home</option>
                <option value="away">Team B Home</option>
              </select>
            </div>

            {/* Mode */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Mode</label>
              <select value={mode} onChange={e => setMode(e.target.value as 'game' | 'series')}
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-primary focus:border-primary">
                <option value="game">Single Game</option>
                <option value="series">7-Game Series</option>
              </select>
            </div>
          </div>

          <button type="submit" disabled={loading}
            className="w-full md:w-auto px-8 py-3 bg-primary text-white font-bold rounded-md hover:bg-primary-dark disabled:opacity-50 transition-colors">
            {loading ? 'Loading...' : 'Predict Matchup'}
          </button>
        </form>
      </div>

      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-8">
          {error}
        </div>
      )}

      {result && (
        <div className="space-y-6">
          <ForecastSection result={result} colorA={colorA} colorB={colorB} />
          <FourFactorSection result={result} colorA={colorA} colorB={colorB} />
          {result.top_drivers && result.top_drivers.length > 0 && (
            <TopDriversSection drivers={result.top_drivers} teamA={result.teamA.name} teamB={result.teamB.name} colorA={colorA} colorB={colorB} />
          )}
          {result.shot_profile && (
            <ShotProfileSection profile={result.shot_profile} teamA={result.teamA.name} teamB={result.teamB.name} colorA={colorA} colorB={colorB} />
          )}
          {result.series_prediction && (
            <SeriesSection series={result.series_prediction} teamA={result.teamA} teamB={result.teamB} colorA={colorA} colorB={colorB} />
          )}
          <VolatilitySection volatility={result.volatility} />
          <RecentFormSection teamA={result.teamA} teamB={result.teamB} formA={result.recent_form_a} formB={result.recent_form_b} colorA={colorA} colorB={colorB} />
          <MetadataSection metadata={result.metadata} season={result.season} />
        </div>
      )}
    </div>
  );
}

export default function NBAMatchupPage() {
  return (
    <Suspense fallback={<div className="container mx-auto px-4 py-8">Loading...</div>}>
      <MatchupPageInner />
    </Suspense>
  );
}

// ==================== Forecast Section ====================

function ForecastSection({ result, colorA, colorB }: { result: NBAMatchupResult; colorA: TeamColors; colorB: TeamColors }) {
  const { forecast, teamA, teamB } = result;
  const favorite = forecast.margin > 0 ? teamA : teamB;

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-2xl font-bold mb-6 text-center">
        {result.mode === 'series' ? 'Game Forecast (Game 1)' : 'Game Forecast'}
      </h2>

      {/* Team headers */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="text-center">
          {teamA.logo_url && (
            <img src={teamA.logo_url} alt={teamA.name} className="w-20 h-20 mx-auto mb-2 object-contain" />
          )}
          <p className="text-lg font-bold" style={{ color: colorA.primary }}>{teamA.name}</p>
          <div className="w-12 h-1 mx-auto rounded-full mt-1 mb-1" style={{ backgroundColor: colorA.primary }} />
          <p className="text-xs text-gray-500">{teamA.conference} · {teamA.division}</p>
          {teamA.rank && <p className="text-sm text-gray-600">#{teamA.rank}</p>}
          <p className="text-sm text-gray-600">{teamA.record}</p>
        </div>

        <div className="flex items-center justify-center">
          <div className="text-center">
            <p className="text-sm text-gray-600 mb-1">vs</p>
            <p className="text-xs text-gray-500">
              {result.site === 'home' ? `@ ${teamA.name}` :
               result.site === 'away' ? `@ ${teamB.name}` : 'Neutral'}
            </p>
          </div>
        </div>

        <div className="text-center">
          {teamB.logo_url && (
            <img src={teamB.logo_url} alt={teamB.name} className="w-20 h-20 mx-auto mb-2 object-contain" />
          )}
          <p className="text-lg font-bold" style={{ color: colorB.primary }}>{teamB.name}</p>
          <div className="w-12 h-1 mx-auto rounded-full mt-1 mb-1" style={{ backgroundColor: colorB.primary }} />
          <p className="text-xs text-gray-500">{teamB.conference} · {teamB.division}</p>
          {teamB.rank && <p className="text-sm text-gray-600">#{teamB.rank}</p>}
          <p className="text-sm text-gray-600">{teamB.record}</p>
        </div>
      </div>

      {/* Predicted Score */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="text-center">
          <p className="text-5xl font-bold mono" style={{ color: colorA.primary }}>
            {forecast.pts_a.toFixed(0)}
          </p>
          <p className="text-sm text-gray-600 mt-1">Predicted Score</p>
        </div>

        <div className="flex items-center justify-center">
          <div className="text-center">
            <p className="text-sm text-gray-600 mb-2">Expected Margin</p>
            <p className="text-3xl font-bold mono">
              {forecast.margin > 0 ? '+' : ''}{forecast.margin.toFixed(1)}
            </p>
            <p className="text-xs text-gray-500 mt-2">
              Score range: {forecast.margin_low.toFixed(1)} to {forecast.margin_high.toFixed(1)}
            </p>
          </div>
        </div>

        <div className="text-center">
          <p className="text-5xl font-bold mono" style={{ color: colorB.primary }}>
            {forecast.pts_b.toFixed(0)}
          </p>
          <p className="text-sm text-gray-600 mt-1">Predicted Score</p>
        </div>
      </div>

      {/* Win Probability Bar */}
      <div className="mb-4">
        <div className="flex justify-between mb-2">
          <span className="text-lg font-bold" style={{ color: colorA.primary }}>
            {(forecast.prob_a * 100).toFixed(1)}%
          </span>
          <span className="text-sm text-gray-600">Win Probability</span>
          <span className="text-lg font-bold" style={{ color: colorB.primary }}>
            {(forecast.prob_b * 100).toFixed(1)}%
          </span>
        </div>
        <div className="w-full h-8 rounded-full overflow-hidden flex relative">
          <div className="h-full transition-all" style={{ width: `${forecast.prob_a * 100}%`, backgroundColor: colorA.primary }} />
          <div className="h-full transition-all flex-1" style={{ backgroundColor: colorB.primary }} />
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <span className="text-xs font-medium text-white drop-shadow">{favorite.name} favored</span>
          </div>
        </div>
        <div className="flex justify-between mt-1 text-xs">
          <span style={{ color: colorA.primary }} className="font-semibold">{teamA.name}</span>
          <span style={{ color: colorB.primary }} className="font-semibold">{teamB.name}</span>
        </div>
      </div>

      {/* Ratings comparison */}
      <div className="grid grid-cols-3 gap-4 mt-4 pt-4 border-t border-gray-100 text-sm">
        <div className="text-center">
          <p className="font-bold" style={{ color: colorA.primary }}>{teamA.adj_o.toFixed(1)}</p>
          <p className="text-xs text-gray-500 mt-0.5">Adj. Offense</p>
        </div>
        <div className="text-center">
          <p className="text-xs text-gray-600">Expected Pace</p>
          <p className="font-bold">{forecast.pace.toFixed(1)}</p>
          <p className="text-xs text-gray-500">possessions</p>
        </div>
        <div className="text-center">
          <p className="font-bold" style={{ color: colorB.primary }}>{teamB.adj_o.toFixed(1)}</p>
          <p className="text-xs text-gray-500 mt-0.5">Adj. Offense</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 mt-2 text-sm">
        <div className="text-center">
          <p className="font-bold" style={{ color: colorA.primary }}>{teamA.adj_d.toFixed(1)}</p>
          <p className="text-xs text-gray-500 mt-0.5">Adj. Defense</p>
        </div>
        <div className="text-center">
          <p className="font-bold" style={{ color: colorB.primary }}>{teamB.adj_d.toFixed(1)}</p>
          <p className="text-xs text-gray-500 mt-0.5">Adj. Defense</p>
        </div>
      </div>
    </div>
  );
}

// ==================== Four Factor Section ====================

function FourFactorSection({ result, colorA, colorB }: { result: NBAMatchupResult; colorA: TeamColors; colorB: TeamColors }) {
  const { four_factor_edges, teamA, teamB } = result;

  const factors = [
    { name: 'Effective FG%', key: 'efg', edge: four_factor_edges.efg_edge, valueA: four_factor_edges.exp_efg_a, valueB: four_factor_edges.exp_efg_b },
    { name: 'Turnover Rate', key: 'tov', edge: four_factor_edges.tov_edge, valueA: four_factor_edges.exp_tov_a, valueB: four_factor_edges.exp_tov_b },
    { name: 'Off. Reb%', key: 'orb', edge: four_factor_edges.orb_edge, valueA: four_factor_edges.exp_orb_a, valueB: four_factor_edges.exp_orb_b },
    { name: 'FT Rate (FTA/FGA)', key: 'ftr', edge: four_factor_edges.ftr_edge, valueA: four_factor_edges.exp_ftr_a, valueB: four_factor_edges.exp_ftr_b },
  ];

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-2xl font-bold mb-2">Efficiency Profile</h2>

      <div className="flex gap-4 mb-5 text-xs font-medium">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: colorA.primary }} />
          <span style={{ color: colorA.primary }}>{teamA.name} edge</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: colorB.primary }} />
          <span style={{ color: colorB.primary }}>{teamB.name} edge</span>
        </span>
      </div>

      <div className="space-y-6">
        {factors.map(factor => (
          <div key={factor.key}>
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm font-medium">{factor.name}</span>
              <span className="text-sm font-bold mono">
                Edge: {factor.edge > 0 ? '+' : ''}{factor.edge.toFixed(2)}%
              </span>
            </div>
            <div className="flex justify-between text-xs font-medium mb-2">
              <span style={{ color: colorA.primary }}>{teamA.name}: {factor.valueA.toFixed(1)}%</span>
              <span style={{ color: colorB.primary }}>{teamB.name}: {factor.valueB.toFixed(1)}%</span>
            </div>
            <FactorBar value={factor.edge} colorA={colorA} colorB={colorB} />
          </div>
        ))}
      </div>

      <div className="mt-4 pt-4 border-t border-gray-100 flex justify-between text-sm">
        <span className="text-gray-600">FFI Edge</span>
        <span className="font-bold mono" style={{ color: result.ffi_edge > 0 ? colorA.primary : colorB.primary }}>
          {result.ffi_edge > 0 ? '+' : ''}{result.ffi_edge.toFixed(1)}
        </span>
      </div>
    </div>
  );
}

function FactorBar({ value, colorA, colorB }: { value: number; colorA: TeamColors; colorB: TeamColors }) {
  const percentage = Math.min(Math.abs(value) / 10 * 100, 100);
  const bg = value > 0 ? colorA.primary : colorB.primary;
  return (
    <div className="w-full h-6 bg-gray-200 rounded overflow-hidden">
      <div className="h-full transition-all" style={{
        width: `${percentage}%`,
        marginLeft: value < 0 ? `${100 - percentage}%` : '0',
        backgroundColor: bg,
      }} />
    </div>
  );
}

// ==================== Top Drivers Section ====================

function TopDriversSection({ drivers, teamA, teamB, colorA, colorB }: {
  drivers: NonNullable<NBAMatchupResult['top_drivers']>;
  teamA: string;
  teamB: string;
  colorA: TeamColors;
  colorB: TeamColors;
}) {
  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-2xl font-bold mb-2">Key Matchup Drivers</h2>
      <p className="text-sm text-gray-600 mb-6">Top factors contributing to the projected margin</p>
      <div className="space-y-4">
        {drivers.map((driver, i) => {
          const leadTeam = driver.team === 'a' ? teamA : teamB;
          const color = driver.team === 'a' ? colorA.primary : colorB.primary;
          return (
            <div key={i} className="border-l-4 pl-4 py-2" style={{ borderColor: color }}>
              <div className="flex justify-between items-start">
                <div>
                  <p className="font-bold text-lg">{i + 1}. {driver.factor}</p>
                  <p className="text-sm text-gray-700 mt-1">
                    {leadTeam} has a {Math.abs(driver.edge).toFixed(1)}% edge
                  </p>
                </div>
                <div className="text-right ml-4">
                  <p className="text-2xl font-bold mono" style={{ color }}>
                    {driver.points > 0 ? '+' : ''}{driver.points.toFixed(1)}
                  </p>
                  <p className="text-xs text-gray-600">pts impact</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ==================== Shot Profile Section ====================

function ShotProfileSection({ profile, teamA, teamB, colorA, colorB }: { profile: NonNullable<NBAMatchupResult['shot_profile']>; teamA: string; teamB: string; colorA: TeamColors; colorB: TeamColors }) {
  const metrics = [
    { label: '3P Attempt Rate', a: profile.fg3_rate_a, b: profile.fg3_rate_b, edge: profile.fg3_rate_edge },
    { label: '3P Percentage', a: profile.fg3_pct_a, b: profile.fg3_pct_b, edge: profile.fg3_pct_edge },
    { label: '2P Percentage', a: profile.fg2_pct_a, b: profile.fg2_pct_b, edge: profile.fg2_pct_edge },
  ];

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-2xl font-bold mb-6">Shot Profile</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {metrics.map(m => (
          <div key={m.label}>
            <p className="text-sm font-medium text-gray-700 mb-3">{m.label}</p>
            <div className="flex justify-between mb-1">
              <span className="text-sm" style={{ color: colorA.primary }}>{teamA}</span>
              <span className="text-sm font-bold">{m.a.toFixed(1)}%</span>
            </div>
            <div className="flex justify-between mb-2">
              <span className="text-sm" style={{ color: colorB.primary }}>{teamB}</span>
              <span className="text-sm font-bold">{m.b.toFixed(1)}%</span>
            </div>
            <p className="text-xs text-gray-600">
              Edge: <span className="font-bold" style={{ color: m.edge > 0 ? colorA.primary : colorB.primary }}>
                {m.edge > 0 ? '+' : ''}{m.edge.toFixed(1)}%
              </span>
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ==================== Series Section (NBA-specific) ====================

function SeriesSection({ series, teamA, teamB, colorA, colorB }: {
  series: NBASeriesPrediction;
  teamA: NBAMatchupResult['teamA'];
  teamB: NBAMatchupResult['teamB'];
  colorA: TeamColors;
  colorB: TeamColors;
}) {
  const aWins = series.series_home === 'a' ? teamA : teamB;
  const favorite = series.prob_a_series > 0.5 ? teamA : teamB;

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-2xl font-bold mb-2">7-Game Series Prediction</h2>
      <p className="text-sm text-gray-600 mb-6">
        2-2-1-1-1 format · Home court: <span className="font-semibold">{aWins.name}</span>
      </p>

      {/* Series win probability bar */}
      <div className="mb-6">
        <div className="flex justify-between mb-2">
          <span className="text-xl font-bold" style={{ color: colorA.primary }}>
            {(series.prob_a_series * 100).toFixed(1)}%
          </span>
          <span className="text-sm text-gray-600">Series Win Probability</span>
          <span className="text-xl font-bold" style={{ color: colorB.primary }}>
            {(series.prob_b_series * 100).toFixed(1)}%
          </span>
        </div>
        <div className="w-full h-10 rounded-full overflow-hidden flex relative">
          <div className="h-full transition-all" style={{ width: `${series.prob_a_series * 100}%`, backgroundColor: colorA.primary }} />
          <div className="h-full flex-1" style={{ backgroundColor: colorB.primary }} />
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-sm font-bold text-white drop-shadow">{favorite.name} win series</span>
          </div>
        </div>
      </div>

      {/* Series length breakdown */}
      <div className="grid grid-cols-2 gap-6 mb-6">
        <div>
          <p className="text-sm font-semibold mb-3" style={{ color: colorA.primary }}>{teamA.name} wins in…</p>
          <div className="space-y-2">
            {[
              { label: '4 games (sweep)', val: series.prob_sweep_a },
              { label: '5 games', val: series.prob_a_in_5 },
              { label: '6 games', val: series.prob_a_in_6 },
              { label: '7 games', val: series.prob_a_in_7 },
            ].map(row => (
              <div key={row.label} className="flex justify-between items-center text-sm">
                <span className="text-gray-600">{row.label}</span>
                <span className="font-bold mono">{(row.val * 100).toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </div>

        <div>
          <p className="text-sm font-semibold mb-3" style={{ color: colorB.primary }}>{teamB.name} wins in…</p>
          <div className="space-y-2">
            {[
              { label: '4 games (sweep)', val: series.prob_sweep_b },
              { label: '5 games', val: series.prob_b_in_5 },
              { label: '6 games', val: series.prob_b_in_6 },
              { label: '7 games', val: series.prob_b_in_7 },
            ].map(row => (
              <div key={row.label} className="flex justify-between items-center text-sm">
                <span className="text-gray-600">{row.label}</span>
                <span className="font-bold mono">{(row.val * 100).toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Game schedule */}
      <div>
        <p className="text-sm font-semibold text-gray-700 mb-3">Series Schedule</p>
        <div className="grid grid-cols-7 gap-1">
          {series.game_schedule.map(g => (
            <div key={g.game} className="text-center p-2 rounded text-xs"
              style={{ backgroundColor: g.site === 'home' ? withOpacity(colorA.primary, 0.15) : withOpacity(colorB.primary, 0.15) }}>
              <p className="font-bold">G{g.game}</p>
              <p className="text-gray-500 mt-0.5">{g.site === 'home' ? teamA.name.slice(0, 3).toUpperCase() : teamB.name.slice(0, 3).toUpperCase()}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ==================== Volatility Section ====================

function VolatilitySection({ volatility }: { volatility: NBAMatchupResult['volatility'] }) {
  const getColor = (s: number) => s < 30 ? 'text-green-600' : s < 60 ? 'text-yellow-600' : s < 80 ? 'text-orange-500' : 'text-red-600';
  const getLabel = (s: number) => s < 30 ? 'Low' : s < 60 ? 'Moderate' : s < 80 ? 'High' : 'Extreme';

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-2xl font-bold mb-4">Game Volatility</h2>
      <p className="text-sm text-gray-600 mb-6">Unpredictability based on pace, 3-point volume, and recent variance</p>

      <div className="flex items-center justify-center mb-6">
        <div className="text-center">
          <p className={`text-6xl font-bold ${getColor(volatility.volatility_score)}`}>
            {volatility.volatility_score.toFixed(0)}
          </p>
          <p className="text-xl font-semibold text-gray-700 mt-2">{getLabel(volatility.volatility_score)} Volatility</p>
        </div>
      </div>

      <div className="mb-6">
        <div className="w-full h-8 rounded-full overflow-hidden relative"
          style={{ background: 'linear-gradient(to right, #10b981 0%, #fbbf24 30%, #f59e0b 60%, #ef4444 100%)' }}>
          <div className="absolute inset-0 flex items-center">
            <div className="w-1 h-full bg-black shadow-lg" style={{ marginLeft: `${volatility.volatility_score}%` }} />
          </div>
        </div>
        <div className="flex justify-between text-xs text-gray-600 mt-1">
          <span>Low (0)</span><span>Moderate (50)</span><span>Extreme (100)</span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-6">
        {[
          { label: 'Pace', val: volatility.pace_component },
          { label: '3P Volume', val: volatility.three_pt_component },
          { label: 'Variance', val: volatility.variance_component },
        ].map(c => (
          <div key={c.label} className="text-center p-3 bg-gray-50 rounded">
            <p className="text-2xl font-bold">{c.val.toFixed(0)}</p>
            <p className="text-xs text-gray-600 mt-1">{c.label}</p>
          </div>
        ))}
      </div>

      {volatility.upset_warning && (
        <div className="mb-4 px-3 py-2 bg-red-50 border border-red-200 rounded text-sm text-red-700 font-medium">
          ⚠ {volatility.upset_warning}
        </div>
      )}

      {volatility.reasons.length > 0 && (
        <div>
          <p className="font-semibold mb-2">Key Factors:</p>
          <ul className="space-y-1">
            {volatility.reasons.map((r, i) => (
              <li key={i} className="text-sm text-gray-700 flex items-start">
                <span className="mr-2">•</span><span>{r}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ==================== Recent Form Section ====================

function RecentFormSection({ teamA, teamB, formA, formB, colorA, colorB }: {
  teamA: NBAMatchupResult['teamA'];
  teamB: NBAMatchupResult['teamB'];
  formA: NBAMatchupResult['recent_form_a'];
  formB: NBAMatchupResult['recent_form_b'];
  colorA: TeamColors;
  colorB: TeamColors;
}) {
  function TeamForm({ team, form, color }: { team: NBAMatchupResult['teamA']; form: typeof formA; color: TeamColors }) {
    return (
      <div>
        <h3 className="text-lg font-bold mb-4">{team.name}</h3>
        <div className="grid grid-cols-3 gap-3 mb-4">
          <div className="text-center p-3 rounded" style={{ backgroundColor: withOpacity(color.primary, 0.1) }}>
            <p className="text-xl font-bold" style={{ color: color.primary }}>{form.record}</p>
            <p className="text-xs text-gray-600">Record</p>
          </div>
          <div className="text-center p-3 bg-gray-50 rounded">
            <p className="text-xl font-bold">{form.avg_margin > 0 ? '+' : ''}{form.avg_margin.toFixed(1)}</p>
            <p className="text-xs text-gray-600">Avg Margin</p>
          </div>
          <div className="text-center p-3 bg-gray-50 rounded">
            <p className="text-xl font-bold">±{form.variance.toFixed(1)}</p>
            <p className="text-xs text-gray-600">Variance</p>
          </div>
        </div>

        {form.games.length > 0 && (
          <div className="space-y-2">
            {form.games.map((game, i) => (
              <div key={i} className="flex items-center justify-between text-sm border-b border-gray-100 pb-2">
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
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-2xl font-bold mb-6">Recent Form (Last {formA.games_analyzed} Games)</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <TeamForm team={teamA} form={formA} color={colorA} />
        <TeamForm team={teamB} form={formB} color={colorB} />
      </div>
    </div>
  );
}

// ==================== Metadata Footer ====================

function MetadataSection({ metadata, season }: { metadata: NBAMatchupResult['metadata']; season: string }) {
  return (
    <div className="bg-gray-50 rounded-lg p-4 text-xs text-gray-600">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div><p className="font-semibold">Season</p><p>{season}</p></div>
        <div><p className="font-semibold">HCA</p><p>{metadata.hca_points.toFixed(2)} pts</p></div>
        <div><p className="font-semibold">Prediction σ</p><p>{metadata.prediction_sigma.toFixed(2)} pts</p></div>
        <div><p className="font-semibold">Model R²</p><p>{metadata.coefficients.r_squared?.toFixed(3) ?? 'N/A'}</p></div>
      </div>
    </div>
  );
}
