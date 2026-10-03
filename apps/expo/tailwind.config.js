const { tailwindColors, fontFamily } = require('./src/theme/tokens.ts');

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,jsx,ts,tsx}',
    './src/**/*.{js,jsx,ts,tsx}',
    // Core returns Tailwind class strings (e.g. lib/bprTiers), so scan it too.
    '../../packages/core/src/**/*.{js,jsx,ts,tsx}',
  ],
  presets: [require('nativewind/preset')],
  theme: {
    extend: {
      colors: tailwindColors,
      fontFamily,
    },
  },
  plugins: [],
};
