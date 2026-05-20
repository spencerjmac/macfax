'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { api } from '@/lib/api';
import { nbaApi } from '@/lib/nba-api';
import type { GameDetailResponse } from '@/types/games';
import WPChart from './WPChart';
import BoxScoreTable from './BoxScoreTable';
import FourFactorsTab from './FourFactorsTab';
import InsightsTab from './InsightsTab';

type TabId = 'overview' | 'boxscore' | 'fourfactors' | 'insights';

const TABS: { id: TabId; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'boxscore', label: 'Box score' },
  { id: 'fourfactors', label: 'Four factors' },
  { id: 'insights', label: 'Insights' },
];

interface Props {
  gameId: string;
  league: 'ncaa' | 'nba';
}

function Skeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="h-24 rounded-xl bg-ui-surface" />
      <div className="h-10 rounded-xl bg-ui-surface" />
      <div className="h-64 rounded-xl bg-ui-surface" />
    </div>
  );
}

function BackLink({ league }: { league: 'ncaa' | 'nba' }) {
  const href = league === 'ncaa' ? '/ncaa/rankings' : '/nba/rankings';
  const label = league === 'ncaa' ? 'NCAA Rankings' : 'NBA Rankings';
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-1.5 text-sm text-text-muted hover:text-text-primary transition-colors mb-4"
    >
      <ArrowLeft className="h-4 w-4" />
      {label}
    </Link>
  );
}

