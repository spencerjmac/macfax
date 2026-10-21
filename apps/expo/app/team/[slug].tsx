import { Stack, useLocalSearchParams } from 'expo-router';
import { ExternalLink } from '@/src/components/ui/icons';
import { Pressable, Text, View } from 'react-native';

import { Container, ScrollScreen } from '@/src/components/ui/Screen';
import { AsyncView } from '@/src/components/ui/StateViews';
import { TeamLogo } from '@/src/components/ui/TeamLogo';
import { fetchRankings } from '@/src/lib/api';
import { openLink } from '@/src/lib/links';
import { useAsync } from '@/src/lib/useAsync';
import { palette } from '@/src/theme/tokens';

/**
 * PLACEHOLDER team screen. It shows the team's row from the current-season
 * rankings (already cached by the Rankings and Home screens) and links to the
 * full team page on the website. The real port of web's team page comes later.
 */
export default function TeamScreen() {
  const { slug } = useLocalSearchParams<{ slug: string }>();

  const team = useAsync(
    async ({ force }) => {
      const { teams } = await fetchRankings(undefined, { force });
      return teams.find((t) => t.teamId === slug) ?? null;
    },
    [slug],
  );

  const title = team.status === 'ready' && team.data ? team.data.teamName : 'Team';

  return (
    <ScrollScreen>
      <Stack.Screen options={{ title }} />
      <AsyncView
        state={team}
        loadingLabel="Loading team…"
        errorTitle="Could not load team"
        isEmpty={(data) => data === null}
        emptyTitle="Team not found"
        emptyMessage={`No team with the id "${slug}" is in the current rankings.`}
      >
        {(data) => {
          if (!data) return null;
          const stats = [
            { k: 'Rank', v: `#${data.rank}` },
            { k: 'AdjEM', v: `${data.adjEM > 0 ? '+' : ''}${data.adjEM.toFixed(1)}` },
            { k: 'AdjO', v: data.adjO.toFixed(1) },
            { k: 'AdjD', v: data.adjD.toFixed(1) },
            { k: 'Tempo', v: data.adjTempo.toFixed(1) },
            { k: 'FFI', v: data.four_factor_index_100 == null ? '-' : data.four_factor_index_100.toFixed(1) },
          ];
          return (
            <>
              <View className="border-b border-ink-line bg-ink">
                <Container className="flex-row items-center gap-4 py-8">
                  <TeamLogo uri={data.logoUrl} name={data.teamName} size={72} />
                  <View className="flex-1">
                    <Text className="font-display-semibold text-[13px] uppercase tracking-[2px] text-brand2">
                      {data.conference} · {data.season}
                    </Text>
                    <Text className="mt-1 font-display text-4xl uppercase text-text-onDark">{data.teamName}</Text>
                    <Text className="mt-1 font-mono text-sm text-ink-fg">{data.record}</Text>
                  </View>
                </Container>
              </View>

              <Container className="gap-6 py-8">
                <View className="flex-row flex-wrap gap-3">
                  {stats.map((s) => (
                    <View key={s.k} className="min-w-[100px] flex-1 items-center rounded-[10px] border border-ink-line bg-ink-2 px-3 py-4">
                      <Text className="mb-1.5 font-sans-semibold text-[10px] uppercase tracking-wider text-ink-fg2">{s.k}</Text>
                      <Text className="font-mono-semibold text-xl text-text-onDark">{s.v}</Text>
                    </View>
                  ))}
                </View>

                <View className="items-start gap-3 rounded-[14px] border border-ink-line bg-ink-2 p-5">
                  <Text className="font-sans text-sm leading-5 text-ink-fg">
                    The full team page (schedule, roster, four factors, charts) is not in the app yet.
                  </Text>
                  <Pressable
                    onPress={() => openLink({ kind: 'web', path: `/ncaa/team/${data.teamId}` })}
                    accessibilityRole="link"
                    className="flex-row items-center gap-2 rounded-lg border border-brand bg-brand px-5 py-2.5 active:bg-brand-hover"
                  >
                    <Text className="font-display-semibold text-sm uppercase tracking-wider text-text-onDark">Open on macfax.usu.edu</Text>
                    <ExternalLink color={palette.textOnDark} size={15} strokeWidth={1.5} />
                  </Pressable>
                </View>
              </Container>
            </>
          );
        }}
      </AsyncView>
    </ScrollScreen>
  );
}
