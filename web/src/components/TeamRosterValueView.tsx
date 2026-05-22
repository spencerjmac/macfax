"use client";

import type { NBAPlayerSeasonStats } from "@/types/nba";
import { getBPRTier, fmtSigned } from "@/lib/bprTiers";
import { clsx } from "clsx";
import Link from "next/link";

interface Props {
  teamName: string;
  teamSlug?: string;
  seasonDisplay?: string;
  totalWinsAdded: number;
  players: NBAPlayerSeasonStats[];
  className?: string;
}

export function TeamRosterValueView({
  teamName,
  teamSlug,
  seasonDisplay,
  totalWinsAdded,
  players,
  className,
}: Props) {
  // Sort descending by wins_added, nulls last
  const sorted = [...players].sort(
    (a, b) => (b.wins_added ?? -Infinity) - (a.wins_added ?? -Infinity),
  );

  // Max wins_added for bar scaling
  const maxWins = Math.max(...sorted.map((p) => Math.abs(p.wins_added ?? 0)), 1);

  return (
    <div
      className={clsx(
        "bg-slate-900 border border-slate-700 rounded-xl overflow-hidden font-mono",
        className,
      )}
    >
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-700 bg-slate-800/60">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs uppercase tracking-widest text-slate-500 mb-0.5">
              Roster Value {seasonDisplay && `· ${seasonDisplay}`}
            </div>
            <h2 className="text-slate-100 text-lg font-semibold">
              {teamSlug ? (
                <Link href={`/nba/team/${teamSlug}`} className="hover:text-teal-400 transition-colors">
                  {teamName}
                </Link>
              ) : (
                teamName
              )}
            </h2>
          </div>
          <div className="text-right">
            <div className="text-xs text-slate-500 uppercase tracking-wider mb-0.5">Total wins added</div>
            <div
              className={clsx(
                "text-3xl font-bold tabular-nums",
                getBPRTier(totalWinsAdded / Math.max(players.length, 1)).color,
              )}
            >
              {fmtSigned(totalWinsAdded, 1)}
            </div>
          </div>
        </div>
      </div>

      {/* Player rows */}
      <div className="divide-y divide-slate-800">
        {sorted.map((player) => {
          const tier = getBPRTier(player.wins_added);
          const barWidth =
            player.wins_added != null
              ? Math.min(100, Math.abs(player.wins_added / maxWins) * 100)
              : 0;
          const isNegative = (player.wins_added ?? 0) < 0;

          return (
            <div key={player.id} className="flex items-center gap-3 px-5 py-3 hover:bg-slate-800/40 transition-colors">
              {/* Name */}
              <div className="w-40 flex-shrink-0">
                <span className="text-sm text-slate-200 truncate block">{player.player_name}</span>
                <span className="text-xs text-slate-600">{player.mpg?.toFixed(0) ?? "—"} MPG · {player.gp ?? "—"} GP</span>
              </div>

              {/* Bar */}
              <div className="flex-1 relative h-4 bg-slate-800 rounded-sm overflow-hidden">
                <div
                  className={clsx("absolute top-0 h-full rounded-sm transition-all", tier.barColor)}
                  style={{
                    width: `${barWidth}%`,
                    left: isNegative ? `${100 - barWidth}%` : 0,
                  }}
                />
              </div>

              {/* Value */}
              <div className={clsx("w-16 text-right text-sm font-semibold tabular-nums", tier.color)}>
                {fmtSigned(player.wins_added, 1)}
              </div>

              {/* BPR adj */}
              <div className="w-16 text-right text-xs text-slate-500 tabular-nums">
                {fmtSigned(player.bpr_replacement_adjusted, 1)} BPR
              </div>
            </div>
          );
        })}
      </div>

      <div className="px-5 py-2 text-xs text-slate-600 border-t border-slate-800">
        Wins added = (BPR + 2.0) × MPG/48 × GP/56 · Replacement level = BPR −2.0
      </div>
    </div>
  );
}
