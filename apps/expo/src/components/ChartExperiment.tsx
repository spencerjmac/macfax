import { useCallback, useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';

import WPChartDom from '@/src/components/charts/WPChartDom';
import { WPChartNative } from '@/src/components/charts/WPChartNative';
import { fetchSampleWPChartData } from '@/src/lib/api';

const APPROACHES = [
  { key: 'a', label: "A: 'use dom'" },
  { key: 'b', label: 'B: native SVG' },
] as const;

export type ChartApproach = (typeof APPROACHES)[number]['key'];

export function ChartExperiment({ initial = 'a' }: { initial?: ChartApproach }) {
  const [approach, setApproach] = useState<ChartApproach>(initial);
  // Stable identity: a new function each render would restart the DOM component's fetch.
  const loadViaNative = useCallback(() => fetchSampleWPChartData(), []);

  return (
    <ScrollView className="flex-1" contentContainerClassName="p-4">
      <View className="mb-4 flex-row gap-2">
        {APPROACHES.map(({ key, label }) => (
          <Pressable
            key={key}
            onPress={() => setApproach(key)}
            className={`flex-1 items-center rounded-md border px-3 py-2 ${
              approach === key ? 'border-brand bg-brand' : 'border-ink-line bg-ink-2'
            }`}
          >
            <Text className="font-sans-semibold text-sm text-text-onDark">{label}</Text>
          </Pressable>
        ))}
      </View>

      <View className="overflow-hidden rounded-md border border-ink-line bg-ink-2">
        {approach === 'a' ? (
          <WPChartDom loadViaNative={loadViaNative} dom={{ style: { height: 320 }, scrollEnabled: false }} />
        ) : (
          <WPChartNative />
        )}
      </View>
    </ScrollView>
  );
}
