import SvgChart, { SVGRenderer } from '@wuba/react-native-echarts/svgChart';
import { LineChart } from 'echarts/charts';
import { GridComponent, MarkLineComponent, TooltipComponent } from 'echarts/components';
import * as echarts from 'echarts/core';
import { useEffect, useRef, useState } from 'react';
import { Text, View } from 'react-native';

import type { GameTeamRef, WPPoint } from '@macfax/core/types/games';

import { buildWPOption } from '@/src/charts/wpOption';

echarts.use([LineChart, GridComponent, TooltipComponent, MarkLineComponent, SVGRenderer]);

const CHART_HEIGHT = 220;

interface WPChartNativeProps {
  curve: WPPoint[];
  homeTeam: GameTeamRef;
  awayTeam: GameTeamRef;
}

/**
 * EXPERIMENTAL, UNVERIFIED ON DEVICE. Do not use in real screens yet.
 *
 * The win-probability chart rendered natively with @wuba/react-native-echarts
 * (react-native-svg renderer) from the same option object as the web chart.
 * It has only been bundle-compiled for iOS and Android and rendered on web,
 * where the wrapper takes a plain-DOM path rather than react-native-svg.
 * Expected problem on native: the tooltip formatter returns HTML, which a
 * renderer without a DOM will show as raw text.
 */
export function WPChartNative({ curve, homeTeam, awayTeam }: WPChartNativeProps) {
  const [width, setWidth] = useState(0);
  // An error is tagged with the inputs that caused it and hidden once they change.
  const [failure, setFailure] = useState<{ message: string; inputs: unknown[] } | null>(null);
  const chartRef = useRef<any>(null);

  useEffect(() => {
    if (!width || !chartRef.current) return;
    let chart: echarts.ECharts | undefined;
    try {
      chart = echarts.init(chartRef.current, undefined, { renderer: 'svg', width, height: CHART_HEIGHT });
      chart.setOption(buildWPOption(curve, homeTeam, awayTeam));
    } catch (error) {
      // echarts runs synchronously here (it needs the ref), so its exception can only reach the UI through state.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setFailure({ message: error instanceof Error ? error.message : String(error), inputs: [curve, homeTeam, awayTeam, width] });
    }
    return () => chart?.dispose();
  }, [curve, homeTeam, awayTeam, width]);

  const renderError = failure && [curve, homeTeam, awayTeam, width].every((value, i) => value === failure.inputs[i]) ? failure.message : null;

  return (
    <View className="rounded-md border border-ink-line bg-ink-2 p-3">
      {/* The chart needs an explicit pixel width, so measure the box it sits in. */}
      <View style={{ height: CHART_HEIGHT }} onLayout={(event) => setWidth(Math.floor(event.nativeEvent.layout.width))}>
        {width ? <SvgChart ref={chartRef} /> : null}
      </View>
      <Text className="mt-2 font-mono text-[11px] text-ink-fg2">native SVG renderer · {width}px</Text>
      {renderError ? <Text className="mt-2 font-mono text-xs text-negative">Render failed: {renderError}</Text> : null}
    </View>
  );
}
