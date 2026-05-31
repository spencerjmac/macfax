'use client';

import { useState, useMemo } from 'react';
import { TeamSeason } from '@/types';
import { getTeamColors, readable, DEFAULT_A, DEFAULT_B } from '@/lib/team-colors';

interface MatchupToolProps {
  teams: TeamSeason[];
}

export default function MatchupTool({ teams }: MatchupToolProps) {
  const [teamA, setTeamA] = useState<TeamSeason | null>(null);
  const [teamB, setTeamB] = useState<TeamSeason | null>(null);
  const [location, setLocation] = useState<'neutral' | 'teamA' | 'teamB'>('neutral');
  const [searchA, setSearchA] = useState('');
  const [searchB, setSearchB] = useState('');

  const colorA = teamA ? (getTeamColors(teamA.teamId)?.primary ?? DEFAULT_A.primary) : DEFAULT_A.primary;
  const colorB = teamB ? (getTeamColors(teamB.teamId)?.primary ?? DEFAULT_B.primary) : DEFAULT_B.primary;

  const filteredTeamsA = useMemo(() => {
    if (!searchA) return [];
    const query = searchA.toLowerCase();
    return teams.filter(t => t.teamName.toLowerCase().includes(query)).slice(0, 10);
  }, [searchA, teams]);

  const filteredTeamsB = useMemo(() => {
    if (!searchB) return [];
    const query = searchB.toLowerCase();
    return teams.filter(t => t.teamName.toLowerCase().includes(query)).slice(0, 10);
  }, [searchB, teams]);

  const matchup = useMemo(() => {
    if (!teamA || !teamB) return null;

    const homeAdj = location === 'teamA' ? 3.5 : location === 'teamB' ? -3.5 : 0;
    const adjEM_diff = teamA.adjEM - teamB.adjEM + homeAdj;
    const tempo_diff = teamA.adjTempo - teamB.adjTempo;
    const avgTempo = (teamA.adjTempo + teamB.adjTempo) / 2;

    const projectedA = Math.round(0.5 * avgTempo + (teamA.adjO - teamB.adjD) / 2 + adjEM_diff / 2 + 20);
    const projectedB = Math.round(0.5 * avgTempo + (teamB.adjO - teamA.adjD) / 2 - adjEM_diff / 2 + 20);
    const winA = Math.round(100 / (1 + Math.pow(10, -adjEM_diff / 11)));

    const eFG_edge = teamA.eFG_margin - teamB.eFG_margin;
    const tov_edge = teamA.tov_edge - teamB.tov_edge;
    const reb_edge = teamA.reb_edge - teamB.reb_edge;
    const ftr_edge = teamA.ftr_margin - teamB.ftr_margin;

    return {
      adjEM_diff,
      tempo_diff,
      avgTempo,
      projectedA,
      projectedB,
      winA,
      eFG_edge,
      tov_edge,
      reb_edge,
      ftr_edge,
    };
  }, [teamA, teamB, location]);

  return (
    <div className="space-y-8">
      {/* Team Selectors */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Team A */}
        <div>
          <label className="block text-sm font-medium text-text-muted mb-2">Team A</label>
          <div className="relative">
            <input
              type="text"
              value={teamA?.teamName || searchA}
              onChange={(e) => { setSearchA(e.target.value); setTeamA(null); }}
              placeholder="Search for a team..."
              className="w-full px-4 py-3 border border-ui-border rounded-lg focus:outline-none focus:ring-2 focus:ring-brand"
            />
            {searchA && !teamA && filteredTeamsA.length > 0 && (
              <div className="absolute z-10 w-full mt-1 bg-ui-card border border-ui-border rounded-lg shadow-lg max-h-60 overflow-y-auto">
                {filteredTeamsA.map((team) => (
                  <button
                    key={team.teamId}
                    onClick={() => { setTeamA(team); setSearchA(''); }}
                    className="w-full px-4 py-2 text-left hover:bg-ui-surface flex items-center gap-2"
                  >
                    <img src={team.logoUrl} alt="" className="w-6 h-6" />
                    <span>{team.teamName}</span>
                    <span className="text-text-muted text-sm ml-auto">#{team.rank}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {teamA && (
            <div
              className="mt-4 p-4 rounded-lg border-2"
              style={{ backgroundColor: colorA + '14', borderColor: colorA + '40' }}
            >
              <div className="flex items-center gap-3 mb-3">
                <img src={teamA.logoUrl} alt="" className="w-12 h-12" />
                <div>
                  <div className="font-bold text-lg">{teamA.teamName}</div>
                  <div className="text-text-muted text-sm">#{teamA.rank} · {teamA.conference}</div>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2 text-sm">
                <div>
                  <div className="text-text-muted">AdjEM</div>
                  <div className="font-mono font-bold">{teamA.adjEM.toFixed(1)}</div>
                </div>
                <div>
                  <div className="text-text-muted">AdjO</div>
                  <div className="font-mono font-bold">{teamA.adjO.toFixed(1)}</div>
                </div>
                <div>
                  <div className="text-text-muted">AdjD</div>
                  <div className="font-mono font-bold">{teamA.adjD.toFixed(1)}</div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Team B */}
        <div>
          <label className="block text-sm font-medium text-text-muted mb-2">Team B</label>
          <div className="relative">
            <input
              type="text"
              value={teamB?.teamName || searchB}
              onChange={(e) => { setSearchB(e.target.value); setTeamB(null); }}
              placeholder="Search for a team..."
              className="w-full px-4 py-3 border border-ui-border rounded-lg focus:outline-none focus:ring-2 focus:ring-brand"
            />
            {searchB && !teamB && filteredTeamsB.length > 0 && (
              <div className="absolute z-10 w-full mt-1 bg-ui-card border border-ui-border rounded-lg shadow-lg max-h-60 overflow-y-auto">
                {filteredTeamsB.map((team) => (
                  <button
                    key={team.teamId}
                    onClick={() => { setTeamB(team); setSearchB(''); }}
                    className="w-full px-4 py-2 text-left hover:bg-ui-surface flex items-center gap-2"
                  >
                    <img src={team.logoUrl} alt="" className="w-6 h-6" />
                    <span>{team.teamName}</span>
                    <span className="text-text-muted text-sm ml-auto">#{team.rank}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {teamB && (
            <div
              className="mt-4 p-4 rounded-lg border-2"
              style={{ backgroundColor: colorB + '14', borderColor: colorB + '40' }}
            >
              <div className="flex items-center gap-3 mb-3">
                <img src={teamB.logoUrl} alt="" className="w-12 h-12" />
                <div>
                  <div className="font-bold text-lg">{teamB.teamName}</div>
                  <div className="text-text-muted text-sm">#{teamB.rank} · {teamB.conference}</div>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2 text-sm">
                <div>
                  <div className="text-text-muted">AdjEM</div>
                  <div className="font-mono font-bold">{teamB.adjEM.toFixed(1)}</div>
                </div>
                <div>
                  <div className="text-text-muted">AdjO</div>
                  <div className="font-mono font-bold">{teamB.adjO.toFixed(1)}</div>
                </div>
                <div>
                  <div className="text-text-muted">AdjD</div>
                  <div className="font-mono font-bold">{teamB.adjD.toFixed(1)}</div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Location Toggle */}
      {teamA && teamB && (
        <div className="flex justify-center">
          <div className="inline-flex border border-ui-border rounded-lg p-1 bg-ui-surface">
            <button
              onClick={() => setLocation('teamA')}
              className={`px-6 py-2 rounded font-medium transition-colors ${
                location === 'teamA' ? 'bg-primary text-white' : 'text-text-muted hover:text-text-primary'
              }`}
            >
              @ {teamA.teamName}
            </button>
            <button
              onClick={() => setLocation('neutral')}
              className={`px-6 py-2 rounded font-medium transition-colors ${
                location === 'neutral' ? 'bg-neutral text-white' : 'text-text-muted hover:text-text-primary'
              }`}
            >
              Neutral
            </button>
            <button
              onClick={() => setLocation('teamB')}
              className={`px-6 py-2 rounded font-medium transition-colors ${
                location === 'teamB' ? 'bg-secondary text-white' : 'text-text-muted hover:text-text-primary'
              }`}
            >
              @ {teamB.teamName}
            </button>
          </div>
        </div>
      )}

      {/* Matchup Analysis */}
      {matchup && teamA && teamB && (
        <div className="space-y-6">
          {/* Game Forecast */}
          <div className="bg-ui-card border border-ui-border rounded-lg p-8 text-center">
            <h2 className="text-2xl font-bold mb-6">Game Forecast</h2>
            <div className="flex items-center justify-center gap-12 mb-6">
              <div>
                <div className="text-sm text-text-muted mb-2">{teamA.teamName}</div>
                <div className="text-5xl font-bold font-mono" style={{ color: readable(colorA) }}>
                  {matchup.projectedA}
                </div>
              </div>
              <div className="space-y-1">
                <div className="text-xs text-text-muted">Expected margin</div>
                <div className="text-2xl font-bold font-mono text-text-primary">
                  {matchup.adjEM_diff > 0 ? '+' : ''}{matchup.adjEM_diff.toFixed(1)}
                </div>
                <div className="text-xs text-text-muted">
                  {matchup.adjEM_diff >= 0 ? teamA.teamName : teamB.teamName}
                  {' · '}
                  {matchup.adjEM_diff >= 0 ? matchup.winA : 100 - matchup.winA}% win
                </div>
              </div>
              <div>
                <div className="text-sm text-text-muted mb-2">{teamB.teamName}</div>
                <div className="text-5xl font-bold font-mono" style={{ color: readable(colorB) }}>
                  {matchup.projectedB}
                </div>
              </div>
            </div>

            {/* Win probability bar */}
            <div className="h-3 rounded overflow-hidden flex mb-2">
              <div style={{ width: `${matchup.winA}%`, background: colorA }} />
              <div style={{ width: `${100 - matchup.winA}%`, background: colorB }} />
            </div>
            <div className="flex justify-between text-xs text-text-muted mb-4">
              <span style={{ color: readable(colorA) }}>{matchup.winA}%</span>
              <span style={{ color: readable(colorB) }}>{100 - matchup.winA}%</span>
            </div>

            <div className="text-text-muted text-sm">
              Projected at {matchup.avgTempo.toFixed(1)} tempo
              {location !== 'neutral' && ' · includes home-court advantage'}
            </div>
          </div>

          {/* Four-Factor Breakdown */}
          <div>
            <h2 className="text-2xl font-bold mb-4">Four-Factor Breakdown</h2>
            <div className="space-y-3">
              <FFBar
                label="Effective FG%"
                aVal={(teamA.eFG_margin ?? 0) * 100}
                bVal={(teamB.eFG_margin ?? 0) * 100}
                aColor={colorA} bColor={colorB}
                aName={teamA.teamName} bName={teamB.teamName}
                impact={matchup.eFG_edge * 100 * 0.93}
              />
              <FFBar
                label="Turnover Rate"
                aVal={(teamA.tov_edge ?? 0) * 100}
                bVal={(teamB.tov_edge ?? 0) * 100}
                aColor={colorA} bColor={colorB}
                aName={teamA.teamName} bName={teamB.teamName}
                impact={matchup.tov_edge * 100 * 0.84}
              />
              <FFBar
                label="Offensive Reb%"
                aVal={(teamA.reb_edge ?? 0) * 100}
                bVal={(teamB.reb_edge ?? 0) * 100}
                aColor={colorA} bColor={colorB}
                aName={teamA.teamName} bName={teamB.teamName}
                impact={matchup.reb_edge * 100 * 0.42}
              />
              <FFBar
                label="Free-Throw Rate"
                aVal={(teamA.ftr_margin ?? 0) * 100}
                bVal={(teamB.ftr_margin ?? 0) * 100}
                aColor={colorA} bColor={colorB}
                aName={teamA.teamName} bName={teamB.teamName}
                impact={matchup.ftr_edge * 100 * 0.18}
              />
            </div>
          </div>

          {/* Other Metrics */}
          <div className="grid md:grid-cols-2 gap-4">
            <div className="p-6 bg-ui-surface border border-ui-border rounded-lg">
              <div className="text-text-muted text-sm mb-2">Efficiency Margin Diff</div>
              <div className="text-3xl font-bold font-mono">
                {matchup.adjEM_diff > 0 ? '+' : ''}{matchup.adjEM_diff.toFixed(2)}
              </div>
              <div className="text-sm text-text-muted mt-2">
                Favors {matchup.adjEM_diff > 0 ? teamA.teamName : teamB.teamName}
              </div>
            </div>
            <div className="p-6 bg-ui-surface border border-ui-border rounded-lg">
              <div className="text-text-muted text-sm mb-2">Tempo Difference</div>
              <div className="text-3xl font-bold font-mono">
                {matchup.tempo_diff > 0 ? '+' : ''}{matchup.tempo_diff.toFixed(1)}
              </div>
              <div className="text-sm text-text-muted mt-2">
                {Math.abs(matchup.tempo_diff) < 2
                  ? 'Similar pace'
                  : matchup.tempo_diff > 0
                  ? `${teamA.teamName} faster`
                  : `${teamB.teamName} faster`}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Empty State */}
      {(!teamA || !teamB) && (
        <div className="text-center py-16 text-text-muted">
          <p className="text-lg">Select two teams to see matchup analysis</p>
        </div>
      )}
    </div>
  );
}

function FFBar({
  label,
  aVal,
  bVal,
  aColor,
  bColor,
  aName,
  bName,
  impact,
}: {
  label: string;
  aVal: number;
  bVal: number;
  aColor: string;
  bColor: string;
  aName: string;
  bName: string;
  impact: number;
}) {
  const edge = aVal - bVal;
  const favA = edge >= 0;
  const absA = Math.abs(aVal);
  const absB = Math.abs(bVal);
  const tot = absA + absB || 1;
  const aw = (absA / tot) * 100;
  const bw = (absB / tot) * 100;

  return (
    <div className="p-4 bg-ui-card border border-ui-border rounded-lg">
      <div className="flex justify-between items-baseline mb-1">
        <span className="text-sm font-medium">{label}</span>
        <span className="text-xs font-mono" style={{ color: favA ? readable(aColor) : readable(bColor) }}>
          Edge {edge > 0 ? '+' : ''}{edge.toFixed(1)}%
        </span>
      </div>
      <div className="flex justify-between text-xs mb-2">
        <span style={{ color: readable(aColor) }}>{aName} {aVal.toFixed(1)}%</span>
        <span style={{ color: readable(bColor) }}>{bName} {bVal.toFixed(1)}%</span>
      </div>
      <div className="h-2 rounded overflow-hidden flex bg-ui-surface">
        <div style={{ width: aw + '%', background: aColor }} />
        <div style={{ width: bw + '%', background: bColor }} />
      </div>
      <div className="text-xs text-text-muted mt-1">
        Impact: {impact > 0 ? '+' : ''}{impact.toFixed(1)} pts · {favA ? aName : bName}
      </div>
    </div>
  );
}
