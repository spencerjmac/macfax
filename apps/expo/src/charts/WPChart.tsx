import { Text, View } from 'react-native';

import type { GameTeamRef, WPPoint } from '@macfax/core/types/games';

import WPChartDom from '@/src/charts/WPChartDom';

const CHART_HEIGHT = 220;

interface WPChartProps {
  curve: WPPoint[];
  homeTeam: GameTeamRef;
  awayTeam: GameTeamRef;
}

/**
 * Win-probability chart. Takes data as props: the screen fetches through
 * src/lib/api.ts and passes the result in. Rendering is delegated to a DOM
 * component so the web chart code runs unchanged on every platform.
 */
export function WPChart({ curve, homeTeam, awayTeam }: WPChartProps) {
  if (!curve.length) {
    return (
      <View className="rounded-md border border-ink-line bg-ink-2 p-6">
        <Text className="text-center font-sans text-sm text-ink-fg2">
          Win probability curve unavailable. Play-by-play data is not yet synced for this game.
        </Text>
      </View>
    );
  }

  return (
    <View className="rounded-md border border-ink-line bg-ink-2 p-3">
      <Text className="mb-2 font-sans-semibold text-sm text-text-onDark">Win Probability</Text>
      <View style={{ height: CHART_HEIGHT }}>
        <WPChartDom
          curve={curve}
          homeTeam={homeTeam}
          awayTeam={awayTeam}
          height={CHART_HEIGHT}
          dom={{ style: { height: CHART_HEIGHT }, scrollEnabled: false }}
        />
      </View>
      <View className="mt-1 flex-row justify-between px-1">
        <Text className="font-sans-medium text-[11px] text-blue-400">{homeTeam.name}</Text>
        <Text className="font-sans text-[11px] text-ink-fg2">{awayTeam.name}</Text>
      </View>
    </View>
  );
}
