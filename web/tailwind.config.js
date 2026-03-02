/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
    './src/lib/**/*.{js,ts,jsx,tsx}',
  ],
  safelist: [
    // Rankings table color classes - full gradient
    'bg-emerald-500/10', 'bg-emerald-500/20', 'bg-emerald-500/30',
    'bg-teal-500/10', 'bg-teal-500/15', 'bg-teal-500/20',
    'bg-yellow-500/10', 'bg-yellow-500/15', 'bg-yellow-500/20',
    'bg-amber-500/10', 'bg-amber-500/15', 'bg-amber-500/20',
    'bg-orange-500/10', 'bg-orange-500/20', 'bg-orange-500/30',
    'bg-rose-500/10', 'bg-rose-500/20', 'bg-rose-500/30',
    'text-emerald-800', 'text-emerald-900', 'text-emerald-950',
    'text-teal-800', 'text-teal-900', 'text-teal-950',
    'text-yellow-800', 'text-yellow-900', 'text-yellow-950',
    'text-amber-800', 'text-amber-900', 'text-amber-950',
    'text-orange-800', 'text-orange-900', 'text-orange-950',
    'text-rose-800', 'text-rose-900', 'text-rose-950',
  ],
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
      },
    },
  },
  plugins: [],
}
