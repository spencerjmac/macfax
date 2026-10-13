import { type Href, router } from 'expo-router';
import { Linking } from 'react-native';

import { WEB_ORIGIN } from '@/src/lib/api';

/**
 * Where a card or button goes: a screen inside the app, or a page on the
 * website for features the app does not have yet.
 */
export type LinkTarget = { kind: 'app'; href: Href } | { kind: 'web'; path: string };

export function openLink(target: LinkTarget): void {
  if (target.kind === 'app') {
    router.push(target.href);
  } else {
    Linking.openURL(`${WEB_ORIGIN}${target.path}`);
  }
}
