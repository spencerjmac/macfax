import { Redirect, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';

import { WPChartNative } from '@/src/charts/experimental/WPChartNative';
import { WPChart } from '@/src/charts/WPChart';
import { ThemeSample } from '@/src/components/ThemeSample';
import { AsyncView } from '@/src/components/ui/StateViews';
import { fetchSampleWPChartData } from '@/src/lib/api';
import { GATE_ENABLED } from '@/src/lib/devFlags';
import { useAsync } from '@/src/lib/useAsync';

const TABS = [
  { key: 'theme', label: 'Theme' },
  { key: 'chart', label: 'Chart' },
  { key: 'chart-native', label: 'Chart (exp.)' },
] as const;

type TabKey = (typeof TABS)[number]['key'];

/** The screen fetches; the charts only receive data. */
function ChartTab({ experimental }: { experimental: boolean }) {
  const game = useAsync(() => fetchSampleWPChartData(), []);
  return (
    <ScrollView className="flex-1" contentContainerClassName="p-4">
      <AsyncView state={game} loadingLabel="Loading a sample game…" errorTitle="Could not load a sample game">
        {(data) => (
          <>
            <Text className="mb-3 font-sans-semibold text-sm text-text-onDark">
              {data.homeTeam.name} vs {data.awayTeam.name} · game {data.gameId} · {data.date}
            </Text>
            {experimental ? (
              <WPChartNative curve={data.curve} homeTeam={data.homeTeam} awayTeam={data.awayTeam} />
            ) : (
              <WPChart curve={data.curve} homeTeam={data.homeTeam} awayTeam={data.awayTeam} />
            )}
          </>
        )}
      </AsyncView>
    </ScrollView>
  );
}

/**
 * Developer test bench, not part of the product: theme samples and the chart
 * components. Reachable at /gate only when GATE_ENABLED (see src/lib/devFlags.ts).
 * /gate?tab=chart opens a tab directly.
 */
export default function Gate() {
  const params = useLocalSearchParams<{ tab?: string }>();
  const initialTab = TABS.find(({ key }) => key === params.tab)?.key ?? 'theme';
  const [tab, setTab] = useState<TabKey>(initialTab);

  if (!GATE_ENABLED) return <Redirect href="/" />;

  return (
    <View className="flex-1 bg-bg">
      <View className="flex-row border-b border-ink-line bg-ink-2">
        {TABS.map(({ key, label }) => (
          <Pressable
            key={key}
            onPress={() => setTab(key)}
            className={`flex-1 items-center border-b-2 py-3 ${tab === key ? 'border-brand' : 'border-transparent'}`}
          >
            <Text
              className={`font-display-semibold text-sm uppercase tracking-wider ${
                tab === key ? 'text-text-onDark' : 'text-ink-fg2'
              }`}
            >
              {label}
            </Text>
          </Pressable>
        ))}
      </View>
      {tab === 'theme' ? <ThemeSample /> : null}
      {tab === 'chart' ? <ChartTab experimental={false} /> : null}
      {tab === 'chart-native' ? <ChartTab experimental /> : null}
    </View>
  );
}
