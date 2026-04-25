'use client';

import { useMemo, useRef } from 'react';
import { useRouter } from 'next/navigation';
import ReactECharts from 'echarts-for-react';
import type { NBATeamSeasonRatings } from '@/types/nba';

interface NBAEfficiencyLandscapeProps {
  data: NBATeamSeasonRatings[];
  seasonDisplay?: string;
}

export default function NBAEfficiencyLandscape({ data, seasonDisplay }: NBAEfficiencyLandscapeProps) {
  const router = useRouter();
  const chartRef = useRef<ReactECharts | null>(null);

  const { eastTeams, westTeams, avgAdj } = useMemo(() => {
    const valid = data.filter((t) => t.adj_off != null && t.adj_def != null);
    const eastTeams = valid.filter((t) => t.team_conference === 'East');
    const westTeams = valid.filter((t) => t.team_conference === 'West');

    const offValues = valid.map((t) => t.adj_off!);
    const defValues = valid.map((t) => t.adj_def!);
    const avgOff = offValues.length ? offValues.reduce((a, b) => a + b, 0) / offValues.length : 115;
    const avgDef = defValues.length ? defValues.reduce((a, b) => a + b, 0) / defValues.length : 115;

    return { eastTeams, westTeams, avgAdj: { off: avgOff, def: avgDef } };
  }, [data]);

  if (data.length === 0) {
    return (
      <div className="text-center py-20 bg-ui-card border border-ui-border rounded-lg">
        <p className="text-text-muted">No rankings data available. Run <code className="bg-gray-100 px-1 rounded text-xs">nba_compute_ratings --season 2026</code></p>
      </div>
    );
  }

  const toScatter = (teams: NBATeamSeasonRatings[]) =>
    teams.map((t) => ({
      name: t.team_abbreviation,
      value: [t.adj_off, t.adj_def],
      slug: t.team_slug,
      fullName: t.team_name,
      rank: t.rank_adj_net,
      ffi: t.ffi,
    }));

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        const d = params.data;
        return `
          <div style="font-weight:600;margin-bottom:4px">${d.fullName}</div>
          <div>Adj Off: <b>${Number(d.value[0]).toFixed(1)}</b></div>
          <div>Adj Def: <b>${Number(d.value[1]).toFixed(1)}</b> <span style="color:#888;font-size:11px">(lower = better)</span></div>
          ${d.rank != null ? `<div>Rank: <b>#${d.rank}</b></div>` : ''}
          ${d.ffi != null ? `<div>FFI: <b>${Number(d.ffi).toFixed(1)}</b></div>` : ''}
        `;
      },
    },
    legend: {
      data: ['East', 'West'],
      top: 0,
      right: 0,
      textStyle: { color: '#6b7280' },
    },
    grid: {
      left: '8%',
      right: '5%',
      top: '10%',
      bottom: '12%',
    },
    xAxis: {
      name: 'Adj Offensive Rating →',
      nameLocation: 'middle',
      nameGap: 32,
      nameTextStyle: { color: '#6b7280', fontSize: 12 },
      type: 'value',
      scale: true,
      splitLine: { lineStyle: { color: '#e5e7eb', type: 'dashed' } },
      axisLabel: { color: '#6b7280', fontSize: 11 },
    },
    yAxis: {
      name: '↑ Adj Defensive Rating (lower = better)',
      nameLocation: 'middle',
      nameGap: 52,
      nameTextStyle: { color: '#6b7280', fontSize: 12 },
      type: 'value',
      scale: true,
      inverse: true, // Lower def rating = better = toward TOP of chart
      splitLine: { lineStyle: { color: '#e5e7eb', type: 'dashed' } },
      axisLabel: { color: '#6b7280', fontSize: 11 },
    },
    series: [
      {
        name: 'East',
        type: 'scatter',
        data: toScatter(eastTeams),
        symbolSize: 38,
        itemStyle: { color: '#3b82f6', opacity: 0.85 },
        emphasis: { itemStyle: { color: '#1d4ed8', opacity: 1 } },
        label: {
          show: true,
          formatter: (p: any) => p.data?.name || '',
          position: 'inside',
          color: '#fff',
          fontSize: 9,
          fontWeight: 'bold',
        },
        markLine: {
          silent: true,
          symbol: ['none', 'none'],
          label: { show: false },
          lineStyle: { color: '#9ca3af', type: 'dashed', width: 1 },
          data: [
            { xAxis: avgAdj.off },
            { yAxis: avgAdj.def },
          ],
        },
      },
      {
        name: 'West',
        type: 'scatter',
        data: toScatter(westTeams),
        symbolSize: 38,
        itemStyle: { color: '#f97316', opacity: 0.85 },
        emphasis: { itemStyle: { color: '#c2410c', opacity: 1 } },
        label: {
          show: true,
          formatter: (p: any) => p.data?.name || '',
          position: 'inside',
          color: '#fff',
          fontSize: 9,
          fontWeight: 'bold',
        },
      },
    ],
  };

  const handleChartClick = (params: any) => {
    if (params.data?.slug) {
      router.push(`/nba/team/${params.data.slug}`);
    }
  };

  return (
    <div className="space-y-6">
      {/* Chart card */}
      <div className="bg-ui-card border border-ui-border rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-bold">Efficiency Landscape</h2>
            <p className="text-sm text-text-muted mt-0.5">
              Adj Off (x) vs Adj Def (y, inverted — better teams top-right) · click a team to open its profile
            </p>
          </div>
          {seasonDisplay && (
            <span className="text-sm font-medium text-text-muted bg-ui-surface px-3 py-1 rounded-full border border-ui-border">
              {seasonDisplay}
            </span>
          )}
        </div>
        <ReactECharts
          ref={chartRef}
          option={option}
          style={{ height: 520 }}
          onEvents={{ click: handleChartClick }}
          notMerge
        />
      </div>

      {/* Legend / quadrant guide */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        {[
          { quad: 'Top-right', label: 'Elite (high off + low def)', color: 'bg-emerald-100 text-emerald-800' },
          { quad: 'Top-left', label: 'Defensive only', color: 'bg-blue-100 text-blue-800' },
          { quad: 'Bottom-right', label: 'Offensive only', color: 'bg-amber-100 text-amber-800' },
          { quad: 'Bottom-left', label: 'Struggling (low off + high def)', color: 'bg-rose-100 text-rose-800' },
        ].map(({ quad, label, color }) => (
          <div key={quad} className={`px-3 py-2 rounded-md border ${color} border-current/20`}>
            <div className="font-semibold">{quad}</div>
            <div className="text-xs mt-0.5 opacity-80">{label}</div>
          </div>
        ))}
      </div>

      {/* Data table */}
      <div className="bg-ui-card border border-ui-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-ui-surface border-b border-ui-border">
              <th className="text-left py-2 px-4 text-xs text-text-muted font-semibold uppercase tracking-wide">Rank</th>
              <th className="text-left py-2 px-4 text-xs text-text-muted font-semibold uppercase tracking-wide">Team</th>
              <th className="text-left py-2 px-4 text-xs text-text-muted font-semibold uppercase tracking-wide">Conf</th>
              <th className="text-right py-2 px-4 text-xs text-text-muted font-semibold uppercase tracking-wide">Adj Net</th>
              <th className="text-right py-2 px-4 text-xs text-text-muted font-semibold uppercase tracking-wide">Adj Off</th>
              <th className="text-right py-2 px-4 text-xs text-text-muted font-semibold uppercase tracking-wide">Adj Def</th>
              <th className="text-right py-2 px-4 text-xs text-text-muted font-semibold uppercase tracking-wide">FFI</th>
            </tr>
          </thead>
          <tbody>
            {[...data]
              .sort((a, b) => (a.rank_adj_net ?? 99) - (b.rank_adj_net ?? 99))
              .map((t) => (
                <tr
                  key={t.team_slug}
                  className="border-b border-ui-border/50 hover:bg-ui-surface/50 cursor-pointer"
                  onClick={() => router.push(`/nba/team/${t.team_slug}`)}
                >
                  <td className="py-2 px-4 font-mono text-text-muted text-xs">#{t.rank_adj_net ?? '—'}</td>
                  <td className="py-2 px-4 font-medium">{t.team_name}</td>
                  <td className="py-2 px-4 text-text-muted text-xs">{t.team_conference}</td>
                  <td className="py-2 px-4 text-right font-mono font-semibold text-brand">
                    {t.adj_net != null ? (t.adj_net >= 0 ? '+' : '') + t.adj_net.toFixed(1) : '—'}
                  </td>
                  <td className="py-2 px-4 text-right font-mono text-emerald-700">
                    {t.adj_off?.toFixed(1) ?? '—'}
                  </td>
                  <td className="py-2 px-4 text-right font-mono text-rose-700">
                    {t.adj_def?.toFixed(1) ?? '—'}
                  </td>
                  <td className="py-2 px-4 text-right font-mono">
                    {t.ffi?.toFixed(1) ?? '—'}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
