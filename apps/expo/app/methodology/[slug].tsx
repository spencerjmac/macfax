import { getMethodologyBySlug } from '@macfax/core/lib/methodologyContent';
import { Stack, useLocalSearchParams } from 'expo-router';
import { View } from 'react-native';

import { MethodologyArticle } from '@/src/components/methodology/MethodologyArticle';
import { ScrollScreen } from '@/src/components/ui/Screen';
import { EmptyState } from '@/src/components/ui/StateViews';

/** One methodology article (web's /methodology/[slug]). Content comes from packages/core; no network. */
export default function MethodologyArticleScreen() {
  const { slug } = useLocalSearchParams<{ slug: string }>();
  const content = getMethodologyBySlug(slug);

  return (
    <ScrollScreen>
      <Stack.Screen options={{ title: content ? content.title : 'Methodology' }} />
      {content ? (
        <View className="w-full max-w-[768px] self-center px-4 py-8">
          <MethodologyArticle content={content} />
        </View>
      ) : (
        <EmptyState title="Article not found" message={`There is no methodology article called "${slug}".`} />
      )}
    </ScrollScreen>
  );
}
