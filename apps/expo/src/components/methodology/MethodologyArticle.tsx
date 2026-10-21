import type { FormulaContent, MethodologyContent } from '@macfax/core/lib/methodologyTypes';
import { AlertTriangle, ArrowRight, BookOpen, Clock } from '@/src/components/ui/icons';
import { Pressable, ScrollView, Text, View } from 'react-native';

import { openLink } from '@/src/lib/links';
import { ink, palette } from '@/src/theme/tokens';

// Band colors keyed by the `color` names used in core's methodology content.
const BAND_STYLES: Record<string, { box: string; text: string }> = {
  success: { box: 'border-positive/30 bg-positive/15', text: 'text-positive' },
  brand: { box: 'border-brand/40 bg-brand/15', text: 'text-brand2' },
  secondary: { box: 'border-brandBlue/40 bg-brandBlue/15', text: 'text-sky-300' },
  warning: { box: 'border-yellow-400/30 bg-yellow-400/10', text: 'text-yellow-300' },
  negative: { box: 'border-negative/30 bg-negative/10', text: 'text-red-300' },
};
const DEFAULT_BAND = { box: 'border-ink-line bg-ink-2', text: 'text-text-onDark' };

function SectionHeading({ children }: { children: string }) {
  return (
    <Text className="mb-3 mt-8 border-b border-ink-line pb-2 font-sans-semibold text-lg text-text-onDark">{children}</Text>
  );
}

function Body({ children }: { children: string }) {
  return <Text className="font-sans text-base leading-6 text-ink-fg">{children}</Text>;
}

/**
 * The article's formula as plain monospace text. Web typesets `latex` with
 * KaTeX; the app has no math renderer, so it shows the LaTeX source as written,
 * followed by the plain-language version (`prose`) when there is one.
 */
function FormulaCard({ formula }: { formula: FormulaContent }) {
  return (
    <View className="mt-8 overflow-hidden rounded-lg border border-ink-line bg-ink-2">
      <View className="flex-row items-center justify-between border-b border-ink-line bg-ink-3 px-4 py-2">
        <Text className="font-display-semibold text-xs uppercase tracking-widest text-text-onDark">Formula</Text>
        {formula.latex ? <Text className="font-mono text-[10px] uppercase tracking-wider text-ink-fg2">LaTeX source</Text> : null}
      </View>
      <View className="gap-3 p-4">
        {formula.latex ? (
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <Text selectable className="font-mono text-sm leading-6 text-brand2">
              {formula.latex.trim()}
            </Text>
          </ScrollView>
        ) : null}
        {formula.prose ? (
          <Text selectable className="font-mono text-sm leading-6 text-text-onDark">
            {formula.prose}
          </Text>
        ) : null}
      </View>
    </View>
  );
}

/**
 * One methodology article, rendered from a MethodologyContent object in
 * packages/core. Port of web/src/components/methodology/MethodologyArticle.tsx
 * and its small helper components, folded into this one file.
 */
