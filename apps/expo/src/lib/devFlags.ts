/**
 * The /gate screen is a developer test bench (theme samples, chart experiments).
 * It is available in development builds, or in any build made with
 * EXPO_PUBLIC_ENABLE_GATE=1 (used for automated screenshots of exported bundles).
 */
export const GATE_ENABLED = __DEV__ || process.env.EXPO_PUBLIC_ENABLE_GATE === '1';
