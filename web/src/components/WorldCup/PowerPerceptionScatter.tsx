'use client';

import { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import type { WorldCupTeam } from '@/types/worldcup';

interface PowerPerceptionScatterProps {
  teams: WorldCupTeam[];
}

const CONF_COLORS: Record<string, string> = {
  UEFA:     '#4f8ef7',
  CONMEBOL: '#2ecc71',
  CAF:      '#f39c12',
  CONCACAF: '#e74c3c',
  AFC:      '#9b59b6',
  OFC:      '#95a5a6',
};

const CONFEDERATIONS = ['UEFA', 'CONMEBOL', 'CAF', 'CONCACAF', 'AFC', 'OFC'] as const;

export default function PowerPerceptionScatter({ teams }: PowerPerceptionScatterProps) {
  const option = useMemo(() => {
    const seriesByConf = CONFEDERATIONS.map((conf) => {
      const confTeams = teams.filter((t) => t.confederation === conf);
      return {
        name: conf,
        type: 'scatter',
        data: confTeams.map((t) => ({
          value: [t.fifa_points, t.elo_rating],
          name: t.name,
          flag: t.flag_emoji,
          elo: t.elo_rating,
          fifaRank: t.fifa_rank,
          fifaPoints: t.fifa_points,
          eloRank: t.elo_rank,
          delta: t.elo_vs_fifa,
        })),
        symbolSize: 28,
        itemStyle: { color: 'transparent', borderColor: 'transparent' },
        label: {
          show: true,
          formatter: (params: any) => params.data.flag,
          fontSize: 22,
          lineHeight: 24,
        },
        emphasis: {
          itemStyle: { color: CONF_COLORS[conf], opacity: 0.2, borderWidth: 2, borderColor: CONF_COLORS[conf] },
          label: { show: true, fontSize: 22 },
        },
      };
    });

    return {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'item',
        formatter: (params: any) => {
          const d = params.data;
          const deltaSign = d.delta > 0 ? '+' : '';
          return `
            <div style="font-weight:600;margin-bottom:4px">${d.flag} ${d.name}</div>
            <div>Elo Rating: <b>${Number(d.elo).toFixed(1)}</b></div>
            <div>FIFA Points: <b>${Number(d.fifaPoints).toFixed(2)}</b></div>
            <div>FIFA Rank: <b>#${d.fifaRank}</b> &nbsp; Elo Rank: <b>#${d.eloRank}</b></div>
            <div>Δ (Elo vs FIFA): <b>${deltaSign}${d.delta}</b></div>
          `;
        },
      },
      legend: {
        data: CONFEDERATIONS as unknown as string[],
        bottom: 0,
        textStyle: { color: '#6b7280', fontSize: 11 },
        itemWidth: 10,
        itemHeight: 10,
      },
      grid: {
        left: '10%',
        right: '6%',
        top: '14%',
        bottom: '12%',
      },
      xAxis: {
        name: 'FIFA Points →',
        nameLocation: 'middle',
        nameGap: 32,
        nameTextStyle: { color: '#6b7280', fontSize: 12 },
        type: 'value',
        min: 1200,
        max: 1950,
        splitLine: { lineStyle: { color: '#e5e7eb', type: 'dashed' } },
        axisLabel: { color: '#6b7280', fontSize: 11 },
        axisLine: { lineStyle: { color: '#d1d5db' } },
      },
      yAxis: {
        name: 'Elo Rating ↑',
        nameLocation: 'middle',
        nameGap: 50,
        nameTextStyle: { color: '#6b7280', fontSize: 12 },
        type: 'value',
        min: 1400,
        max: 2250,
        splitLine: { lineStyle: { color: '#e5e7eb', type: 'dashed' } },
        axisLabel: { color: '#6b7280', fontSize: 11 },
        axisLine: { lineStyle: { color: '#d1d5db' } },
      },
      graphic: [
        {
          type: 'text',
          left: '10%',
          top: '18%',
          style: { text: 'Undervalued by FIFA', fill: '#9ca3af', fontSize: 11, fontStyle: 'italic' },
        },
        {
          type: 'text',
          left: '62%',
          top: '72%',
          style: { text: 'Overvalued by FIFA', fill: '#9ca3af', fontSize: 11, fontStyle: 'italic' },
        },
      ],
      series: seriesByConf,
    };
  }, [teams]);

  return (
    <div className="bg-ui-card border border-ui-border rounded-lg p-6">
      <div className="mb-4">
        <h2 className="text-xl font-bold">Efficiency Landscape</h2>
        <p className="text-sm text-text-muted mt-0.5">
          Elo rating vs. FIFA points — teams in the upper-left are rated higher by our model than FIFA
        </p>
      </div>
      <ReactECharts
        option={option}
        style={{ height: 500 }}
        notMerge
      />
    </div>
  );
}
