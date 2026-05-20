'use client';

import clsx from 'clsx';
import type { FourFactorsTeam, GameTeamRef } from '@/types/games';

interface Props {
  fourFactors: { home: FourFactorsTeam; away: FourFactorsTeam };
  homeTeam: GameTeamRef;
  awayTeam: GameTeamRef;
}

interface Factor {
  key: keyof FourFactorsTeam;
  label: string;
  desc: string;
  fmt: (v: number | null) => string;
  higherBetter: boolean;
}

const FACTORS: Factor[] = [
  {
    key: 'efg_pct',
    label: 'eFG%',
    desc: 'Effective Field Goal %',
    fmt: (v) => (v != null ? `${v.toFixed(1)}%` : '—'),
    higherBetter: true,
  },
  {
    key: 'tov_pct',
    label: 'TOV%',
    desc: 'Turnover Rate (lower = better)',
    fmt: (v) => (v != null ? `${v.toFixed(1)}%` : '—'),
    higherBetter: false,
  },
  {
    key: 'orb_pct',
    label: 'ORB%',
    desc: 'Offensive Rebound %',
    fmt: (v) => (v != null ? `${v.toFixed(1)}%` : '—'),
    higherBetter: true,
  },
  {
    key: 'ftr',
    label: 'FTR',
    desc: 'Free Throw Rate (FTA / FGA)',
    fmt: (v) => (v != null ? v.toFixed(1) : '—'),
    higherBetter: true,
  },
];

export default function FourFactorsTab({ fourFactors, homeTeam, awayTeam }: Props) {
  return (
    <div className="overflow-hidden rounded-xl border border-ui-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-ui-border bg-ui-surface">
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-text-muted">
              Factor
            </th>
            <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-text-muted">
              {awayTeam.abbr} (away)
            </th>
            <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-text-muted">
              Edge
            </th>
            <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-text-muted">
              {homeTeam.abbr} (home)
            </th>
          </tr>
        </thead>
        <tbody>
          {FACTORS.map(({ key, label, desc, fmt, higherBetter }) => {
            const hVal = fourFactors.home[key];
            const aVal = fourFactors.away[key];

            const homeWins =
              hVal != null &&
              aVal != null &&
              (higherBetter ? hVal > aVal : hVal < aVal);
            const awayWins =
              hVal != null &&
              aVal != null &&
              (higherBetter ? aVal > hVal : aVal < hVal);

            // Edge: positive means home is better (for higher-better factors)
            let edgeStr = '—';
            if (hVal != null && aVal != null) {
              const diff = higherBetter ? hVal - aVal : aVal - hVal;
              edgeStr = `${diff >= 0 ? '+' : ''}${diff.toFixed(1)}`;
            }

            return (
              <tr key={key} className="border-b border-ui-border/50 last:border-0">
                <td className="px-4 py-3">
                  <div className="font-medium text-text-primary">{label}</div>
                  <div className="text-xs text-text-muted">{desc}</div>
                </td>
                <td
                  className={clsx(
                    'px-4 py-3 text-center font-mono',
                    awayWins
                      ? 'font-bold text-emerald-400'
                      : homeWins
                      ? 'text-text-muted'
                      : 'text-text-secondary'
                  )}
                >
                  {fmt(aVal)}
                </td>
                <td className="px-4 py-3 text-center">
                  {hVal != null && aVal != null ? (
                    <span
                      className={clsx(
                        'text-xs font-semibold',
                        hVal - aVal === 0
                          ? 'text-text-muted'
                          : homeWins
                          ? 'text-blue-400'
                          : 'text-rose-400'
                      )}
                    >
                      {edgeStr}
                    </span>
                  ) : (
                    <span className="text-text-muted">—</span>
                  )}
                </td>
                <td
                  className={clsx(
                    'px-4 py-3 text-center font-mono',
                    homeWins
                      ? 'font-bold text-emerald-400'
                      : awayWins
                      ? 'text-text-muted'
                      : 'text-text-secondary'
                  )}
                >
                  {fmt(hVal)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="border-t border-ui-border bg-ui-surface px-4 py-2 text-[11px] text-text-muted">
        Edge = home minus away (positive favors home). Four Factors framework by Dean Oliver.
      </div>
    </div>
  );
}
