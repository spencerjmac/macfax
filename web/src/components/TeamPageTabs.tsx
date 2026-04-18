'use client';

import { useState, useEffect, useMemo } from 'react';
import { TeamSeason, NCAAPlayerSeasonStats } from '@/types';
import { TeamRanks, ChecklistItem, CinderellaIndexResult } from '@/lib/rankings';
import { StatCard, MetricCard, FactorCardWithRanks } from './StatCards';
import ChampionChecklistCard from './ChampionChecklistCard';
import Link from 'next/link';
import { api } from '@/lib/api';
import clsx from 'clsx';

interface TeamPageTabsProps {
  team: TeamSeason;
  ranks: TeamRanks;
  checklist: {
    passedCount: number;
    total: number;
    items: ChecklistItem[];
  };
  cinderella: CinderellaIndexResult;
}

type TabId = 'overview' | 'four-factors' | 'offense-defense' | 'resume' | 'charts' | 'game-log' | 'players';

function asPercentPoint(value: number | null | undefined): number | null {
  if (value == null || Number.isNaN(value)) return null;
  return Math.abs(value) <= 1 ? value * 100 : value;
}

function formatPercent(value: number | null | undefined, digits = 1): string {
  const pct = asPercentPoint(value);
  if (pct == null) return 'N/A';
  return `${pct.toFixed(digits)}%`;
}

export default function TeamPageTabs({ team, ranks, checklist, cinderella }: TeamPageTabsProps) {
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [players, setPlayers] = useState<NCAAPlayerSeasonStats[]>([]);
  const [playersLoading, setPlayersLoading] = useState(false);
  const [playersLoaded, setPlayersLoaded] = useState(false);

  useEffect(() => {
    if (activeTab === 'players' && !playersLoaded) {
      setPlayersLoading(true);
      // team.season is "2024-25" format — take the start year and add 1 → 2025
      // e.g. "2025-26".split('-')[0] = "2025" → 2025 + 1 = 2026
      const startYear = team.season ? parseInt(team.season.split('-')[0], 10) : NaN;
      const seasonYear = !isNaN(startYear) && startYear > 0 ? startYear + 1 : undefined;
      api.getTeamRoster(team.teamId, seasonYear)
        .then((data) => { setPlayers(data); setPlayersLoaded(true); })
        .catch(() => setPlayers([]))
        .finally(() => setPlayersLoading(false));
    }
  }, [activeTab, playersLoaded, team.teamId, team.season]);
  
  const tabs = [
    { id: 'overview' as TabId, label: 'Overview' },
    { id: 'four-factors' as TabId, label: 'Four Factors' },
    { id: 'offense-defense' as TabId, label: 'Off/Def' },
    { id: 'resume' as TabId, label: 'Resume' },
    { id: 'charts' as TabId, label: 'Charts' },
    { id: 'game-log' as TabId, label: 'Game Log' },
    { id: 'players' as TabId, label: 'Players' },
  ];
  
  return (
    <div>
      {/* Tab Navigation */}
      <div className="border-b border-ui-border mb-6">
        <div className="flex space-x-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={clsx(
                'px-6 py-3 font-medium transition-colors border-b-2',
                activeTab === tab.id
                  ? 'border-brand text-brand'
                  : 'border-transparent text-text-muted hover:text-text-primary'
              )}
            >
              {tab.label}
            </button>
          ))}
          {/* Roster Outlook — navigates to a separate page */}
          <Link
            href={`/outlook/${team.teamId}`}
            className="px-6 py-3 font-medium transition-colors border-b-2 border-transparent text-text-muted hover:text-text-primary flex items-center gap-1"
          >
            Outlook
            <span className="text-xs text-brand font-semibold ml-0.5">↗</span>
          </Link>
        </div>
      </div>
      
      {/* Tab Content */}
      <div>
        {activeTab === 'overview' && <OverviewTab team={team} ranks={ranks} checklist={checklist} cinderella={cinderella} />}
        {activeTab === 'four-factors' && <FourFactorsTab team={team} ranks={ranks} />}
        {activeTab === 'offense-defense' && <OffenseDefenseTab team={team} ranks={ranks} />}
        {activeTab === 'resume' && <ResumeTab team={team} ranks={ranks} />}
        {activeTab === 'charts' && <ChartsTab team={team} />}
        {activeTab === 'game-log' && <GameLogTab team={team} />}
        {activeTab === 'players' && <PlayersTab players={players} loading={playersLoading} />}
      </div>
    </div>
  );
}

