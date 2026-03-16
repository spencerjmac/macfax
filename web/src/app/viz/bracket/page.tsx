'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { BracketData, BracketTeamData, TeamRoundProbs } from '@/types';
import VisualBracket from '@/components/VisualBracket';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const REGIONS = ['East', 'West', 'South', 'Midwest'] as const;
type RegionName = typeof REGIONS[number];

// Standard R64 matchup pairs (top → bottom of bracket)
const R64_PODS: [number, number][] = [
  [1, 16], [8, 9],
  [5, 12], [4, 13],
  [6, 11], [3, 14],
  [7, 10], [2, 15],
];

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function pct(p: number): string {
  if (p >= 0.995) return '99%';
  if (p < 0.005)  return '<1%';
  return `${Math.round(p * 100)}%`;
}

function pBar(p: number, color: string) {
  const w = Math.max(4, Math.round(p * 100));
  return (
    <div className="w-full bg-gray-100 rounded-full h-1.5 overflow-hidden">
      <div className={`h-full rounded-full ${color}`} style={{ width: `${w}%` }} />
    </div>
  );
}

function champColor(p: number) {
  if (p >= 0.20) return 'bg-yellow-400';
  if (p >= 0.10) return 'bg-orange-400';
  if (p >= 0.05) return 'bg-blue-400';
  if (p >= 0.02) return 'bg-blue-300';
  return 'bg-gray-300';
}

function emColor(em: number) {
  if (em > 20) return 'text-emerald-600 font-bold';
  if (em > 10) return 'text-blue-600 font-semibold';
  if (em > 0)  return 'text-text-primary';
  return 'text-red-500';
}

// ---------------------------------------------------------------------------
// Team row inside a region card (one row per team in a matchup pair)
// ---------------------------------------------------------------------------

