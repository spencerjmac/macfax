'use client';

import { useState, useRef, useEffect } from 'react';
import clsx from 'clsx';
import type { OutlookPlayer, PlayerSearchResult, PlaceholderArchetype } from '@/types/outlook';
import { api } from '@/lib/api';

interface PlayerSearchModalProps {
  isOpen: boolean;
  season: number;
  alreadyAddedIds: Set<number>;
  onAdd: (player: OutlookPlayer) => void;
  onClose: () => void;
}

type Tab = 'search' | 'archetype';

// Stable deterministic negative ID for a placeholder archetype key.
// Ensures duplicate-detection via alreadyAddedIds works reliably.
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
    // Placeholders are synthetic external additions — they have no prior DB
    // history and represent hypothetical roster additions beyond the current
    // team.  'newcomer' is the correct recruitment_type: the scenario engine
    // applies a newcomer uncertainty multiplier that is appropriate for a
    // player whose college track record is unknown or absent.
    recruitment_type: 'newcomer',
    projection_uncertainty: a.uncertainty,
    rotation_rank: null,
    n_prior_seasons: 0,
    // Explicit synthetic-player markers so the UI and any downstream
    // inspection can identify this as an archetype-derived placeholder.
    is_placeholder: true,
    placeholder_key: a.key,
  };
}

const TIER_LABELS: Record<string, string> = {
  elite:          'All-American',
  all_conference: 'All-Conference',
  starter:        'Starter',
  rotation:       'Reserve',
  bench:          'Bench',
};

const CONF_LABELS: Record<string, string> = {
  national:  'National',
  power:     'Power Conf',
  high_mid:  'High Mid-Major',
  mid_major: 'Mid-Major',
};

// Display order for archetype groups
const CONF_GROUP_ORDER = ['national', 'power', 'high_mid', 'mid_major'];

// Ordering for display within each group
const TIER_ORDER: Record<string, number> = { elite: 0, starter: 1, rotation: 2 };

