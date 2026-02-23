'use client';

import { useState, useEffect } from 'react';
import { TeamSeason } from '@/types';
import { TeamRanks, ChecklistItem } from '@/lib/rankings';
import { StatCard, MetricCard, FactorCardWithRanks } from './StatCards';
import ChampionChecklistCard from './ChampionChecklistCard';
import clsx from 'clsx';

interface TeamPageTabsProps {
  team: TeamSeason;
  ranks: TeamRanks;
  checklist: {
    passedCount: number;
    total: number;
    items: ChecklistItem[];
  };
}

type TabId = 'overview' | 'four-factors' | 'offense-defense' | 'resume' | 'charts' | 'game-log';

export default function TeamPageTabs({ team, ranks, checklist }: TeamPageTabsProps) {
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  
  const tabs = [
    { id: 'overview' as TabId, label: 'Overview' },
    { id: 'four-factors' as TabId, label: 'Four Factors' },
    { id: 'offense-defense' as TabId, label: 'Off/Def' },
    { id: 'resume' as TabId, label: 'Resume' },
    { id: 'charts' as TabId, label: 'Charts' },
    { id: 'game-log' as TabId, label: 'Game Log' },
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
                  ? 'border-brand-orange text-brand-orange'
                  : 'border-transparent text-text-muted hover:text-text-primary'
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>
      
      {/* Tab Content */}
      <div>
        {activeTab === 'overview' && <OverviewTab team={team} ranks={ranks} checklist={checklist} />}
        {activeTab === 'four-factors' && <FourFactorsTab team={team} ranks={ranks} />}
        {activeTab === 'offense-defense' && <OffenseDefenseTab team={team} ranks={ranks} />}
        {activeTab === 'resume' && <ResumeTab team={team} ranks={ranks} />}
        {activeTab === 'charts' && <ChartsTab team={team} />}
        {activeTab === 'game-log' && <GameLogTab team={team} />}
      </div>
    </div>
  );
}

// Overview Tab
function OverviewTab({ 
  team, 
  ranks, 
  checklist 
}: { 
  team: TeamSeason; 
  ranks: TeamRanks;
  checklist: {
    passedCount: number;
    total: number;
    items: ChecklistItem[];
  };
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
            color="text-brand-orange"
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
              <div className="p-6 bg-gradient-to-br from-brand-orange/10 to-brand-orange/5 border border-brand-orange/20 rounded-lg mb-4">
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="text-text-muted text-sm">Four Factor Index (WZ100)</div>
                  {ranks.fourFactorIndex && (
                    <div className="text-xs font-mono px-2 py-0.5 rounded bg-brand-orange/20 text-brand-orange font-semibold">
                      #{ranks.fourFactorIndex}
                    </div>
                  )}
                </div>
                <div className="text-5xl font-bold font-mono text-brand-orange mb-2">
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
                value={(team.eFG * 100).toFixed(1) + '%'}
                rank={ranks.eFG}
              />
              <StatCard 
                label="TOV%" 
                value={(team.tov * 100).toFixed(1) + '%'}
                rank={ranks.tov}
              />
              <StatCard 
                label="ORB%" 
                value={(team.orb * 100).toFixed(1) + '%'}
                rank={ranks.orb}
              />
              <StatCard 
                label="FTR" 
                value={(team.ftr * 100).toFixed(1) + '%'}
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
    </div>
  );
}

