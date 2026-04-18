'use client';

import { useState, useCallback, useMemo } from 'react';
import clsx from 'clsx';
import type {
  RosterOutlookData,
  ScenarioPlayer,
  ScenarioProjectionResult,
  OutlookPlayer,
  TeamOutlookProjection,
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
import { PlayerSearchModal } from './PlayerSearchModal';

type ViewMode = 'baseline' | 'edit' | 'compare';

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
    national_rank_range_low: s.national_rank_range_low,
    national_rank_range_high: s.national_rank_range_high,
    // offense/defense rank ranges reuse baseline as approximation (single-team scenario)
    projected_offense_rank: baseline.projected_offense_rank,
    offense_rank_range_low: baseline.offense_rank_range_low,
    offense_rank_range_high: baseline.offense_rank_range_high,
    projected_defense_rank: baseline.projected_defense_rank,
    defense_rank_range_low: baseline.defense_rank_range_low,
    defense_rank_range_high: baseline.defense_rank_range_high,
    team_projection_uncertainty: s.team_projection_uncertainty,
    returner_minutes_fraction: s.returner_minutes_fraction,
    continuity_score: s.continuity_score,
    continuity_value_score: s.continuity_value_score,
    transfer_dependence_score: s.transfer_dependence_score,
    transfer_fit_risk_score: s.transfer_fit_risk_score,
    approx_national_rank: s.approx_national_rank,
  };
}

interface RosterOutlookPageProps {
  data: RosterOutlookData;
}

