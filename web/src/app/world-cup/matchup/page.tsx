'use client';

import { useEffect, useState } from 'react';
import { worldCupApi } from '@/lib/worldcup-api';
import { getWorldCupTeamColors } from '@/lib/worldcup-colors';
import type { WorldCupTeam, WorldCupMatchupResult } from '@/types/worldcup';

export const dynamic = 'force-dynamic';

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export default function WorldCupMatchupPage() {
  const [teams, setTeams] = useState<WorldCupTeam[]>([]);
  const [teamA, setTeamA] = useState('');
  const [teamB, setTeamB] = useState('');
  const [result, setResult] = useState<WorldCupMatchupResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    worldCupApi
      .getRankings()
      .then((data) => {
        const sorted = [...data].sort((a, b) => a.elo_rank - b.elo_rank);
        setTeams(sorted);
        if (sorted.length >= 2) {
          setTeamA(sorted[0].name);
          setTeamB(sorted[1].name);
        }
      })
      .catch(() => setError('Failed to load teams.'));
  }, []);

  async function handleCompare() {
    if (!teamA || !teamB || teamA === teamB) return;
    setLoading(true);
    setError(null);
    try {
      const data = await worldCupApi.getMatchup(teamA, teamB);
      setResult(data);
    } catch {
      setError('Failed to load matchup.');
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  function handleSwap() {
    setTeamA(teamB);
    setTeamB(teamA);
    setResult(null);
  }

  return (
    <div>
      <div className="bg-surface border-b border-ui-border">
        <div className="max-w-[1240px] mx-auto px-8 py-10 pb-[34px]">
          <p className="kicker-sport text-brand mb-[9px]">WORLD CUP · MATCHUP</p>
          <h1 className="font-display font-bold text-[clamp(32px,4vw,48px)] leading-none uppercase tracking-[0.005em] m-0 mb-[14px]">
            Hypothetical Matchup
          </h1>
          <p className="text-[15px] text-muted m-0">
            Pick any two of the 48 teams and get win / draw / loss odds based on Elo rating.
          </p>
        </div>
      </div>

      <div className="max-w-[1240px] mx-auto px-8 py-8 space-y-8">
        <div className="p-6 bg-ui-card border border-ui-border rounded-lg">
          <div className="flex flex-col md:flex-row items-stretch md:items-end gap-4">
            <div className="flex-1">
              <label className="block text-xs font-display font-semibold uppercase tracking-[0.06em] text-muted mb-2">
                Team A
              </label>
              <select
                value={teamA}
                onChange={(e) => setTeamA(e.target.value)}
                className="w-full px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/50"
              >
                {teams.map((t) => (
                  <option key={t.name} value={t.name}>
                    {t.flag_emoji} {t.name} (#{t.elo_rank})
                  </option>
                ))}
              </select>
            </div>

            <button
              onClick={handleSwap}
              className="px-3 py-2 text-sm font-medium text-muted border border-ui-border rounded-lg hover:bg-ui-surface transition-colors"
              title="Swap teams"
            >
              ⇄
            </button>

            <div className="flex-1">
              <label className="block text-xs font-display font-semibold uppercase tracking-[0.06em] text-muted mb-2">
                Team B
              </label>
              <select
                value={teamB}
                onChange={(e) => setTeamB(e.target.value)}
                className="w-full px-3 py-2 bg-ui-surface border border-ui-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand/50"
              >
                {teams.map((t) => (
                  <option key={t.name} value={t.name}>
                    {t.flag_emoji} {t.name} (#{t.elo_rank})
                  </option>
                ))}
              </select>
            </div>

            <button
              onClick={handleCompare}
              disabled={loading || !teamA || !teamB || teamA === teamB}
              className="px-6 py-2 bg-brand text-white text-sm font-display font-semibold uppercase tracking-[0.04em] rounded-lg hover:bg-brand-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Comparing…' : 'Compare'}
            </button>
          </div>

          {teamA && teamB && teamA === teamB && (
            <p className="text-sm text-negative mt-3">Pick two different teams.</p>
          )}
          {error && <p className="text-sm text-negative mt-3">{error}</p>}
        </div>

        {result && (() => {
          const colorsA = getWorldCupTeamColors(result.teamA.name, 0);
          const colorsB = getWorldCupTeamColors(result.teamB.name, 1);
          return (
          <div className="p-6 bg-ui-card border border-ui-border rounded-lg">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-2">
                <span className="text-2xl">{result.teamA.flag_emoji}</span>
                <span className="font-display font-bold text-lg uppercase tracking-[0.02em]">
                  {result.teamA.name}
                </span>
              </div>
              <span className="text-sm text-muted font-display uppercase tracking-[0.06em]">vs</span>
              <div className="flex items-center gap-2">
                <span className="font-display font-bold text-lg uppercase tracking-[0.02em]">
                  {result.teamB.name}
                </span>
                <span className="text-2xl">{result.teamB.flag_emoji}</span>
              </div>
            </div>

            {/* Win / Draw / Loss bar */}
            <div className="mb-2 flex justify-between text-lg font-bold">
              <span style={{ color: colorsA.primary }}>{pct(result.win_pct_a)}</span>
              <span className="text-muted text-sm self-end pb-0.5">Draw {pct(result.draw_pct)}</span>
              <span style={{ color: colorsB.primary }}>{pct(result.win_pct_b)}</span>
            </div>
            <div className="w-full h-8 rounded-full overflow-hidden flex">
              <div
                className="h-full transition-all"
                style={{ width: pct(result.win_pct_a), backgroundColor: colorsA.primary }}
              />
              <div
                className="h-full bg-slate-400 transition-all"
                style={{ width: pct(result.draw_pct) }}
              />
              <div
                className="h-full transition-all"
                style={{ width: pct(result.win_pct_b), backgroundColor: colorsB.primary }}
              />
            </div>
            <div className="flex justify-between mt-1 text-xs">
              <span className="font-semibold" style={{ color: colorsA.primary }}>{result.teamA.name} win</span>
              <span className="font-semibold" style={{ color: colorsB.primary }}>{result.teamB.name} win</span>
            </div>

            {/* Elo comparison */}
            <div className="grid grid-cols-3 gap-4 mt-8 pt-6 border-t border-ui-border text-center">
              <div>
                <p className="font-mono font-bold text-2xl" style={{ color: colorsA.primary }}>
                  {result.teamA.elo_rating.toFixed(1)}
                </p>
                <p className="text-xs text-muted mt-1 uppercase tracking-[0.06em]">Elo Rating</p>
              </div>
              <div>
                <p className="font-mono font-bold text-2xl text-text-primary">
                  {result.elo_diff > 0 ? '+' : ''}
                  {result.elo_diff.toFixed(1)}
                </p>
                <p className="text-xs text-muted mt-1 uppercase tracking-[0.06em]">Elo Diff (A − B)</p>
              </div>
              <div>
                <p className="font-mono font-bold text-2xl" style={{ color: colorsB.primary }}>
                  {result.teamB.elo_rating.toFixed(1)}
                </p>
                <p className="text-xs text-muted mt-1 uppercase tracking-[0.06em]">Elo Rating</p>
              </div>
            </div>

            <p className="text-xs text-muted mt-6">
              Neutral venue. Draw probability is modeled from the Elo gap — closer matchups carry a
              higher chance of a draw.
            </p>
          </div>
          );
        })()}
      </div>
    </div>
  );
}
