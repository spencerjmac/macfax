import { ArrowRight, ExternalLink } from '@/src/components/ui/icons';
import { Pressable, Text, View } from 'react-native';

import { MyTeams } from '@/src/components/hub/MyTeams';
import { VizArt } from '@/src/components/hub/VizArt';
import { Container } from '@/src/components/ui/Screen';
import { AsyncView } from '@/src/components/ui/StateViews';
import { TeamLogo } from '@/src/components/ui/TeamLogo';
import type { HubConfig } from '@/src/config/ncaaHub';
import type { RankingRow } from '@/src/lib/api';
import { openLink, type LinkTarget } from '@/src/lib/links';
import type { AsyncResult } from '@/src/lib/useAsync';
import { palette } from '@/src/theme/tokens';

const signed = (value: number, digits: number) => `${value > 0 ? '+' : ''}${value.toFixed(digits)}`;

function Kicker({ children, className = 'text-brand' }: { children: React.ReactNode; className?: string }) {
  return <Text className={`font-display-semibold text-[13px] uppercase tracking-[2px] ${className}`}>{children}</Text>;
}

function SectionHead({ kicker, title, link }: { kicker: string; title: string; link?: { label: string; target: LinkTarget } }) {
  return (
    <View className="mb-6 flex-row flex-wrap items-end justify-between gap-3">
      <View className="gap-2">
        <Kicker>{kicker}</Kicker>
        <Text className="font-display text-3xl uppercase text-text-onDark md:text-4xl">{title}</Text>
      </View>
      {link ? (
        <Pressable onPress={() => openLink(link.target)} accessibilityRole="link" className="flex-row items-center gap-2">
          <Text className="font-display-semibold text-sm uppercase tracking-wider text-brand">{link.label}</Text>
          {link.target.kind === 'web' ? (
            <ExternalLink color={palette.brand} size={15} strokeWidth={1.5} />
          ) : (
            <ArrowRight color={palette.brand} size={16} strokeWidth={1.5} />
          )}
        </Pressable>
      ) : null}
    </View>
  );
}

function Stat({ label, value, valueClassName = 'text-text-onDark' }: { label: string; value: string; valueClassName?: string }) {
  return (
    <View>
      <Text className="mb-1 font-sans-semibold text-[10px] uppercase tracking-wider text-ink-fg2">{label}</Text>
      <Text className={`font-mono-semibold text-base ${valueClassName}`}>{value}</Text>
    </View>
  );
}