export default function RosterOutlookPage({ data }: RosterOutlookPageProps) {
  const { team, season, projection, players, fit } = data;

  // ── Scenario state ─────────────────────────────────────────────────────────
  const [mode, setMode] = useState<ViewMode>('baseline');
  const [scenarioPlayers, setScenarioPlayers] = useState<ScenarioPlayer[]>(() =>
    players.map(p => ({ ...p, scenarioState: 'baseline' as const }))
  );
  const [scenarioResult, setScenarioResult] = useState<ScenarioProjectionResult | null>(null);
  const [scenarioLoading, setScenarioLoading] = useState(false);
  const [scenarioError, setScenarioError] = useState<string | null>(null);
  const [showAddPlayer, setShowAddPlayer] = useState(false);

  // ── Active players in the scenario (not removed) ──────────────────────────
  const activePlayers = useMemo(
    () => scenarioPlayers.filter(p => p.scenarioState !== 'removed'),
    [scenarioPlayers],
  );

  const addedIds = useMemo(
    () => new Set(scenarioPlayers.map(p => p.player_id)),
    [scenarioPlayers],
  );

  // ── Actions ────────────────────────────────────────────────────────────────

  function togglePlayer(playerId: number) {
    setScenarioPlayers(prev =>
      prev.map(p => {
        if (p.player_id !== playerId) return p;
        // Added players are removed from the list entirely via removePlayer().
        // Baseline players toggle between baseline and removed.
        if (p.scenarioState === 'added') return p;
        return {
          ...p,
          scenarioState: p.scenarioState === 'removed' ? 'baseline' : 'removed',
        };
      })
    );
    // Clear stale scenario result
    setScenarioResult(null);
    setScenarioError(null);
  }

  function removeAddedPlayer(playerId: number) {
    setScenarioPlayers(prev => prev.filter(p => p.player_id !== playerId));
    setScenarioResult(null);
    setScenarioError(null);
  }

  function addPlayer(player: OutlookPlayer) {
    if (addedIds.has(player.player_id)) return; // duplicate guard
    setScenarioPlayers(prev => [
      ...prev,
      {
        ...player,
        scenarioState: 'added',
        // Assign a reasonable default minutes share (10%) for added players
        minutes_share_p2: player.minutes_share_p2 ?? 0.10,
      },
    ]);
    setScenarioResult(null);
    setScenarioError(null);
  }

  const runScenario = useCallback(async () => {
    const active = scenarioPlayers.filter(p => p.scenarioState !== 'removed');
    if (active.length === 0) {
      setScenarioError('Scenario roster is empty. Add or restore at least one player.');
      return;
    }

    setScenarioLoading(true);
    setScenarioError(null);

    // Normalise minutes shares so they sum to 5.0 (engine expectation)
    const totalShares = active.reduce((s, p) => s + (p.minutes_share_p2 ?? 0.1), 0);
    const scale = totalShares > 0 ? 5.0 / totalShares : 1;

    const playerPayloads = active.map(p => ({
      player_id: p.player_id ?? null,
      player_name: p.player_name,
      projected_obpr: p.projected_obpr ?? 0,
      projected_dbpr: p.projected_dbpr ?? 0,
      projected_bpr: p.projected_bpr ?? 0,
      minutes_share: (p.minutesOverride ?? p.minutes_share_p2 ?? 0.1) * scale,
      recruitment_type: p.recruitment_type,
      projection_uncertainty: p.projection_uncertainty ?? 0.5,
    }));

    try {
      const result = await api.getScenarioProjection({
        from_season_year: season.year,
        team_slug: team.slug,
        players: playerPayloads,
      });
      setScenarioResult(result);
      setMode('compare');
    } catch (err: any) {
      setScenarioError(err.message || 'Scenario projection failed.');
    } finally {
      setScenarioLoading(false);
    }
  }, [scenarioPlayers, season.year, team.slug]);

  function resetScenario() {
    setScenarioPlayers(players.map(p => ({ ...p, scenarioState: 'baseline' as const })));
    setScenarioResult(null);
    setScenarioError(null);
    setMode('baseline');
  }

  // ── Derived display state ─────────────────────────────────────────────────
  const scenarioProjectionForCards = scenarioResult
    ? scenarioToProjection(scenarioResult, projection)
    : null;

  const isEditing = mode === 'edit';
  const isCompare = mode === 'compare' && scenarioResult !== null;
  const hasEdits = scenarioPlayers.some(p => p.scenarioState !== 'baseline');

  const displayedPlayers = isEditing || isCompare
    ? scenarioPlayers
    : players.map(p => ({ ...p, scenarioState: 'baseline' as const }));

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Page subtitle + mode bar */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="text-sm text-text-muted">
            Projecting <span className="font-medium text-text-primary">{season.projected_season_year}</span> season
            {' '}· Based on {season.year} roster data
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Mode tabs */}
          <div className="flex rounded-lg border border-ui-border overflow-hidden text-sm">
            <button
              className={clsx(
                'px-4 py-1.5 font-medium transition-colors',
                mode === 'baseline' && !isEditing && !isCompare
                  ? 'bg-ui-surface text-text-primary'
                  : 'text-text-muted hover:text-text-primary',
              )}
              onClick={() => setMode('baseline')}
            >
              Baseline
            </button>
            <button
              className={clsx(
                'px-4 py-1.5 font-medium transition-colors border-l border-ui-border',
                isEditing ? 'bg-brand/10 text-brand' : 'text-text-muted hover:text-text-primary',
              )}
              onClick={() => setMode('edit')}
            >
              Edit Roster
            </button>
            {(isCompare || scenarioResult) && (
              <button
                className={clsx(
                  'px-4 py-1.5 font-medium transition-colors border-l border-ui-border',
                  isCompare ? 'bg-brand/10 text-brand' : 'text-text-muted hover:text-text-primary',
                )}
                onClick={() => setMode('compare')}
              >
                Compare
              </button>
            )}
          </div>

          {/* Edit actions */}
          {isEditing && (
            <>
              <button
                onClick={() => setShowAddPlayer(true)}
                className="text-sm px-3 py-1.5 rounded-lg border border-brand text-brand hover:bg-brand/10 transition-colors"
              >
                + Add Player
              </button>
              <button
                onClick={runScenario}
                disabled={scenarioLoading || activePlayers.length === 0}
                className={clsx(
                  'text-sm px-4 py-1.5 rounded-lg font-medium transition-colors',
                  'bg-brand text-white hover:bg-brand-hover disabled:opacity-50 disabled:cursor-not-allowed',
                )}
              >
                {scenarioLoading ? 'Computing…' : 'Run Scenario'}
              </button>
              {hasEdits && (
                <button
                  onClick={resetScenario}
                  className="text-sm px-3 py-1.5 rounded-lg border border-ui-border text-text-muted hover:text-text-primary transition-colors"
                >
                  Reset
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Scenario error */}
      {scenarioError && (
        <div className="bg-rose-50 border border-rose-200 rounded-lg px-4 py-3 text-sm text-rose-700">
          {scenarioError}
        </div>
      )}

      {/* Top cards — show scenario overlay when in compare mode */}
      <OutlookTopCards
        projection={projection}
        fit={fit}
        scenarioProjection={isCompare ? scenarioProjectionForCards : undefined}
        isScenarioMode={isCompare}
      />

      {/* Compare summary card */}
      {isCompare && scenarioProjectionForCards && (
        <CompareSummaryCard baseline={projection} scenario={scenarioProjectionForCards} />
      )}

      {/* Player table */}
      <div>
        <h2 className="text-base font-semibold text-text-primary mb-3">
          Roster Projections
          {isEditing && (
            <span className="ml-2 text-sm font-normal text-brand">
              ({activePlayers.length} active · {scenarioPlayers.length - activePlayers.length} removed)
            </span>
          )}
        </h2>
        <PlayerOutlookTable
          players={displayedPlayers}
          isScenarioMode={isEditing || isCompare}
          onTogglePlayer={isEditing ? (id) => {
            const p = scenarioPlayers.find(pl => pl.player_id === id);
            if (p?.scenarioState === 'added') removeAddedPlayer(id);
            else togglePlayer(id);
          } : undefined}
          canEdit={isEditing}
        />
      </div>

      {/* Bottom diagnostic grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <ContinuityCards
            projection={projection}
            scenarioProjection={isCompare ? scenarioProjectionForCards : null}
          />
          <PortalDeltaCard
            projection={projection}
            scenarioProjection={isCompare ? scenarioProjectionForCards : null}
          />
        </div>

        <div className="space-y-4">
          <BestFiveLineup players={isEditing || isCompare ? activePlayers : players} />
          <FitDetailCard fit={fit} />
        </div>
      </div>

      {/* Player search modal */}
      <PlayerSearchModal
        isOpen={showAddPlayer}
        season={season.year}
        alreadyAddedIds={addedIds}
        onAdd={addPlayer}
        onClose={() => setShowAddPlayer(false)}
      />
    </div>
  );
}
