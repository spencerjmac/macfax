'use dom';

import { LineChart } from 'echarts/charts';
import { GridComponent, MarkLineComponent, TooltipComponent } from 'echarts/components';
import * as echarts from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { useEffect, useRef } from 'react';

import type { GameTeamRef, WPPoint } from '@macfax/core/types/games';

import { buildWPOption } from '@/src/charts/wpOption';

echarts.use([LineChart, GridComponent, TooltipComponent, MarkLineComponent, CanvasRenderer]);

interface WPChartDomProps {
  curve: WPPoint[];
  homeTeam: GameTeamRef;
  awayTeam: GameTeamRef;
  height: number;
  dom?: import('expo/dom').DOMProps;
}

/**
 * The DOM half of WPChart: runs in a WebView on native and as plain DOM on web.
 * It makes no network requests. Data arrives as small serializable props and
 * the ECharts option (which contains functions) is built here, because
 * functions cannot cross the native bridge.
 */
export default function WPChartDom({ curve, homeTeam, awayTeam, height }: WPChartDomProps) {
  const chartEl = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!chartEl.current) return;
    const chart = echarts.init(chartEl.current);
    chart.setOption(buildWPOption(curve, homeTeam, awayTeam));
    const onResize = () => chart.resize();
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('resize', onResize);
      chart.dispose();
    };
  }, [curve, homeTeam, awayTeam]);

  return <div ref={chartEl} style={{ width: '100%', height }} />;
}
