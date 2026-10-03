import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { fmtSigned, getBPRTier, type BPRTier } from '@macfax/core/lib/bprTiers';

const SAMPLE_WINS_ADDED = [9.4, 6.1, 3.2, 0.8, -1.5, null];

export default function Gate() {
  const tiers: { winsAdded: number | null; tier: BPRTier }[] = SAMPLE_WINS_ADDED.map((winsAdded) => ({
    winsAdded,
    tier: getBPRTier(winsAdded),
  }));

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>Shared core: bprTiers</Text>
      {tiers.map(({ winsAdded, tier }) => (
        <View key={String(winsAdded)} style={styles.row}>
          <Text style={styles.value}>{fmtSigned(winsAdded)}</Text>
          <Text style={styles.label}>{tier.label}</Text>
          <Text style={styles.classes}>{tier.color}</Text>
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16, gap: 8 },
  title: { fontSize: 20, fontWeight: '700', marginBottom: 8 },
  row: { flexDirection: 'row', gap: 12, alignItems: 'center' },
  value: { width: 56, fontVariant: ['tabular-nums'] },
  label: { width: 140, fontWeight: '600' },
  classes: { color: '#666' },
});
