'use client';

import { TeamSeason } from '@/types';
import { TeamRanks } from '@/lib/rankings';
import { RankPill } from './StatCards';
import Link from 'next/link';

interface TeamHeaderProps {
  team: TeamSeason;
  ranks?: TeamRanks;
}

export default function TeamHeader({ team, ranks }: TeamHeaderProps) {
  return (
    <>
      {/* Back Link */}
      <Link 
        href="/rankings" 
        className="inline-flex items-center text-brand hover:text-brand-hover mb-6"
      >
        <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
        Back to Rankings
      </Link>
      
      {/* Team Header */}
      <div className="bg-ui-card border border-ui-border rounded-lg p-8 mb-8">
        <div className="flex items-start gap-6">
          {/* Logo */}
          <img 
            src={team.logoUrl}
            alt={team.teamName}
            className="w-24 h-24 object-contain"
            onError={(e) => {
              (e.target as HTMLImageElement).src = '/logos/default.png';
            }}
          />
          
          {/* Info */}
          <div className="flex-1">
            <div className="flex items-baseline gap-4 mb-2">
              <h1 className="text-4xl font-bold">{team.teamName}</h1>
              <span className="text-xl text-text-muted">{team.conference}</span>
            </div>
            
            <div className="flex items-center gap-6 text-lg flex-wrap">
              {team.record && (
                <div>
                  <span className="text-text-muted">Record:</span>{' '}
                  <span className="font-mono font-bold">{team.record}</span>
                </div>
              )}
              <div className="flex items-center gap-2">
                <span className="text-text-muted">Rank:</span>
                <span className="font-mono font-bold text-brand">#{team.rank}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-text-muted">AdjEM:</span>
                <span className="font-mono font-bold text-brand">
                  {team.adjEM.toFixed(2)}
                </span>
                {ranks && <RankPill rank={ranks.adjEM} />}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
