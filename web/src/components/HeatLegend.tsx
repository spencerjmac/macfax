import { HEAT_ABOVE, HEAT_BELOW } from '@macfax/core/lib/rankingUtils';

interface HeatLegendProps {
  /** What the percentile is measured against, e.g. "all D1 teams". */
  basis: string;
  /** Optional extra note shown after the basis. */
  note?: string;
}

const SWATCH = 'inline-block w-[10px] h-[10px] rounded-sm shrink-0';

/**
 * One-line key for the table heat map (heatStyleFromPercentile, light surface):
 * coral strongest → faintest, an unshaded middle, teal faintest → strongest.
 */
export default function HeatLegend({ basis, note }: HeatLegendProps) {
  return (
    <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] text-muted">
      <span>Below avg</span>
      <span className="inline-flex items-center gap-[2px]" aria-hidden="true">
        {[...HEAT_BELOW].reverse().map((color) => (
          <span key={`below-${color}`} className={SWATCH} style={{ background: color }} />
        ))}
        <span className={`${SWATCH} bg-white border border-ui-border`} />
        {HEAT_ABOVE.map((color) => (
          <span key={`above-${color}`} className={SWATCH} style={{ background: color }} />
        ))}
      </span>
      <span>Above avg</span>
      <span>· percentile vs. {basis}</span>
      {note && <span>· {note}</span>}
    </div>
  );
}
