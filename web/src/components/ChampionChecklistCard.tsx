'use client';

import { ChecklistItem } from '@/lib/rankings';
import clsx from 'clsx';

// Simple SVG icons
const CheckCircle2Icon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <circle cx="12" cy="12" r="10" strokeWidth={2} />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4" />
  </svg>
);

const XCircleIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <circle cx="12" cy="12" r="10" strokeWidth={2} />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 9l-6 6M9 9l6 6" />
  </svg>
);

interface ChampionChecklistCardProps {
  passedCount: number;
  total: number;
  items: ChecklistItem[];
}

export default function ChampionChecklistCard({
  passedCount,
  total,
  items,
}: ChampionChecklistCardProps) {
  const percentage = (passedCount / total) * 100;
  
  return (
    <div className="bg-ui-card border border-ui-border rounded-lg p-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-2xl font-bold">🔮 Crystal Ball</h2>
          <div className="text-sm font-mono px-3 py-1 bg-brand-orange text-white rounded-full">
            {passedCount} / {total}
          </div>
        </div>
        <p className="text-text-muted text-sm">
          National Champion Checklist — 15 criteria based on historical championship winners*
        </p>
        
        {/* Progress Bar */}
        <div className="mt-4 bg-ui-surface rounded-full h-3 overflow-hidden">
          <div
            className={clsx(
              'h-full transition-all duration-500 rounded-full',
              percentage >= 80 ? 'bg-success' : percentage >= 60 ? 'bg-brand-orange' : 'bg-warning'
            )}
            style={{ width: `${percentage}%` }}
          />
        </div>
        <div className="text-right text-xs text-text-muted mt-1">
          {percentage.toFixed(0)}% complete
        </div>
        <div className="mt-4 text-[10px] text-text-muted italic bg-ui-surface/50 p-2 rounded border border-ui-border/50">
          *The "UConn Rule": Four Factor criteria are calculated based on 19 of the last 21 National Champions, explicitly excluding the anomalous 2011 & 2014 UConn runs to ensure stricter, more accurate predictive thresholds.
        </div>
      </div>
      
      {/* Checklist Items */}
      <div className="space-y-3 max-h-[600px] overflow-y-auto pr-2">
        {items.map((item) => (
          <ChecklistItemRow key={item.key} item={item} />
        ))}
      </div>
    </div>
  );
}

function ChecklistItemRow({ item }: { item: ChecklistItem }) {
  const Icon = item.passed ? CheckCircle2Icon : XCircleIcon;
  const iconColor = item.passed ? 'text-success' : 'text-text-muted';
  const isNA = item.valueDisplay === 'N/A';
  
  return (
    <div className={clsx(
      'p-4 rounded-lg border transition-all',
      item.passed 
        ? 'bg-success/5 border-success/20' 
        : isNA 
        ? 'bg-ui-surface border-ui-border opacity-70'
        : 'bg-ui-surface border-ui-border'
    )}>
      <div className="flex items-start gap-3">
        {/* Icon */}
        <Icon className={clsx('w-5 h-5 flex-shrink-0 mt-0.5', iconColor)} />
        
        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2 mb-1">
            <h3 className="font-semibold text-sm">{item.label}</h3>
            <div className={clsx(
              'text-xs font-mono px-2 py-0.5 rounded whitespace-nowrap',
              item.passed 
                ? 'bg-success/20 text-success' 
                : isNA
                ? 'bg-ui-surface text-text-muted'
                : 'bg-warning/20 text-warning'
            )}>
              {item.passed ? 'PASS' : isNA ? 'N/A' : 'FAIL'}
            </div>
          </div>
          
          {/* Value vs Threshold */}
          <div className="text-xs space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-text-muted">Value:</span>
              <span className="font-mono font-semibold">{item.valueDisplay}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-text-muted">Need:</span>
              <span className="font-mono text-text-muted">{item.thresholdDisplay}</span>
            </div>
          </div>
          
          {/* Detail */}
          {item.detail && (
            <p className="text-xs text-text-muted mt-2 italic">
              {item.detail}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
