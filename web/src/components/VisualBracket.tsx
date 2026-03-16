'use client';

/**
 * VisualBracket — Interactive NCAA Tournament bracket.
 *
 * Layout approach:
 *   Each half has 16 matchups total (8 per region × 2 regions stacked).
 *   We use a fixed BAND_H per matchup slot so every round column has
 *   the same pixel height and matchups align perfectly via band centering.
 *
 * Column order:
 *   LEFT  side: R64 → R32 → S16 → E8   (East top, South bottom)
 *   CENTER:     Final Four + Championship
 *   RIGHT side: E8 → S16 → R32 → R64   (West top, Midwest bottom)
 */

import { useMemo, useState } from 'react';
import Link from 'next/link';
import type { BracketData, BracketTeamData, TeamRoundProbs } from '@/types';

// ─── layout constants ─────────────────────────────────────────────────────
const SLOT_H   = 34;              // px per team row
const BAND_H   = SLOT_H * 2 + 16; // px per matchup band (2 teams + breathing room)
const COL_W    = 152;             // px per round column
const COL_GAP  = 10;              // px between columns (connector lives here)
const HEADER_H = 26;              // px for round label above each column
const N_MATCHUPS_PER_SIDE = 16;   // 8 matchups × 2 regions per combined column
const TOTAL_H  = N_MATCHUPS_PER_SIDE * BAND_H;  // total column height

type Round = 'R64' | 'R32' | 'S16' | 'E8' | 'FF' | 'Championship';

// ─── data types ───────────────────────────────────────────────────────────

interface SlotTeam {
  team:  BracketTeamData;
  probs: TeamRoundProbs;
}

interface Matchup {
  top:             SlotTeam | null;
  bottom:          SlotTeam | null;
  predictedWinner: SlotTeam | null;
}

// ─── helpers ─────────────────────────────────────────────────────────────

function pct(p: number | undefined): string {
  if (p === undefined || p === null) return '—';
  if (p >= 0.995) return '>99%';
  if (p < 0.005)  return '<1%';
  return `${Math.round(p * 100)}%`;
}

const WIN_PROB_KEY: Record<Round, keyof TeamRoundProbs | null> = {
  R64:          'p_r32',
  R32:          'p_s16',
  S16:          'p_e8',
  E8:           'p_ff',
  FF:           'p_final',
  Championship: 'p_champion',
};

function chipStyle(p: number): string {
  if (p >= 0.60) return 'bg-emerald-500 text-white';
  if (p >= 0.40) return 'bg-emerald-100 text-emerald-800';
  if (p >= 0.25) return 'bg-blue-100 text-blue-800';
  if (p >= 0.10) return 'bg-slate-100 text-slate-600';
  return 'bg-slate-50 text-slate-400';
}

// ─── build matchup trees ─────────────────────────────────────────────────

const SEED_PAIRS: [number, number][] = [
  [1, 16], [8, 9],
  [5, 12], [4, 13],
  [6, 11], [3, 14],
  [7, 10], [2, 15],
];

function buildRegionMatchups(
  regionSlots: BracketData['regions']['East'],
  probs: Record<string, TeamRoundProbs>,
): Record<Round, Matchup[]> {
  const bySlot: Record<number, BracketTeamData[]> = {};
  for (const slot of regionSlots) bySlot[slot.seed] = slot.teams;

  function resolveFirstFour(seed: number): BracketTeamData | null {
    const t = bySlot[seed] ?? [];
    if (!t.length) return null;
    if (t.length === 1) return t[0];
    return (probs[t[0].slug]?.p_r32 ?? 0) >= (probs[t[1].slug]?.p_r32 ?? 0) ? t[0] : t[1];
  }

  function toSlot(t: BracketTeamData | null): SlotTeam | null {
    if (!t) return null;
    return { team: t, probs: probs[t.slug] ?? ({} as TeamRoundProbs) };
  }

  const r64Teams: (BracketTeamData | null)[] = [];
  for (const [hi, lo] of SEED_PAIRS) {
    r64Teams.push(resolveFirstFour(hi));
    r64Teams.push(resolveFirstFour(lo));
  }

  const r64: Matchup[] = [];
  for (let i = 0; i < r64Teams.length; i += 2) {
    const top = toSlot(r64Teams[i]);
    const btm = toSlot(r64Teams[i + 1]);
    r64.push({ top, bottom: btm, predictedWinner: (top?.probs.p_r32 ?? 0) >= (btm?.probs.p_r32 ?? 0) ? top : btm });
  }

  function advance(prev: Matchup[], wk: keyof TeamRoundProbs): Matchup[] {
    const next: Matchup[] = [];
    for (let i = 0; i < prev.length; i += 2) {
      const a = toSlot(prev[i]?.predictedWinner?.team ?? null);
      const b = toSlot(prev[i + 1]?.predictedWinner?.team ?? null);
      next.push({ top: a, bottom: b, predictedWinner: (a?.probs[wk] ?? 0) >= (b?.probs[wk] ?? 0) ? a : b });
    }
    return next;
  }

  const r32 = advance(r64, 'p_s16');
  const s16 = advance(r32, 'p_e8');
  const e8  = advance(s16, 'p_ff');
  return { R64: r64, R32: r32, S16: s16, E8: e8, FF: [], Championship: [] };
}