// Overview Tab
function OverviewTab({ 
  team, 
  ranks, 
  checklist,
  cinderella,
}: { 
  team: TeamSeason; 
  ranks: TeamRanks;
  checklist: {
    passedCount: number;
    total: number;
    items: ChecklistItem[];
  };
  cinderella: CinderellaIndexResult;
}) {
  return (
    <div className="space-y-8">
      {/* Core Metrics - 4 cards in a row */}
      <div>
        <h2 className="text-2xl font-bold mb-4">Core Metrics</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard
            label="Adjusted Efficiency Margin"
            value={team.adjEM.toFixed(2)}
            rank={ranks.adjEM}
            color="text-brand"
          />
          <MetricCard
            label="Adjusted Offensive Efficiency"
            value={team.adjO.toFixed(1)}
            rank={ranks.adjO}
            color="text-success"
          />
          <MetricCard
            label="Adjusted Defensive Efficiency"
            value={team.adjD.toFixed(1)}
            rank={ranks.adjD}
            color="text-secondary"
          />
          <MetricCard
            label="Adjusted Tempo"
            value={team.adjTempo.toFixed(1)}
            rank={ranks.adjT}
            color="text-text-primary"
          />
        </div>
      </div>
      
      {/* Two-column layout: Four Factor Index + Champion Checklist */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Left: Four Factor Index & Quick Stats */}
        <div className="space-y-6">
          <div>
            <h2 className="text-2xl font-bold mb-4">Four Factor Performance</h2>
            
            {/* Four Factor Index */}
            {team.four_factor_index_100 != null && (
              <div className="p-6 bg-gradient-to-br from-brand/10 to-brand/5 border border-brand/20 rounded-lg mb-4">
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="text-text-muted text-sm">Four Factor Index (WZ100)</div>
                  {ranks.fourFactorIndex && (
                    <div className="text-xs font-mono px-2 py-0.5 rounded bg-brand/20 text-brand font-semibold">
                      #{ranks.fourFactorIndex}
                    </div>
                  )}
                </div>
                <div className="text-5xl font-bold font-mono text-brand mb-2">
                  {team.four_factor_index_100.toFixed(1)}
                </div>
                <p className="text-xs text-text-muted">
                  Overall four-factor dominance score
                </p>
              </div>
            )}
            
            {/* Four Factors Snapshot */}
            <div className="grid grid-cols-2 gap-3">
              <StatCard 
                label="eFG%" 
                value={formatPercent(team.eFG)}
                rank={ranks.eFG}
              />
              <StatCard 
                label="TOV%" 
                value={formatPercent(team.tov)}
                rank={ranks.tov}
              />
              <StatCard 
                label="ORB%" 
                value={formatPercent(team.orb)}
                rank={ranks.orb}
              />
              <StatCard 
                label="FTR" 
                value={formatPercent(team.ftr)}
                rank={ranks.ftr}
              />
            </div>
          </div>
        </div>
        
        {/* Right: Champion Checklist */}
        <ChampionChecklistCard
          passedCount={checklist.passedCount}
          total={checklist.total}
          items={checklist.items}
        />
      </div>

      {/* Cinderella Index — only shown for seeds 9+ after bracket is set */}
      {team.tournament_seed != null && team.tournament_seed >= 9 && (
        <CinderellaCard team={team} cin={cinderella} />
      )}
    </div>
  );
}

