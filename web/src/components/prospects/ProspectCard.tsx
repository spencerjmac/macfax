'use client';

import Image from 'next/image';
import clsx from 'clsx';
import { Prospect } from '@/types/prospects';

interface Props {
  prospect: Prospect;
}

// ─── Stat meta ────────────────────────────────────────────────────────────────

const STATS = [
  { key: 'bpm'  as const, label: 'BPM',  thresholds: [[14, 'elite'], [10, 'good'], [7, 'avg'], [-99, 'poor']] as [number, string][], fmt: (v: number) => v.toFixed(1), barMax: 20,   barMin: -5 },
  { key: 'dbpm' as const, label: 'DBPM', thresholds: [[5,  'elite'], [2,  'good'], [0, 'avg'], [-99, 'poor']] as [number, string][], fmt: (v: number) => v.toFixed(1), barMax: 10,   barMin: -5 },
  { key: 'per'  as const, label: 'PER',  thresholds: [[28, 'elite'], [22, 'good'], [17,'avg'], [-99, 'poor']] as [number, string][], fmt: (v: number) => v.toFixed(1), barMax: 40,   barMin: 5  },
  { key: 'ts'   as const, label: 'TS%',  thresholds: [[.64,'elite'], [.58,'good'], [.53,'avg'],[-99, 'poor']] as [number, string][], fmt: (v: number) => `${(v*100).toFixed(1)}%`, barMax: 0.75, barMin: 0.40 },
];

type StatKey = 'bpm' | 'dbpm' | 'per' | 'ts';

function getLevel(key: StatKey, val: number | null): 'elite' | 'good' | 'avg' | 'poor' | 'null' {
  if (val == null) return 'null';
  const meta = STATS.find(s => s.key === key)!;
  for (const [thresh, level] of meta.thresholds) {
    if (val >= thresh) return level as 'elite' | 'good' | 'avg' | 'poor';
  }
  return 'poor';
}

const LEVEL_STYLES = {
  elite: { text: 'text-emerald-600', badge: 'bg-emerald-100 text-emerald-700', bar: 'bg-emerald-500' },
  good:  { text: 'text-emerald-500', badge: 'bg-emerald-50  text-emerald-600', bar: 'bg-emerald-400' },
  avg:   { text: 'text-text-primary', badge: 'bg-slate-100 text-slate-600',    bar: 'bg-slate-400'   },
  poor:  { text: 'text-red-500',      badge: 'bg-red-50    text-red-600',       bar: 'bg-red-400'     },
  null:  { text: 'text-text-muted',   badge: 'bg-slate-50  text-text-muted',    bar: 'bg-slate-200'   },
};

function barPct(meta: typeof STATS[number], val: number | null): number {
  if (val == null) return 0;
  return Math.min(100, Math.max(0, ((val - meta.barMin) / (meta.barMax - meta.barMin)) * 100));
}

// ─── Strengths & Concerns derivation ─────────────────────────────────────────

function getProfile(p: Prospect) {
  const stats = [
    { key: 'bpm' as StatKey, label: 'BPM',  val: p.bpm,  meta: STATS[0] },
    { key: 'dbpm'as StatKey, label: 'DBPM', val: p.dbpm, meta: STATS[1] },
    { key: 'per' as StatKey, label: 'PER',  val: p.per,  meta: STATS[2] },
    { key: 'ts'  as StatKey, label: 'TS%',  val: p.ts,   meta: STATS[3] },
  ];
  const strengths = stats.filter(s => {
    if (s.val == null) return false;
    const l = getLevel(s.key, s.val);
    return l === 'elite' || l === 'good';
  });
  const concerns = stats.filter(s => s.val != null && getLevel(s.key, s.val) === 'poor');
  return { strengths, concerns };
}

// ─── Breakdown bar ────────────────────────────────────────────────────────────