function TeamRow({
  team,
  probs,
  isTop,
}: {
  team: BracketTeamData;
  probs: TeamRoundProbs | undefined;
  isTop: boolean;
}) {
  const p = probs ?? { p_r64: 1, p_r32: 0, p_s16: 0, p_e8: 0, p_ff: 0, p_final: 0, p_champion: 0 };
  const isFF = team.is_first_four;

  return (
    <div
      className={`flex items-center gap-2 px-3 py-2 hover:bg-gray-50 transition-colors ${
        isTop ? '' : 'border-t border-gray-100'
      }`}
    >
      {/* Seed */}
      <span className="w-6 text-center text-xs font-bold text-text-muted shrink-0">
        {team.seed}
      </span>

      {/* Name + First Four badge */}
      <div className="flex-1 min-w-0">
        <Link
          href={`/teams/${team.slug}`}
          className="text-sm font-medium text-text-primary hover:text-primary truncate block"
        >
          {team.name}
        </Link>
        <div className="flex items-center gap-1.5 mt-0.5">
          <span className="text-xs text-text-muted">{team.record}</span>
          {isFF && (
            <span className="text-[10px] px-1 py-0.5 bg-amber-100 text-amber-700 rounded font-semibold leading-none">
              FIRST FOUR
            </span>
          )}
        </div>
      </div>

      {/* AdjEM */}
      <span className={`text-xs tabular-nums w-10 text-right shrink-0 ${emColor(team.adj_em)}`}>
        {team.adj_em > 0 ? '+' : ''}{team.adj_em.toFixed(1)}
      </span>

      {/* Probability columns */}
      <div className="hidden lg:flex gap-3 shrink-0">
        <div className="w-9 text-right">
          <div className="text-xs text-text-muted tabular-nums">{pct(p.p_s16)}</div>
          {pBar(p.p_s16, 'bg-blue-400')}
        </div>
        <div className="w-9 text-right">
          <div className="text-xs text-text-muted tabular-nums">{pct(p.p_e8)}</div>
          {pBar(p.p_e8, 'bg-indigo-400')}
        </div>
        <div className="w-9 text-right">
          <div className="text-xs text-text-muted tabular-nums">{pct(p.p_ff)}</div>
          {pBar(p.p_ff, 'bg-purple-400')}
        </div>
        <div className="w-9 text-right">
          <div className={`text-xs font-bold tabular-nums ${p.p_champion >= 0.10 ? 'text-yellow-600' : 'text-text-muted'}`}>
            {pct(p.p_champion)}
          </div>
          {pBar(p.p_champion, champColor(p.p_champion))}
        </div>
      </div>

      {/* Mobile: just champion prob */}
      <div className="flex lg:hidden shrink-0 w-10 text-right">
        <div className="w-full">
          <div className={`text-xs font-bold tabular-nums ${p.p_champion >= 0.10 ? 'text-yellow-600' : 'text-text-muted'}`}>
            {pct(p.p_champion)}
          </div>
          {pBar(p.p_champion, champColor(p.p_champion))}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// A single R64 matchup pod (2 teams)
// ---------------------------------------------------------------------------

function MatchupPod({
  seedHigh,
  seedLow,
  slots,
  probs,
}: {
  seedHigh: number;
  seedLow: number;
  slots: BracketData['regions'][RegionName];
  probs: Record<string, TeamRoundProbs>;
}) {
  // Flat map of seed → teams
  const bySlot: Record<number, BracketTeamData[]> = {};
  for (const slot of slots) bySlot[slot.seed] = slot.teams;

  const highTeams = bySlot[seedHigh] ?? [];
  const lowTeams  = bySlot[seedLow]  ?? [];
  const allTeams  = [...highTeams, ...lowTeams];

  if (allTeams.length === 0) return null;

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden mb-2">
      {allTeams.map((team, idx) => (
        <TeamRow
          key={team.slug}
          team={team}
          probs={probs[team.slug]}
          isTop={idx === 0}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Region card
// ---------------------------------------------------------------------------

function RegionCard({
  name,
  slots,
  probs,
}: {
  name: RegionName;
  slots: BracketData['regions'][RegionName];
  probs: Record<string, TeamRoundProbs>;
}) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
        <h3 className="text-base font-bold text-text-primary">{name} Region</h3>
        {/* Column headers */}
        <div className="hidden lg:flex items-center gap-2 mt-1">
          <span className="w-6 shrink-0" />
          <span className="flex-1 text-xs text-text-muted">Team</span>
          <span className="w-10 text-right text-xs text-text-muted shrink-0">EM</span>
          <div className="flex gap-3 shrink-0">
            <span className="w-9 text-right text-xs text-blue-500">S16</span>
            <span className="w-9 text-right text-xs text-indigo-500">E8</span>
            <span className="w-9 text-right text-xs text-purple-500">FF</span>
            <span className="w-9 text-right text-xs text-yellow-600">Champ</span>
          </div>
        </div>
      </div>
      <div className="p-3">
        {R64_PODS.map(([sH, sL]) => (
          <MatchupPod
            key={`${sH}-${sL}`}
            seedHigh={sH}
            seedLow={sL}
            slots={slots}
            probs={probs}
          />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Leaderboard
// ---------------------------------------------------------------------------

function Leaderboard({ data }: { data: BracketData }) {
  // Flatten all teams
  const allTeams: BracketTeamData[] = [];
  for (const region of REGIONS) {
    for (const slot of data.regions[region]) {
      allTeams.push(...slot.teams);
    }
  }

  const sorted = [...allTeams].sort(
    (a, b) => (data.probabilities[b.slug]?.p_champion ?? 0) - (data.probabilities[a.slug]?.p_champion ?? 0)
  );

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
        <h3 className="text-base font-bold">Championship Leaderboard</h3>
        <p className="text-xs text-text-muted mt-0.5">All 68 teams sorted by P(Champion)</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50">
              <th className="text-left px-3 py-2 text-xs text-text-muted font-semibold w-8">#</th>
              <th className="text-left px-3 py-2 text-xs text-text-muted font-semibold">Team</th>
              <th className="text-center px-2 py-2 text-xs text-text-muted font-semibold">Region</th>
              <th className="text-center px-2 py-2 text-xs text-text-muted font-semibold">Seed</th>
              <th className="text-center px-2 py-2 text-xs text-text-muted font-semibold">Record</th>
              <th className="text-center px-2 py-2 text-xs text-text-muted font-semibold">AdjEM</th>
              <th className="text-center px-2 py-2 text-xs text-blue-500 font-semibold">S16</th>
              <th className="text-center px-2 py-2 text-xs text-indigo-500 font-semibold">E8</th>
              <th className="text-center px-2 py-2 text-xs text-purple-500 font-semibold">FF</th>
              <th className="text-center px-2 py-2 text-xs text-text-muted font-semibold">Final</th>
              <th className="text-center px-2 py-2 text-xs text-yellow-600 font-semibold">Champ</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((team, idx) => {
              const p = data.probabilities[team.slug];
              if (!p) return null;
              return (
                <tr key={team.slug} className={`border-b border-gray-100 hover:bg-gray-50 ${idx < 4 ? 'bg-yellow-50/30' : ''}`}>
                  <td className="px-3 py-2 text-xs text-text-muted">{idx + 1}</td>
                  <td className="px-3 py-2">
                    <Link href={`/teams/${team.slug}`} className="font-medium hover:text-primary text-sm">
                      {team.name}
                    </Link>
                    {team.is_first_four && (
                      <span className="ml-1.5 text-[10px] px-1 py-0.5 bg-amber-100 text-amber-700 rounded">FF</span>
                    )}
                  </td>
                  <td className="px-2 py-2 text-center text-xs text-text-muted">{team.region}</td>
                  <td className="px-2 py-2 text-center text-xs font-bold">{team.seed}</td>
                  <td className="px-2 py-2 text-center text-xs text-text-muted">{team.record}</td>
                  <td className={`px-2 py-2 text-center text-xs tabular-nums ${emColor(team.adj_em)}`}>
                    {team.adj_em > 0 ? '+' : ''}{team.adj_em.toFixed(1)}
                  </td>
                  <td className="px-2 py-2 text-center text-xs tabular-nums">{pct(p.p_s16)}</td>
                  <td className="px-2 py-2 text-center text-xs tabular-nums">{pct(p.p_e8)}</td>
                  <td className="px-2 py-2 text-center text-xs tabular-nums text-purple-600 font-semibold">{pct(p.p_ff)}</td>
                  <td className="px-2 py-2 text-center text-xs tabular-nums">{pct(p.p_final)}</td>
                  <td className={`px-2 py-2 text-center text-xs tabular-nums font-bold ${p.p_champion >= 0.10 ? 'text-yellow-600' : p.p_champion >= 0.05 ? 'text-orange-500' : 'text-text-muted'}`}>
                    {pct(p.p_champion)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function BracketPage() {
  const [data, setData] = useState<BracketData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<RegionName | 'Leaderboard' | 'Bracket'>('Bracket');

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const d = await api.getBracket({ n_sims: 10000 });
        setData(d);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load bracket data');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // Top 3 championship favorites for the hero section
  const topPicks = data
    ? Object.entries(data.probabilities)
        .sort((a, b) => b[1].p_champion - a[1].p_champion)
        .slice(0, 4)
        .map(([slug, probs]) => ({
          slug,
          probs,
          team: REGIONS.flatMap(r => data.regions[r].flatMap(s => s.teams)).find(t => t.slug === slug),
        }))
        .filter(x => x.team)
    : [];

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-2 text-text-muted text-sm mb-2">
          <Link href="/viz" className="hover:text-primary">Visualizations</Link>
          <span>/</span>
          <span>Bracket Simulator</span>
        </div>
        <h1 className="text-3xl font-bold mb-1">
          🏀 Bracket Simulator
        </h1>
        <p className="text-text-muted">
          Monte Carlo win probabilities for all 68 tournament teams based on Adjusted Efficiency Ratings.
          {data && (
            <span className="ml-2 text-xs bg-gray-100 px-2 py-0.5 rounded text-gray-600">
              {data.n_sims.toLocaleString()} simulations · {data.season_label}
            </span>
          )}
        </p>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-20 text-text-muted">
          <div className="text-center">
            <div className="text-4xl mb-3">⚙️</div>
            <p className="font-medium">Running simulations…</p>
            <p className="text-sm mt-1">Simulating 2,000 tournament paths</p>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
          {error}
        </div>
      )}

      {data && (
        <>
          {/* Top Favorites */}
          {topPicks.length > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
              {topPicks.map(({ slug, probs, team }, idx) => (
                <Link
                  key={slug}
                  href={`/teams/${slug}`}
                  className={`rounded-xl border p-3 hover:shadow-md transition-shadow ${
                    idx === 0 ? 'border-yellow-300 bg-yellow-50' : 'border-gray-200 bg-white'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-text-muted font-medium">
                      {idx === 0 ? '🏆 FAVORITE' : `#${idx + 1}`}
                    </span>
                    <span className="text-xs font-semibold text-text-muted">
                      {team!.region} {team!.seed}
                    </span>
                  </div>
                  <div className="font-bold text-sm truncate">{team!.name}</div>
                  <div className="mt-1.5">
                    <span className={`text-lg font-bold ${idx === 0 ? 'text-yellow-600' : 'text-text-primary'}`}>
                      {pct(probs.p_champion)}
                    </span>
                    <span className="text-xs text-text-muted ml-1">to win</span>
                  </div>
                  <div className="mt-1.5 text-xs text-text-muted">
                    FF: {pct(probs.p_ff)} · F: {pct(probs.p_final)}
                  </div>
                </Link>
              ))}
            </div>
          )}

          {/* Final Four pairings note */}
          <div className="mb-4 text-xs text-text-muted bg-blue-50 border border-blue-100 rounded-lg px-3 py-2">
            <strong>Final Four:</strong>{' '}
            {data.ff_pairings.map(([a, b], i) => (
              <span key={i}>{i > 0 ? ' · ' : ''}{a} winner vs {b} winner</span>
            ))}
          </div>

          {/* Tabs */}
          <div className="flex gap-1 border-b border-gray-200 mb-5 overflow-x-auto pb-px">
            {(['Bracket', ...REGIONS, 'Leaderboard'] as const).map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 text-sm font-medium rounded-t whitespace-nowrap transition-colors ${
                  activeTab === tab
                    ? 'bg-white border border-b-white border-gray-200 text-primary -mb-px'
                    : 'text-text-muted hover:text-text-primary'
                }`}
              >
                {tab === 'Bracket' ? '🗓 Bracket' : tab}
              </button>
            ))}
          </div>

          {/* Tab content */}
          {activeTab === 'Bracket' ? (
            <VisualBracket data={data} />
          ) : activeTab === 'Leaderboard' ? (
            <Leaderboard data={data} />
          ) : (
            <RegionCard
              name={activeTab}
              slots={data.regions[activeTab]}
              probs={data.probabilities}
            />
          )}
        </>
      )}
    </div>
  );
}