// Cinderella Index Card (team profile)
function CinderellaCard({ team, cin }: { team: TeamSeason; cin: CinderellaIndexResult }) {
  const getTierLabel = (score: number) => {
    if (score >= 65) return { label: 'Elite Cinderella Threat', color: 'text-red-700', bg: 'bg-red-50 border-red-200' };
    if (score >= 50) return { label: 'Notable Upset Risk',     color: 'text-amber-700', bg: 'bg-amber-50 border-amber-200' };
    if (score >= 35) return { label: 'Moderate Risk',          color: 'text-blue-700',  bg: 'bg-blue-50 border-blue-200' };
    return             { label: 'Low Threat',                  color: 'text-slate-500', bg: 'bg-slate-50 border-slate-200' };
  };

  const tier = getTierLabel(cin.profileScore);

  function MiniBar({ label, value, color }: { label: string; value: number; color: string }) {
    return (
      <div>
        <div className="flex justify-between text-xs mb-1">
          <span className="text-text-muted">{label}</span>
          <span className={clsx('font-mono font-semibold', color)}>{value.toFixed(0)}</span>
        </div>
        <div className="h-1.5 bg-ui-border rounded-full overflow-hidden">
          <div className={clsx('h-full rounded-full', color.replace('text-', 'bg-'))} style={{ width: `${value}%` }} />
        </div>
      </div>
    );
  }

  return (
    <div className="p-5 border border-ui-border rounded-lg bg-ui-surface">
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-lg">🥿</span>
            <h2 className="text-lg font-bold">Cinderella Index</h2>
          </div>
          <p className="text-xs text-text-muted">
            Upset-potential score based on strength, defense, possession, variance &amp; resume.
          </p>
        </div>
        <div className="text-right">
          <div className="text-4xl font-bold font-mono text-text-primary">{cin.profileScore.toFixed(0)}</div>
          <div className={clsx('text-xs font-semibold mt-0.5', tier.color)}>{tier.label}</div>
        </div>
      </div>

      {cin.seedResidual != null && (
        <div className={clsx(
          'mb-4 px-3 py-2 rounded-md border text-xs font-medium',
          cin.seedResidual > 2 ? 'bg-red-50 border-red-200 text-red-800'
            : cin.seedResidual > 0 ? 'bg-amber-50 border-amber-200 text-amber-800'
            : 'bg-slate-50 border-slate-200 text-slate-500',
        )}>
          {cin.seedResidual > 0
            ? `⚠ Seeded ${cin.seedResidual} spot${cin.seedResidual !== 1 ? 's' : ''} worse than AdjEM suggests — underseeded!`
            : cin.seedResidual < 0
            ? `AdjEM-to-seed is ${Math.abs(cin.seedResidual)} spot${Math.abs(cin.seedResidual) !== 1 ? 's' : ''} better than seed — correctly or overseeded.`
            : 'Seeded exactly where AdjEM expects.'}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <MiniBar label={`Underseeded (28%)`} value={cin.underseededStrength} color="text-brand" />
        <MiniBar label={`Defense (27%)`}     value={cin.defenseScore}        color="text-blue-600" />
        <MiniBar label={`Possession (21%)`}  value={cin.possessionScore}     color="text-green-600" />
        <MiniBar label={`Variance (14%)`}    value={cin.varianceScore}       color="text-purple-600" />
        <MiniBar label={`Resume (10%)`}      value={cin.resumeScore}         color="text-amber-600" />
      </div>

      <div className="mt-3 text-right">
        <a href="/viz/cinderella" className="text-xs text-brand hover:underline">
          View full Cinderella Index →
        </a>
      </div>
    </div>
  );
}

// Four Factors Tab
function FourFactorsTab({ team, ranks }: { team: TeamSeason; ranks: TeamRanks }) {
  return (
    <div className="space-y-8">
      {/* Four Factor Index Summary */}
      {team.four_factor_index_100 != null && (
        <div className="p-6 bg-gradient-to-br from-brand/10 to-brand/5 border border-brand/20 rounded-lg">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xl font-bold">Four Factor Index (WZ100)</h2>
            {ranks.fourFactorIndex && (
              <div className="text-sm font-mono px-3 py-1 rounded bg-brand/20 text-brand font-semibold">
                #{ranks.fourFactorIndex}
              </div>
            )}
          </div>
          <div className="text-4xl font-bold font-mono text-brand mb-2">
            {team.four_factor_index_100.toFixed(1)}
          </div>
          <p className="text-sm text-text-muted">
            A composite rating that measures how strong a team is across the four key areas most tied to winning.
          </p>
        </div>
      )}
      
      <div>
        <h2 className="text-2xl font-bold mb-4">Four Factors Breakdown</h2>
        <p className="text-text-muted mb-6">
          The Four Factors of Basketball Success, showing both offensive and defensive performance 
          plus the margin/edge for each factor. Ranks shown for offense, defense, and margin.
        </p>
        
        <div className="space-y-6">
          {/* eFG% */}
          <FactorCardWithRanks
            name="Effective Field Goal %"
            offense={formatPercent(team.eFG)}
            offenseRank={ranks.eFG}
            defense={formatPercent(team.eFG_d)}
            defenseRank={ranks.eFG_d}
            margin={formatPercent(team.eFG_margin)}
            marginRank={ranks.eFG_margin}
            marginPositive={team.eFG_margin > 0}
            description="Field goal percentage adjusted for 3-pointers being worth more"
          />
          
          {/* TOV% */}
          <FactorCardWithRanks
            name="Turnover Rate"
            offense={formatPercent(team.tov)}
            offenseRank={ranks.tov}
            defense={formatPercent(team.tov_d)}
            defenseRank={ranks.tov_d}
            margin={formatPercent(team.tov_edge)}
            marginRank={ranks.tov_edge}
            marginPositive={team.tov_edge > 0}
            description="Turnovers per 100 plays (forcing > committing is good)"
          />
          
          {/* ORB% */}
          <FactorCardWithRanks
            name="Rebounding Rate"
            offense={formatPercent(team.orb)}
            offenseRank={ranks.orb}
            defense={formatPercent(team.drb)}
            defenseRank={ranks.drb}
            margin={formatPercent(team.reb_edge)}
            marginRank={ranks.reb_edge}
            marginPositive={team.reb_edge > 0}
            description="Offensive rebound % vs Defensive rebound %"
          />
          
          {/* FTR */}
          <FactorCardWithRanks
            name="Free Throw Rate"
            offense={formatPercent(team.ftr)}
            offenseRank={ranks.ftr}
            defense={formatPercent(team.ftr_d)}
            defenseRank={ranks.ftr_d}
            margin={formatPercent(team.ftr_margin)}
            marginRank={ranks.ftr_margin}
            marginPositive={team.ftr_margin > 0}
            description="Free throw attempts per field goal attempt"
          />
        </div>
      </div>
    </div>
  );
}

// Offense/Defense Tab
function OffenseDefenseTab({ team, ranks }: { team: TeamSeason; ranks: TeamRanks }) {
  return (
    <div className="space-y-8">
      <div className="grid md:grid-cols-2 gap-6">
        {/* Offense */}
        <div>
          <h2 className="text-2xl font-bold mb-4 text-success">Offensive Profile</h2>
          <div className="space-y-4">
            <StatCard 
              label="Adj Offensive Efficiency" 
              value={team.adjO.toFixed(1)}
              rank={ranks.adjO}
            />
            {team.fg2_pct !== null && (
              <StatCard 
                label="2P%" 
                value={formatPercent(team.fg2_pct)}
                rank={ranks.fg2_pct}
              />
            )}
            {team.fg3_pct !== null && (
              <StatCard 
                label="3P%" 
                value={formatPercent(team.fg3_pct)}
                rank={ranks.fg3_pct}
              />
            )}
            {team.fg3_rate !== null && (
              <StatCard 
                label="3P Rate" 
                value={formatPercent(team.fg3_rate)}
                rank={ranks.fg3_rate}
              />
            )}
            <StatCard 
              label="eFG%" 
              value={formatPercent(team.eFG)}
              rank={ranks.eFG}
            />
            <StatCard 
              label="TOV%" 
              value={formatPercent(team.tov)}
              rank={ranks.tov}
              description="Lower is better"
            />
            <StatCard 
              label="ORB%" 
              value={formatPercent(team.orb)}
              rank={ranks.orb}
            />
            <StatCard 
              label="FTR" 
              value={formatPercent(team.ftr)}
              rank={ranks.ftr}
            />
          </div>
        </div>
        
        {/* Defense */}
        <div>
          <h2 className="text-2xl font-bold mb-4 text-secondary">Defensive Profile</h2>
          <div className="space-y-4">
            <StatCard 
              label="Adj Defensive Efficiency" 
              value={team.adjD.toFixed(1)}
              rank={ranks.adjD}
              description="Lower is better"
            />
            {team.fg2_pct_d !== null && (
              <StatCard 
                label="Opp 2P%" 
                value={formatPercent(team.fg2_pct_d)}
                rank={ranks.fg2_pct_d}
                description="Lower is better"
              />
            )}
            {team.fg3_pct_d !== null && (
              <StatCard 
                label="Opp 3P%" 
                value={formatPercent(team.fg3_pct_d)}
                rank={ranks.fg3_pct_d}
                description="Lower is better"
              />
            )}
            {team.fg3_rate_d !== null && (
              <StatCard 
                label="Opp 3P Rate" 
                value={formatPercent(team.fg3_rate_d)}
                rank={ranks.fg3_rate_d}
                description="Lower is better"
              />
            )}
            <StatCard 
              label="Opp eFG%" 
              value={formatPercent(team.eFG_d)}
              rank={ranks.eFG_d}
              description="Lower is better"
            />
            <StatCard 
              label="Forced TOV%" 
              value={formatPercent(team.tov_d)}
              rank={ranks.tov_d}
            />
            <StatCard 
              label="DRB%" 
              value={formatPercent(team.drb)}
              rank={ranks.drb}
            />
            <StatCard 
              label="Opp FTR" 
              value={formatPercent(team.ftr_d)}
              rank={ranks.ftr_d}
              description="Lower is better"
            />
          </div>
        </div>
      </div>
    </div>
  );
}

// Resume Tab
function ResumeTab({ team, ranks }: { team: TeamSeason; ranks: TeamRanks }) {
  const [gameLog, setGameLog] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchGameLog() {
      try {
        const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
        // Parse season year: "2025-26" -> 2026 (use ending year)
        const seasonYear = parseInt(team.season.split('-')[0]) + 1;
        const url = `${apiBase}/api/teams/${team.teamId}/gamelog/?season=${seasonYear}`;
        const response = await fetch(url);
        if (response.ok) {
          const data = await response.json();
          setGameLog(data.game_log || []);
        }
      } catch (error) {
        console.error('Failed to fetch game log:', error);
      } finally {
        setLoading(false);
      }
    }
    fetchGameLog();
  }, [team.teamId, team.season]);

  // Compute quadrant records
  const quadrantRecords = useMemo(() => {
    const records: Record<string, { w: number; l: number }> = {
      Q1: { w: 0, l: 0 },
      Q2: { w: 0, l: 0 },
      Q3: { w: 0, l: 0 },
      Q4: { w: 0, l: 0 },
    };
    
    gameLog.forEach(game => {
      if (game.quadrant && game.result) {
        const quad = game.quadrant;
        if (game.result === 'W') {
          records[quad].w++;
        } else {
          records[quad].l++;
        }
      }
    });
    
    return records;
  }, [gameLog]);

  // Best wins: Wins sorted by opponent rank (lower = better), then by game_value
  const bestWins = useMemo(() => {
    return gameLog
      .filter(g => g.result === 'W' && g.opponent_net_rank !== null)
      .sort((a, b) => {
        // Primary: opponent rank (lower is better)
        if (a.opponent_net_rank !== b.opponent_net_rank) {
          return a.opponent_net_rank - b.opponent_net_rank;
        }
        // Secondary: location priority (A > N > H)
        const locOrder: Record<string, number> = { A: 0, N: 1, H: 2 };
        if (locOrder[a.home_away] !== locOrder[b.home_away]) {
          return locOrder[a.home_away] - locOrder[b.home_away];
        }
        // Tertiary: game value (higher is better)
        return (b.game_value || 0) - (a.game_value || 0);
      })
      .slice(0, 5);
  }, [gameLog]);

  // Worst losses: Losses sorted by opponent rank (higher = worse), then by game_value
  const worstLosses = useMemo(() => {
    return gameLog
      .filter(g => g.result === 'L' && g.opponent_net_rank !== null)
      .sort((a, b) => {
        // Primary: opponent rank (higher is worse for losses)
        if (a.opponent_net_rank !== b.opponent_net_rank) {
          return b.opponent_net_rank - a.opponent_net_rank;
        }
        // Secondary: location priority (H > N > A for losses)
        const locOrder: Record<string, number> = { H: 0, N: 1, A: 2 };
        if (locOrder[a.home_away] !== locOrder[b.home_away]) {
          return locOrder[a.home_away] - locOrder[b.home_away];
        }
        // Tertiary: game value (lower/more negative is worse)
        return (a.game_value || 0) - (b.game_value || 0);
      })
      .slice(0, 5);
  }, [gameLog]);

  return (
    <div className="space-y-8">
      <h2 className="text-2xl font-bold mb-4">Team Resume</h2>
      
      <div className="grid md:grid-cols-2 gap-6">
        {/* WAB */}
        <div className="p-6 bg-ui-surface border border-ui-border rounded-lg">
          <div className="flex items-start justify-between gap-2 mb-2">
            <div className="text-text-muted text-sm">Wins Above Bubble</div>
            {team.wab !== null && ranks.wab && (
              <div className="text-xs font-mono px-2 py-0.5 rounded bg-brand/20 text-brand font-semibold">
                #{ranks.wab}
              </div>
            )}
          </div>
          <div className="text-4xl font-bold font-mono text-brand">
            {team.wab !== null ? (
              <>{team.wab > 0 ? '+' : ''}{team.wab.toFixed(2)}</>
            ) : (
              <span className="text-text-muted">N/A</span>
            )}
          </div>
          <p className="text-text-muted text-sm mt-2">
            Expected wins above a bubble team with the same schedule
          </p>
        </div>
        
        {/* NET Ranking */}
        <div className="p-6 bg-ui-surface border border-ui-border rounded-lg">
          <div className="flex items-start justify-between gap-2 mb-2">
            <div className="text-text-muted text-sm">NET Ranking</div>
            {team.net_rank && (
              <div className="text-xs font-mono px-2 py-0.5 rounded bg-brand/20 text-brand font-semibold">
                #{team.net_rank}
              </div>
            )}
          </div>
          <div className="text-4xl font-bold font-mono text-brand">
            {team.net_rank ? (
              `#${team.net_rank}`
            ) : (
              <span className="text-text-muted">N/A</span>
            )}
          </div>
          <p className="text-text-muted text-sm mt-2">
            NCAA Evaluation Tool ranking
          </p>
        </div>
        
        {/* SOR */}
        <div className="p-6 bg-ui-surface border border-ui-border rounded-lg">
          <div className="flex items-start justify-between gap-2 mb-2">
            <div className="text-text-muted text-sm">Strength of Record</div>
            {team.sor_rank && (
              <div className="text-xs font-mono px-2 py-0.5 rounded bg-brand/20 text-brand font-semibold">
                #{team.sor_rank}
              </div>
            )}
          </div>
          <div className="text-4xl font-bold font-mono text-brand">
            {team.sor_rank ? (
              `#${team.sor_rank}`
            ) : (
              <span className="text-text-muted">N/A</span>
            )}
          </div>
          <p className="text-text-muted text-sm mt-2">
            Resume quality: probability baseline team achieves this record
          </p>
        </div>
        
        {/* SOS - Strength of Schedule */}
        <div className="p-6 bg-ui-surface border border-ui-border rounded-lg">
          <div className="flex items-start justify-between gap-2 mb-2">
            <div className="text-text-muted text-sm">Strength of Schedule</div>
            {team.sos_rank && (
              <div className="text-xs font-mono px-2 py-0.5 rounded bg-brand/20 text-brand font-semibold">
                #{team.sos_rank}
              </div>
            )}
          </div>
          <div className="text-4xl font-bold font-mono text-brand">
            {team.sos_win_pct !== null ? (
              `${(team.sos_win_pct * 100).toFixed(1)}%`
            ) : (
              <span className="text-text-muted">N/A</span>
            )}
          </div>
          <p className="text-text-muted text-sm mt-2">
            Expected win% for an average D1 team vs this schedule
          </p>
        </div>
      </div>

      {/* Quadrant Records */}
      <div>
        <h3 className="text-xl font-bold mb-4">Quadrant Records</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {(['Q1', 'Q2', 'Q3', 'Q4'] as const).map(quad => {
            const record = quadrantRecords[quad];
            const total = record.w + record.l;
            const hasGames = total > 0;
            
            return (
              <div key={quad} className="p-4 bg-ui-surface border border-ui-border rounded-lg text-center">
                <div className="text-text-muted text-sm mb-1">{quad}</div>
                <div className={`text-2xl font-bold font-mono ${hasGames ? 'text-brand' : 'text-text-muted'}`}>
                  {hasGames ? `${record.w}-${record.l}` : '-'}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Best Wins */}
      <div>
        <h3 className="text-xl font-bold mb-4">Best Wins</h3>
        {bestWins.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-ui-border">
                  <th className="text-left py-2 px-3 text-sm font-semibold text-text-muted">Date</th>
                  <th className="text-left py-2 px-3 text-sm font-semibold text-text-muted">Opponent</th>
                  <th className="text-center py-2 px-3 text-sm font-semibold text-text-muted">Rank</th>
                  <th className="text-center py-2 px-3 text-sm font-semibold text-text-muted">Loc</th>
                  <th className="text-center py-2 px-3 text-sm font-semibold text-text-muted">Quad</th>
                  <th className="text-center py-2 px-3 text-sm font-semibold text-text-muted">Game Value</th>
                </tr>
              </thead>
              <tbody>
                {bestWins.map((game, idx) => {
                  const isQ1orQ2 = game.quadrant === 'Q1' || game.quadrant === 'Q2';
                  return (
                    <tr key={idx} className="border-b border-ui-border hover:bg-ui-surface/50">
                      <td className="py-2 px-3 text-sm">{new Date(game.game_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</td>
                      <td className="py-2 px-3 text-sm font-semibold">{game.opponent_name}</td>
                      <td className="py-2 px-3 text-sm text-center font-mono">#{game.opponent_net_rank}</td>
                      <td className="py-2 px-3 text-sm text-center font-mono">{game.home_away}</td>
                      <td className="py-2 px-3 text-center">
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${
                          isQ1orQ2 ? 'bg-green-500/20 text-green-400' : 'bg-ui-border text-text-muted'
                        }`}>
                          {game.quadrant}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-sm text-center font-mono">
                        {game.game_value !== null && game.game_value !== undefined ? 
                          (game.game_value > 0 ? '+' : '') + game.game_value.toFixed(3) : 
                          'N/A'
                        }
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-6 bg-ui-surface border border-ui-border rounded-lg text-center text-text-muted">
            {loading ? 'Loading...' : 'No wins recorded'}
          </div>
        )}
      </div>

      {/* Worst Losses */}
      <div>
        <h3 className="text-xl font-bold mb-4">Worst Losses</h3>
        {worstLosses.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-ui-border">
                  <th className="text-left py-2 px-3 text-sm font-semibold text-text-muted">Date</th>
                  <th className="text-left py-2 px-3 text-sm font-semibold text-text-muted">Opponent</th>
                  <th className="text-center py-2 px-3 text-sm font-semibold text-text-muted">Rank</th>
                  <th className="text-center py-2 px-3 text-sm font-semibold text-text-muted">Loc</th>
                  <th className="text-center py-2 px-3 text-sm font-semibold text-text-muted">Quad</th>
                  <th className="text-center py-2 px-3 text-sm font-semibold text-text-muted">Game Value</th>
                </tr>
              </thead>
              <tbody>
                {worstLosses.map((game, idx) => {
                  const isQ3orQ4 = game.quadrant === 'Q3' || game.quadrant === 'Q4';
                  return (
                    <tr key={idx} className="border-b border-ui-border hover:bg-ui-surface/50">
                      <td className="py-2 px-3 text-sm">{new Date(game.game_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</td>
                      <td className="py-2 px-3 text-sm font-semibold">{game.opponent_name}</td>
                      <td className="py-2 px-3 text-sm text-center font-mono">#{game.opponent_net_rank}</td>
                      <td className="py-2 px-3 text-sm text-center font-mono">{game.home_away}</td>
                      <td className="py-2 px-3 text-center">
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${
                          isQ3orQ4 ? 'bg-red-500/20 text-red-400' : 'bg-ui-border text-text-muted'
                        }`}>
                          {game.quadrant}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-sm text-center font-mono">
                        {game.game_value !== null && game.game_value !== undefined ? 
                          (game.game_value > 0 ? '+' : '') + game.game_value.toFixed(3) : 
                          'N/A'
                        }
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-6 bg-ui-surface border border-ui-border rounded-lg text-center text-text-muted">
            {loading ? 'Loading...' : 'No losses recorded'}
          </div>
        )}
      </div>

      {!team.wab && !team.sos_adjEM && !team.sor_rank && !team.net_rank && (
        <div className="p-6 bg-ui-surface border border-ui-border rounded-lg text-center text-text-muted">
          Resume metrics not available for this team.
        </div>
      )}
    </div>
  );
}

// Charts Tab (placeholder)
function ChartsTab({ team }: { team: TeamSeason }) {
  return (
    <div className="space-y-8">
      <h2 className="text-2xl font-bold mb-4">Visualizations</h2>
      <div className="grid md:grid-cols-2 gap-6">
        <div className="p-12 bg-ui-surface border border-ui-border rounded-lg text-center">
          <div className="text-6xl mb-4">📊</div>
          <h3 className="font-bold text-lg mb-2">Trapezoid of Excellence</h3>
          <p className="text-text-muted text-sm">Coming soon</p>
        </div>
        <div className="p-12 bg-ui-surface border border-ui-border rounded-lg text-center">
          <div className="text-6xl mb-4">📈</div>
          <h3 className="font-bold text-lg mb-2">Season Trends</h3>
          <p className="text-text-muted text-sm">Coming soon</p>
        </div>
        <div className="p-12 bg-ui-surface border border-ui-border rounded-lg text-center">
          <div className="text-6xl mb-4">🎯</div>
          <h3 className="font-bold text-lg mb-2">Shot Chart</h3>
          <p className="text-text-muted text-sm">Coming soon</p>
        </div>
        <div className="p-12 bg-ui-surface border border-ui-border rounded-lg text-center">
          <div className="text-6xl mb-4">🏆</div>
          <h3 className="font-bold text-lg mb-2">Championship Probability</h3>
          <p className="text-text-muted text-sm">Coming soon</p>
        </div>
      </div>
    </div>
  );
}

// Game Log Tab
function GameLogTab({ team }: { team: TeamSeason }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [gameLog, setGameLog] = useState<any[]>([]);

  useEffect(() => {
    const fetchGameLog = async () => {
      try {
        setLoading(true);
        setError(null);

        const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
        // Parse season year: "2025-26" -> 2026 (use ending year)
        const seasonYear = parseInt(team.season.split('-')[0]) + 1;
        const response = await fetch(
          `${apiBase}/api/teams/${team.teamId}/gamelog/?season=${seasonYear}`
        );
        
        if (!response.ok) {
          throw new Error(`Failed to fetch game log: ${response.statusText}`);
        }
        
        const data = await response.json();
        setGameLog(data.game_log || []);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load game log');
        console.error('Error fetching game log:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchGameLog();
  }, [team.teamId, team.season]);

  if (loading) {
    return (
      <div className="p-12 text-center text-text-muted">
        Loading game log...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 bg-ui-surface border border-ui-border rounded-lg text-center">
        <p className="text-red-500 mb-2">Error loading game log</p>
        <p className="text-text-muted text-sm">{error}</p>
      </div>
    );
  }

  if (gameLog.length === 0) {
    return (
      <div className="p-6 bg-ui-surface border border-ui-border rounded-lg text-center text-text-muted">
        No games found for this team.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold mb-4">{team.season} Game Log</h2>
      
      <div className="overflow-x-auto">
        <table className="w-full border border-ui-border rounded-lg">
          <thead className="bg-ui-surface-dark">
            <tr>
              <th className="px-4 py-3 text-left text-sm font-semibold">Date</th>
              <th className="px-4 py-3 text-left text-sm font-semibold">Opponent</th>
              <th className="px-4 py-3 text-center text-sm font-semibold">Location</th>
              <th className="px-4 py-3 text-center text-sm font-semibold">Result</th>
              <th className="px-4 py-3 text-right text-sm font-semibold">Score</th>
              <th className="px-4 py-3 text-right text-sm font-semibold">ORtg</th>
              <th className="px-4 py-3 text-right text-sm font-semibold">DRtg</th>
              <th className="px-4 py-3 text-right text-sm font-semibold">eFG%</th>
              <th className="px-4 py-3 text-right text-sm font-semibold">TOV%</th>
              <th className="px-4 py-3 text-right text-sm font-semibold">ORB%</th>
              <th className="px-4 py-3 text-right text-sm font-semibold">FTR</th>
            </tr>
          </thead>
          <tbody>
            {gameLog.map((game, index) => {
              const isNonD1 = game.opponent_is_d1 === false;
              const oppPts = game.margin != null ? game.pts - game.margin : null;
              const scoreStr = oppPts != null ? `${game.pts}-${oppPts}` : `${game.pts}`;
              return (
              <tr
                key={game.id || index}
                className={clsx(
                  'border-t border-ui-border transition-colors',
                  isNonD1 ? 'bg-ui-surface/50' : 'hover:bg-ui-surface-dark/50'
                )}
              >
                <td className="px-4 py-3 text-sm">
                  {new Date(game.game_date).toLocaleDateString('en-US', {
                    month: 'short',
                    day: 'numeric',
                  })}
                </td>
                <td className="px-4 py-3 text-sm font-medium">
                  {game.opponent_name}
                  {isNonD1 && (
                    <span className="ml-2 text-xs text-amber-500/90 font-normal">
                      (Non-D1)
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-center text-sm">
                  <span
                    className={clsx(
                      'px-2 py-1 rounded text-xs font-medium',
                      game.home_away === 'H' && 'bg-green-500/20 text-green-400',
                      game.home_away === 'A' && 'bg-red-500/20 text-red-400',
                      game.home_away === 'N' && 'bg-blue-500/20 text-blue-400'
                    )}
                  >
                    {game.home_away === 'H' ? 'Home' : game.home_away === 'A' ? 'Away' : 'Neutral'}
                  </span>
                </td>
                <td className="px-4 py-3 text-center text-sm">
                  <span
                    className={clsx(
                      'font-bold',
                      game.result === 'W' ? 'text-green-400' : 'text-red-400'
                    )}
                  >
                    {game.result}
                  </span>
                </td>
                <td className="px-4 py-3 text-right text-sm font-mono">
                  {scoreStr}
                </td>
                {isNonD1 ? (
                  <td colSpan={6} className="px-4 py-3 text-sm text-text-muted italic">
                    Non-D1 opponent — advanced stats not computed
                  </td>
                ) : (
                  <>
                    <td className="px-4 py-3 text-right text-sm font-mono">
                      {game.ortg?.toFixed(1) ?? '—'}
                    </td>
                    <td className="px-4 py-3 text-right text-sm font-mono">
                      {game.drtg?.toFixed(1) ?? '—'}
                    </td>
                    <td className="px-4 py-3 text-right text-sm font-mono">
                      {game.efg_pct != null ? formatPercent(game.efg_pct) : '—'}
                    </td>
                    <td className="px-4 py-3 text-right text-sm font-mono">
                      {game.tov_pct != null ? formatPercent(game.tov_pct) : '—'}
                    </td>
                    <td className="px-4 py-3 text-right text-sm font-mono">
                      {game.orb_pct != null ? formatPercent(game.orb_pct) : '—'}
                    </td>
                    <td className="px-4 py-3 text-right text-sm font-mono">
                      {game.ftr != null ? formatPercent(game.ftr) : '—'}
                    </td>
                  </>
                )}
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      
      <div className="text-sm text-text-muted mt-4">
        Total Games: {gameLog.length}
      </div>
    </div>
  );
}

// Players Tab
function PlayersTab({
  players,
  loading,
}: {
  players: NCAAPlayerSeasonStats[];
  loading: boolean;
}) {
  if (loading) {
    return <div className="text-text-muted py-8 text-center">Loading roster...</div>;
  }

  if (players.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-text-muted mb-2">No player data available for this team.</p>
        <p className="text-xs text-text-muted font-mono">
          Run: <code>python manage.py sync_ncaa_player_gamelogs --season 2025</code>
          <br />then: <code>python manage.py compute_ncaa_player_season_stats --season 2025</code>
        </p>
      </div>
    );
  }

  function fmtPct(v: number | null | undefined): string {
    if (v == null) return '—';
    return `${(v * 100).toFixed(1)}%`;
  }

  function fmtStat(v: number | null | undefined, digits = 1): string {
    if (v == null) return '—';
    return v.toFixed(digits);
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-text-muted border-b border-ui-border">
            <th className="text-left px-3 py-2 font-medium">Player</th>
            <th className="text-center px-3 py-2 font-medium w-8">Pos</th>
            <th className="text-right px-3 py-2 font-medium">GP</th>
            <th className="text-right px-3 py-2 font-medium">MPG</th>
            <th className="text-right px-3 py-2 font-medium text-brand">PTS</th>
            <th className="text-right px-3 py-2 font-medium">REB</th>
            <th className="text-right px-3 py-2 font-medium">AST</th>
            <th className="text-right px-3 py-2 font-medium">STL</th>
            <th className="text-right px-3 py-2 font-medium">BLK</th>
            <th className="text-right px-3 py-2 font-medium">TOV</th>
            <th className="text-right px-3 py-2 font-medium">FG%</th>
            <th className="text-right px-3 py-2 font-medium">3P%</th>
            <th className="text-right px-3 py-2 font-medium">FT%</th>
          </tr>
        </thead>
        <tbody>
          {players.map((p) => (
            <tr
              key={p.player_id}
              className="border-b border-ui-border/50 hover:bg-ui-surface/50 transition-colors"
            >
              <td className="px-3 py-2">
                <div className="flex items-center gap-2">
                  {p.jersey && (
                    <span className="text-xs text-text-muted w-5 text-right shrink-0">
                      #{p.jersey}
                    </span>
                  )}
                  <span className="font-medium text-text-primary">{p.player_name}</span>
                </div>
              </td>
              <td className="px-3 py-2 text-center text-text-muted">{p.position || '—'}</td>
              <td className="px-3 py-2 text-right font-mono">{p.gp}</td>
              <td className="px-3 py-2 text-right font-mono">{fmtStat(p.mpg)}</td>
              <td className="px-3 py-2 text-right font-mono font-semibold text-brand">{fmtStat(p.pts)}</td>
              <td className="px-3 py-2 text-right font-mono">{fmtStat(p.reb)}</td>
              <td className="px-3 py-2 text-right font-mono">{fmtStat(p.ast)}</td>
              <td className="px-3 py-2 text-right font-mono">{fmtStat(p.stl)}</td>
              <td className="px-3 py-2 text-right font-mono">{fmtStat(p.blk)}</td>
              <td className="px-3 py-2 text-right font-mono">{fmtStat(p.tov)}</td>
              <td className="px-3 py-2 text-right font-mono">{fmtPct(p.fg_pct)}</td>
              <td className="px-3 py-2 text-right font-mono">{fmtPct(p.fg3_pct)}</td>
              <td className="px-3 py-2 text-right font-mono">{fmtPct(p.ft_pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
