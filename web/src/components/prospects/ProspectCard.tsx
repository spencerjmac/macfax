'use client';

import Image from 'next/image';
import clsx from 'clsx';
import { Prospect } from '@/types/prospects';

interface Props {
  prospect: Prospect;
}

// ─── Stat formatting helpers ──────────────────────────────────────────────────

function fmtNum(v: number | null, decimals = 1): string {
  if (v == null) return '—';
  return v.toFixed(decimals);
}
function fmtPct(v: number | null): string {
  if (v == null) return '—';
  return `${(v * 100).toFixed(1)}%`;
}
function fmtSigned(v: number | null, decimals = 1): string {
  if (v == null) return '—';
  return v >= 0 ? `+${v.toFixed(decimals)}` : v.toFixed(decimals);
}

function bpmColor(v: number | null): string {
  if (v == null) return 'text-text-muted';
  if (v >= 14) return 'text-emerald-600 font-bold';
  if (v >= 10) return 'text-emerald-500';
  if (v >= 7)  return 'text-text-primary';
  return 'text-red-500';
}

// ─── Stat tile (top 4 quick stats) ───────────────────────────────────────────

function StatTile({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="flex flex-col items-center bg-white border border-ui-border rounded-lg px-3 py-2.5 flex-1 min-w-0">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-text-muted mb-1">{label}</span>
      <span className={clsx('text-lg font-mono font-bold leading-tight', valueClass ?? 'text-text-primary')}>
        {value}
      </span>
    </div>
  );
}

// ─── Stat row inside a section ────────────────────────────────────────────────