// ─── TeamCell ────────────────────────────────────────────────────────────

function TeamCell({
  slot, round, isWinner, tooltipRight = false,
}: {
  slot: SlotTeam | null; round: Round; isWinner: boolean; tooltipRight?: boolean;
}) {
  const [show, setShow] = useState(false);

  if (!slot) {
    return (
      <div style={{ height: SLOT_H }} className="flex items-center justify-center border border-dashed border-gray-200 rounded-md bg-gray-50/80 text-[10px] text-gray-300">
        TBD
      </div>
    );
  }

  const { team, probs } = slot;
  const winKey = WIN_PROB_KEY[round];
  const winP   = winKey ? (probs[winKey] as number) : undefined;

  return (
    <div className="relative" style={{ height: SLOT_H }}>
      <Link
        href={`/teams/${team.slug}`}
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        className={[
          'flex items-center gap-1.5 px-2 rounded-md border transition-all duration-100 h-full w-full overflow-hidden',
          isWinner
            ? 'border-primary bg-primary/10 shadow-sm ring-1 ring-primary/20'
            : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm',
        ].join(' ')}
      >
        {/* Seed badge */}
        <span className={[
          'shrink-0 w-[18px] h-[18px] flex items-center justify-center rounded text-[9px] font-bold',
          isWinner ? 'bg-primary text-white' : 'bg-gray-100 text-gray-500',
        ].join(' ')}>
          {team.seed}
        </span>

        {/* Name */}
        <span className={[
          'flex-1 truncate text-[11px] leading-tight',
          isWinner ? 'font-semibold text-gray-900' : 'text-gray-700',
        ].join(' ')}>
          {team.name}
        </span>

        {/* Win-probability chip */}
        {winP !== undefined && winP > 0.005 && (
          <span className={`shrink-0 text-[9px] font-bold px-1 py-px rounded ${chipStyle(winP)}`}>
            {pct(winP)}
          </span>
        )}
      </Link>

      {/* Hover tooltip */}
      {show && (
        <div className={[
          'absolute bottom-full mb-1 z-[200] w-52 bg-gray-950 text-white rounded-xl p-3 shadow-2xl text-[11px] pointer-events-none border border-gray-800',
          tooltipRight ? 'right-0' : 'left-0',
        ].join(' ')}>
          <div className="font-bold text-sm mb-2 truncate">{team.name}</div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 mb-2 text-[10px]">
            <span className="text-gray-400">Seed</span>       <span className="text-right">{team.seed} · {team.region}</span>
            <span className="text-gray-400">Record</span>     <span className="text-right">{team.record}</span>
            <span className="text-gray-400">AdjEM</span>
            <span className={`text-right font-semibold ${team.adj_em > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {team.adj_em > 0 ? '+' : ''}{team.adj_em.toFixed(1)}
            </span>
          </div>
          <div className="border-t border-gray-800 pt-2 grid grid-cols-2 gap-x-4 gap-y-0.5 text-[10px]">
            <span className="text-gray-400">P(S16)</span>      <span className="text-right">{pct(probs.p_s16)}</span>
            <span className="text-gray-400">P(E8)</span>       <span className="text-right">{pct(probs.p_e8)}</span>
            <span className="text-gray-400">P(Final Four)</span> <span className="text-right text-purple-300">{pct(probs.p_ff)}</span>
            <span className="text-gray-400">P(Final)</span>    <span className="text-right">{pct(probs.p_final)}</span>
            <span className="text-gray-400">P(Champion)</span> <span className="text-right text-yellow-300 font-bold">{pct(probs.p_champion)}</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── MatchupBlock — two cells in a bordered card ─────────────────────────

function MatchupBlock({ matchup, round, tooltipRight }: {
  matchup: Matchup; round: Round; tooltipRight?: boolean;
}) {
  const isTop = matchup.predictedWinner?.team.slug === matchup.top?.team.slug;
  const isBtm = matchup.predictedWinner?.team.slug === matchup.bottom?.team.slug;
  // Note: no overflow-hidden so tooltips can escape above the card
  return (
    <div className="rounded-lg border border-gray-200 shadow-sm bg-white" style={{ height: SLOT_H * 2 + 1 }}>
      <TeamCell slot={matchup.top}    round={round} isWinner={isTop} tooltipRight={tooltipRight} />
      <div className="border-t border-gray-100" style={{ height: 1 }} />
      <TeamCell slot={matchup.bottom} round={round} isWinner={isBtm} tooltipRight={tooltipRight} />
    </div>
  );
}

// ─── RoundColumn — positions N matchups evenly in TOTAL_H ────────────────

function RoundColumn({ matchups, round, label, tooltipRight = false }: {
  matchups: Matchup[]; round: Round; label: string; tooltipRight?: boolean;
}) {
  const n      = matchups.length;
  const matchupH = SLOT_H * 2 + 1;  // actual rendered height
  const bandH  = TOTAL_H / n;

  return (
    <div className="flex-shrink-0 flex flex-col" style={{ width: COL_W }}>
      {/* Round label */}
      <div
        className="flex items-center justify-center text-[10px] font-bold uppercase tracking-widest text-gray-400"
        style={{ height: HEADER_H }}
      >
        {label}
      </div>
      {/* Matchup blocks, absolutely positioned within a fixed-height container */}
      <div className="relative" style={{ height: TOTAL_H }}>
        {matchups.map((m, i) => {
          const topPx = i * bandH + (bandH - matchupH) / 2;
          return (
            <div
              key={i}
              className="absolute left-0 right-0"
              style={{ top: Math.round(topPx), height: matchupH }}
            >
              <MatchupBlock matchup={m} round={round} tooltipRight={tooltipRight} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── ConnectorSVG — bracket lines between adjacent columns ───────────────

function ConnectorSVG({ fromN, toN, direction }: {
  fromN: number; toN: number; direction: 'right' | 'left';
}) {
  const fromBH = TOTAL_H / fromN;
  const toBH   = TOTAL_H / toN;
  const W      = COL_GAP;
  const isR    = direction === 'right';

  const lines: { yA: number; yB: number; yT: number }[] = [];
  for (let ti = 0; ti < toN; ti++) {
    const matchupH = SLOT_H * 2 + 1;
    const yA = (ti * 2)     * fromBH + fromBH / 2;
    const yB = (ti * 2 + 1) * fromBH + fromBH / 2;
    const yT = ti            * toBH   + toBH   / 2;
    lines.push({ yA, yB, yT });
  }

  const x1 = isR ? 0 : W;
  const x2 = isR ? W : 0;
  const mx  = W / 2;

  return (
    <svg
      className="flex-shrink-0"
      width={W}
      height={TOTAL_H + HEADER_H}
      style={{ overflow: 'visible', marginTop: 0 }}
    >
      <g transform={`translate(0,${HEADER_H})`}>
        {lines.map(({ yA, yB, yT }, i) => (
          <g key={i}>
            <line x1={x1} y1={yA} x2={mx} y2={yA} stroke="#d1d5db" strokeWidth={1} />
            <line x1={x1} y1={yB} x2={mx} y2={yB} stroke="#d1d5db" strokeWidth={1} />
            <line x1={mx} y1={yA} x2={mx} y2={yB} stroke="#d1d5db" strokeWidth={1} />
            <line x1={mx} y1={yT} x2={x2} y2={yT} stroke="#d1d5db" strokeWidth={1} />
          </g>
        ))}
      </g>
    </svg>
  );
}

// ─── CenterColumn ────────────────────────────────────────────────────────
// Shows: Semifinal 1 → National Championship game → Semifinal 2
// All three are rendered as proper MatchupBlocks so the full title game is visible.

function CenterColumn({ ff0A, ff0B, ff1A, ff1B }: {
  ff0A: SlotTeam | null; ff0B: SlotTeam | null;
  ff1A: SlotTeam | null; ff1B: SlotTeam | null;
}) {
  const CW       = 204;
  const SIDE     = 12;   // horizontal padding
  const matchupH = SLOT_H * 2 + 1;
  const labelH   = 18;   // height of each section label
  const lineH    = 22;   // vertical connector gap between blocks

  // Semifinal matchups
  const sf1: Matchup = {
    top: ff0A, bottom: ff0B,
    predictedWinner: (ff0A?.probs.p_champion ?? 0) >= (ff0B?.probs.p_champion ?? 0) ? ff0A : ff0B,
  };
  const sf2: Matchup = {
    top: ff1A, bottom: ff1B,
    predictedWinner: (ff1A?.probs.p_champion ?? 0) >= (ff1B?.probs.p_champion ?? 0) ? ff1A : ff1B,
  };

  // Championship game: winner of sf1 (top) vs winner of sf2 (bottom)
  const champMatchup: Matchup = {
    top:    sf1.predictedWinner,
    bottom: sf2.predictedWinner,
    predictedWinner:
      (sf1.predictedWinner?.probs.p_champion ?? 0) >= (sf2.predictedWinner?.probs.p_champion ?? 0)
        ? sf1.predictedWinner
        : sf2.predictedWinner,
  };

  // Total inner content height: label + matchup + line + label + matchup + line + label + matchup
  const innerH = (labelH + matchupH) * 3 + lineH * 2;
  const startY = Math.max(0, Math.round((TOTAL_H - innerH) / 2));

  // Absolute top of each section
  const sf1Top   = startY;
  const champSectionTop = startY + labelH + matchupH + lineH;
  const sf2Top   = champSectionTop + labelH + matchupH + lineH;

  // Vertical mid-point of each matchup block (for connector lines)
  const sf1MidY  = sf1Top  + labelH + matchupH / 2;
  const champMidY = champSectionTop + labelH + matchupH / 2;
  const sf2MidY  = sf2Top  + labelH + matchupH / 2;

  return (
    <div className="flex-shrink-0 flex flex-col" style={{ width: CW }}>
      {/* Column header */}
      <div
        className="flex items-center justify-center text-[10px] font-bold uppercase tracking-widest text-gray-400"
        style={{ height: HEADER_H }}
      >
        Final Four
      </div>

      <div className="relative" style={{ height: TOTAL_H }}>
        {/* SVG connector lines */}
        <svg
          className="absolute inset-0 pointer-events-none"
          width={CW} height={TOTAL_H}
          style={{ overflow: 'visible' }}
        >
          {/* Left edge stubs into sf1 (from E8 left side) */}
          <line x1={0} y1={sf1MidY - SLOT_H / 2} x2={SIDE - 2} y2={sf1MidY - SLOT_H / 2} stroke="#d1d5db" strokeWidth={1} />
          <line x1={0} y1={sf1MidY + SLOT_H / 2} x2={SIDE - 2} y2={sf1MidY + SLOT_H / 2} stroke="#d1d5db" strokeWidth={1} />
          {/* Right edge stubs into sf2 (from E8 right side) */}
          <line x1={CW} y1={sf2MidY - SLOT_H / 2} x2={CW - SIDE + 2} y2={sf2MidY - SLOT_H / 2} stroke="#d1d5db" strokeWidth={1} />
          <line x1={CW} y1={sf2MidY + SLOT_H / 2} x2={CW - SIDE + 2} y2={sf2MidY + SLOT_H / 2} stroke="#d1d5db" strokeWidth={1} />
          {/* sf1 winner → top of championship matchup */}
          <line x1={CW / 2} y1={sf1MidY  + matchupH / 2 + 2} x2={CW / 2} y2={champMidY - matchupH / 2 - 2} stroke="#fbbf24" strokeWidth={1.5} strokeDasharray="3 2" />
          {/* sf2 winner → bottom of championship matchup */}
          <line x1={CW / 2} y1={champMidY + matchupH / 2 + 2} x2={CW / 2} y2={sf2MidY  - matchupH / 2 - 2} stroke="#fbbf24" strokeWidth={1.5} strokeDasharray="3 2" />
        </svg>

        {/* ── Semifinal 1: East vs South ── */}
        <div className="absolute" style={{ top: sf1Top, left: SIDE, right: SIDE }}>
          <div className="text-[9px] font-bold text-gray-400 uppercase tracking-widest text-center mb-1">
            Semifinal · East vs South
          </div>
          <MatchupBlock matchup={sf1} round="FF" tooltipRight={false} />
        </div>

        {/* ── National Championship ── */}
        <div className="absolute" style={{ top: champSectionTop, left: SIDE, right: SIDE }}>
          <div className="text-[9px] font-bold text-yellow-500 uppercase tracking-widest text-center mb-1">
            🏆 National Championship
          </div>
          {/* Gold ring wrapper to distinguish from semis */}
          <div className="rounded-lg ring-2 ring-yellow-400 shadow-lg">
            <MatchupBlock matchup={champMatchup} round="Championship" tooltipRight={false} />
          </div>
        </div>

        {/* ── Semifinal 2: West vs Midwest ── */}
        <div className="absolute" style={{ top: sf2Top, left: SIDE, right: SIDE }}>
          <div className="text-[9px] font-bold text-gray-400 uppercase tracking-widest text-center mb-1">
            Semifinal · West vs Midwest
          </div>
          <MatchupBlock matchup={sf2} round="FF" tooltipRight={true} />
        </div>
      </div>
    </div>
  );
}

// ─── Main export ─────────────────────────────────────────────────────────

export default function VisualBracket({ data }: { data: BracketData }) {
  const { regions, probabilities, ff_pairings } = data;

  const em = useMemo(() => {
    const out: Partial<Record<string, ReturnType<typeof buildRegionMatchups>>> = {};
    for (const r of ['East', 'West', 'South', 'Midwest']) {
      const slots = regions[r as keyof typeof regions];
      if (slots) out[r] = buildRegionMatchups(slots, probabilities);
    }
    return out;
  }, [regions, probabilities]);

  if (!em.East || !em.West || !em.South || !em.Midwest) {
    return <div className="text-gray-400 text-sm p-8">Bracket data unavailable.</div>;
  }

  const [ffL_A, ffL_B] = ff_pairings[0] ?? ['East', 'South'];
  const [ffR_A, ffR_B] = ff_pairings[1] ?? ['West', 'Midwest'];

  const ff0A = em[ffL_A]?.E8[0]?.predictedWinner ?? null;
  const ff0B = em[ffL_B]?.E8[0]?.predictedWinner ?? null;
  const ff1A = em[ffR_A]?.E8[0]?.predictedWinner ?? null;
  const ff1B = em[ffR_B]?.E8[0]?.predictedWinner ?? null;

  function best(a: SlotTeam | null, b: SlotTeam | null): SlotTeam | null {
    if (!a) return b; if (!b) return a;
    return (a.probs.p_champion ?? 0) >= (b.probs.p_champion ?? 0) ? a : b;
  }
  // Combined matchup arrays per round for connector rendering
  const L = {
    R64: [...em.East.R64, ...em.South.R64],
    R32: [...em.East.R32, ...em.South.R32],
    S16: [...em.East.S16, ...em.South.S16],
    E8:  [...em.East.E8,  ...em.South.E8],
  };
  const R = {
    R64: [...em.West.R64, ...em.Midwest.R64],
    R32: [...em.West.R32, ...em.Midwest.R32],
    S16: [...em.West.S16, ...em.Midwest.S16],
    E8:  [...em.West.E8,  ...em.Midwest.E8],
  };

  function lcol(round: keyof typeof L, ci: number) {
    const combined = L[round];
    const labels: Record<number, string> = { 0: 'East', 1: 'R32', 2: 'S16', 3: 'South' };
    return (
      <RoundColumn
        key={`L-${round}`}
        matchups={combined}
        round={round as Round}
        label={labels[ci]}
        tooltipRight={false}
      />
    );
  }

  function rcol(round: keyof typeof R, ci: number) {
    const combined = R[round];
    const labels: Record<number, string> = { 0: 'West', 1: 'S16', 2: 'R32', 3: 'Midwest' };
    return (
      <RoundColumn
        key={`R-${round}`}
        matchups={combined}
        round={round as Round}
        label={labels[ci]}
        tooltipRight={true}
      />
    );
  }

  return (
    <div className="overflow-x-auto pb-6">
      <div className="inline-flex flex-col min-w-0">

        {/* Legend row */}
        <div className="flex items-center gap-5 mb-5 text-[11px] text-gray-500 flex-wrap">
          <div className="flex items-center gap-1.5">
            <span className="w-4 h-4 rounded border-2 border-primary bg-primary/10 inline-block shrink-0" />
            <span>Predicted winner</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="px-1.5 py-0.5 rounded bg-emerald-500 text-white text-[9px] font-bold">63%</span>
            <span>% chance to win that game</span>
          </div>
          <div className="text-gray-400 italic">Hover any team for full probability breakdown</div>
        </div>

        {/* Region header labels */}
        <div className="flex items-end mb-2" style={{ gap: 0 }}>
          <div className="text-xs font-bold text-gray-600 uppercase tracking-wider" style={{ width: COL_W }}>← East Region</div>
          <div style={{ width: COL_GAP * 3 + COL_W * 2 }} />
          <div className="text-xs font-bold text-gray-500 uppercase tracking-wider text-center flex-shrink-0" style={{ width: COL_W }}>E8 / FF</div>
          <div style={{ width: 162 + COL_GAP * 2 }} />
          <div className="text-xs font-bold text-gray-500 uppercase tracking-wider text-center flex-shrink-0" style={{ width: COL_W }}>E8 / FF</div>
          <div style={{ width: COL_GAP * 3 + COL_W * 2 }} />
          <div className="text-xs font-bold text-gray-600 uppercase tracking-wider text-right" style={{ width: COL_W }}>West Region →</div>
        </div>

        {/* Bracket */}
        <div className="flex items-start" style={{ gap: 0 }}>
          {/* LEFT SIDE */}
          {lcol('R64', 0)}
          <ConnectorSVG fromN={L.R64.length} toN={L.R32.length} direction="right" />
          {lcol('R32', 1)}
          <ConnectorSVG fromN={L.R32.length} toN={L.S16.length} direction="right" />
          {lcol('S16', 2)}
          <ConnectorSVG fromN={L.S16.length} toN={L.E8.length}  direction="right" />
          {lcol('E8',  3)}

          {/* Gap before center */}
          <div style={{ width: COL_GAP * 2 }} />

          {/* CENTER */}
          <CenterColumn ff0A={ff0A} ff0B={ff0B} ff1A={ff1A} ff1B={ff1B} />

          {/* Gap after center */}
          <div style={{ width: COL_GAP * 2 }} />

          {/* RIGHT SIDE */}
          {rcol('E8',  0)}
          <ConnectorSVG fromN={R.E8.length}  toN={R.S16.length} direction="left" />
          {rcol('S16', 1)}
          <ConnectorSVG fromN={R.S16.length} toN={R.R32.length} direction="left" />
          {rcol('R32', 2)}
          <ConnectorSVG fromN={R.R32.length} toN={R.R64.length} direction="left" />
          {rcol('R64', 3)}
        </div>

        {/* South / Midwest labels at bottom */}
        <div className="flex items-start mt-1" style={{ gap: 0 }}>
          <div style={{ width: COL_W }} />
          <div style={{ width: COL_GAP }} />
          <div style={{ width: COL_W + COL_GAP + COL_W + COL_GAP }} />
          <div className="text-xs font-bold text-gray-600 uppercase tracking-wider" style={{ width: COL_W }}>← South Region</div>
          <div style={{ width: COL_GAP * 2 + 162 + COL_GAP * 2 }} />
          <div className="text-xs font-bold text-gray-600 uppercase tracking-wider text-right" style={{ width: COL_W }}>Midwest Region →</div>
        </div>
      </div>
    </div>
  );
}
