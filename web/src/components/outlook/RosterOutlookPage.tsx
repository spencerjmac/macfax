'use client';

import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import clsx from 'clsx';
import type {
  RosterOutlookData,
  ScenarioPlayer,
  ScenarioProjectionResult,
  OutlookPlayer,
  TeamOutlookProjection,
  PlaceholderArchetype,
} from '@/types/outlook';
import { api } from '@/lib/api';
import { OutlookTopCards } from './OutlookTopCards';
import { PlayerOutlookTable } from './PlayerOutlookTable';
import {
  ContinuityCards,
  PortalDeltaCard,
  FitDetailCard,
  BestFiveLineup,
  CompareSummaryCard,
} from './DiagnosticCards';

// Cast ScenarioProjectionResult → partial TeamOutlookProjection for shared components
function scenarioToProjection(s: ScenarioProjectionResult, baseline: TeamOutlookProjection): TeamOutlookProjection & { approx_national_rank?: number } {
  return {
    ...baseline,
    projected_adj_o: s.projected_adj_o,
    projected_adj_d: s.projected_adj_d,
    projected_adj_em: s.projected_adj_em,
    projected_adj_o_low: s.projected_adj_o_low,
    projected_adj_o_high: s.projected_adj_o_high,
    projected_adj_d_low: s.projected_adj_d_low,
    projected_adj_d_high: s.projected_adj_d_high,
    projected_adj_em_low: s.projected_adj_em_low,
    projected_adj_em_high: s.projected_adj_em_high,
    projected_national_rank: s.approx_national_rank,
    projected_offense_rank: s.projected_offense_rank ?? baseline.projected_offense_rank,
    projected_defense_rank: s.projected_defense_rank ?? baseline.projected_defense_rank,
    team_projection_uncertainty: s.team_projection_uncertainty,
    returner_minutes_fraction: s.returner_minutes_fraction,
    continuity_score: s.continuity_score,
    continuity_value_score: s.continuity_value_score,
    transfer_dependence_score: s.transfer_dependence_score,
    transfer_fit_risk_score: s.transfer_fit_risk_score,
    approx_national_rank: s.approx_national_rank,
  };
}

// ── Stable deterministic negative ID for a placeholder archetype key ─────────
function archetypePlayerId(key: string): number {
  let h = 2166136261;
  for (let i = 0; i < key.length; i++) {
    h ^= key.charCodeAt(i);
    h = (Math.imul(h, 16777619)) >>> 0;
  }
  return -(h % 10_000_000 + 1);
}

function archetypeToPlayer(a: PlaceholderArchetype): OutlookPlayer {
  return {
    player_id: archetypePlayerId(a.key),
    player_name: a.display_name,
    player_short_name: a.display_name,
    position: a.role_bucket === 'G' ? 'G' : a.role_bucket === 'Wing' ? 'F' : 'C',
    headshot_url: null,
    projected_obpr: a.projected_obpr,
    projected_dbpr: a.projected_dbpr,
    projected_bpr: a.projected_bpr,
    minutes_share_p2: a.minutes_share,
    mpg_p2: a.mpg,
    role_bucket: a.role_bucket,
    recruitment_type: 'newcomer',
    projection_uncertainty: a.uncertainty,
    rotation_rank: null,
    n_prior_seasons: 0,
    is_placeholder: true,
    placeholder_key: a.key,
  };
}

const CONF_TIER_LABELS: Record<string, string> = {
  all_conference: 'All-Conference',
  starter:        'Starter',
  rotation:       'Rotation Player',
  bench:          'Bench Player',
};

const CONF_TIER_ORDER: Record<string, number> = {
  all_conference: 0, starter: 1, rotation: 2, bench: 3,
};

