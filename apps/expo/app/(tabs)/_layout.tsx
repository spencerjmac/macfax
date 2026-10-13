import { Tabs } from 'expo-router';
import { BookOpen, House, Trophy } from '@/src/components/ui/icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppHeader } from '@/src/components/ui/AppHeader';
import { fontFamily, ink, palette } from '@/src/theme/tokens';

const TAB_BAR_HEIGHT = 60;

/** The three bottom tabs. Each tab screen gets the shared header with the wordmark. */
export default function TabsLayout() {
  const insets = useSafeAreaInsets();

  return (
    <Tabs
      screenOptions={{
        header: ({ options }) => <AppHeader title={options.title} />,
        sceneStyle: { backgroundColor: palette.bg },
        // The default 49px bar clips the label under the icon with this font, so set the height explicitly.
        tabBarStyle: {
          backgroundColor: ink[2],
          borderTopColor: ink.line,
          height: TAB_BAR_HEIGHT + insets.bottom,
          paddingTop: 4,
        },
        tabBarActiveTintColor: palette.brand2,
        tabBarInactiveTintColor: ink.fg2,
        tabBarLabelStyle: { fontFamily: fontFamily['sans-medium'], fontSize: 11 },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: 'Home', tabBarIcon: ({ color, size }) => <House color={color} size={size} strokeWidth={1.5} /> }}
      />
      <Tabs.Screen
        name="rankings"
        options={{ title: 'Rankings', tabBarIcon: ({ color, size }) => <Trophy color={color} size={size} strokeWidth={1.5} /> }}
      />
      <Tabs.Screen
        name="methodology"
        options={{
          title: 'Methodology',
          tabBarIcon: ({ color, size }) => <BookOpen color={color} size={size} strokeWidth={1.5} />,
        }}
      />
    </Tabs>
  );
}
