import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

export default function RootLayout() {
  return (
    <>
      <Stack>
        <Stack.Screen name="index" options={{ title: 'Macfax' }} />
        <Stack.Screen name="gate" options={{ title: 'Gate' }} />
      </Stack>
      <StatusBar style="light" />
    </>
  );
}
