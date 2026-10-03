import { ScrollView, Text, View } from 'react-native';

import { fmtSigned, getBPRTier, type BPRTier } from '@macfax/core/lib/bprTiers';

import { fontFamily, gold, heat, ink, negativeInk, palette } from '@/src/theme/tokens';

const SAMPLE_WINS_ADDED = [9.4, 6.1, 3.2, 0.8, -1.5, null];

type Swatch = { name: string; value: string };

const SWATCH_GROUPS: { title: string; swatches: Swatch[] }[] = [
  {
    title: 'Brand',
    swatches: [
      { name: 'bg', value: palette.bg },
      { name: 'brand', value: palette.brand },
      { name: 'brand hover', value: palette.brandHover },
      { name: 'brand2', value: palette.brand2 },
      { name: 'brandBlue', value: palette.brandBlue },
      { name: 'positive', value: palette.positive },
      { name: 'negative', value: palette.negative },
      { name: 'warning', value: palette.warning },
      { name: 'muted', value: palette.muted },
    ],
  },
  {
    title: 'Ink',
    swatches: [
      { name: 'ink', value: ink.DEFAULT },
      { name: 'ink-2', value: ink[2] },
      { name: 'ink-3', value: ink[3] },
      { name: 'ink-line', value: ink.line },
      { name: 'ink-fg', value: ink.fg },
      { name: 'ink-fg2', value: ink.fg2 },
    ],
  },
  {
    title: 'Heat (shown on white, as on web)',
    swatches: Object.entries(heat).map(([name, value]) => ({ name: `heat-${name}`, value })),
  },
  {
    title: 'Gold and negative ink',
    swatches: [
      { name: 'gold', value: gold.DEFAULT },
      { name: 'gold-strong', value: gold.strong },
      { name: 'gold-bg', value: gold.bg },
      { name: 'gold-line', value: gold.line },
      { name: 'negative-ink', value: negativeInk },
    ],
  },
];

const FONT_LINES: { family: string; sample: string }[] = [
  { family: fontFamily.display, sample: 'OSWALD 700 — POWER RANKINGS 0123456789' },
  { family: fontFamily['display-semibold'], sample: 'OSWALD 600 — POWER RANKINGS 0123456789' },
  { family: fontFamily['display-medium'], sample: 'Oswald 500 — Power Rankings 0123456789' },
  { family: fontFamily['display-regular'], sample: 'Oswald 400 — Power Rankings 0123456789' },
  { family: fontFamily.sans, sample: 'Inter 400 — Utah State Aggies 0123456789' },
  { family: fontFamily['sans-medium'], sample: 'Inter 500 — Utah State Aggies 0123456789' },
  { family: fontFamily['sans-semibold'], sample: 'Inter 600 — Utah State Aggies 0123456789' },
  { family: fontFamily['sans-bold'], sample: 'Inter 700 — Utah State Aggies 0123456789' },
  { family: fontFamily.mono, sample: 'IBM Plex Mono 400 — +12.34 118.6 0O1lI' },
  { family: fontFamily['mono-medium'], sample: 'IBM Plex Mono 500 — +12.34 118.6 0O1lI' },
  { family: fontFamily['mono-semibold'], sample: 'IBM Plex Mono 600 — +12.34 118.6 0O1lI' },
];

function SectionTitle({ children }: { children: string }) {
  return <Text className="mb-2 mt-6 font-display-semibold text-xs uppercase tracking-widest text-brand">{children}</Text>;
}

export default function Gate() {
  const tiers: { winsAdded: number | null; tier: BPRTier }[] = SAMPLE_WINS_ADDED.map((winsAdded) => ({
    winsAdded,
    tier: getBPRTier(winsAdded),
  }));

  return (
    <ScrollView className="flex-1 bg-bg" contentContainerClassName="p-4 pb-12">
      <Text className="font-display text-3xl uppercase text-text-onDark">Theme gate</Text>
      <Text className="mt-1 font-sans text-sm text-ink-fg2">
        Tokens, fonts and NativeWind classes. Compare against the web site.
      </Text>

      {/* Swatches use inline styles from tokens.ts, so they show the raw token values. */}
      {SWATCH_GROUPS.map((group) => (
        <View key={group.title}>
          <SectionTitle>{group.title}</SectionTitle>
          <View className="flex-row flex-wrap gap-3">
            {group.swatches.map((swatch) => (
              <View key={swatch.name} className="w-24">
                <View className="h-12 overflow-hidden rounded-md border border-ink-line bg-white">
                  <View style={{ flex: 1, backgroundColor: swatch.value }} />
                </View>
                <Text className="mt-1 font-sans-medium text-xs text-ink-fg">{swatch.name}</Text>
                <Text className="font-mono text-[10px] text-ink-fg2">{swatch.value}</Text>
              </View>
            ))}
          </View>
        </View>
      ))}

      <SectionTitle>Same tokens through NativeWind classes</SectionTitle>
      <View className="flex-row flex-wrap gap-3">
        <View className="h-12 w-24 rounded-md bg-brand" />
        <View className="h-12 w-24 rounded-md bg-ink-3" />
        <View className="h-12 w-24 rounded-md border border-gold-line bg-gold-bg" />
        <View className="h-12 w-24 rounded-md bg-white">
          <View className="flex-1 rounded-md bg-heat-3" />
        </View>
        <View className="h-12 w-24 rounded-md bg-negative-ink" />
      </View>

      <SectionTitle>Fonts</SectionTitle>
      {FONT_LINES.map((line) => (
        <Text key={line.family} style={{ fontFamily: line.family }} className="py-1 text-lg text-text-onDark">
          {line.sample}
        </Text>
      ))}
      <Text className="py-1 font-display text-lg text-text-onDark">font-display class (Oswald 700)</Text>
      <Text className="py-1 font-sans text-lg text-text-onDark">font-sans class (Inter 400)</Text>
      <Text className="py-1 font-mono text-lg text-text-onDark">font-mono class (IBM Plex Mono 400)</Text>

      <SectionTitle>Core bprTiers class strings via NativeWind</SectionTitle>
      {tiers.map(({ winsAdded, tier }) => (
        <View key={String(winsAdded)} className="mb-2 rounded-md border border-ink-line bg-ink-2 p-3">
          <View className="flex-row items-center gap-3">
            <Text className={`w-14 font-mono-semibold text-base ${tier.color}`}>{fmtSigned(winsAdded)}</Text>
            <View className={`rounded px-2 py-1 ${tier.bgColor}`}>
              <Text className={`font-sans-semibold text-xs ${tier.color}`}>{tier.label}</Text>
            </View>
            <View className="h-2 flex-1 overflow-hidden rounded-full bg-ink-3">
              <View
                className={`h-2 rounded-full ${tier.barColor}`}
                style={{ width: `${Math.max(8, Math.min(100, ((winsAdded ?? 0) + 2) * 8))}%` }}
              />
            </View>
          </View>
          <Text className="mt-2 font-mono text-[10px] text-ink-fg2">
            {tier.color} {tier.bgColor} {tier.barColor}
          </Text>
        </View>
      ))}
    </ScrollView>
  );
}
