'use client';

import { TeamSeason } from '@/types';
import Link from 'next/link';
import { ChevronLeft } from 'lucide-react';

interface TeamHeaderProps {
  team: TeamSeason;
}

export default function TeamHeader({ team }: TeamHeaderProps) {
  const fmtEM = (v: number) => (v > 0 ? '+' : '') + v.toFixed(2);

  return (
    <header className="bg-ink text-white relative overflow-hidden">
      {/* teal glow */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{ background: 'radial-gradient(700px 300px at 92% -20%, rgba(64,144,128,0.18), transparent 60%)' }}
      />
      <div className="max-w-[1240px] mx-auto px-8 pt-[30px] relative">
        {/* back */}
        <Link
          href="/ncaa/rankings"
          className="inline-flex items-center gap-[7px] text-ink-fg2 hover:text-brand2 font-semibold text-[13px] pb-[22px] transition-colors"
        >
          <ChevronLeft className="w-4 h-4" strokeWidth={1.5} />
          Back to rankings
        </Link>

        {/* header row */}
        <div className="flex items-center gap-6 pb-[26px]">
          {/* logo — white tile so dark logos are visible */}
          {team.logoUrl ? (
            <img
              src={team.logoUrl}
              alt={team.teamName}
              className="w-[84px] h-[84px] object-contain bg-white rounded-[16px] p-[11px] shadow-[0_6px_18px_rgba(0,0,0,0.3)] shrink-0"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
            />
          ) : (
            <div className="w-[84px] h-[84px] bg-white rounded-[16px] flex items-center justify-center text-2xl font-bold text-ink shrink-0">
              {team.teamName.charAt(0)}
            </div>
          )}

          {/* identity */}
          <div className="flex-1 min-w-0">
            <div className="font-mono font-bold text-[12px] text-brand2 tracking-[0.1em] uppercase mb-[9px] inline-flex items-center gap-2">
              No. {team.rank}
              <span className="text-ink-fg2 font-normal">· {team.conference}</span>
            </div>
            <h1 className="font-display font-bold text-[clamp(38px,5vw,60px)] leading-[0.95] uppercase tracking-[0.005em] m-0 text-white">
              {team.teamName}
            </h1>
            <div className="font-sans text-[14px] text-ink-fg mt-[10px] flex gap-[18px] flex-wrap">
              {team.record && (
                <span>Record <b className="text-white font-mono font-semibold">{team.record}</b></span>
              )}
              {team.adjTempo != null && (
                <span>Tempo <b className="text-white font-mono font-semibold">{team.adjTempo.toFixed(1)}</b></span>
              )}
              <span>Off <b className="text-white font-mono font-semibold">{team.adjO.toFixed(1)}</b></span>
              <span>Def <b className="text-white font-mono font-semibold">{team.adjD.toFixed(1)}</b></span>
            </div>
          </div>

          {/* AdjEM hero stat */}
          <div className="shrink-0 text-right">
            <span className="block font-sans font-semibold text-[11px] tracking-[0.08em] uppercase text-ink-fg2 mb-2">
              Adj. Efficiency Margin
            </span>
            <span className="font-mono font-bold text-[46px] leading-none text-brand2">
              {fmtEM(team.adjEM)}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}
