'use client';

import { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import type { WPPoint, GameTeamRef } from '@/types/games';

interface WPChartProps {
  curve: WPPoint[];
  homeTeam: GameTeamRef;
  awayTeam: GameTeamRef;
}

function fmtLabel(t: number): string {
  const pct = Math.round(t * 100);
  if (pct === 0) return 'Start';
  if (pct === 50) return 'Half';
  if (pct === 100) return 'End';
  return `${pct}%`;
}

export default function WPChart({ curve, homeTeam, awayTeam }: WPChartProps) {
  const option = useMemo(() => {
    if (!curve.length) return null;

    const xData = curve.map((p) => p.t);
    const yData = curve.map((p) => +(p.wp * 100).toFixed(1));

    return {
      backgroundColor: 'transparent',
      animation: false,
      grid: { top: 24, right: 16, bottom: 40, left: 48, containLabel: false },
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#1a1a1a',
        borderColor: '#333',
        textStyle: { color: '#e5e7eb', fontSize: 12 },
        formatter: (params: { dataIndex: number }[]) => {
          if (!params[0]) return '';
          const pt = curve[params[0].dataIndex];
          const pct = (pt.wp * 100).toFixed(0);
          return `<div style="line-height:1.6">
            <strong style="color:#f9fafb">${fmtLabel(pt.t)}</strong><br/>
            ${homeTeam.abbr} <b>${pt.home_score}</b> – ${awayTeam.abbr} <b>${pt.away_score}</b><br/>
            ${homeTeam.abbr} win prob: <b style="color:#60a5fa">${pct}%</b>
          </div>`;
        },
      },
      xAxis: {
        type: 'value',
        min: 0,
        max: Math.max(...xData, 1),
        axisLabel: {
          formatter: (v: number) => fmtLabel(v),
          color: '#9ca3af',
          fontSize: 11,
          interval: 'auto',
        },
        axisLine: { lineStyle: { color: '#374151' } },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        min: 0,
        max: 100,
        axisLabel: {
          formatter: '{value}%',
          color: '#9ca3af',
          fontSize: 11,
        },
        splitLine: { lineStyle: { color: '#1f2937', type: 'dashed' } },
      },
      series: [
        {
          type: 'line',
          data: xData.map((x, i) => [x, yData[i]]),
          smooth: false,
          lineStyle: { color: '#3b82f6', width: 2 },
          itemStyle: { color: '#3b82f6' },
          symbol: 'none',
          areaStyle: {
            color: {
              type: 'linear',
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(59,130,246,0.28)' },
                { offset: 0.45, color: 'rgba(59,130,246,0.06)' },
                { offset: 0.55, color: 'rgba(239,68,68,0.06)' },
                { offset: 1, color: 'rgba(239,68,68,0.10)' },
              ],
            },
          },
          markLine: {
            silent: true,
            symbol: 'none',
            data: [
              {
                yAxis: 50,
                lineStyle: { color: '#6b7280', type: 'dashed', width: 1 },
                label: { show: false },
              },
              {
                xAxis: 0.5,
                lineStyle: { color: '#374151', type: 'dotted', width: 1 },
                label: {
                  formatter: 'Half',
                  color: '#6b7280',
                  fontSize: 10,
                  position: 'insideStartTop',
                },
              },
            ],
          },
        },
      ],
    };
  }, [curve, homeTeam.abbr, awayTeam.abbr]);

  if (!curve.length) {
    return (
      <div className="rounded-xl border border-ui-border bg-ui-surface p-6 text-center text-sm text-text-muted">
        Win probability curve unavailable — play-by-play data not yet synced for this game.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-ui-border bg-ui-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-semibold text-text-primary">Win Probability</span>
        <div className="flex gap-4 text-xs text-text-muted">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 rounded bg-blue-500" />
            {homeTeam.abbr} home win prob
          </span>
        </div>
      </div>
      <ReactECharts
        option={option!}
        style={{ height: 220 }}
        notMerge
        lazyUpdate
      />
      <div className="mt-1 flex justify-between text-[11px] text-text-muted px-1">
        <span className="text-blue-400 font-medium">{homeTeam.name}</span>
        <span>{awayTeam.name}</span>
      </div>
    </div>
  );
}