const CONF_DISPLAY: Record<string, string> = {
  ACC:  'ACC',         A10:  'Atlantic 10',    AE:   'America East',
  Amer: 'American',    ASun: 'ASUN',           B10:  'Big Ten',
  B12:  'Big 12',      BE:   'Big East',        BSky: 'Big Sky',
  BSth: 'Big South',   BW:   'Big West',        CAA:  'CAA',
  CUSA: 'Conference USA', Horz: 'Horizon League', Ivy:  'Ivy League',
  MAAC: 'MAAC',        MAC:  'MAC',             MEAC: 'MEAC',
  MVC:  'Missouri Valley', MWC: 'Mountain West', NEC:  'NEC',
  OVC:  'Ohio Valley', Pat:  'Patriot League',  SB:   'Sun Belt',
  SC:   'Southern',    SEC:  'SEC',             SWAC: 'SWAC',
  Slnd: 'Southland',   Sum:  'Summit League',   WAC:  'WAC',
  WCC:  'West Coast',
};

function confLabel(code: string): string {
  return CONF_DISPLAY[code] ?? code;
}

// ── Suggested players section ─────────────────────────────────────────────────
function SuggestedSection({
  players,
  addedIds,
  onAdd,
}: {
  players: OutlookPlayer[];
  addedIds: Set<number>;
  onAdd: (p: OutlookPlayer) => void;
}) {
  const [expanded, setExpanded] = useState(true);
  return (
    <div className="border border-ui-border rounded-xl overflow-hidden">
      <button
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 bg-ui-surface text-left hover:bg-ui-surface/80 transition-colors"
      >
        <span className="text-sm font-semibold text-text-primary">Add from this team&apos;s roster</span>
        <span className="text-xs text-text-muted">{expanded ? '▲' : '▼'}</span>
      </button>
      {expanded && (
        <div className="max-h-64 overflow-y-auto divide-y divide-ui-border">
          {players.map(p => {
            const added = addedIds.has(p.player_id);
            return (
              <div
                key={p.player_id}
                onClick={() => !added && onAdd(p)}
                className={clsx(
                  'flex items-center justify-between px-4 py-2.5',
                  added ? 'opacity-40' : 'hover:bg-ui-surface cursor-pointer',
                )}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-text-primary truncate">{p.player_name}</span>
                    {p.position && <span className="text-xs text-text-muted font-mono">{p.position}</span>}
                    {p.role_bucket && (
                      <span className="text-xs px-1 rounded bg-ui-surface border border-ui-border text-text-muted font-mono">
                        {p.role_bucket}
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-text-muted">
                    {p.mpg_p2 != null ? `${p.mpg_p2.toFixed(0)} MPG` : '—'}
                  </div>
                </div>
                <div className="flex-shrink-0 text-right ml-3">
                  <div className={clsx(
                    'text-sm font-mono font-semibold',
                    (p.projected_bpr ?? 0) >= 3 ? 'text-emerald-700' : 'text-text-primary',
                  )}>
                    {p.projected_bpr != null ? `${p.projected_bpr >= 0 ? '+' : ''}${p.projected_bpr.toFixed(2)}` : '—'}
                  </div>
                  <div className="text-xs text-text-muted">BPR</div>
                </div>
                <div className="flex-shrink-0 ml-3 w-12 text-right">
                  {added
                    ? <span className="text-xs text-text-muted">Added</span>
                    : <span className="text-xs px-2 py-1 rounded border border-brand text-brand hover:bg-brand/10 transition-colors">+ Add</span>
                  }
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── D1 player search section ──────────────────────────────────────────────────
function SearchSection({
  season,
  addedIds,
  onAdd,
}: {
  season: number;
  addedIds: Set<number>;
  onAdd: (p: OutlookPlayer) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<OutlookPlayer[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (expanded) setTimeout(() => inputRef.current?.focus(), 50);
    else { setQuery(''); setResults([]); setError(null); }
  }, [expanded]);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (query.trim().length < 2) { setResults([]); return; }
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await api.searchPlayers(query.trim(), season);
        setResults(data);
      } catch {
        setError('Search failed. Try again.');
      } finally {
        setLoading(false);
      }
    }, 300);
  }, [query, season]);

  return (
    <div className="border border-ui-border rounded-xl overflow-hidden">
      <button
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 bg-ui-surface text-left hover:bg-ui-surface/80 transition-colors"
      >
        <span className="text-sm font-semibold text-text-primary">Search any D1 player</span>
        <span className="text-xs text-text-muted">{expanded ? '▲' : '▼'}</span>
      </button>
      {expanded && (
        <>
          <div className="px-4 py-3 border-t border-ui-border">
            <input
              ref={inputRef}
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Type player name…"
              className="w-full px-3 py-2 rounded-lg border border-ui-border text-sm text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-brand/40 focus:border-brand"
            />
          </div>
          <div className="max-h-64 overflow-y-auto divide-y divide-ui-border border-t border-ui-border">
            {loading && <div className="text-center py-5 text-sm text-text-muted animate-pulse">Searching…</div>}
            {error && <div className="text-center py-4 text-sm text-rose-600">{error}</div>}
            {!loading && query.trim().length < 2 && (
              <div className="text-center py-5 text-sm text-text-muted">Type at least 2 characters</div>
            )}
            {!loading && results.length === 0 && query.trim().length >= 2 && !error && (
              <div className="text-center py-5 text-sm text-text-muted">No results for &quot;{query}&quot;</div>
            )}
            {results.map(p => {
              const added = addedIds.has(p.player_id);
              const sr = p as any; // PlayerSearchResult has team_name
              return (
                <div
                  key={p.player_id}
                  onClick={() => !added && onAdd(p)}
                  className={clsx(
                    'flex items-center justify-between px-4 py-2.5',
                    added ? 'opacity-40' : 'hover:bg-ui-surface cursor-pointer',
                  )}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-text-primary">{p.player_name}</span>
                      {p.position && <span className="text-xs text-text-muted font-mono">{p.position}</span>}
                      {p.role_bucket && (
                        <span className="text-xs px-1 rounded bg-ui-surface border border-ui-border text-text-muted font-mono">{p.role_bucket}</span>
                      )}
                    </div>
                    <div className="text-xs text-text-muted mt-0.5">
                      {sr.team_name ?? 'Unknown'}
                      {p.recruitment_type && (
                        <span className="ml-2 capitalize opacity-70">{p.recruitment_type}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex-shrink-0 text-right ml-3">
                    <div className={clsx(
                      'text-sm font-mono font-semibold',
                      (p.projected_bpr ?? 0) >= 3 ? 'text-emerald-700' : 'text-text-primary',
                    )}>
                      {p.projected_bpr?.toFixed(2) ?? '—'}
                    </div>
                    <div className="text-xs text-text-muted">BPR</div>
                  </div>
                  <div className="flex-shrink-0 ml-3 w-12 text-right">
                    {added
                      ? <span className="text-xs text-text-muted">Added</span>
                      : <span className="text-xs px-2 py-1 rounded border border-brand text-brand hover:bg-brand/10 transition-colors">+ Add</span>
                    }
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

// ── Archetype picker section ───────────────────────────────────────────────────
function ArchetypeSection({
  addedIds,
  onAdd,
}: {
  addedIds: Set<number>;
  onAdd: (p: OutlookPlayer) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [activeRole, setActiveRole] = useState<'G' | 'Wing' | 'Big'>('G');
  const [archetypes, setArchetypes] = useState<PlaceholderArchetype[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!expanded || archetypes.length > 0 || loading) return;
    setLoading(true);
    api.getPlaceholderArchetypes()
      .then(d => setArchetypes(d.archetypes))
      .catch(() => setError('Could not load archetypes.'))
      .finally(() => setLoading(false));
  }, [expanded, archetypes.length, loading]);

  // Elite (national All-American) for the active role
  const eliteArchetype = useMemo(
    () => archetypes.find(a => a.quality_tier === 'elite' && a.role_bucket === activeRole && !a.conference),
    [archetypes, activeRole],
  );

  // Per-conference archetypes for the active role, flat sorted list
  const confRows = useMemo(() => {
    return archetypes
      .filter(a => !!a.conference && a.role_bucket === activeRole)
      .sort((a, b) => {
        const nameA = confLabel(a.conference);
        const nameB = confLabel(b.conference);
        if (nameA !== nameB) return nameA.localeCompare(nameB);
        return (CONF_TIER_ORDER[a.quality_tier] ?? 9) - (CONF_TIER_ORDER[b.quality_tier] ?? 9);
      });
  }, [archetypes, activeRole]);

  return (
    <div className="border border-ui-border rounded-xl overflow-hidden">
      <button
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 bg-ui-surface text-left hover:bg-ui-surface/80 transition-colors"
      >
        <span className="text-sm font-semibold text-text-primary">Add hypothetical player</span>
        <span className="text-xs text-text-muted">{expanded ? '▲' : '▼'}</span>
      </button>
      {expanded && (
        <div className="border-t border-ui-border">
          {/* Position tabs */}
          <div className="flex border-b border-ui-border">
            {(['G', 'Wing', 'Big'] as const).map(role => (
              <button
                key={role}
                onClick={() => setActiveRole(role)}
                className={clsx(
                  'flex-1 px-3 py-2 text-xs font-medium transition-colors',
                  activeRole === role
                    ? 'text-brand border-b-2 border-brand bg-white'
                    : 'text-text-muted hover:text-text-primary border-b-2 border-transparent bg-ui-surface',
                )}
              >
                {role === 'G' ? 'Guards' : role === 'Wing' ? 'Wings / Forwards' : 'Bigs'}
              </button>
            ))}
          </div>

          {loading && <div className="text-center py-6 text-sm text-text-muted animate-pulse">Loading archetypes…</div>}
          {error && <div className="text-center py-4 text-sm text-rose-600">{error}</div>}

          {!loading && !error && (
            <div className="max-h-80 overflow-y-auto">
              {/* All-American Caliber at top */}
              {eliteArchetype && (() => {
                const fakeId = archetypePlayerId(eliteArchetype.key);
                const added = addedIds.has(fakeId);
                return (
                  <div
                    onClick={() => !added && onAdd(archetypeToPlayer(eliteArchetype))}
                    className={clsx(
                      'flex items-center justify-between px-4 py-2.5 border-b border-ui-border',
                      added ? 'opacity-40' : 'hover:bg-ui-surface cursor-pointer',
                    )}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-text-primary">All-American Caliber Player</div>
                      <div className="text-xs text-text-muted">{eliteArchetype.mpg.toFixed(0)} MPG · n={eliteArchetype.sample_n}</div>
                    </div>
                    <div className="flex-shrink-0 text-right ml-3">
                      <div className="text-sm font-mono font-semibold text-emerald-700">
                        +{eliteArchetype.projected_bpr.toFixed(2)}
                      </div>
                      <div className="text-xs text-text-muted">BPR</div>
                    </div>
                    <div className="flex-shrink-0 ml-3 w-12 text-right">
                      {added ? <span className="text-xs text-text-muted">Added</span>
                        : <span className="text-xs px-2 py-1 rounded border border-brand text-brand hover:bg-brand/10 transition-colors">+ Add</span>}
                    </div>
                  </div>
                );
              })()}

              {/* Flat list: {Conference Full Name} {Tier} */}
              {confRows.map(a => {
                const fakeId = archetypePlayerId(a.key);
                const added = addedIds.has(fakeId);
                const label = `${confLabel(a.conference)} ${CONF_TIER_LABELS[a.quality_tier] ?? a.quality_tier}`;
                return (
                  <div
                    key={a.key}
                    onClick={() => !added && onAdd(archetypeToPlayer(a))}
                    className={clsx(
                      'flex items-center justify-between px-4 py-2.5 border-b border-ui-border last:border-0',
                      added ? 'opacity-40' : 'hover:bg-ui-surface cursor-pointer',
                    )}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-text-primary">{label}</div>
                      <div className="text-xs text-text-muted">{a.mpg.toFixed(0)} MPG · n={a.sample_n}</div>
                    </div>
                    <div className="flex-shrink-0 text-right ml-3">
                      <div className={clsx(
                        'text-sm font-mono font-semibold',
                        a.projected_bpr >= 3 ? 'text-emerald-700' : 'text-text-primary',
                      )}>
                        {a.projected_bpr >= 0 ? '+' : ''}{a.projected_bpr.toFixed(2)}
                      </div>
                      <div className="text-xs text-text-muted">BPR</div>
                    </div>
                    <div className="flex-shrink-0 ml-3 w-12 text-right">
                      {added ? <span className="text-xs text-text-muted">Added</span>
                        : <span className="text-xs px-2 py-1 rounded border border-brand text-brand hover:bg-brand/10 transition-colors">+ Add</span>}
                    </div>
                  </div>
                );
              })}

              {confRows.length === 0 && !eliteArchetype && (
                <div className="text-center py-6 text-sm text-text-muted">No archetypes available</div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Roster builder table ──────────────────────────────────────────────────────
function RosterTable({
  players,
  onRemove,
}: {
  players: ScenarioPlayer[];
  onRemove: (id: number) => void;
}) {
  if (players.length === 0) {
    return (
      <div className="border border-dashed border-ui-border rounded-xl py-10 text-center text-sm text-text-muted">
        Add players above to build your roster
      </div>
    );
  }
  return (
    <div className="border border-ui-border rounded-xl overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-ui-surface border-b border-ui-border">
            <th className="text-left px-4 py-2.5 font-medium text-text-muted text-xs uppercase tracking-wider">Player</th>
            <th className="text-center px-3 py-2.5 font-medium text-text-muted text-xs uppercase tracking-wider">Pos</th>
            <th className="text-right px-3 py-2.5 font-medium text-text-muted text-xs uppercase tracking-wider">BPR</th>
            <th className="text-right px-3 py-2.5 font-medium text-text-muted text-xs uppercase tracking-wider">MPG</th>
            <th className="text-center px-3 py-2.5 font-medium text-text-muted text-xs uppercase tracking-wider">Role</th>
            <th className="text-center px-3 py-2.5 font-medium text-text-muted text-xs uppercase tracking-wider">Type</th>
            <th className="px-3 py-2.5" />
          </tr>
        </thead>
        <tbody className="divide-y divide-ui-border">
          {players.map(p => (
            <tr key={p.player_id} className="hover:bg-ui-surface/50">
              <td className="px-4 py-2.5 font-medium text-text-primary truncate max-w-[160px]">
                {p.player_name}
              </td>
              <td className="px-3 py-2.5 text-center text-text-muted font-mono text-xs">{p.position || '—'}</td>
              <td className={clsx(
                'px-3 py-2.5 text-right font-mono font-semibold',
                (p.projected_bpr ?? 0) >= 3 ? 'text-emerald-700' : 'text-text-primary',
              )}>
                {p.projected_bpr != null
                  ? `${p.projected_bpr >= 0 ? '+' : ''}${p.projected_bpr.toFixed(2)}`
                  : '—'}
              </td>
              <td className="px-3 py-2.5 text-right text-text-muted">
                {p.mpg_p2 != null ? p.mpg_p2.toFixed(0) : '—'}
              </td>
              <td className="px-3 py-2.5 text-center text-xs text-text-muted font-mono">{p.role_bucket ?? '—'}</td>
              <td className="px-3 py-2.5 text-center">
                <span className={clsx(
                  'text-xs px-1.5 py-0.5 rounded font-medium',
                  p.recruitment_type === 'returner' ? 'bg-emerald-50 text-emerald-700' :
                  p.recruitment_type === 'transfer' ? 'bg-amber-50 text-amber-700' :
                  'bg-sky-50 text-sky-700',
                )}>
                  {p.recruitment_type}
                </span>
              </td>
              <td className="px-3 py-2.5 text-right">
                <button
                  onClick={() => onRemove(p.player_id)}
                  className="text-xs text-text-muted hover:text-rose-600 transition-colors"
                >
                  ✕
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Main page component ───────────────────────────────────────────────────────

interface RosterOutlookPageProps {
  data: RosterOutlookData;
}

export default function RosterOutlookPage({ data }: RosterOutlookPageProps) {
  const { team, season, projection, players, fit } = data;

  // ── Scenario state ─────────────────────────────────────────────────────────
  // Roster starts empty; user builds it from scratch using the three add sections.
  const [scenarioPlayers, setScenarioPlayers] = useState<ScenarioPlayer[]>([]);
  const [scenarioResult, setScenarioResult] = useState<ScenarioProjectionResult | null>(null);
  const [scenarioLoading, setScenarioLoading] = useState(false);
  const [scenarioError, setScenarioError] = useState<string | null>(null);

  const addedIds = useMemo(
    () => new Set(scenarioPlayers.map(p => p.player_id)),
    [scenarioPlayers],
  );

  // ── Actions ────────────────────────────────────────────────────────────────

  // Add from the "suggested players" section (current team's roster).
  // Force recruitment_type='returner': these players are returning next season
  // regardless of how they arrived in the current season.
  function addSuggestedPlayer(player: OutlookPlayer) {
    if (addedIds.has(player.player_id)) return;
    setScenarioPlayers(prev => [
      ...prev,
      { ...player, recruitment_type: 'returner', scenarioState: 'added' },
    ]);
    setScenarioResult(null);
    setScenarioError(null);
  }

  // Add from D1 search or archetype.
  // D1 search players are transfers to this team — their stored recruitment_type
  // reflects the prior season on their old team, not the upcoming season here.
  // Placeholders (archetypes) already carry the correct type ('newcomer').
  function addPlayer(player: OutlookPlayer) {
    if (addedIds.has(player.player_id)) return;
    setScenarioPlayers(prev => [
      ...prev,
      {
        ...player,
        recruitment_type: player.is_placeholder ? player.recruitment_type : 'transfer',
        scenarioState: 'added',
        minutes_share_p2: player.minutes_share_p2 ?? 0.10,
      },
    ]);
    setScenarioResult(null);
    setScenarioError(null);
  }

  function removePlayer(playerId: number) {
    setScenarioPlayers(prev => prev.filter(p => p.player_id !== playerId));
    setScenarioResult(null);
    setScenarioError(null);
  }

  const runScenario = useCallback(async () => {
    if (scenarioPlayers.length === 0) {
      setScenarioError('Roster is empty. Add at least one player.');
      return;
    }

    setScenarioLoading(true);
    setScenarioError(null);

    const totalShares = scenarioPlayers.reduce((s, p) => s + (p.minutes_share_p2 ?? 0.1), 0);
    const scale = totalShares > 0 ? 5.0 / totalShares : 1;

    const playerPayloads = scenarioPlayers.map(p => ({
      player_id: p.player_id ?? null,
      player_name: p.player_name,
      projected_obpr: p.projected_obpr ?? 0,
      projected_dbpr: p.projected_dbpr ?? 0,
      projected_bpr: p.projected_bpr ?? 0,
      minutes_share: (p.minutesOverride ?? p.minutes_share_p2 ?? 0.1) * scale,
      // Issue 1 fix: baseline players become returners next season.
      // In this builder flow all players are 'added', but suggested-roster players
      // already have recruitment_type='returner' set at add time.
      recruitment_type: p.scenarioState === 'baseline' ? 'returner' : p.recruitment_type,
      projection_uncertainty: p.projection_uncertainty ?? 0.5,
    }));

    try {
      const result = await api.getScenarioProjection({
        from_season_year: season.year,
        team_slug: team.slug,
        players: playerPayloads,
      });
      setScenarioResult(result);
    } catch (err: any) {
      setScenarioError(err.message || 'Scenario projection failed.');
    } finally {
      setScenarioLoading(false);
    }
  }, [scenarioPlayers, season.year, team.slug]);

  function resetScenario() {
    setScenarioPlayers([]);
    setScenarioResult(null);
    setScenarioError(null);
  }

  const scenarioProjection = scenarioResult
    ? scenarioToProjection(scenarioResult, projection)
    : null;

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">

      {/* ── Builder sections ── */}
      <div className="space-y-3">
        <h2 className="text-base font-semibold text-text-primary">Build Your Roster</h2>
        <SuggestedSection
          players={players}
          addedIds={addedIds}
          onAdd={addSuggestedPlayer}
        />
        <SearchSection
          season={season.year}
          addedIds={addedIds}
          onAdd={addPlayer}
        />
        <ArchetypeSection
          addedIds={addedIds}
          onAdd={addPlayer}
        />
      </div>

      {/* ── Roster table ── */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-text-primary">
            Your Roster
            {scenarioPlayers.length > 0 && (
              <span className="ml-2 text-sm font-normal text-text-muted">
                ({scenarioPlayers.length} player{scenarioPlayers.length !== 1 ? 's' : ''})
              </span>
            )}
          </h2>
          {scenarioPlayers.length > 0 && (
            <button
              onClick={resetScenario}
              className="text-xs text-text-muted hover:text-text-primary transition-colors"
            >
              Clear all
            </button>
          )}
        </div>
        <RosterTable players={scenarioPlayers} onRemove={removePlayer} />
      </div>

      {/* ── Run button ── */}
      <div className="flex items-center gap-3">
        <button
          onClick={runScenario}
          disabled={scenarioLoading || scenarioPlayers.length === 0}
          className={clsx(
            'px-6 py-2.5 rounded-lg font-semibold text-sm transition-colors',
            'bg-brand text-white hover:bg-brand-hover disabled:opacity-50 disabled:cursor-not-allowed',
          )}
        >
          {scenarioLoading ? 'Computing…' : 'Run Scenario'}
        </button>
        {scenarioResult && (
          <button
            onClick={resetScenario}
            className="text-sm px-3 py-2 rounded-lg border border-ui-border text-text-muted hover:text-text-primary transition-colors"
          >
            Reset
          </button>
        )}
      </div>

      {/* ── Error ── */}
      {scenarioError && (
        <div className="bg-rose-50 border border-rose-200 rounded-lg px-4 py-3 text-sm text-rose-700">
          {scenarioError}
        </div>
      )}

      {/* ── Results (only after run) ── */}
      {scenarioResult && scenarioProjection && (
        <div className="space-y-6 pt-2 border-t border-ui-border">
          <div>
            <h2 className="text-base font-semibold text-text-primary mb-1">Scenario Results</h2>
            <p className="text-xs text-text-muted">Projected {season.projected_season_year} season</p>
          </div>

          <OutlookTopCards
            projection={projection}
            fit={fit}
            scenarioProjection={scenarioProjection}
            isScenarioMode={true}
          />

          <CompareSummaryCard baseline={projection} scenario={scenarioProjection} />

          <div>
            <h2 className="text-base font-semibold text-text-primary mb-3">Roster Projections</h2>
            <PlayerOutlookTable
              players={scenarioPlayers}
              isScenarioMode={true}
              canEdit={false}
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2 space-y-4">
              <ContinuityCards projection={scenarioProjection} scenarioProjection={null} />
              <PortalDeltaCard projection={projection} scenarioProjection={scenarioProjection} />
            </div>
            <div className="space-y-4">
              <BestFiveLineup players={scenarioPlayers} />
              <FitDetailCard fit={fit} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
