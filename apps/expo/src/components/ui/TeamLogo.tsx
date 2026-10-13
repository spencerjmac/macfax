import { Image } from 'expo-image';
import { useState } from 'react';
import { Text, View } from 'react-native';

interface TeamLogoProps {
  /** Absolute logo URL (see resolveLogoUrl), or null. */
  uri: string | null;
  name: string;
  size?: number;
}

/**
 * Team logo on a white tile, so dark logos stay visible on the navy
 * background. With no logo, or if the image fails to load, it shows the
 * team's initial instead (the web tables' fallback).
 */
export function TeamLogo({ uri, name, size = 28 }: TeamLogoProps) {
  const [failed, setFailed] = useState(false);
  const radius = Math.round(size * 0.2);
  const pad = Math.max(2, Math.round(size * 0.1));

  if (!uri || failed) {
    return (
      <View style={{ width: size, height: size, borderRadius: radius }} className="items-center justify-center bg-ink-3">
        <Text style={{ fontSize: Math.round(size * 0.45) }} className="font-sans-bold text-ink-fg">
          {name.charAt(0)}
        </Text>
      </View>
    );
  }

  return (
    <View style={{ width: size, height: size, borderRadius: radius, padding: pad }} className="bg-white">
      <Image
        source={{ uri }}
        style={{ flex: 1 }}
        contentFit="contain"
        accessibilityLabel={name}
        onError={() => setFailed(true)}
        recyclingKey={uri}
        transition={100}
      />
    </View>
  );
}
