import { router } from 'expo-router';
import { ChevronLeft } from '@/src/components/ui/icons';
import { Pressable, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { palette } from '@/src/theme/tokens';

interface AppHeaderProps {
  /** Screen title. On tab screens it sits beside the wordmark. */
  title?: string;
  /** Show a back button (stack screens). */
  showBack?: boolean;
}

/**
 * The one header used by every screen: dark ink band with the teal rule from
 * the website's navigation. Tab screens show the wordmark; stack screens show
 * a back button, which falls back to Home when there is no history (for
 * example after opening a deep link).
 */
export function AppHeader({ title, showBack = false }: AppHeaderProps) {
  const insets = useSafeAreaInsets();

  const goBack = () => {
    if (router.canGoBack()) router.back();
    else router.replace('/');
  };

  return (
    <View style={{ paddingTop: insets.top }} className="border-b-4 border-brand bg-ink">
      <View className="h-14 w-full max-w-[1240px] flex-row items-center gap-3 self-center px-4">
        {showBack ? (
          <Pressable onPress={goBack} accessibilityRole="button" accessibilityLabel="Back" hitSlop={12} className="-ml-2 p-1">
            <ChevronLeft color={palette.textOnDark} size={26} strokeWidth={1.5} />
          </Pressable>
        ) : (
          <Text className="font-display text-2xl uppercase tracking-wide text-text-onDark">
            mac<Text className="text-brand">fax</Text>
          </Text>
        )}
        {title ? (
          <Text
            numberOfLines={1}
            className={
              showBack
                ? 'flex-1 font-display-semibold text-lg uppercase tracking-wide text-text-onDark'
                : 'flex-1 text-right font-display-medium text-sm uppercase tracking-widest text-ink-fg2'
            }
          >
            {title}
          </Text>
        ) : null}
      </View>
    </View>
  );
}
