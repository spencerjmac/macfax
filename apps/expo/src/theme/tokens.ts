/**
 * Macfax design tokens for the Expo app.
 *
 * Source of truth (copied by hand, keep in sync):
 *   - web/src/app/globals.css   (the :root CSS variable block)
 *   - web/tailwind.config.js    (theme.extend.colors / fontFamily)
 *
 * The web config points Tailwind colors at CSS variables; React Native has no
 * :root, so the resolved literal values live here. tailwind.config.js in this
 * app reads this file, so NativeWind classes and StyleSheet code share it.
 */

export const palette = {
  // MacFax brand tokens
  bg: '#0b1220',
  surface: '#ffffff',
  text: '#0b1220',
  textOnDark: '#f8fafc',
  muted: '#64748b',
  border: '#e2e8f0',

  brand: '#409080',
  brandHover: '#357d70',
  brand2: '#70c070',
  brandBlue: '#3080b0',

  positive: '#22c55e',
  negative: '#ef4444',
  warning: '#94a3b8',
  uiSurface: '#F7F7F8',
} as const;

// Broadcast-ink (2026 redesign): dark bands for heroes, headers, footers
export const ink = {
  DEFAULT: '#0b1220',
  2: '#131c2e',
  3: '#1b2740',
  line: '#243149',
  fg: '#c2cde0',
  fg2: '#8d9bb5',
} as const;

// Heat-map scale: single-hue teal, national-baseline anchored
export const heat = {
  3: 'rgba(64, 144, 128, 0.52)',
  2: 'rgba(64, 144, 128, 0.34)',
  1: 'rgba(64, 144, 128, 0.16)',
  0: 'rgba(100, 116, 139, 0.05)',
  'lo-1': 'rgba(100, 116, 139, 0.10)',
  'lo-2': 'rgba(100, 116, 139, 0.14)',
  // Negative heat (2026.2): restrained red for genuinely negative values
  'neg-1': 'rgba(184, 53, 46, 0.09)',
  'neg-2': 'rgba(184, 53, 46, 0.17)',
  'neg-3': 'rgba(184, 53, 46, 0.27)',
} as const;

// Champion gold (2026.2): historical champions only
export const gold = {
  DEFAULT: '#b8912f',
  strong: '#96751f',
  bg: 'rgba(184, 145, 47, 0.13)',
  line: 'rgba(184, 145, 47, 0.55)',
} as const;

// Negative ink (2026.2): problem values only
export const negativeInk = '#b8352e';

/**
 * React Native has no font fallback stacks and no numeric weights for custom
 * fonts: each weight is its own family, named after the loaded font file.
 * Web equivalents: sans = Inter, mono = IBM Plex Mono, display = Oswald.
 */
export const fontFamily = {
  sans: 'Inter_400Regular',
  'sans-medium': 'Inter_500Medium',
  'sans-semibold': 'Inter_600SemiBold',
  'sans-bold': 'Inter_700Bold',
  mono: 'IBMPlexMono_400Regular',
  'mono-medium': 'IBMPlexMono_500Medium',
  'mono-semibold': 'IBMPlexMono_600SemiBold',
  display: 'Oswald_700Bold',
  'display-regular': 'Oswald_400Regular',
  'display-medium': 'Oswald_500Medium',
  'display-semibold': 'Oswald_600SemiBold',
} as const;

/** Tailwind `theme.extend.colors`, mirroring web/tailwind.config.js. */
export const tailwindColors = {
  brand: {
    DEFAULT: palette.brand,
    hover: palette.brandHover,
    orange: palette.brand,
    'orange-hover': palette.brandHover,
    black: palette.bg,
  },
  brand2: palette.brand2,
  brandBlue: palette.brandBlue,
  ui: {
    bg: palette.surface,
    surface: palette.uiSurface,
    card: palette.surface,
    border: palette.border,
  },
  bg: palette.bg,
  surface: palette.surface,
  text: {
    primary: palette.text,
    muted: palette.muted,
    onDark: palette.textOnDark,
  },
  muted: palette.muted,
  border: palette.border,
  primary: { DEFAULT: palette.brand, hover: palette.brandHover },
  secondary: { DEFAULT: palette.brandBlue },
  positive: palette.positive,
  negative: palette.negative,
  success: palette.positive,
  warning: palette.warning,
  neutral: palette.muted,
  ink,
  heat,
  gold,
  'negative-ink': negativeInk,
  chart: {
    1: palette.brandBlue,
    2: palette.brand,
    3: palette.brand2,
    4: '#94a3b8',
    5: '#64748b',
    6: '#4E79A7',
    7: palette.brand,
    8: palette.brand2,
    9: palette.negative,
    10: '#B07AA1',
  },
} as const;
