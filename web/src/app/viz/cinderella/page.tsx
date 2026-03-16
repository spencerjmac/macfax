'use client';

import { useState, useEffect, useMemo } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { CinderellaData, CinderellaTeam } from '@/types';
import clsx from 'clsx';

// ---------------------------------------------------------------------------
// Tiers
// ---------------------------------------------------------------------------

type Tier = { bg: string; text: string; border: string; label: string };

const TIERS: Tier[] = [
  { bg: 'bg-red-50',    text: 'text-red-800',    border: 'border-red-300',    label: 'Elite Threat'    },
  { bg: 'bg-amber-50',  text: 'text-amber-800',  border: 'border-amber-300',  label: 'Notable Threat'  },
  { bg: 'bg-blue-50',   text: 'text-blue-800',   border: 'border-blue-200',   label: 'Moderate Risk'   },
  { bg: 'bg-slate-50',  text: 'text-slate-500',  border: 'border-slate-200',  label: 'Low Threat'      },
];

function getTier(score: number): Tier {
  if (score >= 65) return TIERS[0];
  if (score >= 50) return TIERS[1];
  if (score >= 35) return TIERS[2];
  return TIERS[3];
}

function getTierColor(score: number): string {
  if (score >= 65) return 'bg-red-500';
  if (score >= 50) return 'bg-amber-400';
  if (score >= 35) return 'bg-blue-400';
  return 'bg-slate-300';
}

// ---------------------------------------------------------------------------
// Sub-score bar
// ---------------------------------------------------------------------------

function ScoreBar({
  label,
  value,
  max = 100,
  color,
}: {
  label: string;
  value: number;
  max?: number;
  color?: string;
}) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-text-muted">{label}</span>
        <span className="font-mono font-semibold">{value.toFixed(1)}</span>
      </div>
      <div className="h-1.5 bg-ui-border rounded-full overflow-hidden">
        <div
          className={clsx('h-full rounded-full transition-all', color ?? 'bg-brand')}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component detail tooltip labels
// ---------------------------------------------------------------------------

const COMPONENT_LABELS: Record<string, string> = {
  adj_em_pct:      'AdjEM pctile',
  adj_d_pct:       'Defense pctile',
  opp_efg_pct:     'Opp eFG% pctile',
  opp_tov_pct:     'Forced TOV% pctile',
  tov_avoid_pct:   'TOV avoid pctile',
  orb_pct:         'ORB% pctile',
  fg3_rate_pct:    '3PA rate pctile',
  fg3_pct_pct:     '3P% pctile',
  slow_tempo_pct:  'Slow tempo pctile',
  wab_pct:         'WAB pctile',
  sos_pct:         'SOS pctile',
};

// ---------------------------------------------------------------------------
// Team row
// ---------------------------------------------------------------------------

