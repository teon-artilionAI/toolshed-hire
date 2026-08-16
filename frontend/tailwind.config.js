/**
 * Toolshed Hire design tokens.
 *
 * Derived from design-system/toolshed-hire/MASTER.md and its
 * BRAND-OVERRIDE.md. Two rules matter and are enforced by the token names
 * themselves.
 *
 * 1. `accent` is the brand amber and is for brand identity and primary
 *    actions only. It never encodes a status.
 * 2. `status.*` encodes state and is never used for a button, so the two
 *    readings on a screen full of statuses do not fight each other.
 *
 * Amber carries ink text, never white. White on this amber is about
 * 2.1:1 and fails; ink is about 9.8:1 and passes comfortably.
 */

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#141613',
        paper: '#F8FAFC',
        surface: '#FFFFFF',
        muted: '#F1F2F4',
        line: '#E2E5E9',
        slate: {
          DEFAULT: '#334155',
          soft: '#475569',
          // `faint` is the quietest text on a light ground. It was #94A3B8,
          // which is 2.5:1 on paper and fails AA outright at the 12px sizes
          // it is used at. This value is 5.2:1 on paper and 5.4:1 on
          // surface, and still reads as the quietest step in the ramp.
          faint: '#5D6B7E',
          // The counterpart for a dark ground. The owner's sidebar and the
          // demo panel are dark, and there darkening the text makes it
          // worse, so quiet text there steps up rather than down. 7:1 on
          // slate, 12:1 on ink.
          dim: '#CBD5E1',
        },
        accent: {
          DEFAULT: '#F0A600',
          hover: '#D69400',
          wash: '#FEF6E0',
          ink: '#141613',
        },
        status: {
          available: '#047857',
          'available-wash': '#ECFDF5',
          onhire: '#0369A1',
          'onhire-wash': '#EFF6FF',
          due: '#B45309',
          'due-wash': '#FFFBEB',
          overdue: '#B91C1C',
          'overdue-wash': '#FEF2F2',
          // Was #64748B, which is 4.34:1 on its own wash and misses AA at
          // the 12px the pill is set in. This clears it at 5.6:1.
          inactive: '#4E5B6F',
          'inactive-wash': '#F1F5F9',
        },
      },
      fontFamily: {
        sans: ['"Fira Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"Fira Code"', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        // Body stays at 16px. Nothing readable drops below 12px.
        xs: ['0.75rem', { lineHeight: '1.1rem' }],
        sm: ['0.875rem', { lineHeight: '1.3rem' }],
        base: ['1rem', { lineHeight: '1.5rem' }],
        lg: ['1.125rem', { lineHeight: '1.6rem' }],
        xl: ['1.375rem', { lineHeight: '1.85rem' }],
        '2xl': ['1.75rem', { lineHeight: '2.1rem' }],
        '3xl': ['2.25rem', { lineHeight: '2.6rem' }],
      },
      spacing: {
        // Density 7/10. Standard scale from the design system.
        xs: '0.25rem',
        sm: '0.5rem',
        md: '1rem',
        lg: '1.5rem',
        xl: '2rem',
        '2xl': '3rem',
      },
      borderRadius: {
        DEFAULT: '0.375rem',
        lg: '0.5rem',
      },
      boxShadow: {
        // Soft UI Evolution: softer than flat, clearer than neumorphism.
        card: '0 1px 2px rgba(20, 22, 19, 0.05), 0 1px 3px rgba(20, 22, 19, 0.06)',
        raised: '0 2px 4px rgba(20, 22, 19, 0.06), 0 4px 12px rgba(20, 22, 19, 0.08)',
        pop: '0 8px 24px rgba(20, 22, 19, 0.12)',
      },
      transitionDuration: {
        DEFAULT: '180ms',
      },
    },
  },
  plugins: [],
}
