"use client";

import type { NBAPlayerSeasonStats } from "@/types/nba";
import { getBPRTier, fmtSigned } from "@/lib/bprTiers";
import { clsx } from "clsx";

interface Props {
  players: NBAPlayerSeasonStats[];
  className?: string;
}

interface CompareRow {
  key: keyof NBAPlayerSeasonStats;
  label: string;
  format?: (v: unknown) => string;
  higherIsBetter?: boolean;
}

const COMPARE_ROWS: CompareRow[] = [
  { key: "wins_added",                label: "Wins Added",       higherIsBetter: true },
  { key: "bpr_replacement_adjusted",  label: "BPR (repl adj)",  higherIsBetter: true },
  { key: "obpr_replacement_adjusted", label: "Off BPR (adj)",   higherIsBetter: true },
  { key: "dbpr_replacement_adjusted", label: "Def BPR (adj)",   higherIsBetter: true },
  { key: "bpr",                        label: "BPR (raw)",        higherIsBetter: true },
];

export function PlayerCompareView({ players, className }: Props) {
  if (!players.length) {
    return <div className="text-slate-500 font-mono text-sm p-6">No players to compare.</div>;
  }

  return (
    <div
      className={clsx(
        "bg-slate-900 border border-slate-700 rounded-xl overflow-x-auto font-mono",
        className,
      )}
    >
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-slate-700 bg-slate-800/60">
            <th className="px-4 py-3 text-left text-xs uppercase tracking-wider text-slate-500 w-36">
              Metric
            </th>
            {players.map((p) => (
              <th key={p.id} className="px-4 py-3 text-center">
                <div className="text-slate-100 font-semibold truncate max-w-[140px]">{p.player_name}</div>
                <div className="text-xs text-slate-500 font-normal mt-0.5">
                  {p.team_name} · {p.season_display}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {COMPARE_ROWS.map((row) => {
            const values = players.map((p) => {
              const v = p[row.key];
              return typeof v === "number" ? v : null;
            });
            const validValues = values.filter((v): v is number => v !== null);
            const best = validValues.length
              ? row.higherIsBetter !== false
                ? Math.max(...validValues)
                : Math.min(...validValues)
              : null;

            return (
              <tr key={row.key} className="hover:bg-slate-800/30 transition-colors">
                <td className="px-4 py-3 text-xs uppercase tracking-wider text-slate-500">
                  {row.label}
                </td>
                {players.map((p, i) => {
                  const v = values[i];
                  const isBest = v !== null && v === best && validValues.length > 1;
                  const tier = row.key === "wins_added" ? getBPRTier(v) : null;
                  return (
                    <td key={p.id} className="px-4 py-3 text-center">
                      <span
                        className={clsx(
                          "tabular-nums font-semibold text-base",
                          tier ? tier.color : isBest ? "text-emerald-400" : "text-slate-300",
                        )}
                      >
                        {v !== null ? fmtSigned(v, 2) : "—"}
                      </span>
                      {isBest && (
                        <span className="ml-1 text-xs text-emerald-500">▲</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}

          {/* Tier row */}
          <tr className="bg-slate-800/20">
            <td className="px-4 py-3 text-xs uppercase tracking-wider text-slate-500">Tier</td>
            {players.map((p) => {
              const tier = getBPRTier(p.wins_added);
              return (
                <td key={p.id} className="px-4 py-3 text-center">
                  <span
                    className={clsx(
                      "text-xs px-2 py-0.5 rounded-md",
                      tier.bgColor,
                      tier.color,
                    )}
                  >
                    {tier.label}
                  </span>
                </td>
              );
            })}
          </tr>

          {/* Playing time */}
          <tr className="border-t border-slate-700">
            <td className="px-4 py-3 text-xs uppercase tracking-wider text-slate-500">Minutes</td>
            {players.map((p) => (
              <td key={p.id} className="px-4 py-3 text-center text-slate-400 text-xs">
                {p.gp ?? "—"} GP · {p.mpg?.toFixed(1) ?? "—"} MPG
              </td>
            ))}
          </tr>
        </tbody>
      </table>

      <div className="px-4 py-2 text-xs text-slate-700 border-t border-slate-800">
        BPR adj = stored BPR + 2.0 (replacement offset) · ▲ = leads category
      </div>
    </div>
  );
}
