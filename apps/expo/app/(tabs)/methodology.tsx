import { METHODOLOGY_SECTIONS, methodologyContent } from '@macfax/core/lib/methodologyContent';
import type { MethodologyContent } from '@macfax/core/lib/methodologyTypes';
import { router } from 'expo-router';
import { Pressable, Text, View } from 'react-native';

import { Container, ScrollScreen } from '@/src/components/ui/Screen';

function MethodologyCard({ content }: { content: MethodologyContent }) {
  return (
    <Pressable
      onPress={() => router.push(`/methodology/${content.slug}`)}
      accessibilityRole="link"
      className="w-full items-start rounded-xl border border-ink-line bg-ink-2 p-5 active:border-brand md:w-[32%]"
    >
      <Text className="mb-1 font-sans-semibold text-base text-text-onDark">{content.title}</Text>
      <Text className="mb-3 font-sans text-sm leading-5 text-ink-fg2">{content.description}</Text>
      <View className="rounded-full border border-brand/30 bg-brand/10 px-2.5 py-0.5">
        <Text className="font-sans-medium text-xs text-brand2">{content.bestUsedFor}</Text>
      </View>
    </Pressable>
  );
}

/** Methodology tab: the index of articles (web's /methodology page). Content comes from packages/core; no network. */
export default function MethodologyScreen() {
  return (
    <ScrollScreen>
      <Container className="py-8">
        <Text className="font-display text-4xl uppercase text-text-onDark">Macfax Methodology</Text>
        <Text className="mb-10 mt-3 max-w-[672px] font-sans text-base leading-6 text-ink-fg md:text-lg md:leading-7">
          Macfax is independent, transparent, still improving, and built around basketball logic. These pages explain
          what each metric measures, how the numbers are calculated, and how to interpret them without overusing them.
        </Text>

        {METHODOLOGY_SECTIONS.map((section) => {
          const items = section.slugs
            .map((slug) => methodologyContent.find((m) => m.slug === slug))
            .filter((m): m is MethodologyContent => Boolean(m));
          return (
            <View key={section.id} className="mb-10">
              <Text className="mb-4 border-b border-ink-line pb-2 font-sans-medium text-xs uppercase tracking-widest text-ink-fg2">
                {section.title}
              </Text>
              <View className="flex-row flex-wrap gap-4">
                {items.map((item) => (
                  <MethodologyCard key={item.slug} content={item} />
                ))}
              </View>
            </View>
          );
        })}
      </Container>
    </ScrollScreen>
  );
}
