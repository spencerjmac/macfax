'use client';

import { useEffect, useState } from 'react';
import { worldCupApi } from '@/lib/worldcup-api';
import { getWorldCupTeamColors, contrastText } from '@/lib/worldcup-colors';
import type { WorldCupGroupResult } from '@/types/worldcup';

export const dynamic = 'force-dynamic';

const GROUPS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'];

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export default function WorldCupGroupsPage() {
  const [group, setGroup] = useState('A');
  const [result, setResult] = useState<WorldCupGroupResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    worldCupApi
      .getGroup(group)
      .then(setResult)
      .catch(() => setError('Failed to load group.'))
      .finally(() => setLoading(false));
  }, [group]);

  const standings = result
    ? [...result.teams].sort((a, b) => b.win_group_pct - a.win_group_pct)
    : [];

  return (
    <div>
      <div className="bg-surface border-b border-ui-border">
        <div className="max-w-[1240px] mx-auto px-8 py-10 pb-[34px]">
          <p className="kicker-sport text-brand mb-[9px]">WORLD CUP · GROUP ODDS</p>
          <h1 className="font-display font-bold text-[clamp(32px,4vw,48px)] leading-none uppercase tracking-[0.005em] m-0 mb-[14px]">
            Group Winner Probability
          </h1>
          <p className="text-[15px] text-muted m-0">
            Pick a group — every team plays every other team once. Odds come from exact
            enumeration of all 729 possible round-robin outcomes.
          </p>
        </div>
      </div>

      <div className="max-w-[1240px] mx-auto px-8 py-8 space-y-8">
        {/* Group selector */}
        <div className="flex items-center gap-3">
          <label htmlFor="group-select" className="text-xs font-display font-semibold uppercase tracking-[0.06em] text-muted">
            Group
          </label>
          <select
            id="group-select"
            value={group}
            onChange={(e) => setGroup(e.target.value)}
            className="px-3 py-2 bg-ui-card border border-ui-border rounded-lg text-sm font-display font-semibold focus:outline-none focus:ring-2 focus:ring-brand/50"
          >
            {GROUPS.map((g) => (
              <option key={g} value={g}>
                Group {g}
              </option>
            ))}
          </select>
        </div>

        {error && <p className="text-sm text-negative">{error}</p>}
        {loading && <p className="text-sm text-muted">Loading…</p>}

        {result && !loading && (
          <>
            {/* Win-group distribution bar */}
            <div className="p-6 bg-ui-card border border-ui-border rounded-lg">
              <h2 className="font-display font-bold text-[16px] uppercase tracking-[0.02em] mb-4">
                Group {result.group} — Win Probability
              </h2>
              <div className="w-full h-10 rounded-full overflow-hidden flex">
                {standings.map((t, i) => {
                  const colors = getWorldCupTeamColors(t.name, i);
                  return (
                    <div
                      key={t.name}
                      className="h-full transition-all flex items-center justify-center"
                      style={{ width: pct(t.win_group_pct), backgroundColor: colors.primary }}
                    >
                      {t.win_group_pct >= 0.06 && (
                        <span
                          className="text-xs font-bold drop-shadow"
                          style={{ color: contrastText(colors.primary) }}
                        >
                          {pct(t.win_group_pct)}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
              <div className="flex flex-wrap gap-x-6 gap-y-2 mt-4">
                {standings.map((t, i) => {
                  const colors = getWorldCupTeamColors(t.name, i);
                  return (
                    <div key={t.name} className="flex items-center gap-2 text-sm">
                      <span
                        className="inline-block w-3 h-3 rounded-sm"
                        style={{ backgroundColor: colors.primary }}
                      />
                      <span className="text-lg leading-none">{t.flag_emoji}</span>
                      <span className="font-medium text-text-primary">{t.name}</span>
                      <span className="font-mono font-semibold" style={{ color: colors.primary }}>
                        {pct(t.win_group_pct)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Team table */}
            <div className="p-6 bg-ui-card border border-ui-border rounded-lg overflow-x-auto">
              <h2 className="font-display font-bold text-[16px] uppercase tracking-[0.02em] mb-4">
                Projected Standings
              </h2>
              <table className="w-full">
                <thead>
                  <tr className="border-b border-ink-line bg-ink">
                    <th className="px-3 py-[13px] text-xs font-display font-semibold text-white uppercase tracking-[0.06em] text-left">#</th>
                    <th className="px-3 py-[13px] text-xs font-display font-semibold text-white uppercase tracking-[0.06em] text-left">Team</th>
                    <th className="px-3 py-[13px] text-xs font-display font-semibold text-white uppercase tracking-[0.06em] text-right">Elo</th>
                    <th className="px-3 py-[13px] text-xs font-display font-semibold text-white uppercase tracking-[0.06em] text-right">FIFA</th>
                    <th className="px-3 py-[13px] text-xs font-display font-semibold text-white uppercase tracking-[0.06em] text-right">Win Group</th>
                    <th className="px-3 py-[13px] text-xs font-display font-semibold text-white uppercase tracking-[0.06em] text-right">Advance</th>
                  </tr>
                </thead>
                <tbody>
                  {standings.map((t, i) => {
                    const colors = getWorldCupTeamColors(t.name, i);
                    return (
                      <tr key={t.name} className="border-b border-ui-border">
                        <td className="px-3 py-2 text-sm font-mono font-semibold text-text-primary">{i + 1}</td>
                        <td className="px-3 py-2 text-sm">
                          <span className="inline-flex items-center gap-2">
                            <span className="text-lg leading-none">{t.flag_emoji}</span>
                            <span className="font-medium text-text-primary">{t.name}</span>
                          </span>
                        </td>
                        <td className="px-3 py-2 text-sm font-mono font-semibold text-brand text-right">
                          {t.elo_rating.toFixed(1)}
                        </td>
                        <td className="px-3 py-2 text-sm font-mono text-text-primary text-right">{t.fifa_rank}</td>
                        <td className="px-3 py-2 text-sm font-mono font-semibold text-right" style={{ color: colors.primary }}>
                          {pct(t.win_group_pct)}
                        </td>
                        <td className="px-3 py-2 text-sm font-mono text-muted text-right">{pct(t.advance_pct)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="text-xs text-muted mt-4">
                Advance = probability of finishing 1st or 2nd. Ties on points are broken by
                head-to-head record, then by Elo rating.
              </p>
            </div>

            {/* Fixtures */}
            <div className="p-6 bg-ui-card border border-ui-border rounded-lg overflow-x-auto">
              <h2 className="font-display font-bold text-[16px] uppercase tracking-[0.02em] mb-4">
                Fixture Odds
              </h2>
              <table className="w-full">
                <thead>
                  <tr className="border-b border-ink-line bg-ink">
                    <th className="px-3 py-[13px] text-xs font-display font-semibold text-white uppercase tracking-[0.06em] text-left">Matchup</th>
                    <th className="px-3 py-[13px] text-xs font-display font-semibold text-white uppercase tracking-[0.06em] text-right">Win A</th>
                    <th className="px-3 py-[13px] text-xs font-display font-semibold text-white uppercase tracking-[0.06em] text-right">Draw</th>
                    <th className="px-3 py-[13px] text-xs font-display font-semibold text-white uppercase tracking-[0.06em] text-right">Win B</th>
                  </tr>
                </thead>
                <tbody>
                  {result.fixtures.map((f) => {
                    const colorsA = getWorldCupTeamColors(f.team_a);
                    const colorsB = getWorldCupTeamColors(f.team_b);
                    return (
                      <tr key={`${f.team_a}-${f.team_b}`} className="border-b border-ui-border">
                        <td className="px-3 py-2 text-sm font-medium text-text-primary">
                          {f.team_a} vs {f.team_b}
                        </td>
                        <td className="px-3 py-2 text-sm font-mono text-right" style={{ color: colorsA.primary }}>
                          {pct(f.p_a_win)}
                        </td>
                        <td className="px-3 py-2 text-sm font-mono text-muted text-right">{pct(f.p_draw)}</td>
                        <td className="px-3 py-2 text-sm font-mono text-right" style={{ color: colorsB.primary }}>
                          {pct(f.p_b_win)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