function StatRow({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="flex items-center justify-between py-1 border-b border-ui-border last:border-0">
      <span className="text-xs text-text-muted">{label}</span>
      <span className={clsx('text-xs font-mono font-semibold', valueClass ?? 'text-text-primary')}>{value}</span>
    </div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export function ProspectCard({ prospect: p }: Props) {
  const noteLines = p.note.split(/;\s*/).filter(Boolean);
  const bpmStr = fmtSigned(p.bpm);

  const hasComp = !!p.comp1;
  const hasProfile = p.strengths.length > 0 || p.weaknesses.length > 0;

  return (
    <div className="p-4 bg-slate-50">

      {/* ── Player header ── */}
      <div className="flex items-center gap-4 mb-4 pb-3 border-b border-ui-border">
        <div className="w-14 h-14 rounded-full overflow-hidden bg-slate-100 flex-shrink-0 flex items-center justify-center border border-ui-border">
          {p.headshot ? (
            <Image src={p.headshot} alt={p.name} width={56} height={56}
              className="object-cover object-top w-full h-full" />
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

      {/* ── Key stats: PPG / REB / AST / BPM ── */}
      <div className="flex gap-2 mb-4">
        <StatTile label="PPG" value={fmtNum(p.ppg)} />
        <StatTile label="REB" value={fmtNum(p.rpg)} />
        <StatTile label="AST" value={fmtNum(p.apg)} />
        <StatTile label="BPM" value={bpmStr} valueClass={bpmColor(p.bpm)} />
      </div>

      {/* ── Three-column body ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">

        {/* Col 1 — Statistical Profile ── */}
        <div className="bg-white border border-ui-border rounded-lg p-4">
          <div className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-3">Statistical Profile</div>

          <div className="mb-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted mb-1.5">Impact</div>
            <StatRow label="Box Plus/Minus" value={bpmStr} valueClass={bpmColor(p.bpm)} />
            <StatRow label="Off. BPM" value={fmtSigned(p.obpm)} valueClass={p.obpm != null && p.obpm >= 7 ? 'text-emerald-500' : undefined} />
            <StatRow label="Def. BPM" value={fmtSigned(p.dbpm)} valueClass={p.dbpm != null && p.dbpm >= 3 ? 'text-emerald-500' : undefined} />
            <StatRow label="Win Shares / 40" value={fmtNum(p.ws40, 3)} />
            <StatRow label="PER" value={fmtNum(p.per)} />
          </div>

          <div className="mb-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted mb-1.5">Efficiency</div>
            <StatRow label="True Shooting %" value={fmtPct(p.ts)} valueClass={p.ts != null && p.ts >= 0.60 ? 'text-emerald-500' : undefined} />
            <StatRow label="Field Goal %" value={fmtPct(p.fgPct)} />
            <StatRow label="Assist %" value={p.astPct != null ? `${p.astPct.toFixed(1)}%` : '—'} />
          </div>

          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted mb-1.5">Defense / Hustle</div>
            <StatRow label="Steals / Game" value={fmtNum(p.stlPg)} />
            <StatRow label="Blocks / Game" value={fmtNum(p.blkPg)} />
            <StatRow label="Off. Reb %" value={p.orbPct != null ? `${p.orbPct.toFixed(1)}%` : '—'} />
          </div>
        </div>

        {/* Col 2 — Strengths & Weaknesses ── */}
        <div className="bg-white border border-ui-border rounded-lg p-4 flex flex-col gap-3">
          <div className="text-xs font-semibold uppercase tracking-wider text-text-muted">Player Profile</div>

          {hasProfile ? (
            <>
              {p.strengths.length > 0 && (
                <div>
                  <div className="text-xs font-semibold text-emerald-600 uppercase tracking-wide mb-1.5">Strengths</div>
                  <ul className="space-y-1.5">
                    {p.strengths.map((s, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-text-primary">
                        <span className="text-emerald-500 mt-0.5 shrink-0">✓</span>
                        <span>{s}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {p.weaknesses.length > 0 && (
                <div>
                  <div className="text-xs font-semibold text-red-500 uppercase tracking-wide mb-1.5">Concerns</div>
                  <ul className="space-y-1.5">
                    {p.weaknesses.map((w, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-text-primary">
                        <span className="text-red-400 mt-0.5 shrink-0">⚠</span>
                        <span>{w}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          ) : (
            <p className="text-xs text-text-muted">Mixed statistical profile — no clear strengths or concerns.</p>
          )}
        </div>

        {/* Col 3 — NBA Comp + Notes ── */}
        <div className="bg-white border border-ui-border rounded-lg p-4 flex flex-col gap-4">

          {hasComp && (
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2">NBA Comp</div>
              <div className="space-y-2">
                {[
                  { name: p.comp1, year: p.comp1Year, pick: p.comp1Pick, sim: p.comp1Sim },
                  { name: p.comp2, year: p.comp2Year, pick: p.comp2Pick, sim: p.comp2Sim },
                ].filter(c => c.name).map((c, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold text-sm text-text-primary truncate">{c.name}</div>
                      <div className="text-[11px] text-text-muted font-mono">
                        {c.year} · {c.pick != null ? `Pick #${c.pick}` : 'Rd 2'}
                      </div>
                    </div>
                    {c.sim != null && (
                      <div className="text-right shrink-0">
                        <div className="text-xs font-mono font-semibold text-brand">{c.sim}%</div>
                        <div className="text-[10px] text-text-muted">match</div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <p className="text-[10px] text-text-muted mt-2 leading-relaxed">
                Statistical similarity to historical draft prospects (2010–2023).
              </p>
            </div>
          )}

          {noteLines.length > 0 && (
            <div className={hasComp ? 'border-t border-ui-border pt-3' : ''}>
              <div className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2">Notes</div>
              <div className="space-y-1 max-h-36 overflow-y-auto">
                {noteLines.map((line, i) => (
                  <p key={i} className="text-xs text-text-muted leading-relaxed">{line}</p>
                ))}
              </div>
            </div>
          )}

          {!hasComp && noteLines.length === 0 && (
            <p className="text-xs text-text-muted">No additional notes.</p>
          )}
        </div>

      </div>
    </div>
  );
}