// Four Factors Tab
function FourFactorsTab({ team, ranks }: { team: TeamSeason; ranks: TeamRanks }) {
  return (
    <div className="space-y-8">
      {/* Four Factor Index Summary */}
      {team.four_factor_index_100 != null && (
        <div className="p-6 bg-gradient-to-br from-brand-orange/10 to-brand-orange/5 border border-brand-orange/20 rounded-lg">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xl font-bold">Four Factor Index (WZ100)</h2>
            {ranks.fourFactorIndex && (
              <div className="text-sm font-mono px-3 py-1 rounded bg-brand-orange/20 text-brand-orange font-semibold">
                #{ranks.fourFactorIndex}
              </div>
            )}
          </div>
          <div className="text-4xl font-bold font-mono text-brand-orange mb-2">
            {team.four_factor_index_100.toFixed(1)}
          </div>
          <p className="text-sm text-text-muted">
            Weighted composite score: eFG% (40%), TOV% (20%), REB% (20%), FTR (20%)
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
            offense={(team.eFG * 100).toFixed(1) + '%'}
            offenseRank={ranks.eFG}
            defense={(team.eFG_d * 100).toFixed(1) + '%'}
            defenseRank={ranks.eFG_d}
            margin={(team.eFG_margin * 100).toFixed(1) + '%'}
            marginRank={ranks.eFG_margin}
            marginPositive={team.eFG_margin > 0}
            description="Field goal percentage adjusted for 3-pointers being worth more"
          />
          
          {/* TOV% */}
          <FactorCardWithRanks
            name="Turnover Rate"
            offense={(team.tov * 100).toFixed(1) + '%'}
            offenseRank={ranks.tov}
            defense={(team.tov_d * 100).toFixed(1) + '%'}
            defenseRank={ranks.tov_d}
            margin={(team.tov_edge * 100).toFixed(1) + '%'}
            marginRank={ranks.tov_edge}
            marginPositive={team.tov_edge > 0}
            description="Turnovers per 100 plays (forcing > committing is good)"
          />
          
          {/* ORB% */}
          <FactorCardWithRanks
            name="Rebounding Rate"
            offense={(team.orb * 100).toFixed(1) + '%'}
            offenseRank={ranks.orb}
            defense={(team.drb * 100).toFixed(1) + '%'}
            defenseRank={ranks.drb}
            margin={(team.reb_edge * 100).toFixed(1) + '%'}
            marginRank={ranks.reb_edge}
            marginPositive={team.reb_edge > 0}
            description="Offensive rebound % vs Defensive rebound %"
          />
          
          {/* FTR */}
          <FactorCardWithRanks
            name="Free Throw Rate"
            offense={(team.ftr * 100).toFixed(1) + '%'}
            offenseRank={ranks.ftr}
            defense={(team.ftr_d * 100).toFixed(1) + '%'}
            defenseRank={ranks.ftr_d}
            margin={(team.ftr_margin * 100).toFixed(1) + '%'}
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
                value={team.fg2_pct.toFixed(1) + '%'}
                rank={ranks.fg2_pct}
              />
            )}
            {team.fg3_pct !== null && (
              <StatCard 
                label="3P%" 
                value={team.fg3_pct.toFixed(1) + '%'}
                rank={ranks.fg3_pct}
              />
            )}
            {team.fg3_rate !== null && (
              <StatCard 
                label="3P Rate" 
                value={team.fg3_rate.toFixed(1) + '%'}
                rank={ranks.fg3_rate}
              />
            )}
            <StatCard 
              label="eFG%" 
              value={team.eFG.toFixed(1) + '%'}
              rank={ranks.eFG}
            />
            <StatCard 
              label="TOV%" 
              value={team.tov.toFixed(1) + '%'}
              rank={ranks.tov}
              description="Lower is better"
            />
            <StatCard 
              label="ORB%" 
              value={team.orb.toFixed(1) + '%'}
              rank={ranks.orb}
            />
            <StatCard 
              label="FTR" 
              value={team.ftr.toFixed(1) + '%'}
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
                value={team.fg2_pct_d.toFixed(1) + '%'}
                rank={ranks.fg2_pct_d}
                description="Lower is better"
              />
            )}
            {team.fg3_pct_d !== null && (
              <StatCard 
                label="Opp 3P%" 
                value={team.fg3_pct_d.toFixed(1) + '%'}
                rank={ranks.fg3_pct_d}
                description="Lower is better"
              />
            )}
            {team.fg3_rate_d !== null && (
              <StatCard 
                label="Opp 3P Rate" 
                value={team.fg3_rate_d.toFixed(1) + '%'}
                rank={ranks.fg3_rate_d}
                description="Lower is better"
              />
            )}
            <StatCard 
              label="Opp eFG%" 
              value={team.eFG_d.toFixed(1) + '%'}
              rank={ranks.eFG_d}
              description="Lower is better"
            />
            <StatCard 
              label="Forced TOV%" 
              value={team.tov_d.toFixed(1) + '%'}
              rank={ranks.tov_d}
            />
            <StatCard 
              label="DRB%" 
              value={team.drb.toFixed(1) + '%'}
              rank={ranks.drb}
            />
            <StatCard 
              label="Opp FTR" 
              value={team.ftr_d.toFixed(1) + '%'}
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
  return (
    <div className="space-y-8">
      <h2 className="text-2xl font-bold mb-4">Team Resume</h2>
      
      <div className="grid md:grid-cols-2 gap-6">
        {/* WAB */}
        <div className="p-6 bg-ui-surface border border-ui-border rounded-lg">
          <div className="flex items-start justify-between gap-2 mb-2">
            <div className="text-text-muted text-sm">Wins Above Bubble</div>
            {team.wab !== null && ranks.wab && (
              <div className="text-xs font-mono px-2 py-0.5 rounded bg-brand-orange/20 text-brand-orange font-semibold">
                #{ranks.wab}
              </div>
            )}
          </div>
          <div className="text-4xl font-bold font-mono text-brand-orange">
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
        
        {/* Barthag */}
        <div className="p-6 bg-ui-surface border border-ui-border rounded-lg">
          <div className="text-text-muted text-sm mb-2">Barthag Rating</div>
          <div className="text-4xl font-bold font-mono text-brand-orange">
            {team.barthag !== null ? (
              team.barthag.toFixed(4)
            ) : (
              <span className="text-text-muted">N/A</span>
            )}
          </div>
          <p className="text-text-muted text-sm mt-2">
            Power rating (win probability vs average team on neutral court)
          </p>
        </div>
        
        {/* SOS */}
        <div className="p-6 bg-ui-surface border border-ui-border rounded-lg">
          <div className="text-text-muted text-sm mb-2">Strength of Schedule (AdjEM)</div>
          <div className="text-4xl font-bold font-mono">
            {team.sos_adjEM !== null ? (
              team.sos_adjEM.toFixed(2)
            ) : (
              <span className="text-text-muted">N/A</span>
            )}
          </div>
          <p className="text-text-muted text-sm mt-2">
            Average opponent efficiency margin
          </p>
        </div>
        
        {/* Luck */}
        <div className="p-6 bg-ui-surface border border-ui-border rounded-lg">
          <div className="text-text-muted text-sm mb-2">Luck Rating</div>
          <div className="text-4xl font-bold font-mono">
            {team.luck !== null ? (
              <>{team.luck > 0 ? '+' : ''}{team.luck.toFixed(3)}</>
            ) : (
              <span className="text-text-muted">N/A</span>
            )}
          </div>
          <p className="text-text-muted text-sm mt-2">
            How "lucky" a team has been in close games
          </p>
        </div>
        
        {/* Placeholder for future resume metrics */}
        <div className="p-6 bg-ui-surface border border-ui-border rounded-lg opacity-60">
          <div className="text-text-muted text-sm mb-2">Quadrant 1 Record</div>
          <div className="text-4xl font-bold font-mono text-text-muted">N/A</div>
          <p className="text-text-muted text-sm mt-2">
            Record vs Quadrant 1 opponents (data pending)
          </p>
        </div>
        
        <div className="p-6 bg-ui-surface border border-ui-border rounded-lg opacity-60">
          <div className="text-text-muted text-sm mb-2">Quadrant 2 Record</div>
          <div className="text-4xl font-bold font-mono text-text-muted">N/A</div>
          <p className="text-text-muted text-sm mt-2">
            Record vs Quadrant 2 opponents (data pending)
          </p>
        </div>
        
        <div className="p-6 bg-ui-surface border border-ui-border rounded-lg opacity-60">
          <div className="text-text-muted text-sm mb-2">NET Ranking</div>
          <div className="text-4xl font-bold font-mono text-text-muted">N/A</div>
          <p className="text-text-muted text-sm mt-2">
            NCAA Evaluation Tool ranking (data pending)
          </p>
        </div>
        
        <div className="p-6 bg-ui-surface border border-ui-border rounded-lg opacity-60">
          <div className="text-text-muted text-sm mb-2">SOR (Strength of Record)</div>
          <div className="text-4xl font-bold font-mono text-text-muted">N/A</div>
          <p className="text-text-muted text-sm mt-2">
            Resume quality metric (data pending)
          </p>
        </div>
      </div>
      
      {!team.wab && !team.sos_adjEM && !team.luck && !team.barthag && (
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
        
        // Fetch from Django API
        const response = await fetch(
          `http://localhost:8000/api/teams/${team.teamId}/gamelog?season=2026`
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
  }, [team.teamId]);

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
      <h2 className="text-2xl font-bold mb-4">2025-26 Game Log</h2>
      
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
            {gameLog.map((game, index) => (
              <tr 
                key={game.id || index}
                className="border-t border-ui-border hover:bg-ui-surface-dark/50 transition-colors"
              >
                <td className="px-4 py-3 text-sm">
                  {new Date(game.game_date).toLocaleDateString('en-US', { 
                    month: 'short', 
                    day: 'numeric' 
                  })}
                </td>
                <td className="px-4 py-3 text-sm font-medium">
                  {game.opponent_name}
                </td>
                <td className="px-4 py-3 text-center text-sm">
                  <span className={clsx(
                    'px-2 py-1 rounded text-xs font-medium',
                    game.home_away === 'H' && 'bg-green-500/20 text-green-400',
                    game.home_away === 'A' && 'bg-red-500/20 text-red-400',
                    game.home_away === 'N' && 'bg-blue-500/20 text-blue-400'
                  )}>
                    {game.home_away === 'H' ? 'Home' : game.home_away === 'A' ? 'Away' : 'Neutral'}
                  </span>
                </td>
                <td className="px-4 py-3 text-center text-sm">
                  <span className={clsx(
                    'font-bold',
                    game.result === 'W' ? 'text-green-400' : 'text-red-400'
                  )}>
                    {game.result}
                  </span>
                </td>
                <td className="px-4 py-3 text-right text-sm">
                  {game.pts}-{game.pts - (game.margin || 0)}
                </td>
                <td className="px-4 py-3 text-right text-sm font-mono">
                  {game.ortg?.toFixed(1) || '-'}
                </td>
                <td className="px-4 py-3 text-right text-sm font-mono">
                  {game.drtg?.toFixed(1) || '-'}
                </td>
                <td className="px-4 py-3 text-right text-sm font-mono">
                  {game.efg_pct ? (game.efg_pct * 100).toFixed(1) + '%' : '-'}
                </td>
                <td className="px-4 py-3 text-right text-sm font-mono">
                  {game.tov_pct ? (game.tov_pct * 100).toFixed(1) + '%' : '-'}
                </td>
                <td className="px-4 py-3 text-right text-sm font-mono">
                  {game.orb_pct ? (game.orb_pct * 100).toFixed(1) + '%' : '-'}
                </td>
                <td className="px-4 py-3 text-right text-sm font-mono">
                  {game.ftr ? (game.ftr * 100).toFixed(1) + '%' : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      
      <div className="text-sm text-text-muted mt-4">
        Total Games: {gameLog.length}
      </div>
    </div>
  );
}