function WinBadge({ won }: { won: boolean }) {
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-xs font-semibold ${
        won
          ? 'bg-emerald-500/20 text-emerald-400'
          : 'bg-rose-500/20 text-rose-400'
      }`}
    >
      {won ? 'W' : 'L'}
    </span>
  );
}

function StatPill({
  label,
  value,
  better,
}: {
  label: string;
  value: number | null;
  better: 'up' | 'down' | null; // null = neutral
}) {
  const colorClass =
    better === 'up'
      ? 'text-emerald-400'
      : better === 'down'
      ? 'text-rose-400'
      : 'text-text-primary';

  return (
    <div className="rounded-xl border border-ui-border bg-ui-surface p-3 text-center">
      <div className="text-[11px] text-text-muted mb-1">{label}</div>
      <div className={`text-xl font-semibold ${colorClass}`}>
        {value != null ? value.toFixed(1) : '—'}
      </div>
    </div>
  );
}

export default function GameDetailPage({ gameId, league }: Props) {
  const [data, setData] = useState<GameDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>('overview');

  useEffect(() => {
    setLoading(true);
    setError(null);
    const fetcher = league === 'nba' ? nbaApi.getGameDetail : api.getGameDetail;
    fetcher(gameId)
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch((err: Error) => {
        setError(err.message || 'Failed to load game data');
        setLoading(false);
      });
  }, [gameId, league]);

  if (loading) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-6">
        <BackLink league={league} />
        <Skeleton />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-6">
        <BackLink league={league} />
        <div className="rounded-xl border border-ui-border bg-ui-surface p-8 text-center">
          <p className="text-text-muted">{error ?? 'Game not found.'}</p>
        </div>
      </div>
    );
  }

  const { game_meta, wp_curve, four_factors, box_score, insights } = data;
  const homeWon =
    game_meta.home_score != null &&
    game_meta.away_score != null &&
    game_meta.home_score > game_meta.away_score;
  const awayWon =
    game_meta.home_score != null &&
    game_meta.away_score != null &&
    game_meta.away_score > game_meta.home_score;

  // Relative four factor comparison helpers
  const ffHome = four_factors.home;
  const ffAway = four_factors.away;
  function relDir(homeVal: number | null, awayVal: number | null, higherBetter: boolean) {
    if (homeVal == null || awayVal == null) return null;
    if (higherBetter) return homeVal >= awayVal ? 'up' : 'down';
    return homeVal <= awayVal ? 'up' : 'down';
  }

  const venue = game_meta.venue;
  const dateStr = new Date(game_meta.date + 'T12:00:00').toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      <BackLink league={league} />

      {/* ── Game header ───────────────────────────────────────────────────── */}
      <div className="mb-6 rounded-xl border border-ui-border bg-ui-surface p-5">
        {/* Teams + scores */}
        <div className="flex items-center justify-center gap-8 mb-3">
          {/* Away */}
          <div className="flex flex-col items-center gap-1 min-w-[100px]">
            <span className="text-sm font-medium text-text-secondary">
              {game_meta.away_team.name}
            </span>
            <span
              className={`text-4xl font-bold tabular-nums ${
                awayWon ? 'text-text-primary' : 'text-text-muted'
              }`}
            >
              {game_meta.away_score ?? '—'}
            </span>
            {game_meta.away_score != null && game_meta.home_score != null && (
              <WinBadge won={awayWon} />
            )}
          </div>

          <div className="flex flex-col items-center gap-0.5">
            <span className="text-xs text-text-muted font-semibold uppercase tracking-widest">
              {league.toUpperCase()}
            </span>
            <span className="text-lg text-text-muted font-light">@</span>
            <span className="text-xs text-text-muted">{game_meta.status}</span>
          </div>

          {/* Home */}
          <div className="flex flex-col items-center gap-1 min-w-[100px]">
            <span className="text-sm font-medium text-text-secondary">
              {game_meta.home_team.name}
            </span>
            <span
              className={`text-4xl font-bold tabular-nums ${
                homeWon ? 'text-text-primary' : 'text-text-muted'
              }`}
            >
              {game_meta.home_score ?? '—'}
            </span>
            {game_meta.away_score != null && game_meta.home_score != null && (
              <WinBadge won={homeWon} />
            )}
          </div>
        </div>

        {/* Meta */}
        <div className="text-center text-xs text-text-muted">
          {dateStr}
          {venue ? ` · ${venue}` : ''}
        </div>
      </div>

      {/* ── Tab bar ───────────────────────────────────────────────────────── */}
      <div className="mb-6 border-b border-ui-border">
        <div className="flex gap-0">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-5 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'border-brand text-brand'
                  : 'border-transparent text-text-muted hover:text-text-primary'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Tab panels ────────────────────────────────────────────────────── */}

      {activeTab === 'overview' && (
        <div className="space-y-5">
          <WPChart curve={wp_curve} homeTeam={game_meta.home_team} awayTeam={game_meta.away_team} />
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">
              Four factors — {game_meta.home_team.abbr} (home)
            </p>
            <div className="grid grid-cols-4 gap-3">
              <StatPill
                label="eFG%"
                value={ffHome.efg_pct}
                better={relDir(ffHome.efg_pct, ffAway.efg_pct, true)}
              />
              <StatPill
                label="TOV%"
                value={ffHome.tov_pct}
                better={relDir(ffHome.tov_pct, ffAway.tov_pct, false)}
              />
              <StatPill
                label="ORB%"
                value={ffHome.orb_pct}
                better={relDir(ffHome.orb_pct, ffAway.orb_pct, true)}
              />
              <StatPill
                label="FTR"
                value={ffHome.ftr}
                better={relDir(ffHome.ftr, ffAway.ftr, true)}
              />
            </div>
          </div>
        </div>
      )}

      {activeTab === 'boxscore' && (
        <BoxScoreTable
          homeRows={box_score.home}
          awayRows={box_score.away}
          homeTeam={game_meta.home_team}
          awayTeam={game_meta.away_team}
        />
      )}

      {activeTab === 'fourfactors' && (
        <FourFactorsTab
          fourFactors={four_factors}
          homeTeam={game_meta.home_team}
          awayTeam={game_meta.away_team}
        />
      )}

      {activeTab === 'insights' && <InsightsTab insights={insights} />}
    </div>
  );
}