function BreakdownRow({
  label, value, barPct, color,
}: { label: string; value: string; barPct: number; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-text-muted w-28 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className={clsx('h-full rounded-full', color)} style={{ width: `${barPct}%` }} />
      </div>
      <span className="text-xs font-mono text-text-primary w-10 text-right shrink-0">{value}</span>
    </div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export function ProspectCard({ prospect: p }: Props) {
  const { strengths, concerns } = getProfile(p);
  const noteLines = p.note.split(/;\s*/).filter(Boolean);

  const hasAdjustments = p.srsAdj !== 0 || p.ageAdj !== 0 || p.scoutAdj !== 0 || p.availAdj !== 0;

  return (
    <div className="p-4 bg-slate-50">

      {/* ── Player header ── */}
      <div className="flex items-center gap-4 mb-4 pb-3 border-b border-ui-border">
        <div className="w-14 h-14 rounded-full overflow-hidden bg-slate-100 flex-shrink-0 flex items-center justify-center border border-ui-border">
          {p.headshot ? (
            <Image
              src={p.headshot}
              alt={p.name}
              width={56}
              height={56}
              className="object-cover object-top w-full h-full"
            />
          ) : (
            <span className="text-sm font-bold text-text-muted">
              {p.name.split(' ').map(n => n[0]).slice(0, 2).join('')}
            </span>
          )}
        </div>
        <div>
          <h3 className="font-bold text-text-primary text-base">{p.name}</h3>
          <p className="text-sm text-text-muted">{p.college} · {p.position} · {p.age.toFixed(1)}y</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">

      {/* ── Section 1: MPS Breakdown ── */}
      <div className="bg-white border border-ui-border rounded-lg p-4">
        <div className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-3">
          MPS Breakdown
        </div>
        <div className="space-y-2">
          <BreakdownRow
            label="Composite score"
            value={p.mpsComposite.toFixed(1)}
            barPct={(p.mpsComposite / 100) * 100}
            color="bg-brand"
          />
          {p.srsAdj !== 0 && (
            <BreakdownRow
              label={`Program SRS ${p.srsAdj > 0 ? '+' : ''}${p.srsAdj}`}
              value={`${p.srsAdj > 0 ? '+' : ''}${p.srsAdj}`}
              barPct={Math.abs(p.srsAdj / 5) * 100}
              color={p.srsAdj > 0 ? 'bg-emerald-500' : 'bg-red-400'}
            />
          )}
          {p.ageAdj !== 0 && (
            <BreakdownRow
              label={`Age adj ${p.ageAdj > 0 ? '(youth bonus)' : ''}`}
              value={`${p.ageAdj > 0 ? '+' : ''}${p.ageAdj}`}
              barPct={Math.abs(p.ageAdj / 15) * 100}
              color={p.ageAdj > 0 ? 'bg-emerald-500' : 'bg-red-400'}
            />
          )}
          {p.scoutAdj !== 0 && (
            <BreakdownRow
              label="Scout consensus"
              value={`${p.scoutAdj > 0 ? '+' : ''}${p.scoutAdj}`}
              barPct={Math.abs(p.scoutAdj / 10) * 100}
              color={p.scoutAdj > 0 ? 'bg-amber-500' : 'bg-red-400'}
            />
          )}
          {p.availAdj !== 0 && (
            <BreakdownRow
              label="Availability"
              value={p.availAdj.toFixed(1)}
              barPct={Math.abs(p.availAdj / 8) * 100}
              color="bg-red-400"
            />
          )}
        </div>
        <div className="mt-3 pt-3 border-t border-ui-border flex items-center justify-between">
          <span className="text-xs text-text-muted">Final MPS</span>
          <span className="font-mono font-bold text-base text-text-primary">{p.mps.toFixed(1)}</span>
        </div>
      </div>

      {/* ── Section 2: Stat Profile ── */}
      <div className="bg-white border border-ui-border rounded-lg p-4">
        <div className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-3">
          Stat Profile
        </div>
        <div className="space-y-3">
          {STATS.map(meta => {
            const val = p[meta.key as keyof Prospect] as number | null;
            const level = getLevel(meta.key, val);
            const styles = LEVEL_STYLES[level];
            return (
              <div key={meta.key}>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-text-muted w-10">{meta.label}</span>
                    <span className={clsx('text-[10px] font-semibold px-1.5 py-0.5 rounded', styles.badge)}>
                      {level === 'null' ? '—' : level.charAt(0).toUpperCase() + level.slice(1)}
                    </span>
                  </div>
                  <span className={clsx('text-sm font-mono font-semibold', styles.text)}>
                    {val != null ? meta.fmt(val) : '—'}
                  </span>
                </div>
                <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className={clsx('h-full rounded-full transition-all', styles.bar)}
                    style={{ width: `${barPct(meta, val)}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Section 3: Strengths, Concerns & Notes ── */}
      <div className="bg-white border border-ui-border rounded-lg p-4 flex flex-col gap-3">

        {/* Strengths */}
        {strengths.length > 0 && (
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-emerald-600 mb-2">
              ↑ Strengths
            </div>
            <div className="space-y-1.5">
              {strengths.map(s => {
                const level = getLevel(s.key, s.val);
                const styles = LEVEL_STYLES[level];
                return (
                  <div key={s.key} className="flex items-center gap-2 text-sm">
                    <span className="text-emerald-500 shrink-0">✓</span>
                    <span className="text-text-primary font-medium">
                      {level === 'elite' ? 'Elite' : 'Strong'} {s.label}
                    </span>
                    <span className={clsx('font-mono text-xs ml-auto', styles.text)}>
                      {s.val != null ? s.meta.fmt(s.val) : ''}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Concerns */}
        {concerns.length > 0 && (
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-red-500 mb-2">
              ↓ Concerns
            </div>
            <div className="space-y-1.5">
              {concerns.map(s => (
                <div key={s.key} className="flex items-center gap-2 text-sm">
                  <span className="text-red-400 shrink-0">⚠</span>
                  <span className="text-text-primary font-medium">Weak {s.label}</span>
                  <span className="font-mono text-xs text-red-500 ml-auto">
                    {s.val != null ? s.meta.fmt(s.val) : ''}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {strengths.length === 0 && concerns.length === 0 && (
          <p className="text-xs text-text-muted">Average across tracked stats</p>
        )}

        {/* Model notes */}
        {noteLines.length > 0 && (
          <div className="mt-auto pt-3 border-t border-ui-border">
            <div className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2">
              Model Notes
            </div>
            <div className="space-y-1 max-h-28 overflow-y-auto">
              {noteLines.map((line, i) => (
                <p key={i} className="text-xs text-text-muted leading-relaxed font-mono">
                  {line}
                </p>
              ))}
            </div>
          </div>
        )}
      </div>

      </div>  {/* end grid */}
    </div>
  );
}
