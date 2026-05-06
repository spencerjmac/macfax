'use client';

import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';
import type { ValidationWeekEntry } from '@/types/validation';

interface AccuracyOverTimeChartProps {
  weeks: ValidationWeekEntry[];
}

export function AccuracyOverTimeChart({ weeks }: AccuracyOverTimeChartProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!chartRef.current || weeks.length === 0) return;

    chartInstance.current = echarts.init(chartRef.current);

    const labels = weeks.map(w => {
      const d = new Date(w.week_start + 'T00:00:00');
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    });
    const accuracyData = weeks.map(w => +(w.winner_accuracy * 100).toFixed(1));
    const maeData = weeks.map(w => +w.spread_mae.toFixed(2));

    const option: echarts.EChartsOption = {
      backgroundColor: 'transparent',
      grid: { top: 40, right: 60, bottom: 40, left: 50, containLabel: false },
      tooltip: {
        trigger: 'axis',
        formatter: (params: echarts.TooltipComponentFormatterCallbackParams) => {
          if (!Array.isArray(params)) return '';
          const [acc, mae] = params as { name: string; value: number; seriesName: string }[];
          return `<div style="font-size:12px">
            <strong>${acc?.name ?? ''}</strong><br/>
            Winner Accuracy: <strong>${acc?.value ?? '—'}%</strong><br/>
            Spread MAE: <strong>${mae?.value ?? '—'} pts</strong>
          </div>`;
        },
      },
      legend: {
        top: 0,
        textStyle: { color: '#9ca3af', fontSize: 12 },
        data: ['Winner Accuracy (%)', 'Spread MAE (pts)'],
      },
      xAxis: {
        type: 'category',
        data: labels,
        axisLabel: { color: '#9ca3af', fontSize: 11, rotate: labels.length > 10 ? 30 : 0 },
        axisLine: { lineStyle: { color: '#374151' } },
      },
      yAxis: [
        {
          type: 'value',
          name: '%',
          min: 40,
          max: 100,
          axisLabel: { color: '#9ca3af', fontSize: 11, formatter: '{value}%' },
          splitLine: { lineStyle: { color: '#1f2937' } },
        },
        {
          type: 'value',
          name: 'pts',
          min: 0,
          max: 20,
          axisLabel: { color: '#9ca3af', fontSize: 11 },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: 'Winner Accuracy (%)',
          type: 'line',
          data: accuracyData,
          yAxisIndex: 0,
          smooth: true,
          lineStyle: { color: '#3b82f6', width: 2 },
          itemStyle: { color: '#3b82f6' },
          symbol: 'circle',
          symbolSize: 5,
          areaStyle: { color: 'rgba(59,130,246,0.08)' },
        },
        {
          name: 'Spread MAE (pts)',
          type: 'line',
          data: maeData,
          yAxisIndex: 1,
          smooth: true,
          lineStyle: { color: '#f59e0b', width: 2, type: 'dashed' },
          itemStyle: { color: '#f59e0b' },
          symbol: 'circle',
          symbolSize: 5,
        },
      ],
    };

    chartInstance.current.setOption(option);

    const handleResize = () => chartInstance.current?.resize();
    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
      chartInstance.current?.dispose();
    };
  }, [weeks]);

  if (weeks.length === 0) return null;

  return (
    <div className="bg-ui-card border border-ui-border rounded-xl p-5 mt-8">
      <h2 className="text-lg font-semibold text-text-primary mb-4">Accuracy Over Time</h2>
      <div ref={chartRef} style={{ height: 280 }} />
    </div>
  );
}
