'use client';

import { useState, useEffect } from 'react';
import clsx from 'clsx';
import Link from 'next/link';
import { NBA_TEAM_TABS } from '@/config/nba';
import { nbaApi } from '@/lib/nba-api';
import type { NBATeamSeasonRatings, NBAGame, NBAPlayerSeasonStats } from '@/types/nba';

interface NBATeamPageTabsProps {
  slug: string;
  seasonYear?: number;
  ratings: NBATeamSeasonRatings | null;
  games: NBAGame[];
}

function StatCard({ label, value, sub }: { label: string; value: string | null; sub?: string }) {
  return (
    <div className="bg-ui-card border border-ui-border rounded-lg px-5 py-4 text-center">
      <div className="text-2xl font-bold font-mono">{value ?? '—'}</div>
      <div className="text-xs text-text-muted mt-0.5">{label}</div>
      {sub && <div className="text-[10px] text-text-muted/60 mt-0.5">{sub}</div>}
    </div>
  );
}

function RatingRow({
  label,
  value,
  tooltip,
}: {
  label: string;
  value: number | null;
  tooltip?: string;
}) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-ui-border/50 last:border-0">
      <span className="text-sm text-text-muted" title={tooltip}>{label}</span>
      <span className="text-sm font-mono font-medium">
        {value != null ? value.toFixed(1) : '—'}
      </span>
    </div>
  );
}

function FourFactorRow({
  label,
  off,
  def,
  margin,
  format,
}: {
  label: string;
  off: number | null;
  def: number | null;
  margin: number | null;
  format?: 'percent' | 'decimal';
}) {
  const fmt = (v: number | null) => {
    if (v == null) return '—';
    if (format === 'decimal') return v.toFixed(3);
    return `${(v * 100).toFixed(1)}%`;
  };
  return (
    <tr className="border-b border-ui-border/50">
      <td className="py-2.5 text-sm text-text-muted pr-4">{label}</td>
      <td className="py-2.5 text-sm font-mono text-right">{fmt(off)}</td>
      <td className="py-2.5 text-sm font-mono text-right">{fmt(def)}</td>
      <td
        className={clsx(
          'py-2.5 text-sm font-mono font-medium text-right',
          margin != null && margin > 0 ? 'text-emerald-700' : margin != null && margin < 0 ? 'text-rose-700' : ''
        )}
      >
        {margin != null ? `${margin >= 0 ? '+' : ''}${fmt(margin)}` : '—'}
      </td>
    </tr>
  );
}

function MetricCard({
  label,
  value,
  rank,
  color,
  note,
}: {
  label: string;
  value: string | null;
  rank?: number | null;
  color?: string;
  note?: string;
}) {
  return (
    <div className="bg-ui-card border border-ui-border rounded-lg px-5 py-4 text-center">
      <div className={clsx('text-3xl font-bold font-mono', color ?? 'text-text-primary')}>
        {value ?? '—'}
      </div>
      {rank != null && (
        <div className="text-xs font-bold text-brand mt-0.5">#{rank}</div>
      )}
      <div className="text-xs text-text-muted mt-1">{label}</div>
      {note && <div className="text-[10px] text-text-muted/60 mt-0.5">{note}</div>}
    </div>
  );
}

function FactorTile({
  label,
  value,
  format,
  positive,
}: {
  label: string;
  value: number | null;
  format?: 'percent' | 'decimal';
  positive?: boolean;
}) {
  const fmt = (v: number | null) => {
    if (v == null) return '—';
    const sign = v >= 0 ? '+' : '';
    if (format === 'decimal') return `${sign}${v.toFixed(3)}`;
    return `${sign}${(v * 100).toFixed(1)}%`;
  };
  return (
    <div className="bg-ui-card border border-ui-border rounded-lg p-3">
      <div
        className={clsx(
          'text-xl font-bold font-mono',
          positive === true
            ? 'text-emerald-700'
            : positive === false
            ? 'text-rose-700'
            : 'text-text-primary'
        )}
      >
        {fmt(value)}
      </div>
      <div className="text-xs text-text-muted mt-0.5">{label}</div>
    </div>
  );
}

