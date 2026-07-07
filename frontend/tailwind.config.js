/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        amber: {
          400: '#FBBF24',
          500: '#F59E0B',
        },
        // Pyxidr brand-driven, theme-aware tokens — resolve via CSS variables
        // defined in index.css, so a single `.dark` class toggle on <html>
        // flips every one of these at once. Prefer these over raw gray-* /
        // amber-* utilities for anything that should adapt to light/dark mode.
        surface: {
          0: 'var(--surface-0)',   // page canvas
          1: 'var(--surface-1)',   // card / panel bg
          2: 'var(--surface-2)',   // nested card / row bg
          3: 'var(--surface-3)',   // hover-elevated bg
        },
        border: {
          DEFAULT: 'var(--border)',
          strong: 'var(--border-strong)',
        },
        text: {
          primary: 'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          muted: 'var(--text-muted)',
        },
        brand: {
          DEFAULT: 'var(--brand-accent)',       // Pyxidr blue — primary accent
          hover: 'var(--brand-accent-hover)',
          highlight: 'var(--brand-highlight)',  // Pyxidr magenta — CTA accent
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Cascadia Code', 'monospace'],
      },
      backdropBlur: {
        glass: '20px',
      },
      borderRadius: {
        '4xl': '28px',
      },
    },
  },
  plugins: [],
}
