/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
    './src/lib/**/*.{js,ts,jsx,tsx}',
  ],
  safelist: [],
  theme: {
    extend: {
      colors: {
        // MacFax brand colors using CSS variables
        brand: {
          DEFAULT: 'var(--brand)',
          hover: '#357d70',
          orange: 'var(--brand)', // Fallback mapping for any remaining orange references
          'orange-hover': '#357d70',
          black: 'var(--bg)',
        },
        brand2: 'var(--brand2)',
        brandBlue: 'var(--brandBlue)',
        // UI palette
        ui: {
          bg: 'var(--surface)',
          surface: '#F7F7F8',
          card: 'var(--surface)',
          border: 'var(--border)',
        },
        bg: 'var(--bg)',
        surface: 'var(--surface)',
        text: {
          primary: 'var(--text)',
          muted: 'var(--muted)',
          onDark: 'var(--textOnDark)',
        },
        muted: 'var(--muted)',
        border: 'var(--border)',
        // Semantic colors
        primary: {
          DEFAULT: 'var(--brand)',
          hover: '#357d70',
        },
        secondary: {
          DEFAULT: 'var(--brandBlue)',
        },
        positive: 'var(--positive)',
        negative: 'var(--negative)',
        success: 'var(--positive)',
        warning: 'var(--warning)',
        neutral: 'var(--muted)',
        // Broadcast-ink palette (2026 redesign)
        ink: {
          DEFAULT: 'var(--ink)',
          2: 'var(--ink-2)',
          3: 'var(--ink-3)',
          line: 'var(--ink-line)',
          fg: 'var(--ink-fg)',
          fg2: 'var(--ink-fg2)',
        },
        // Chart palette (categorical) - updated to remove orange
        chart: {
          1: 'var(--brandBlue)',
          2: 'var(--brand)',
          3: 'var(--brand2)',
          4: '#94a3b8',
          5: '#64748b',
          6: '#4E79A7',
          7: 'var(--brand)',
          8: 'var(--brand2)',
          9: 'var(--negative)',
          10: '#B07AA1',
        },
      },
      fontFamily: {
        sans: ['var(--font-inter)', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['var(--font-ibm-plex-mono)', 'IBM Plex Mono', 'monospace'],
        display: ['var(--font-display)', 'Oswald', 'Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
