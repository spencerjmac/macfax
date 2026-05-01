import type { InterpretationBandEntry } from '@/lib/methodologyTypes';
import clsx from 'clsx';

interface InterpretationBandProps {
  bands: InterpretationBandEntry[];
}

const colorMap: Record<string, string> = {
  success: 'bg-success/15 text-success border-success/30',
  brand: 'bg-brand/15 text-brand border-brand/30',
  secondary: 'bg-blue-500/10 text-blue-600 border-blue-500/20',
  warning: 'bg-yellow-400/10 text-yellow-700 border-yellow-400/30',
  negative: 'bg-negative/10 text-negative border-negative/30',
};

export function InterpretationBand({ bands }: InterpretationBandProps) {
  return (
    <div className="space-y-2 my-2">
      {bands.map((band) => (
        <div
          key={band.label}
          className={clsx(
            'flex gap-4 items-start rounded-lg border px-4 py-3',
            colorMap[band.color] ?? 'bg-ui-surface border-ui-border text-text-primary',
          )}
        >
          <div className="min-w-[110px]">
            <div className="font-semibold text-sm">{band.label}</div>
            <div className="font-mono text-xs opacity-80">{band.range}</div>
          </div>
          <div className="text-sm opacity-90">{band.description}</div>
        </div>
      ))}
    </div>
  );
}
