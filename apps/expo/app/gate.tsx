import { useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { ChartExperiment, type ChartApproach } from '@/src/components/ChartExperiment';
import { RankingsTable } from '@/src/components/RankingsTable';
import { ThemeSample } from '@/src/components/ThemeSample';

const TABS = [
  { key: 'theme', label: 'Theme' },
  { key: 'table', label: 'Table' },
  { key: 'chart', label: 'Chart' },
] as const;

type TabKey = (typeof TABS)[number]['key'];

export default function Gate() {
  // /gate?tab=chart&chart=b opens a tab directly (handy for deep links and screenshots).
  const params = useLocalSearchParams<{ tab?: string; chart?: string }>();
  const initialTab = TABS.find(({ key }) => key === params.tab)?.key ?? 'theme';
  const [tab, setTab] = useState<TabKey>(initialTab);

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
      {tab === 'table' ? <RankingsTable /> : null}
      {tab === 'chart' ? <ChartExperiment initial={(params.chart === 'b' ? 'b' : 'a') satisfies ChartApproach} /> : null}
    </View>
  );
}
