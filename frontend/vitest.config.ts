import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config.ts'

/**
 * Vitest configuration for the unit and component tests.
 *
 * I merge this into the Vite configuration instead of repeating it, so a test
 * compiles the source with the same plugins the application build uses. A test
 * that passes against a different compile of the code proves less than it
 * looks like it does.
 *
 * I leave globals off. Every test file imports `describe`, `it` and `expect`
 * from `vitest`, so a reader can see where each name comes from and the type
 * checker needs no ambient declarations to understand a test.
 */

/**
 * The time zone the three branches trade in. I pin it here, before Vitest
 * starts its workers, so a date formats the same way on my machine and in the
 * pipeline, which runs in UTC.
 */
const BRANCH_TIME_ZONE = 'Africa/Johannesburg'
process.env.TZ = BRANCH_TIME_ZONE

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
      // I keep the browser tests out of this run. Playwright owns the e2e
      // folder and its files would fail here, because they expect a real page.
      exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
    },
  }),
)
