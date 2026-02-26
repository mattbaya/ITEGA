/**
 * tailwind.config.ts -- Tailwind CSS v3 Configuration
 *
 * Extends the default Tailwind palette with custom "navy" and "teal" color
 * scales used throughout the Newshare Dashboard UI. The navy palette provides
 * the primary text and background colors, while teal is used for accents,
 * interactive elements, and success states.
 *
 * NOTE: This is a Tailwind CSS v3 configuration file (JS/TS-based). It is
 * NOT compatible with Tailwind CSS v4, which uses a CSS-based configuration
 * system. The package.json pins tailwindcss to ^3.4.0 to ensure compatibility.
 */

import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{ts,tsx}', './index.html'],
  theme: {
    extend: {
      colors: {
        navy: {
          50: '#f0f4f8',
          100: '#d9e2ec',
          200: '#bcccdc',
          300: '#9fb3c8',
          400: '#829ab1',
          500: '#627d98',
          600: '#486581',
          700: '#334e68',
          800: '#243b53',
          900: '#102a43',
        },
        teal: {
          50: '#effcf6',
          100: '#c6f7e2',
          200: '#8eedc7',
          300: '#65d6ad',
          400: '#3ebd93',
          500: '#27ab83',
          600: '#199473',
          700: '#147d64',
          800: '#0c6b58',
          900: '#014d40',
        },
      },
    },
  },
  plugins: [],
};

export default config;
