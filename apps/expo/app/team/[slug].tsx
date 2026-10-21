import { Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';

import { GameLogTable } from '@/src/components/team/GameLogTable';
import { ExternalLink } from '@/src/components/ui/icons';
import { Container } from '@/src/components/ui/Screen';
import { AsyncView } from '@/src/components/ui/StateViews';
import { TeamLogo } from '@/src/components/ui/TeamLogo';
import { fetchRankings, fetchTeamGameLog, seasonYearFromLabel, type RankingRow } from '@/src/lib/api';
import { openLink } from '@/src/lib/links';
import { useAsync } from '@/src/lib/useAsync';
import { palette } from '@/src/theme/tokens';

const TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'games', label: 'Game log' },
] as const;
type TabKey = (typeof TABS)[number]['key'];

function OverviewTab({ team }: { team: RankingRow }) {
  const stats = [
    { k: 'Rank', v: `#${team.rank}` },
    { k: 'AdjEM', v: `${team.adjEM > 0 ? '+' : ''}${team.adjEM.toFixed(1)}` },
    { k: 'AdjO', v: team.adjO.toFixed(1) },
    { k: 'AdjD', v: team.adjD.toFixed(1) },
    { k: 'Tempo', v: team.adjTempo.toFixed(1) },
    { k: 'FFI', v: team.four_factor_index_100 == null ? '-' : team.four_factor_index_100.toFixed(1) },
  ];
  return (
    <ScrollView className="flex-1" contentContainerClassName="pb-10">
      <Container className="gap-6 py-6">
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
            The rest of the team page (four factors, offense and defense, résumé, charts, players) is not in the app yet.
          </Text>
          <Pressable
            onPress={() => openLink({ kind: 'web', path: `/ncaa/team/${team.teamId}` })}
            accessibilityRole="link"
            className="flex-row items-center gap-2 rounded-lg border border-brand bg-brand px-5 py-2.5 active:bg-brand-hover"
          >
            <Text className="font-display-semibold text-sm uppercase tracking-wider text-text-onDark">Open on macfax.usu.edu</Text>
            <ExternalLink color={palette.textOnDark} size={15} strokeWidth={1.5} />
          </Pressable>
        </View>
      </Container>
    </ScrollView>
  );
}

function GameLogTab({ team }: { team: RankingRow }) {
  const seasonYear = seasonYearFromLabel(team.season);
  const games = useAsync(async () => (seasonYear ? fetchTeamGameLog(team.teamId, seasonYear) : []), [team.teamId, seasonYear]);

  return (
    <Container className="flex-1 pt-4">
      <AsyncView
        state={games}
        loadingLabel="Loading game log…"
        errorTitle="Could not load the game log"
        isEmpty={(list) => list.length === 0}
        emptyTitle="No games found for this team."
      >
        {(list) => (
          <View className="flex-1">
            <GameLogTable games={list} />
            <Text className="py-2 font-sans text-xs text-ink-fg2">
              {team.season} · {list.length} games · tap a game to open it on the website
            </Text>
          </View>
        )}
      </AsyncView>
    </Container>
  );
}

/**
 * Team screen with Overview and Game log tabs. `season` (the API's year, e.g.
 * 2025 for 2024-25) comes from the Rankings screen; without it the current
 * season is shown; `tab=games` opens the Game log tab. The full port of web's team page comes later.
 */
export default function TeamScreen() {
  const { slug, season, tab: tabParam } = useLocalSearchParams<{ slug: string; season?: string; tab?: string }>();
  const seasonYear = season && /^\d{4}$/.test(season) ? Number(season) : undefined;
  // ?tab=games opens the game log directly.
  const [tab, setTab] = useState<TabKey>(TABS.find(({ key }) => key === tabParam)?.key ?? 'overview');

  // Reuses the Rankings screen's cached download for the same season.
  const team = useAsync(
    async ({ force }) => {
      const { teams } = await fetchRankings(seasonYear, { force });
      return teams.find((t) => t.teamId === slug) ?? null;
    },
    [slug, seasonYear],
  );

  const title = team.status === 'ready' && team.data ? team.data.teamName : 'Team';

  return (
    <View className="flex-1 bg-bg">
      <Stack.Screen options={{ title }} />
      <AsyncView
        state={team}
        loadingLabel="Loading team…"
        errorTitle="Could not load team"
        isEmpty={(data) => data === null}
        emptyTitle="Team not found"
        emptyMessage={`No team with the id "${slug}" is in the ${seasonYear ? 'selected season' : 'current'} rankings.`}
      >
        {(data) =>
          data ? (
            <View className="flex-1">
              <View className="border-b border-ink-line bg-ink">
                <Container className="flex-row items-center gap-4 py-6">
                  <TeamLogo uri={data.logoUrl} name={data.teamName} size={64} />
                  <View className="flex-1">
                    <Text className="font-display-semibold text-[13px] uppercase tracking-[2px] text-brand2">
                      {data.conference} · {data.season}
                    </Text>
                    <Text className="mt-1 font-display text-3xl uppercase text-text-onDark md:text-4xl">{data.teamName}</Text>
                    <Text className="mt-1 font-mono text-sm text-ink-fg">{data.record}</Text>
                  </View>
                </Container>
                <Container className="flex-row">
                  {TABS.map(({ key, label }) => (
                    <Pressable
                      key={key}
                      onPress={() => setTab(key)}
                      accessibilityRole="tab"
                      accessibilityState={{ selected: tab === key }}
                      className={`mr-6 border-b-2 py-3 ${tab === key ? 'border-brand' : 'border-transparent'}`}
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
                </Container>
              </View>
              {tab === 'overview' ? <OverviewTab team={data} /> : <GameLogTab team={data} />}
            </View>
          ) : null
        }
      </AsyncView>
    </View>
  );
}
