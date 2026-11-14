import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Crypto from 'expo-crypto';

/**
 * Anonymous per-install id, not an account. The app has no logins; the
 * backend keys saved data (e.g. My Teams) by this random UUID. It is created
 * on first use and kept in AsyncStorage, so it lasts until the app is
 * uninstalled or its storage is cleared.
 */
const DEVICE_ID_KEY = 'macfax.deviceId';

// One shared lookup, so callers that start at the same time get the same id
// (and only one is ever created). A failed lookup is dropped so the next call retries.
let deviceIdPromise: Promise<string> | null = null;

async function loadOrCreateDeviceId(): Promise<string> {
  const saved = await AsyncStorage.getItem(DEVICE_ID_KEY);
  if (saved) return saved;
  const created = Crypto.randomUUID();
  await AsyncStorage.setItem(DEVICE_ID_KEY, created);
  return created;
}

export function getDeviceId(): Promise<string> {
  if (!deviceIdPromise) {
    deviceIdPromise = loadOrCreateDeviceId();
    deviceIdPromise.catch(() => {
      deviceIdPromise = null;
    });
  }
  return deviceIdPromise;
}