function LeaderCard({ leader, label }: { leader: RankingRow; label: string }) {
  return (
    <View className="w-full rounded-2xl border border-ink-line bg-ink-2 p-5 md:w-[360px]">
      <View className="mb-4 flex-row items-center gap-2">
        <View className="h-[7px] w-[7px] rounded-full bg-brand2" />
        <Text className="font-mono-semibold text-[11px] uppercase tracking-widest text-brand2">#1 in the model</Text>
      </View>
      <Pressable onPress={() => openLink({ kind: 'app', href: `/team/${leader.teamId}` })} className="mb-4 flex-row items-center gap-4">
        <TeamLogo uri={leader.logoUrl} name={leader.teamName} size={60} />
        <View className="flex-1">
          <Text className="font-mono-semibold text-xs uppercase tracking-wider text-brand2">{label} · No. 1</Text>
          <Text className="mt-1 font-display text-2xl uppercase text-text-onDark">{leader.teamName}</Text>
          <Text className="mt-1 font-sans text-[13px] text-ink-fg2">
            {leader.conference} · {leader.record}
          </Text>
        </View>
      </Pressable>
      <View className="flex-row overflow-hidden rounded-[10px] border border-ink-line">
        {[
          { k: 'AdjEM', v: signed(leader.adjEM, 1) },
          { k: 'AdjO', v: leader.adjO.toFixed(1) },
          { k: 'AdjD', v: leader.adjD.toFixed(1) },
        ].map((s, i) => (
          <View key={s.k} className={`flex-1 items-center bg-ink px-3 py-3 ${i > 0 ? 'border-l border-ink-line' : ''}`}>
            <Text className="mb-1.5 font-sans-semibold text-[10px] uppercase tracking-wider text-ink-fg2">{s.k}</Text>
            <Text className="font-mono-semibold text-xl text-text-onDark">{s.v}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

function TopFive({ teams }: { teams: RankingRow[] }) {
  return (
    <View className="overflow-hidden rounded-[14px] border border-ink-line bg-ink-2">
      {teams.map((team, i) => (
        <Pressable
          key={team.teamId}
          onPress={() => openLink({ kind: 'app', href: `/team/${team.teamId}` })}
          accessibilityRole="link"
          className={`flex-row items-center gap-3 px-4 py-4 active:bg-ink-3 md:gap-4 md:px-6 ${i > 0 ? 'border-t border-ink-line' : ''}`}
        >
          <Text className="w-8 font-display text-2xl text-text-onDark md:w-12">{i + 1}</Text>
          <TeamLogo uri={team.logoUrl} name={team.teamName} size={40} />
          <View className="flex-1">
            <Text numberOfLines={1} className="font-sans-bold text-base text-text-onDark">
              {team.teamName}
            </Text>
            <Text className="mt-1 font-sans text-[13px] text-ink-fg2">
              {team.conference} · {team.record}
            </Text>
          </View>
          {/* AdjO / AdjD need room: wide screens only, as on a phone the name would be squeezed out. */}
          <View className="hidden w-[90px] md:flex">
            <Stat label="AdjO" value={team.adjO.toFixed(1)} />
          </View>
          <View className="hidden w-[90px] md:flex">
            <Stat label="AdjD" value={team.adjD.toFixed(1)} />
          </View>
          <View className="items-end">
            <Stat label="AdjEM" value={signed(team.adjEM, 2)} valueClassName="text-brand2" />
          </View>
        </Pressable>
      ))}
    </View>
  );
}

interface SportHubProps {
  config: HubConfig;
  /** Rankings sorted by rank. The hub shows the first five; hero copy and tools render regardless of its state. */
  rankings: AsyncResult<RankingRow[]>;
}

/**
 * The sport landing page: hero, #1 team spotlight, top five, tool cards and
 * visualization cards. Port of web/src/components/SportHubPage.tsx on the
 * app's dark theme.
 */
export function SportHub({ config, rankings }: SportHubProps) {
  const leader = rankings.status === 'ready' ? rankings.data[0] : undefined;

  return (
    <View>
      {/* Hero */}
      <View className="border-b border-ink-line bg-ink">
        <Container className="flex-col gap-8 py-10 md:flex-row md:items-center md:gap-12 md:py-14">
          <View className="flex-1 items-start gap-4">
            <View className="flex-row items-center gap-3">
              <View className="h-1.5 w-1.5 rounded-full bg-brand2" />
              <Kicker className="text-brand2">{config.eyebrow}</Kicker>
            </View>
            <Text className="font-display text-5xl uppercase leading-[1] text-text-onDark md:text-6xl">{config.title}</Text>
            <Text className="max-w-[520px] font-sans text-base leading-6 text-ink-fg md:text-[17px]">{config.lede}</Text>
            <View className="flex-row flex-wrap gap-3">
              <Pressable
                onPress={() => openLink(config.rankingsTarget)}
                accessibilityRole="link"
                className="flex-row items-center gap-2 rounded-lg border border-brand bg-brand px-5 py-2.5 active:bg-brand-hover"
              >
                <Text className="font-display-semibold text-sm uppercase tracking-wider text-text-onDark">Full rankings</Text>
                <ArrowRight color={palette.textOnDark} size={16} strokeWidth={1.5} />
              </Pressable>
              <Pressable
                onPress={() => openLink(config.secondaryCtaTarget)}
                accessibilityRole="link"
                className="flex-row items-center gap-2 rounded-lg border border-ink-line px-5 py-2.5 active:border-brand2"
              >
                <Text className="font-display-semibold text-sm uppercase tracking-wider text-text-onDark">{config.secondaryCta}</Text>
                {config.secondaryCtaTarget.kind === 'web' ? <ExternalLink color={palette.textOnDark} size={15} strokeWidth={1.5} /> : null}
              </Pressable>
            </View>
          </View>
          {leader ? <LeaderCard leader={leader} label={config.label} /> : null}
        </Container>
      </View>

      {/* My Teams (starred teams, from the Redux store) */}
      <Container className="pt-10 md:pt-14">
        <MyTeams rankings={rankings} />
      </Container>

      {/* Top 5 */}
      <Container className="py-10 md:py-14">
        <SectionHead
          kicker="This week"
          title={`Top of the ${config.label} rankings`}
          link={{ label: `All ${config.teamCount} teams`, target: config.rankingsTarget }}
        />
        <AsyncView
          state={rankings}
          loadingLabel="Loading rankings…"
          errorTitle="Could not load rankings"
          isEmpty={(teams) => teams.length === 0}
          emptyTitle="No rankings yet"
          emptyMessage="Ratings for this season have not been computed."
        >
          {(teams) => <TopFive teams={teams.slice(0, 5)} />}
        </AsyncView>
      </Container>

      {/* Tools */}
      <View className="border-t border-ink-line bg-ink-2">
        <Container className="py-10 md:py-14">
          <SectionHead kicker="Explore" title={`${config.label} tools`} />
          <View className="flex-row flex-wrap gap-4">
            {config.tools.map((tool) => {
              const Icon = tool.icon;
              return (
                <Pressable
                  key={tool.title}
                  onPress={() => openLink(tool.target)}
                  accessibilityRole="link"
                  className="w-full flex-row items-start gap-4 rounded-[14px] border border-ink-line bg-ink p-5 active:border-brand md:w-[32%]"
                >
                  <View className="h-11 w-11 items-center justify-center rounded-[11px] bg-brand/15">
                    <Icon color={palette.brand} size={22} strokeWidth={1.5} />
                  </View>
                  <View className="flex-1">
                    <View className="mb-1.5 flex-row items-center gap-2">
                      <Text className="font-display text-[17px] uppercase text-text-onDark">{tool.title}</Text>
                      {tool.target.kind === 'web' ? <ExternalLink color={palette.muted} size={13} strokeWidth={1.5} /> : null}
                    </View>
                    <Text className="font-sans text-[13px] leading-5 text-ink-fg2">{tool.body}</Text>
                  </View>
                </Pressable>
              );
            })}
          </View>
        </Container>
      </View>

      {/* Visualizations */}
      <Container className="py-10 md:py-14">
        <SectionHead
          kicker="Latest"
          title={`${config.label} visualizations`}
          link={{ label: 'All visualizations', target: config.allVizTarget }}
        />
        <View className="flex-row flex-wrap gap-4">
          {config.viz.map((viz) => (
            <Pressable
              key={viz.title}
              onPress={() => openLink(viz.target)}
              accessibilityRole="link"
              className="w-full overflow-hidden rounded-2xl border border-ink-line bg-ink-2 active:border-brand md:w-[32%]"
            >
              <View className="h-[150px] items-center justify-center border-b border-ink-line bg-ink">
                <VizArt kind={viz.art} />
              </View>
              <View className="gap-2 p-5">
                <Text className="font-sans-semibold text-[11px] uppercase tracking-wider text-ink-fg2">{viz.kick}</Text>
                <Text className="font-display text-[19px] uppercase text-text-onDark">{viz.title}</Text>
                <Text className="font-sans text-[13.5px] leading-5 text-ink-fg2">{viz.body}</Text>
                <View className="flex-row items-center gap-1.5 pt-1">
                  <Text className="font-display-semibold text-[13px] uppercase tracking-wider text-brand">Open on web</Text>
                  <ExternalLink color={palette.brand} size={13} strokeWidth={1.5} />
                </View>
              </View>
            </Pressable>
          ))}
        </View>
      </Container>
    </View>
  );
}
