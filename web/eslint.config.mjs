import { defineConfig, globalIgnores } from 'eslint/config';
import nextVitals from 'eslint-config-next/core-web-vitals';
import nextTs from 'eslint-config-next/typescript';

const CORE_MESSAGE = 'packages/core must stay framework-free (shared with the Expo app); keep this in web/.';
const DOM_GLOBALS = ['window', 'document', 'localStorage', 'sessionStorage', 'navigator'];

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  // Purity rules for shared code. Matches only when linting from the repo root
  // (`npm run lint:core`), where the base path makes these globs resolve.
  {
    files: ['packages/core/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': ['error', {
        paths: ['react', 'react-dom', 'next'].map((name) => ({ name, message: CORE_MESSAGE })),
        patterns: [{ group: ['next/*', 'react/*', 'react-dom/*'], message: CORE_MESSAGE }],
      }],
      'no-restricted-globals': ['error', ...[...DOM_GLOBALS, 'process'].map((name) => ({ name, message: CORE_MESSAGE }))],
      'no-restricted-properties': ['error',
        { object: 'process', property: 'env', message: 'Read env in web/src/lib/api-env.ts and pass values into core.' },
        ...[...DOM_GLOBALS, 'process'].map((property) => ({ object: 'globalThis', property, message: CORE_MESSAGE })),
      ],
      // No pages/ dir at the repo root; this JSX-only rule just warns about it for core files.
      '@next/next/no-html-link-for-pages': 'off',
    },
  },
  globalIgnores([
    '.next/**',
    'out/**',
    'build/**',
    'dist/**',
    'next-env.d.ts',
    // Gitignored design mocks — never ship
    '.design-ref/**',
  ]),
]);