export function PlayerSearchModal({
  isOpen,
  season,
  alreadyAddedIds,
  onAdd,
  onClose,
}: PlayerSearchModalProps) {
  const [activeTab, setActiveTab] = useState<Tab>('search');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<PlayerSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Archetype state
  const [archetypes, setArchetypes] = useState<PlaceholderArchetype[]>([]);
  const [archetypeLoading, setArchetypeLoading] = useState(false);
  const [archetypeError, setArchetypeError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      if (activeTab === 'search') {
        setTimeout(() => inputRef.current?.focus(), 50);
      }
    } else {
      setQuery('');
      setResults([]);
      setError(null);
    }
  }, [isOpen, activeTab]);

  // Load archetypes when the archetype tab is first opened
  useEffect(() => {
    if (!isOpen || activeTab !== 'archetype') return;
    if (archetypes.length > 0 || archetypeLoading) return;
    setArchetypeLoading(true);
    setArchetypeError(null);
    api.getPlaceholderArchetypes()
      .then(data => setArchetypes(data.archetypes))
      .catch(() => setArchetypeError('Could not load archetypes. Try again.'))
      .finally(() => setArchetypeLoading(false));
  }, [isOpen, activeTab, archetypes.length, archetypeLoading]);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
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

  if (!isOpen) return null;

  function handleAdd(player: OutlookPlayer) {
    onAdd(player);
  }

  // Group archetypes for display: national → power → high_mid → mid_major, sorted by tier within
  const archetypeGroups: Array<{ label: string; group: string; items: PlaceholderArchetype[] }> = [];
  const grouped: Record<string, PlaceholderArchetype[]> = {};
  for (const a of archetypes) {
    const g = a.conf_group;
    if (!grouped[g]) grouped[g] = [];
    grouped[g].push(a);
  }
  for (const g of CONF_GROUP_ORDER) {
    const items = grouped[g] ?? [];
    items.sort((a, b) => {
      const ta = TIER_ORDER[a.quality_tier] ?? 9;
      const tb = TIER_ORDER[b.quality_tier] ?? 9;
      if (ta !== tb) return ta - tb;
      // Within tier, order G → Wing → Big
      const roles = { G: 0, Wing: 1, Big: 2 };
      return (roles[a.role_bucket ?? 'G'] ?? 3) - (roles[b.role_bucket ?? 'G'] ?? 3);
    });
    if (items.length > 0) {
      archetypeGroups.push({ label: CONF_LABELS[g] ?? g, group: g, items });
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-24 bg-black/40 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden border border-ui-border">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-ui-border">
          <h2 className="font-semibold text-text-primary">Add Player to Scenario</h2>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-primary transition-colors text-lg leading-none"
          >
            ✕
          </button>
        </div>

        {/* Tab switcher */}
        <div className="flex border-b border-ui-border">
          {(['search', 'archetype'] as Tab[]).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={clsx(
                'flex-1 px-4 py-2.5 text-sm font-medium transition-colors',
                activeTab === tab
                  ? 'text-brand border-b-2 border-brand bg-brand/5'
                  : 'text-text-muted hover:text-text-primary border-b-2 border-transparent',
              )}
            >
              {tab === 'search' ? 'Search Players' : 'Use Archetype'}
            </button>
          ))}
        </div>

        {/* ── Search tab ── */}
        {activeTab === 'search' && (
          <>
            <div className="px-5 py-3 border-b border-ui-border">
              <input
                ref={inputRef}
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="Search player name…"
                className="w-full px-3 py-2 rounded-lg border border-ui-border text-sm text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-brand/40 focus:border-brand"
              />
            </div>

            <div className="overflow-y-auto max-h-96">
              {loading && (
                <div className="text-center py-6 text-sm text-text-muted animate-pulse">Searching…</div>
              )}
              {error && (
                <div className="text-center py-4 text-sm text-rose-600">{error}</div>
              )}
              {!loading && results.length === 0 && query.trim().length >= 2 && !error && (
                <div className="text-center py-6 text-sm text-text-muted">
                  No players found for &quot;{query}&quot;
                </div>
              )}
              {!loading && query.trim().length < 2 && (
                <div className="text-center py-6 text-sm text-text-muted">
                  Type at least 2 characters to search
                </div>
              )}

              {results.map((player) => {
                const alreadyAdded = alreadyAddedIds.has(player.player_id);
                return (
                  <div
                    key={player.player_id}
                    className={clsx(
                      'flex items-center justify-between px-5 py-3 border-b border-ui-border last:border-0',
                      alreadyAdded ? 'opacity-50' : 'hover:bg-ui-surface cursor-pointer',
                    )}
                    onClick={() => !alreadyAdded && handleAdd(player)}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium text-text-primary">{player.player_name}</span>
                        {player.position && (
                          <span className="text-xs text-text-muted font-mono">{player.position}</span>
                        )}
                        {player.role_bucket && (
                          <span className="text-xs px-1 py-0 rounded bg-ui-surface text-text-muted font-mono border border-ui-border">
                            {player.role_bucket}
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-text-muted mt-0.5">
                        {player.team_name ?? 'Unknown team'}
                        {player.recruitment_type && (
                          <span className="ml-2 capitalize opacity-70">{player.recruitment_type}</span>
                        )}
                      </div>
                    </div>

                    <div className="flex-shrink-0 text-right ml-3">
                      <div className={clsx(
                        'text-sm font-mono font-semibold',
                        (player.projected_bpr ?? 0) >= 3 ? 'text-emerald-700' : 'text-text-primary',
                      )}>
                        {player.projected_bpr?.toFixed(2) ?? '—'}
                      </div>
                      <div className="text-xs text-text-muted">BPR</div>
                    </div>

                    <div className="flex-shrink-0 ml-3">
                      {alreadyAdded ? (
                        <span className="text-xs text-text-muted">Added</span>
                      ) : (
                        <span className="text-xs px-2 py-1 rounded border border-brand text-brand hover:bg-brand/10 transition-colors">
                          + Add
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="px-5 py-3 bg-ui-surface text-xs text-text-muted border-t border-ui-border">
              Players shown are from the same source season. Projected values carry over
              from their current team&apos;s Phase 1-2 computation.
            </div>
          </>
        )}

        {/* ── Archetype tab ── */}
        {activeTab === 'archetype' && (
          <>
            <div className="overflow-y-auto max-h-[480px]">
              {archetypeLoading && (
                <div className="text-center py-8 text-sm text-text-muted animate-pulse">
                  Loading archetypes…
                </div>
              )}
              {archetypeError && (
                <div className="text-center py-6 text-sm text-rose-600">{archetypeError}</div>
              )}
              {!archetypeLoading && !archetypeError && archetypeGroups.map(({ label, group, items }) => (
                <div key={group}>
                  <div className="px-5 py-2 sticky top-0 bg-ui-surface border-b border-ui-border z-10">
                    <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">
                      {label}
                    </span>
                  </div>
                  {items.map(archetype => {
                    const fakeId = archetypePlayerId(archetype.key);
                    const alreadyAdded = alreadyAddedIds.has(fakeId);
                    const bpr = archetype.projected_bpr;
                    return (
                      <div
                        key={archetype.key}
                        className={clsx(
                          'flex items-center justify-between px-5 py-3 border-b border-ui-border last:border-0',
                          alreadyAdded ? 'opacity-50' : 'hover:bg-ui-surface cursor-pointer',
                        )}
                        onClick={() => !alreadyAdded && handleAdd(archetypeToPlayer(archetype))}
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-medium text-text-primary">
                              {archetype.display_name}
                            </span>
                            {archetype.role_bucket && (
                              <span className="text-xs px-1 py-0 rounded bg-ui-surface text-text-muted font-mono border border-ui-border">
                                {archetype.role_bucket}
                              </span>
                            )}
                          </div>
                          <div className="text-xs text-text-muted mt-0.5">
                            {TIER_LABELS[archetype.quality_tier] ?? archetype.quality_tier}
                            <span className="mx-1">·</span>
                            {archetype.mpg.toFixed(0)} MPG
                            <span className="mx-1">·</span>
                            n={archetype.sample_n.toLocaleString()} players
                          </div>
                        </div>

                        <div className="flex-shrink-0 text-right ml-3">
                          <div className={clsx(
                            'text-sm font-mono font-semibold',
                            bpr >= 3 ? 'text-emerald-700' : 'text-text-primary',
                          )}>
                            {bpr >= 0 ? '+' : ''}{bpr.toFixed(2)}
                          </div>
                          <div className="text-xs text-text-muted">BPR</div>
                        </div>

                        <div className="flex-shrink-0 ml-3">
                          {alreadyAdded ? (
                            <span className="text-xs text-text-muted">Added</span>
                          ) : (
                            <span className="text-xs px-2 py-1 rounded border border-brand text-brand hover:bg-brand/10 transition-colors">
                              + Add
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>

            <div className="px-5 py-3 bg-ui-surface text-xs text-text-muted border-t border-ui-border">
              Archetypes are derived from the median stats of real D1 player cohorts.
              Each represents a realistic, data-grounded stand-in for scenario planning.
            </div>
          </>
        )}
      </div>
    </div>
  );
}

