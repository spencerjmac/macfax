'use client';

import clsx from 'clsx';

/**
 * Rank Pill component - displays rank as a small badge
 */
interface RankPillProps {
  rank: number | null;
  className?: string;
}

export function RankPill({ rank, className }: RankPillProps) {
  if (rank === null) {
    return (
      <span className={clsx('text-xs font-mono px-2 py-0.5 rounded bg-ui-surface text-text-muted', className)}>
        N/A
      </span>
    );
  }
  
  // Color based on rank
  const colorClass = rank <= 10 
    ? 'bg-success/20 text-success' 
    : rank <= 25 
    ? 'bg-brand-orange/20 text-brand-orange'
    : rank <= 50
    ? 'bg-blue-500/20 text-blue-600'
    : 'bg-ui-surface text-text-muted';
  
  return (
    <span className={clsx('text-xs font-mono px-2 py-0.5 rounded font-semibold', colorClass, className)}>
      #{rank}
    </span>
  );
}

/**
 * Enhanced StatCard with optional rank pill
 */
interface StatCardProps {
  label: string;
  value: string;
  rank?: number | null;
  description?: string;
  color?: string;
}

export function StatCard({ label, value, rank, description, color }: StatCardProps) {
  return (
    <div className="p-4 bg-ui-card border border-ui-border rounded-lg">
      <div className="flex items-start justify-between gap-2 mb-1">
        <div className="text-text-muted text-xs">{label}</div>
        {rank !== undefined && <RankPill rank={rank} />}
      </div>
      <div className={clsx('text-2xl font-bold font-mono', color || 'text-text-primary')}>
        {value}
      </div>
      {description && (
        <p className="text-xs text-text-muted mt-2">{description}</p>
      )}
    </div>
  );
}

/**
 * Large metric card for core stats (like in Overview)
 */
interface MetricCardProps {
  label: string;
  value: string;
  rank?: number | null;
  color?: string;
}

export function MetricCard({ label, value, rank, color }: MetricCardProps) {
  return (
    <div className="p-6 bg-ui-surface border border-ui-border rounded-lg">
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="text-text-muted text-sm">{label}</div>
        {rank !== undefined && <RankPill rank={rank} />}
      </div>
      <div className={clsx('text-4xl font-bold font-mono', color || 'text-text-primary')}>
        {value}
      </div>
    </div>
  );
}

/**
 * Four Factors card with offense, defense, margin - each with ranks
 */
interface FactorCardWithRanksProps {
  name: string;
  offense: string;
  offenseRank?: number | null;
  defense: string;
  defenseRank?: number | null;
  margin: string;
  marginRank?: number | null;
  marginPositive: boolean;
  description: string;
}

export function FactorCardWithRanks({
  name,
  offense,
  offenseRank,
  defense,
  defenseRank,
  margin,
  marginRank,
  marginPositive,
  description,
}: FactorCardWithRanksProps) {
  return (
    <div className="p-6 bg-ui-card border border-ui-border rounded-lg">
      <h3 className="font-bold text-lg mb-2">{name}</h3>
      <p className="text-text-muted text-sm mb-4">{description}</p>
      
      <div className="grid grid-cols-3 gap-4">
        {/* Offense */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <div className="text-text-muted text-xs">Offense</div>
            {offenseRank !== undefined && <RankPill rank={offenseRank} />}
          </div>
          <div className="text-2xl font-mono font-bold text-success">{offense}</div>
        </div>
        
        {/* Defense */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <div className="text-text-muted text-xs">Defense</div>
            {defenseRank !== undefined && <RankPill rank={defenseRank} />}
          </div>
          <div className="text-2xl font-mono font-bold text-secondary">{defense}</div>
        </div>
        
        {/* Margin */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <div className="text-text-muted text-xs">Margin</div>
            {marginRank !== undefined && <RankPill rank={marginRank} />}
          </div>
          <div className={clsx(
            'text-2xl font-mono font-bold',
            marginPositive ? 'text-success' : 'text-warning'
          )}>
            {marginPositive && '+'}{margin}
          </div>
        </div>
      </div>
    </div>
  );
}
