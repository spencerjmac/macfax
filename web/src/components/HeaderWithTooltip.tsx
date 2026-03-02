'use client';

import { Info } from 'lucide-react';
import { useState } from 'react';
import { Better } from '@/lib/metricMetadata';

interface HeaderWithTooltipProps {
  label: string;
  better: Better;
  tooltip: string;
}

export default function HeaderWithTooltip({ label, better, tooltip }: HeaderWithTooltipProps) {
  const [showTooltip, setShowTooltip] = useState(false);
  
  // Better indicator
  const betterIndicator = 
    better === 'higher' ? '↑ Higher is better' :
    better === 'lower' ? '↓ Lower is better' :
    '○ Neutral (style metric)';
  
  const betterColor = 
    better === 'higher' ? 'text-emerald-400' :
    better === 'lower' ? 'text-rose-400' :
    'text-slate-400';
  
  return (
    <div className="relative inline-flex items-center gap-1.5">
      <span>{label}</span>
      <div
        className="relative"
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
      >
        <Info className="w-3.5 h-3.5 text-slate-500 hover:text-brand transition-colors cursor-help" />
        
        {showTooltip && (
          <div className="absolute z-50 top-full left-1/2 -translate-x-1/2 mt-2 w-72 p-3 bg-slate-900 border border-slate-600 rounded-lg shadow-2xl">
            <div className="text-xs space-y-2">
              <p className="text-slate-200 leading-relaxed">{tooltip}</p>
              <div className={`text-xs font-medium ${betterColor} pt-1 border-t border-slate-700`}>
                {betterIndicator}
              </div>
            </div>
            <div className="absolute -top-1 left-1/2 -translate-x-1/2 w-2 h-2 bg-slate-900 border-l border-t border-slate-600 rotate-45" />
          </div>
        )}
      </div>
    </div>
  );
}
