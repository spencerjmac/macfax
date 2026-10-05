import SvgChart, { SVGRenderer } from '@wuba/react-native-echarts/svgChart';
import { LineChart } from 'echarts/charts';
import { GridComponent, MarkLineComponent, TooltipComponent } from 'echarts/components';
import * as echarts from 'echarts/core';
import { useEffect, useRef, useState } from 'react';
import { Text, View } from 'react-native';

import { buildWPOption } from '@/src/charts/wpOption';
import { fetchSampleWPChartData, type WPChartData } from '@/src/lib/api';

echarts.use([LineChart, GridComponent, TooltipComponent, MarkLineComponent, SVGRenderer]);

const CHART_HEIGHT = 220;

type State =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: WPChartData };

/**
 * Approach B: ECharts rendered natively through @wuba/react-native-echarts
 * (react-native-svg renderer), using the same option object as the web chart.
 */
export function WPChartNative() {
  const [state, setState] = useState<State>({ status: 'loading' });
  const [width, setWidth] = useState(0);
  const [renderError, setRenderError] = useState<string | null>(null);
  const chartRef = useRef<any>(null);

  useEffect(() => {
    let cancelled = false;
    fetchSampleWPChartData()
      .then((data) => {
        if (!cancelled) setState({ status: 'ready', data });
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ status: 'error', message: error instanceof Error ? error.message : String(error) });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const data = state.status === 'ready' ? state.data : null;

  useEffect(() => {
    if (!data || !width || !chartRef.current) return;
    let chart: echarts.ECharts | undefined;
    try {
      chart = echarts.init(chartRef.current, undefined, { renderer: 'svg', width, height: CHART_HEIGHT });
      chart.setOption(buildWPOption(data.curve, data.homeTeam, data.awayTeam));
      setRenderError(null);
    } catch (error) {
      setRenderError(error instanceof Error ? error.message : String(error));
    }
    return () => chart?.dispose();
  }, [data, width]);

  return (
    <View className="p-3">
      {state.status === 'loading' ? <Text className="font-mono text-xs text-ink-fg2">Loading chart data…</Text> : null}
      {state.status === 'error' ? (
        <Text className="font-mono text-xs text-negative">Chart data failed: {state.message}</Text>
      ) : null}
      {data ? (
        <>
          <Text className="mb-2 font-sans-semibold text-sm text-text-onDark">
            Win probability: {data.homeTeam.name} vs {data.awayTeam.name}
          </Text>
          {/* The chart needs an explicit pixel width, so measure the box it sits in. */}
          <View
            style={{ height: CHART_HEIGHT }}
            onLayout={(event) => setWidth(Math.floor(event.nativeEvent.layout.width))}
          >
            {width ? <SvgChart ref={chartRef} /> : null}
          </View>
          <Text className="mt-2 font-mono text-[11px] text-ink-fg2">
            game {data.gameId} · {data.date} · {data.curve.length} points · native SVG renderer · {width}px
          </Text>
        </>
      ) : null}
      {renderError ? <Text className="mt-2 font-mono text-xs text-negative">Render failed: {renderError}</Text> : null}
    </View>
  );
}
