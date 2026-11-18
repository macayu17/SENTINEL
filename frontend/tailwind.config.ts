import type { Config } from 'tailwindcss';

// Colors resolve to the CSS variables in app/globals.css, the single source of the palette.
const v = (name: string) => `var(--${name})`;

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: v('ink'), 2: v('ink-2'), 3: v('ink-3'), 4: v('ink-4') },
        line: { DEFAULT: v('line'), soft: v('line-soft'), strong: v('line-strong'), dim: v('line-dim') },
        fg: { DEFAULT: v('fg'), 2: v('fg-2'), muted: v('fg-muted'), faint: v('fg-faint') },
        paper: {
          DEFAULT: v('paper'), 2: v('paper-2'), 3: v('paper-3'),
          rule: v('paper-rule'), fg2: v('paper-fg-2'), muted: v('paper-muted'),
        },
        accent: { DEFAULT: v('accent'), deep: v('accent-deep'), wash: v('accent-wash'), chip: v('accent-chip') },
        caution: { DEFAULT: v('caution'), paper: v('caution-paper') },
        alert: { bg: v('alert-bg'), line: v('alert-line'), fg: v('alert-fg') },
      },
      fontFamily: {
        sans: ['var(--font-sans)', 'system-ui', 'sans-serif'],
        display: ['var(--font-display)', 'var(--font-sans)', 'sans-serif'],
      },
      borderRadius: { panel: '14px', card: '32px' },
    },
  },
  plugins: [],
};

export default config;
