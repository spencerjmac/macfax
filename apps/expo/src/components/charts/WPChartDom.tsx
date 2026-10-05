'use dom';

import { LineChart } from 'echarts/charts';
import { GridComponent, MarkLineComponent, TooltipComponent } from 'echarts/components';
import * as echarts from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { useEffect, useRef, useState } from 'react';

import { buildWPOption } from '@/src/charts/wpOption';
import { fetchSampleWPChartData, type WPChartData } from '@/src/lib/api';

echarts.use([LineChart, GridComponent, TooltipComponent, MarkLineComponent, CanvasRenderer]);

type Source = 'webview fetch' | 'native action';

type State =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: WPChartData; source: Source; note?: string };

interface WPChartDomProps {
  /**
   * Native action: runs on the React Native side, so it is not subject to the
   * WebView's CORS rules. Only used if fetching inside the WebView fails.
   */
  loadViaNative?: () => Promise<WPChartData>;
  dom?: import('expo/dom').DOMProps;
}

const errorText = (error: unknown) => (error instanceof Error ? error.message : String(error));

/**
 * Approach A: the web chart running as a DOM component (a WebView on native,
 * plain DOM on web). Data is fetched here and the ECharts option is built
 * here, so no functions or large payloads cross the native bridge as props.
 */
export default function WPChartDom({ loadViaNative }: WPChartDomProps) {
  const [state, setState] = useState<State>({ status: 'loading' });
  const chartEl = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await fetchSampleWPChartData();
        if (!cancelled) setState({ status: 'ready', data, source: 'webview fetch' });
      } catch (fetchError) {
        if (!loadViaNative) {
          if (!cancelled) setState({ status: 'error', message: errorText(fetchError) });
          return;
        }
        try {
          const data = await loadViaNative();
          if (!cancelled) {
            setState({
              status: 'ready',
              data,
              source: 'native action',
              note: `webview fetch failed: ${errorText(fetchError)}`,
            });
          }
        } catch (nativeError) {
          if (!cancelled) setState({ status: 'error', message: errorText(nativeError) });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadViaNative]);

  const data = state.status === 'ready' ? state.data : null;

  useEffect(() => {
    if (!data || !chartEl.current) return;
    const chart = echarts.init(chartEl.current);
    chart.setOption(buildWPOption(data.curve, data.homeTeam, data.awayTeam));
    const onResize = () => chart.resize();
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('resize', onResize);
      chart.dispose();
    };
  }, [data]);

  const caption: React.CSSProperties = {
    font: '11px ui-monospace, Menlo, monospace',
    color: '#8d9bb5',
    margin: '6px 0 0',
    wordBreak: 'break-word',
  };

  return (
    <div style={{ padding: 12, boxSizing: 'border-box', width: '100%' }}>
      {state.status === 'loading' ? <p style={caption}>Loading chart data…</p> : null}
      {state.status === 'error' ? <p style={{ ...caption, color: '#ef4444' }}>Chart failed: {state.message}</p> : null}
      {state.status === 'ready' ? (
        <>
          <p style={{ font: '600 14px system-ui, sans-serif', color: '#f8fafc', margin: '0 0 8px' }}>
            Win probability: {state.data.homeTeam.name} vs {state.data.awayTeam.name}
          </p>
          <div ref={chartEl} style={{ width: '100%', height: 220 }} />
          <p style={caption}>
            game {state.data.gameId} · {state.data.date} · {state.data.curve.length} points · data via {state.source}
          </p>
          {state.note ? <p style={caption}>{state.note}</p> : null}
        </>
      ) : null}
    </div>
  );
}