export default function NBATeamPageTabs({ slug, seasonYear, ratings, games }: NBATeamPageTabsProps) {
  const [activeTab, setActiveTab] = useState('overview');
  const [players, setPlayers] = useState<NBAPlayerSeasonStats[] | null>(null);
  const [playersLoading, setPlayersLoading] = useState(false);
  const [playersError, setPlayersError] = useState<string | null>(null);

  useEffect(() => {
    if (activeTab !== 'players') return;
    if (players !== null) return; // already loaded
    setPlayersLoading(true);
    setPlayersError(null);
    nbaApi.getTeamRoster(slug, seasonYear)
      .then((data) => setPlayers(data))
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : 'Failed to load roster';
        setPlayersError(msg);
        setPlayers([]);
      })
      .finally(() => setPlayersLoading(false));
  }, [activeTab, slug, seasonYear, players]);

  return (
    <div>
      {/* Tab bar */}
      <div className="border-b border-ui-border mb-6">
        <div className="flex gap-0 overflow-x-auto">
          {NBA_TEAM_TABS.map((tab) => {
            const isLive = tab.phase <= 4;
            return (
              <button
                key={tab.id}
                onClick={() => isLive && setActiveTab(tab.id)}
                className={clsx(
                  'px-5 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap',
                  activeTab === tab.id && isLive
                    ? 'border-brand text-brand'
                    : isLive
                    ? 'border-transparent text-text-muted hover:text-text-primary'
                    : 'border-transparent text-text-muted opacity-40 cursor-default'
                )}
              >
                {tab.label}
                {!isLive && (
                  <span className="ml-1.5 text-[10px] bg-gray-100 text-gray-400 px-1 rounded">
                    Ph{tab.phase}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Overview ──────────────────────────────────────────────────────── */}
      {activeTab === 'overview' && (
        <div className="space-y-8">
          {ratings ? (
            <>
              {/* Core Metrics */}
              <div>
                <h2 className="text-2xl font-bold mb-4">Core Metrics</h2>
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                  <MetricCard
                    label="Adjusted Net Rating"
                    value={ratings.adj_net?.toFixed(1) ?? null}
                    rank={ratings.rank_adj_net}
                    color="text-brand"
                  />
                  <MetricCard
                    label="Adjusted Offensive Rating"
                    value={ratings.adj_off?.toFixed(1) ?? null}
                    color="text-emerald-700"
                  />
                  <MetricCard
                    label="Adjusted Defensive Rating"
                    value={ratings.adj_def?.toFixed(1) ?? null}
                    color="text-rose-700"
                    note="lower = better"
                  />
                  <MetricCard
                    label="Pace (poss/48min)"
                    value={ratings.pace?.toFixed(1) ?? null}
                  />
                </div>
              </div>

              {/* Two-column: FFI + Four Factor tiles | Season summary */}
              <div className="grid md:grid-cols-2 gap-6">
                <div className="space-y-4">
                  {/* FFI big card */}
                  {ratings.ffi != null && (
                    <div className="p-6 bg-gradient-to-br from-brand/10 to-brand/5 border border-brand/20 rounded-lg">
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <div className="text-text-muted text-sm">Four Factor Index</div>
                        {ratings.rank_ffi != null && (
                          <div className="text-xs font-mono px-2 py-0.5 rounded bg-brand/20 text-brand font-semibold">
                            #{ratings.rank_ffi}
                          </div>
                        )}
                      </div>
                      <div className="text-5xl font-bold font-mono text-brand mb-2">
                        {ratings.ffi.toFixed(1)}
                      </div>
                      <p className="text-xs text-text-muted">
                        Composite four-factor dominance score (0–100 scale)
                      </p>
                    </div>
                  )}

                  {/* Four Factor snapshot */}
                  <div className="grid grid-cols-2 gap-3">
                    <FactorTile
                      label="eFG Margin"
                      value={ratings.efg_margin}
                      format="percent"
                      positive={ratings.efg_margin != null ? ratings.efg_margin > 0 : undefined}
                    />
                    <FactorTile
                      label="TOV Edge"
                      value={ratings.tov_edge}
                      format="percent"
                      positive={ratings.tov_edge != null ? ratings.tov_edge > 0 : undefined}
                    />
                    <FactorTile
                      label="OREB Edge"
                      value={ratings.oreb_edge}
                      format="percent"
                      positive={ratings.oreb_edge != null ? ratings.oreb_edge > 0 : undefined}
                    />
                    <FactorTile
                      label="FTA Margin"
                      value={ratings.fta_margin}
                      format="decimal"
                      positive={ratings.fta_margin != null ? ratings.fta_margin > 0 : undefined}
                    />
                  </div>
                </div>

                {/* Season summary */}
                <div className="bg-ui-card border border-ui-border rounded-lg p-5">
                  <h3 className="font-semibold mb-4">Season Summary</h3>
                  <div className="space-y-3">
                    {[
                      { label: 'Games Played', value: String(ratings.games) },
                      { label: 'Adj Net Rank', value: ratings.rank_adj_net != null ? `#${ratings.rank_adj_net}` : '—', brand: true },
                      { label: 'FFI Rank', value: ratings.rank_ffi != null ? `#${ratings.rank_ffi}` : '—', brand: true },
                      { label: 'Adj Off', value: ratings.adj_off?.toFixed(1) ?? '—', green: true },
                      { label: 'Adj Def', value: ratings.adj_def?.toFixed(1) ?? '—', red: true, note: 'lower = better' },
                    ].map(({ label, value, brand, green, red, note }, i, arr) => (
                      <div
                        key={label}
                        className={clsx(
                          'flex justify-between py-2',
                          i < arr.length - 1 ? 'border-b border-ui-border/50' : ''
                        )}
                      >
                        <span className="text-sm text-text-muted">
                          {label}
                          {note && <span className="text-[10px] text-text-muted/60 ml-1">({note})</span>}
                        </span>
                        <span
                          className={clsx(
                            'font-mono font-medium',
                            brand ? 'text-brand' : green ? 'text-emerald-700' : red ? 'text-rose-700' : ''
                          )}
                        >
                          {value}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="py-12 text-center text-text-muted text-sm">
              <p className="font-medium mb-1">No ratings data yet</p>
              <p>Run <code className="bg-gray-100 px-1 rounded text-xs">nba_compute_ratings --season 2026</code></p>
            </div>
          )}
        </div>
      )}

      {/* ── Ratings ───────────────────────────────────────────────────────── */}
      {activeTab === 'ratings' && (
        <div className="max-w-sm">
          {ratings ? (
            <div className="bg-ui-card border border-ui-border rounded-lg p-5">
              <h3 className="font-semibold mb-3">Adjusted Efficiency</h3>
              <RatingRow label="Adj Offensive Rating" value={ratings.adj_off} tooltip="Points scored per 100 possessions vs avg NBA defense" />
              <RatingRow label="Adj Defensive Rating" value={ratings.adj_def} tooltip="Points allowed per 100 possessions vs avg NBA offense (lower = better)" />
              <RatingRow label="Adj Net Rating" value={ratings.adj_net} tooltip="Adj Off minus Adj Def" />
              <RatingRow label="Pace (poss/game)" value={ratings.pace} />
              {ratings.ffi != null && (
                <RatingRow label="FFI (provisional)" value={ratings.ffi} tooltip="Four Factor Index — PROVISIONAL" />
              )}
            </div>
          ) : (
            <div className="py-12 text-center text-text-muted text-sm">No ratings data yet.</div>
          )}
        </div>
      )}

      {/* ── Four Factors ─────────────────────────────────────────────────── */}
      {activeTab === 'four-factors' && (
        <div>
          {ratings ? (
            <div className="overflow-x-auto">
              <table className="w-full max-w-2xl text-sm">
                <thead>
                  <tr className="bg-ui-surface border-b border-ui-border">
                    <th className="text-left py-2 pr-4 text-xs text-text-muted font-semibold uppercase tracking-wide">Factor</th>
                    <th className="text-right py-2 px-3 text-xs text-text-muted font-semibold uppercase tracking-wide">Off</th>
                    <th className="text-right py-2 px-3 text-xs text-text-muted font-semibold uppercase tracking-wide">Def</th>
                    <th className="text-right py-2 px-3 text-xs text-text-muted font-semibold uppercase tracking-wide">Margin</th>
                  </tr>
                </thead>
                <tbody>
                  <FourFactorRow
                    label="eFG%"
                    off={ratings.efg_pct}
                    def={ratings.opp_efg_pct}
                    margin={ratings.efg_margin}
                  />
                  <FourFactorRow
                    label="TOV Rate"
                    off={ratings.tov_rate}
                    def={ratings.opp_tov_rate}
                    margin={ratings.tov_edge != null ? -ratings.tov_edge : null}
                  />
                  <FourFactorRow
                    label="OREB%"
                    off={ratings.oreb_pct}
                    def={ratings.opp_oreb_pct}
                    margin={ratings.oreb_edge}
                  />
                  <FourFactorRow
                    label="FTA/FGA"
                    off={ratings.fta_rate}
                    def={ratings.opp_fta_rate}
                    margin={ratings.fta_margin}
                    format="decimal"
                  />
                </tbody>
              </table>
              <p className="mt-3 text-xs text-text-muted">
                Margin = Off − Def for eFG%/OREB%/FTA; TOV margin = Opp rate − Team rate (positive = better).
              </p>
            </div>
          ) : (
            <div className="py-12 text-center text-text-muted text-sm">No four factor data yet.</div>
          )}
        </div>
      )}

      {/* ── Game Log ─────────────────────────────────────────────────────── */}
      {activeTab === 'game-log' && (
        <div>
          {games.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-ui-surface border-b border-ui-border">
                    <th className="text-left py-2 px-3 text-xs text-text-muted font-semibold uppercase tracking-wide">Date</th>
                    <th className="text-left py-2 px-3 text-xs text-text-muted font-semibold uppercase tracking-wide">Matchup</th>
                    <th className="text-right py-2 px-3 text-xs text-text-muted font-semibold uppercase tracking-wide">Score</th>
                    <th className="text-center py-2 px-3 text-xs text-text-muted font-semibold uppercase tracking-wide">W/L</th>
                  </tr>
                </thead>
                <tbody>
                  {games.map((game) => {
                    const isHome = game.home_team_slug === slug;
                    const teamScore = isHome ? game.home_score : game.away_score;
                    const oppScore = isHome ? game.away_score : game.home_score;
                    const oppAbbr = isHome ? game.away_team_abbr : game.home_team_abbr;
                    const oppSlug = isHome ? game.away_team_slug : game.home_team_slug;
                    const result =
                      teamScore != null && oppScore != null
                        ? teamScore > oppScore
                          ? 'W'
                          : 'L'
                        : null;
                    return (
                      <tr key={game.id} className="border-b border-ui-border/50 hover:bg-ui-surface/50">
                        <td className="py-2 px-3 text-text-muted">
                          {new Date(game.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                        </td>
                        <td className="py-2 px-3">
                          <span className="text-text-muted text-xs mr-1">{isHome ? 'vs.' : '@'}</span>
                          <Link href={`/nba/team/${oppSlug}`} className="hover:text-brand transition-colors font-medium">
                            {oppAbbr}
                          </Link>
                        </td>
                        <td className="py-2 px-3 text-right font-mono">
                          {teamScore != null && oppScore != null ? `${teamScore}–${oppScore}` : '—'}
                        </td>
                        <td className="py-2 px-3 text-center">
                          {result && (
                            <span
                              className={clsx(
                                'text-xs font-bold px-1.5 py-0.5 rounded',
                                result === 'W' ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'
                              )}
                            >
                              {result}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="py-12 text-center text-text-muted text-sm">
              <p className="font-medium mb-1">No games loaded yet</p>
              <p>Run <code className="bg-gray-100 px-1 rounded text-xs">nba_sync_games --season 2026</code></p>
            </div>
          )}
        </div>
      )}

      {/* ── Players ──────────────────────────────────────────────────────── */}
      {activeTab === 'players' && (
        <div>
          {playersLoading && (
            <div className="py-12 text-center text-text-muted text-sm">Loading roster...</div>
          )}
          {!playersLoading && playersError && (
            <div className="py-12 text-center text-text-muted text-sm">
              <p className="font-medium mb-1">No player stats yet</p>
              <p className="text-xs mt-1">
                Run{' '}
                <code className="bg-gray-100 px-1 rounded">
                  nba_sync_team_logs --season {seasonYear ?? 2026}
                </code>{' '}
                then{' '}
                <code className="bg-gray-100 px-1 rounded">
                  nba_compute_player_stats --season {seasonYear ?? 2026}
                </code>
              </p>
            </div>
          )}
          {!playersLoading && players && players.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-ui-surface border-b border-ui-border">
                    <th className="text-left py-2 px-3 text-xs text-text-muted font-semibold uppercase tracking-wide">Player</th>
                    <th className="text-right py-2 px-3 text-xs text-text-muted font-semibold uppercase tracking-wide">GP</th>
                    <th className="text-right py-2 px-3 text-xs text-text-muted font-semibold uppercase tracking-wide">MPG</th>
                    <th className="text-right py-2 px-3 text-xs text-text-muted font-semibold uppercase tracking-wide">PTS</th>
                    <th className="text-right py-2 px-3 text-xs text-text-muted font-semibold uppercase tracking-wide">REB</th>
                    <th className="text-right py-2 px-3 text-xs text-text-muted font-semibold uppercase tracking-wide">AST</th>
                    <th className="text-right py-2 px-3 text-xs text-text-muted font-semibold uppercase tracking-wide">STL</th>
                    <th className="text-right py-2 px-3 text-xs text-text-muted font-semibold uppercase tracking-wide">BLK</th>
                    <th className="text-right py-2 px-3 text-xs text-text-muted font-semibold uppercase tracking-wide">TOV</th>
                    <th className="text-right py-2 px-3 text-xs text-text-muted font-semibold uppercase tracking-wide">FG%</th>
                    <th className="text-right py-2 px-3 text-xs text-text-muted font-semibold uppercase tracking-wide">3P%</th>
                    <th className="text-right py-2 px-3 text-xs text-text-muted font-semibold uppercase tracking-wide">FT%</th>
                    <th className="text-right py-2 px-3 text-xs text-text-muted font-semibold uppercase tracking-wide">+/-</th>
                  </tr>
                </thead>
                <tbody>
                  {players.map((p) => (
                    <tr key={p.id} className="border-b border-ui-border/50 hover:bg-ui-surface/50">
                      <td className="py-2.5 px-3 font-medium">
                        <div className="flex items-center gap-2">
                          <div className="w-6 h-6 rounded-full overflow-hidden bg-ui-surface flex-shrink-0">
                            <img
                              src={`https://cdn.nba.com/headshots/nba/latest/1040x760/${p.player_id}.png`}
                              alt={p.player_name}
                              className="w-6 h-6 object-cover"
                              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                            />
                          </div>
                          {p.player_name}
                        </div>
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono text-text-muted">{p.gp}</td>
                      <td className="py-2.5 px-3 text-right font-mono text-text-muted">
                        {p.mpg != null ? p.mpg.toFixed(1) : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono font-semibold">
                        {p.pts != null ? p.pts.toFixed(1) : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono">
                        {p.reb != null ? p.reb.toFixed(1) : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono">
                        {p.ast != null ? p.ast.toFixed(1) : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono text-text-muted">
                        {p.stl != null ? p.stl.toFixed(1) : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono text-text-muted">
                        {p.blk != null ? p.blk.toFixed(1) : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono text-text-muted">
                        {p.tov != null ? p.tov.toFixed(1) : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono">
                        {p.fg_pct != null ? `${(p.fg_pct * 100).toFixed(1)}%` : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono">
                        {p.fg3_pct != null ? `${(p.fg3_pct * 100).toFixed(1)}%` : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono">
                        {p.ft_pct != null ? `${(p.ft_pct * 100).toFixed(1)}%` : '—'}
                      </td>
                      <td
                        className={clsx(
                          'py-2.5 px-3 text-right font-mono font-medium',
                          p.plus_minus != null && p.plus_minus > 0
                            ? 'text-emerald-700'
                            : p.plus_minus != null && p.plus_minus < 0
                            ? 'text-rose-700'
                            : ''
                        )}
                      >
                        {p.plus_minus != null
                          ? `${p.plus_minus >= 0 ? '+' : ''}${p.plus_minus.toFixed(1)}`
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-3 text-xs text-text-muted">
                Per-game averages for {players[0]?.season_display}. Sorted by PTS.
              </p>
            </div>
          )}
        </div>
      )}

      {/* ── Lineups ───────────────────────────────────────────────────────── */}
      {activeTab === 'lineups' && (
        <div className="py-16 text-center text-text-muted">
          <div className="text-4xl mb-4">📋</div>
          <h3 className="font-semibold text-text-primary mb-2">Lineup Analytics Coming Soon</h3>
          <p className="text-sm max-w-sm mx-auto">
            On/off splits, two-man combos, and lineup efficiency will be available once lineup-level
            box scores are ingested.
          </p>
        </div>
      )}

      {/* ── Injuries ──────────────────────────────────────────────────────── */}
      {activeTab === 'injuries' && (
        <div className="py-16 text-center text-text-muted">
          <div className="text-4xl mb-4">🏥</div>
          <h3 className="font-semibold text-text-primary mb-2">Injury Report Coming Soon</h3>
          <p className="text-sm max-w-sm mx-auto">
            Real-time injury tracking and availability impact analysis will be added in a future update.
          </p>
        </div>
      )}
    </div>
  );
}