function TeamRow({ team, rank }: { team: CinderellaTeam; rank: number }) {
  const [expanded, setExpanded] = useState(false);
  const { cinderella: cin } = team;
  const tier = getTier(cin.profile_score);

  return (
    <>
      <tr
        className={clsx(
          'border-b border-ui-border cursor-pointer select-none transition-colors',
          expanded ? 'bg-ui-hover' : 'hover:bg-ui-hover',
        )}
        onClick={() => setExpanded((v) => !v)}
      >
        {/* Rank */}
        <td className="px-3 py-3 text-center text-sm font-mono font-semibold text-text-muted w-10">
          {rank}
        </td>

        {/* Team */}
        <td className="px-3 py-3 min-w-[180px]">
          <div className="flex items-center gap-2">
            {team.team_logo && (
              <img
                src={team.team_logo}
                alt={team.team_name}
                className="w-7 h-7 object-contain shrink-0"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
            )}
            <div>
              <Link
                href={`/team/${team.team_slug}`}
                className="font-semibold text-sm hover:text-brand transition-colors"
                onClick={(e) => e.stopPropagation()}
              >
                {team.tournament_seed != null && (
                  <span className="text-[11px] font-bold text-brand/70 mr-1">
                    {team.tournament_seed}
                  </span>
                )}
                {team.team_name}
              </Link>
              <div className="text-xs text-text-muted">
                {team.conference}
                {team.tournament_region && (
                  <span className="ml-1 text-brand/60">· {team.tournament_region}</span>
                )}
              </div>
            </div>
          </div>
        </td>

        {/* Record */}
        <td className="px-3 py-3 text-sm font-mono text-center hidden sm:table-cell">
          {team.record}
        </td>

        {/* AdjEM */}
        <td className="px-3 py-3 text-sm font-mono text-center hidden md:table-cell">
          {team.adj_em > 0 ? '+' : ''}{team.adj_em.toFixed(1)}
        </td>

        {/* Overall score bar */}
        <td className="px-3 py-3 w-36 hidden sm:table-cell">
          <div className="flex items-center gap-2">
            <div className="flex-1 h-2 bg-ui-border rounded-full overflow-hidden">
              <div
                className={clsx('h-full rounded-full', getTierColor(cin.profile_score))}
                style={{ width: `${cin.profile_score}%` }}
              />
            </div>
            <span className={clsx('text-xs font-mono font-bold w-8 text-right', tier.text)}>
              {cin.profile_score.toFixed(0)}
            </span>
          </div>
        </td>

        {/* Sub-scores */}
        <td className="px-2 py-3 text-xs font-mono text-center hidden xl:table-cell w-14">
          <span className="text-blue-600">{cin.defense_score.toFixed(0)}</span>
        </td>
        <td className="px-2 py-3 text-xs font-mono text-center hidden xl:table-cell w-14">
          <span className="text-green-600">{cin.possession_score.toFixed(0)}</span>
        </td>
        <td className="px-2 py-3 text-xs font-mono text-center hidden xl:table-cell w-14">
          <span className="text-purple-600">{cin.variance_score.toFixed(0)}</span>
        </td>
        <td className="px-2 py-3 text-xs font-mono text-center hidden xl:table-cell w-14">
          <span className="text-amber-600">{cin.resume_score.toFixed(0)}</span>
        </td>

        {/* Tier label */}
        <td className="px-3 py-3 hidden lg:table-cell w-28">
          <span className={clsx(
            'text-xs font-medium px-2 py-0.5 rounded-full border',
            tier.bg, tier.text, tier.border,
          )}>
            {tier.label}
          </span>
        </td>

        {/* Seed residual */}
        {cin.seed_residual != null && (
          <td className="px-3 py-3 text-center text-xs font-mono hidden lg:table-cell w-16">
            <span className={clsx(
              'font-semibold',
              cin.seed_residual > 0 ? 'text-red-600' : cin.seed_residual < 0 ? 'text-slate-400' : 'text-text-muted',
            )}>
              {cin.seed_residual > 0 ? '+' : ''}{cin.seed_residual}
            </span>
          </td>
        )}

        {/* P(Sweet 16) */}
        {cin.seed_residual != null && (
          <td className="px-3 py-3 text-center text-xs font-mono hidden lg:table-cell w-16">
            {cin.p_sweet16 != null ? (
              <span className={clsx(
                'font-semibold',
                cin.p_sweet16 >= 0.20 ? 'text-emerald-600' :
                cin.p_sweet16 >= 0.10 ? 'text-blue-600' : 'text-text-muted',
              )}>
                {(cin.p_sweet16 * 100).toFixed(0)}%
              </span>
            ) : (
              <span className="text-text-muted">—</span>
            )}
          </td>
        )}

        {/* Expand */}
        <td className="px-3 py-3 text-center text-text-muted text-xs w-8">
          <span className={clsx('transition-transform inline-block', expanded ? 'rotate-90' : '')}>▶</span>
        </td>
      </tr>

      {expanded && (
        <tr className="border-b border-ui-border bg-ui-surface/50">
          <td colSpan={12} className="px-4 py-4">
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4 mb-4">
              <div className="space-y-2">
                <div className="text-xs font-bold text-text-muted uppercase tracking-wide mb-2">
                  Underseeded ({cin.underseeded_strength.toFixed(0)})
                </div>
                <ScoreBar
                  label="AdjEM pctile"
                  value={cin.components.adj_em_pct}
                  color="bg-brand"
                />
                {cin.seed_residual != null && (
                  <div className="text-xs text-text-muted pt-1">
                    Seed residual: <span className={clsx(
                      'font-semibold font-mono',
                      cin.seed_residual > 0 ? 'text-red-600' : 'text-slate-400',
                    )}>
                      {cin.seed_residual > 0 ? '+' : ''}{cin.seed_residual}
                    </span>
                    <span className="ml-1 text-[10px]">(actual − expected seed)</span>
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <div className="text-xs font-bold text-blue-600 uppercase tracking-wide mb-2">
                  Defense ({cin.defense_score.toFixed(0)})
                </div>
                <ScoreBar label="AdjD pctile"        value={cin.components.adj_d_pct}    color="bg-blue-500" />
                <ScoreBar label="Opp eFG% pctile"    value={cin.components.opp_efg_pct}  color="bg-blue-400" />
                <ScoreBar label="Forced TOV% pctile" value={cin.components.opp_tov_pct}  color="bg-blue-300" />
              </div>

              <div className="space-y-2">
                <div className="text-xs font-bold text-green-600 uppercase tracking-wide mb-2">
                  Possession ({cin.possession_score.toFixed(0)})
                </div>
                <ScoreBar label="TOV avoid pctile"   value={cin.components.tov_avoid_pct} color="bg-green-500" />
                <ScoreBar label="Forced TOV% pctile" value={cin.components.opp_tov_pct}   color="bg-green-400" />
                <ScoreBar label="ORB% pctile"        value={cin.components.orb_pct}        color="bg-green-300" />
              </div>

              <div className="space-y-2">
                <div className="text-xs font-bold text-purple-600 uppercase tracking-wide mb-2">
                  Variance ({cin.variance_score.toFixed(0)})
                </div>
                <ScoreBar label="3PA rate pctile"   value={cin.components.fg3_rate_pct}   color="bg-purple-500" />
                <ScoreBar label="3P% pctile"        value={cin.components.fg3_pct_pct}    color="bg-purple-400" />
                <ScoreBar label="Slow tempo pctile" value={cin.components.slow_tempo_pct} color="bg-purple-300" />
              </div>

              <div className="space-y-2">
                <div className="text-xs font-bold text-amber-600 uppercase tracking-wide mb-2">
                  Resume ({cin.resume_score.toFixed(0)})
                </div>
                <ScoreBar label="WAB pctile" value={cin.components.wab_pct} color="bg-amber-500" />
                <ScoreBar label="SOS pctile" value={cin.components.sos_pct} color="bg-amber-400" />
              </div>
            </div>

            <div className="text-xs text-text-muted border-t border-ui-border pt-2">
              All percentiles computed against the full D1 field ({/* shown dynamically */}). Higher = better.
              {cin.seed_residual != null && cin.seed_residual > 0 && (
                <span className="ml-2 text-red-600 font-semibold">
                  ⚠ Seeded {cin.seed_residual} spots worse than AdjEM suggests — Cinderella alert!
                </span>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Seed filter options
// ---------------------------------------------------------------------------

const SEED_FILTERS = [
  { label: 'All Teams',    min: 1,  max: 16 },
  { label: 'Seeds 9–16',   min: 9,  max: 16 },
  { label: 'Seeds 10–16',  min: 10, max: 16 },
  { label: 'Seeds 12–16',  min: 12, max: 16 },
  { label: 'Seeds 13–16',  min: 13, max: 16 },
] as const;

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function CinderellaPage() {
  const [data, setData] = useState<CinderellaData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [season, setSeason] = useState(2026);
  const [showAll, setShowAll] = useState(false);
  const [seedFilter, setSeedFilter] = useState<(typeof SEED_FILTERS)[number]>(SEED_FILTERS[1]);
  const [search, setSearch] = useState('');

  useEffect(() => {
    load();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [season, showAll, seedFilter]);

  async function load() {
    try {
      setLoading(true);
      setError(null);
      const result = await api.getCinderella({
        season,
        min_seed: showAll ? 1 : seedFilter.min,
        max_seed: showAll ? 16 : seedFilter.max,
        show_all: showAll || !data?.has_tournament,
      });
      setData(result);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }

  const filtered = useMemo(() => {
    if (!data) return [];
    const q = search.trim().toLowerCase();
    if (!q) return data.teams;
    return data.teams.filter(
      (t) =>
        t.team_name.toLowerCase().includes(q) ||
        t.conference.toLowerCase().includes(q) ||
        (t.tournament_region?.toLowerCase().includes(q) ?? false),
    );
  }, [data, search]);

  const hasTournament = data?.has_tournament ?? false;

  // Tier summary counts
  const tierCounts = useMemo(() => {
    if (!data) return null;
    const teams = data.teams;
    return {
      elite:    teams.filter((t) => t.cinderella.profile_score >= 65).length,
      notable:  teams.filter((t) => t.cinderella.profile_score >= 50 && t.cinderella.profile_score < 65).length,
      moderate: teams.filter((t) => t.cinderella.profile_score >= 35 && t.cinderella.profile_score < 50).length,
      low:      teams.filter((t) => t.cinderella.profile_score < 35).length,
    };
  }, [data]);

  const hasSeedResiduals = data?.teams.some((t) => t.cinderella.seed_residual != null) ?? false;

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-start gap-4 mb-2">
          <span className="text-4xl">🥿</span>
          <div>
            <h1 className="text-3xl font-bold">Cinderella Index</h1>
            <p className="text-text-muted mt-1">
              Which teams are primed to pull off a tournament upset? Five pillars — underseeded
              strength, defense, possession, variance, and resume — combine into a single profile
              score. Higher = more dangerous.
            </p>
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap gap-3 mb-6 items-center">
        {/* Season */}
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-text-muted">Season:</label>
          <select
            value={season}
            onChange={(e) => setSeason(Number(e.target.value))}
            className="text-sm border border-ui-border rounded px-2 py-1 bg-ui-surface"
          >
            <option value={2026}>2025–26</option>
            <option value={2025}>2024–25</option>
          </select>
        </div>

        {/* Seed filter pills (only if tournament data available) */}
        {hasTournament && (
          <div className="flex gap-1.5">
            {SEED_FILTERS.map((f) => (
              <button
                key={f.label}
                onClick={() => { setSeedFilter(f); setShowAll(f.min === 1); }}
                className={clsx(
                  'text-xs px-3 py-1.5 rounded-full border transition-colors font-medium',
                  !showAll && seedFilter.label === f.label
                    ? 'bg-brand text-white border-brand'
                    : f.min === 1 && showAll
                    ? 'bg-brand text-white border-brand'
                    : 'border-ui-border text-text-muted hover:border-brand hover:text-brand',
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
        )}

        {/* Search */}
        <div className="flex-1 min-w-[160px] max-w-xs">
          <input
            type="text"
            placeholder="Search teams..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full text-sm border border-ui-border rounded px-3 py-1.5 bg-ui-surface placeholder:text-text-muted"
          />
        </div>
      </div>

      {/* Tier summary */}
      {tierCounts && (
        <div className="flex flex-wrap gap-3 mb-6">
          {[
            { label: 'Elite Threat',   count: tierCounts.elite,    color: 'bg-red-50 text-red-800 border-red-300'       },
            { label: 'Notable Threat', count: tierCounts.notable,  color: 'bg-amber-50 text-amber-800 border-amber-300' },
            { label: 'Moderate Risk',  count: tierCounts.moderate, color: 'bg-blue-50 text-blue-800 border-blue-200'    },
            { label: 'Low Threat',     count: tierCounts.low,      color: 'bg-slate-50 text-slate-500 border-slate-200' },
          ].map(({ label, count, color }) => (
            <div key={label} className={clsx('flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-medium', color)}>
              <span className="font-bold text-sm">{count}</span>
              <span>{label}</span>
            </div>
          ))}
        </div>
      )}

      {/* Pre-bracket callout */}
      {!hasTournament && !loading && (
        <div className="mb-5 p-4 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-900">
          <span className="font-semibold">Seeds not yet assigned.</span> Showing all D1 teams ranked
          by their Cinderella profile. Seed-residual scores will automatically activate after the
          bracket is set on Selection Sunday.
        </div>
      )}

      {/* Loading / Error */}
      {loading && (
        <div className="text-center py-16 text-text-muted">Loading Cinderella scores…</div>
      )}
      {error && (
        <div className="text-center py-8 text-red-600">{error}</div>
      )}

      {/* Table */}
      {!loading && !error && data && (
        <div className="overflow-x-auto rounded-lg border border-ui-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-ui-hover border-b border-ui-border">
                <th className="px-3 py-3 text-center text-xs font-semibold text-text-muted w-10">#</th>
                <th className="px-3 py-3 text-left text-xs font-semibold text-text-muted">Team</th>
                <th className="px-3 py-3 text-center text-xs font-semibold text-text-muted hidden sm:table-cell">Record</th>
                <th className="px-3 py-3 text-center text-xs font-semibold text-text-muted hidden md:table-cell">AdjEM</th>
                <th className="px-3 py-3 text-center text-xs font-semibold text-text-muted hidden sm:table-cell">Score</th>
                <th className="px-2 py-3 text-center text-xs font-semibold text-blue-600 hidden xl:table-cell">DEF</th>
                <th className="px-2 py-3 text-center text-xs font-semibold text-green-600 hidden xl:table-cell">POS</th>
                <th className="px-2 py-3 text-center text-xs font-semibold text-purple-600 hidden xl:table-cell">VAR</th>
                <th className="px-2 py-3 text-center text-xs font-semibold text-amber-600 hidden xl:table-cell">RES</th>
                <th className="px-3 py-3 text-center text-xs font-semibold text-text-muted hidden lg:table-cell">Tier</th>
                {hasSeedResiduals && (
                  <th className="px-3 py-3 text-center text-xs font-semibold text-text-muted hidden lg:table-cell" title="Actual seed minus expected seed from AdjEM rank. Positive = more dangerous than seeded.">
                    Δ Seed
                  </th>
                )}
                {hasSeedResiduals && (
                  <th className="px-3 py-3 text-center text-xs font-semibold text-emerald-600 hidden lg:table-cell" title="Analytical probability of advancing to the Sweet 16 based on this team's actual bracket path.">
                    P(S16)
                  </th>
                )}
                <th className="w-8" />
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={12} className="text-center py-12 text-text-muted">
                    No teams match your filters.
                  </td>
                </tr>
              ) : (
                filtered.map((team, i) => (
                  <TeamRow key={team.team_slug} team={team} rank={i + 1} />
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Methodology footnote */}
      {data && (
        <div className="mt-8 p-5 bg-ui-surface border border-ui-border rounded-lg text-xs text-text-muted space-y-2">
          <div className="font-semibold text-text-primary text-sm mb-2">Methodology</div>
          <p>
            The <strong>Cinderella Index</strong> measures a team's potential to pull off a tournament
            upset by combining five pillars. All sub-scores are percentiles computed against the full D1
            field, then weighted into a 0–100 profile score.
          </p>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mt-3">
            {[
              { label: 'Underseeded (28%)',   detail: 'AdjEM percentile + seed residual (post-bracket)',          color: 'text-brand'   },
              { label: 'Defense (27%)',        detail: 'AdjD (50%) + Opp eFG% (30%) + Forced TOV% (20%)',         color: 'text-blue-600' },
              { label: 'Possession (21%)',     detail: 'TOV avoid (40%) + Forced TOV% (35%) + ORB% (25%)',        color: 'text-green-600' },
              { label: 'Variance (14%)',       detail: '3PA rate (45%) + 3P% (25%) + Slow tempo (30%)',           color: 'text-purple-600' },
              { label: 'Resume (10%)',         detail: 'WAB (60%) + SOS difficulty (40%)',                        color: 'text-amber-600' },
            ].map(({ label, detail, color }) => (
              <div key={label} className="p-2 bg-ui-hover rounded border border-ui-border">
                <div className={clsx('font-semibold text-[11px] mb-1', color)}>{label}</div>
                <div className="text-[10px] leading-relaxed">{detail}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
