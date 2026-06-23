'use client';

import { useEffect, useState, useMemo } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import type { TeamSeasonOutlookSummary, OutlookTier } from '@/types/nba';
import { nbaApi } from '@/lib/nba-api';

const TIER_LABELS: Record<OutlookTier, string> = {
  title_contender: 'Title Contender',
  playoff_contender: 'Playoff Contender',
  bubble: 'Bubble Team',
  lottery: 'Lottery Team',
  rebuilding: 'Rebuilding',
};

const TIER_CLASSES: Record<OutlookTier, string> = {
  title_contender: 'bg-yellow-500/20 text-yellow-500 border border-yellow-500/30',
  playoff_contender: 'bg-brand/20 text-brand border border-brand/30',
  bubble: 'bg-amber-500/20 text-amber-500 border border-amber-500/30',
  lottery: 'bg-orange-400/20 text-orange-400 border border-orange-400/30',
  rebuilding: 'bg-ui-surface text-text-muted border border-ui-border',
};

type ConferenceFilter = 'All' | 'East' | 'West';

function netColor(net: number | null): string {
  if (net === null) return 'text-text-primary';
  if (net > 0) return 'text-positive';
  if (net < 0) return 'text-negative';
  return 'text-text-muted';
}

function fmt(v: number | null, dec = 1): string {
  if (v === null) return '—';
  return v > 0 && dec === 1 ? `+${v.toFixed(dec)}` : v.toFixed(dec);
}

function fmtNet(v: number | null): string {
  if (v === null) return '—';
  const s = v.toFixed(1);
  return v > 0 ? `+${s}` : s;
}

export default function NBATeamsPage() {
  const [teams, setTeams] = useState<TeamSeasonOutlookSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [conference, setConference] = useState<ConferenceFilter>('All');

  useEffect(() => {
    nbaApi
      .getTeamOutlooks()
      .then(setTeams)
      .catch((e) => setError(e.message ?? 'Failed to load'))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(
    () => (conference === 'All' ? teams : teams.filter((t) => t.conference === conference)),
    [teams, conference],
  );

  return (
    <div>
      {/* Header */}
      <div className="bg-surface border-b border-ui-border">
        <div className="max-w-[1240px] mx-auto px-8 py-10 pb-[34px]">
          <p className="kicker-sport text-brand mb-[9px]">NBA · 2025-26 Season Outlook</p>
          <h1 className="font-display font-bold text-[clamp(32px,4vw,48px)] leading-none uppercase tracking-[0.005em] m-0 mb-[14px]">
            Team Outlooks
          </h1>
          <p className="text-[15px] text-muted m-0">
            2025-26 final ratings + 2026-27 outlook for all 30 teams
          </p>
        </div>
      </div>

      {/* Conference filter tabs */}
      <div className="border-b border-ui-border bg-surface">
        <div className="max-w-[1240px] mx-auto px-8">
          <div className="flex gap-0">
            {(['All', 'East', 'West'] as ConferenceFilter[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setConference(tab)}
                className={`px-5 py-3 text-[13px] font-medium border-b-2 transition-colors ${
                  conference === tab
                    ? 'border-brand text-brand'
                    : 'border-transparent text-text-muted hover:text-text-primary'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-[1240px] mx-auto px-8 py-8 pb-16">
        {loading && (
          <div className="text-center py-20 text-text-muted">Loading…</div>
        )}

        {error && (
          <div className="text-center py-20 text-negative">{error}</div>
        )}

        {!loading && !error && (
          <div className="bg-ui-card border border-ui-border rounded-lg overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-ui-border">
                  <th className="table-header text-left px-4 py-3 w-10">Rk</th>
                  <th className="table-header text-left px-4 py-3">Team</th>
                  <th className="table-header text-center px-3 py-3">Conf</th>
                  <th className="table-header text-center px-3 py-3">W-L</th>
                  <th className="table-header text-center px-3 py-3">AdjO</th>
                  <th className="table-header text-center px-3 py-3">AdjD</th>
                  <th className="table-header text-center px-3 py-3">AdjNet</th>
                  <th className="table-header text-center px-3 py-3">FFI</th>
                  <th className="table-header text-left px-4 py-3">Outlook</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((team, i) => (
                  <tr
                    key={team.team_slug}
                    className="border-b border-ui-border last:border-0 hover:bg-ui-surface/60 transition-colors cursor-pointer group"
                  >
                    <td className="px-4 py-3 text-[13px] font-mono text-text-muted text-center">
                      {team.league_rank}
                    </td>
                    <td className="px-4 py-3">
                      <Link
                        href={`/nba/teams/${team.team_slug}`}
                        className="flex items-center gap-3 no-underline"
                      >
                        {team.logo_url ? (
                          <img
                            src={team.logo_url}
                            alt={team.team_abbr}
                            width={28}
                            height={28}
                            className="object-contain flex-shrink-0"
                            onError={(e) => {
                              (e.target as HTMLImageElement).style.display = 'none';
                            }}
                          />
                        ) : (
                          <div
                            className="w-7 h-7 rounded-full flex-shrink-0"
                            style={{ backgroundColor: team.primary_color }}
                          />
                        )}
                        <span className="font-medium text-[14px] text-text-primary group-hover:text-brand transition-colors">
                          {team.team_name}
                        </span>
                      </Link>
                    </td>
                    <td className="px-3 py-3 text-[13px] font-mono text-text-muted text-center">
                      {team.conference}
                    </td>
                    <td className="px-3 py-3 text-[13px] font-mono text-text-primary text-center">
                      {team.wins !== null && team.losses !== null
                        ? `${team.wins}-${team.losses}`
                        : '—'}
                    </td>
                    <td className="px-3 py-3 text-[13px] font-mono text-text-primary text-center">
                      {team.adj_offensive_rating?.toFixed(1) ?? '—'}
                    </td>
                    <td className="px-3 py-3 text-[13px] font-mono text-text-primary text-center">
                      {team.adj_defensive_rating?.toFixed(1) ?? '—'}
                    </td>
                    <td className="px-3 py-3 text-center">
                      <span
                        className={`text-[13px] font-mono font-semibold ${netColor(team.adj_net_rating)}`}
                      >
                        {fmtNet(team.adj_net_rating)}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-[13px] font-mono text-text-muted text-center">
                      {team.ffi?.toFixed(1) ?? '—'}
                    </td>
                    <td className="px-4 py-3">
                      {team.outlook_tier ? (
                        <span
                          className={`inline-block text-[11px] font-medium px-2 py-0.5 rounded ${TIER_CLASSES[team.outlook_tier]}`}
                        >
                          {TIER_LABELS[team.outlook_tier]}
                        </span>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