export function MethodologyArticle({ content }: { content: MethodologyContent }) {
  return (
    <View>
      <Text className="font-display text-4xl uppercase text-text-onDark">{content.title}</Text>
      <Text className="mt-2 font-sans text-lg text-ink-fg2">{content.subtitle}</Text>
      <Text className="mt-4 font-sans text-base leading-6 text-ink-fg">{content.summary}</Text>

      <SectionHeading>What It Measures</SectionHeading>
      <Body>{content.whatItMeasures}</Body>

      <SectionHeading>Why It Matters</SectionHeading>
      <Body>{content.whyItMatters}</Body>

      <SectionHeading>How to Interpret</SectionHeading>
      <Body>{content.howToInterpret}</Body>
      {content.interpretationBands?.length ? (
        <View className="mt-3 gap-2">
          {content.interpretationBands.map((band) => {
            const style = BAND_STYLES[band.color] ?? DEFAULT_BAND;
            return (
              <View key={band.label} className={`flex-row items-start gap-4 rounded-lg border px-4 py-3 ${style.box}`}>
                <View className="w-[110px]">
                  <Text className={`font-sans-semibold text-sm ${style.text}`}>{band.label}</Text>
                  <Text className={`font-mono text-xs opacity-80 ${style.text}`}>{band.range}</Text>
                </View>
                <Text className="flex-1 font-sans text-sm leading-5 text-ink-fg">{band.description}</Text>
              </View>
            );
          })}
        </View>
      ) : null}

      {content.basicFormula ? <FormulaCard formula={content.basicFormula} /> : null}

      {content.weights?.length ? (
        <>
          <SectionHeading>Component Weights</SectionHeading>
          <View className="overflow-hidden rounded-lg border border-ink-line">
            <View className="flex-row justify-between border-b border-ink-line bg-ink-3 px-4 py-2">
              <Text className="font-sans-medium text-xs uppercase tracking-wide text-ink-fg2">Factor</Text>
              <Text className="font-sans-medium text-xs uppercase tracking-wide text-ink-fg2">Weight</Text>
            </View>
            {content.weights.map((w, i) => (
              <View key={w.label} className={`flex-row justify-between gap-4 bg-ink-2 px-4 py-3 ${i > 0 ? 'border-t border-ink-line' : ''}`}>
                <Text className="flex-1 font-sans-medium text-sm text-text-onDark">{w.label}</Text>
                <Text className="font-mono-semibold text-sm text-brand2">{w.value}</Text>
              </View>
            ))}
          </View>
        </>
      ) : null}

      {content.technicalNotes.length ? (
        <>
          <SectionHeading>Technical Notes</SectionHeading>
          <View className="gap-2">
            {content.technicalNotes.map((note, i) => (
              <View key={i} className="flex-row gap-2.5">
                <View className="mt-2 h-1.5 w-1.5 rounded-full bg-brand" />
                <Text className="flex-1 font-sans text-sm leading-5 text-ink-fg">{note}</Text>
              </View>
            ))}
          </View>
        </>
      ) : null}

      {content.knownLimitations.length ? (
        <View className="mt-8 rounded-lg border border-yellow-400/30 bg-yellow-400/10 p-4">
          <View className="mb-3 flex-row items-center gap-2">
            <AlertTriangle color="#facc15" size={16} strokeWidth={1.5} />
            <Text className="font-sans-medium text-xs uppercase tracking-wide text-yellow-300">Known Limitations</Text>
          </View>
          <View className="gap-1.5">
            {content.knownLimitations.map((item, i) => (
              <View key={i} className="flex-row gap-2">
                <Text className="font-sans text-sm text-yellow-400">•</Text>
                <Text className="flex-1 font-sans text-sm leading-5 text-yellow-100">{item}</Text>
              </View>
            ))}
          </View>
        </View>
      ) : null}

      {content.example ? (
        <View className="mt-4 rounded-xl border border-brand/30 bg-brand/10 p-5">
          <View className="mb-3 flex-row items-center gap-2">
            <BookOpen color={palette.brand2} size={16} strokeWidth={1.5} />
            <Text className="font-sans-medium text-xs uppercase tracking-wide text-brand2">Example</Text>
          </View>
          <Text className="font-sans text-sm leading-5 text-ink-fg">{content.example}</Text>
        </View>
      ) : null}

      {content.relatedMetrics?.length ? (
        <>
          <SectionHeading>Related Methodology</SectionHeading>
          <View className="flex-row flex-wrap gap-2">
            {content.relatedMetrics.map((m) => (
              <Pressable
                key={m.slug}
                onPress={() => openLink({ kind: 'app', href: `/methodology/${m.slug}` })}
                accessibilityRole="link"
                className="flex-row items-center gap-1.5 rounded-full border border-ink-line bg-ink-2 px-3 py-1.5 active:border-brand"
              >
                <Text className="font-sans-medium text-sm text-brand2">{m.label}</Text>
                <ArrowRight color={palette.brand2} size={12} strokeWidth={1.5} />
              </Pressable>
            ))}
          </View>
        </>
      ) : null}

      <View className="mt-12 flex-row items-center gap-3 border-t border-ink-line pt-6">
        <Clock color={ink.fg2} size={14} strokeWidth={1.5} />
        <Text className="font-sans text-xs text-ink-fg2">
          Last updated: {content.lastUpdated} · Version {content.methodologyVersion}
        </Text>
      </View>
    </View>
  );
}
