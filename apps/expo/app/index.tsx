import { Link } from 'expo-router';
import { Text, View } from 'react-native';

export default function Index() {
  return (
    <View className="flex-1 items-center justify-center gap-4 bg-bg">
      <Text className="font-display text-4xl uppercase text-text-onDark">Macfax</Text>
      <Link href="/gate" className="font-sans-medium text-base text-brand underline">
        Open gate screen
      </Link>
    </View>
  );
}
