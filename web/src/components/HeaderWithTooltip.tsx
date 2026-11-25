'use client';

import { Info } from 'lucide-react';
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Better } from '@macfax/core/lib/metricMetadata';

interface HeaderWithTooltipProps {
  label: string;
  better: Better;
  tooltip: string;
}

const EDGE = 8;   // min gap between tooltip and viewport edge
const GAP = 8;    // gap between icon and tooltip
const ARROW = 8;  // arrow square size (w-2 h-2)

const BETTER_TEXT: Record<Better, string> = {
  higher: '↑ Higher is better',
  lower: '↓ Lower is better',
  neutral: '○ Neutral (style metric)',
};

interface Placement {
  top: number;
  left: number;
  arrowLeft: number;
  above: boolean;
}

/**
 * Column label with an info button. The tooltip is portaled to <body> and positioned `fixed` from the
 * icon's rect, so it escapes the <th>'s inherited text styles and the table's overflow-x-auto clipping.
 * Mouse hover and keyboard focus open it; a tap toggles it. Scroll, resize and Esc close it.
 */
export default function HeaderWithTooltip({ label, better, tooltip }: HeaderWithTooltipProps) {
  const [open, setOpen] = useState(false);
  const [place, setPlace] = useState<Placement | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  // Pointer type of the press in progress: a touch press focuses the button before its click,
  // and that focus must not open the tooltip only for the click to close it again.
  const pressRef = useRef<string | null>(null);
  const tipId = useId();

  const close = useCallback(() => {
    setOpen(false);
    setPlace(null);
  }, []);

  // Measure after the portal mounts, before paint.
  useLayoutEffect(() => {
    if (!open) return;
    const btn = buttonRef.current;
    const tip = tipRef.current;
    if (!btn || !tip) return;
    const r = btn.getBoundingClientRect();
    const vw = document.documentElement.clientWidth;
    const vh = window.innerHeight;
    const w = tip.offsetWidth;
    const h = tip.offsetHeight;
    const iconX = r.left + r.width / 2;
    const left = Math.min(Math.max(iconX - w / 2, EDGE), vw - w - EDGE);
    const fitsBelow = r.bottom + GAP + h <= vh - EDGE;
    const fitsAbove = r.top - GAP - h >= EDGE;
    const above = !fitsBelow && fitsAbove;
    setPlace({
      top: above ? r.top - GAP - h : r.bottom + GAP,
      left,
      arrowLeft: Math.min(Math.max(iconX - left - ARROW / 2, ARROW), w - 2 * ARROW),
      above,
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close(); };
    const onPointerDown = (e: PointerEvent) => {
      const t = e.target as Node;
      if (!buttonRef.current?.contains(t) && !tipRef.current?.contains(t)) close();
    };
    window.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    window.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onPointerDown, true);
    return () => {
      window.removeEventListener('scroll', close, true);
      window.removeEventListener('resize', close);
      window.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', onPointerDown, true);
    };
  }, [open, close]);

  return (
    <span className="inline-flex items-center gap-1">
      <span>{label}</span>
      <button
        ref={buttonRef}
        type="button"
        aria-label={`About ${label}`}
        aria-expanded={open}
        aria-describedby={open ? tipId : undefined}
        className="inline-flex shrink-0 items-center justify-center rounded-sm p-0.5 -m-0.5 opacity-50 transition-opacity hover:opacity-100 focus-visible:opacity-100 focus-visible:outline focus-visible:outline-1 focus-visible:outline-current"
        onPointerEnter={(e) => { if (e.pointerType === 'mouse') setOpen(true); }}
        onPointerLeave={(e) => { if (e.pointerType === 'mouse') close(); }}
        onPointerDown={(e) => { pressRef.current = e.pointerType; }}
        onFocus={() => { if (!pressRef.current) setOpen(true); }}
        onPointerCancel={() => { pressRef.current = null; }}
        onBlur={() => { pressRef.current = null; close(); }}
        onClick={(e) => {
          e.stopPropagation();   // the <th> sorts on click
          const press = pressRef.current;
          pressRef.current = null;
          if (press === 'mouse') return;   // hover already controls it
          if (open) close(); else setOpen(true);
        }}
      >
        <Info className="w-3 h-3" aria-hidden />
      </button>

      {open && createPortal(
        <div
          ref={tipRef}
          id={tipId}
          role="tooltip"
          // React events bubble through portals to the <th>; keep clicks here from sorting.
          onClick={(e) => e.stopPropagation()}
          style={place ? { top: place.top, left: place.left } : { top: 0, left: 0, visibility: 'hidden' }}
          className="fixed z-[60] w-64 max-w-[calc(100vw-16px)] p-3 bg-slate-900 border border-slate-600 rounded-lg shadow-2xl normal-case tracking-normal font-sans font-normal whitespace-normal text-left text-xs"
        >
          <p className="text-slate-200 leading-relaxed">{tooltip}</p>
          <div className="mt-2 pt-1 border-t border-slate-700 font-medium text-slate-400">
            {BETTER_TEXT[better]}
          </div>
          {place && (
            <div
              aria-hidden
              className={
                'absolute w-2 h-2 bg-slate-900 border-slate-600 rotate-45 ' +
                (place.above ? '-bottom-1 border-r border-b' : '-top-1 border-l border-t')
              }
              style={{ left: place.arrowLeft }}
            />
          )}
        </div>,
        document.body,
      )}
    </span>
  );
}
