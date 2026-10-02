import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright configuration for the browser and accessibility tests.
 *
 * I run these against the production build served by `vite preview`, not
 * against the dev server. The bundle a visitor receives is the thing worth
 * testing, and a screen that works under `dev` and breaks once it is built is
 * exactly the defect a browser test exists to catch.
 */

/** I name the IPv4 address so the server and the tests agree on one host.
 *  `localhost` can resolve to IPv6 first on a newer Node. */
const PREVIEW_HOST = '127.0.0.1'

/** The Vite preview default. I pass `--strictPort` so a busy port is a clear
 *  failure instead of a server quietly starting somewhere else. */
const PREVIEW_PORT = 4173

const BASE_URL = `http://${PREVIEW_HOST}:${PREVIEW_PORT}`

/** How long I give the build and the preview server to come up. */
const SERVER_START_TIMEOUT_MS = 120_000

/** A common phone size. At 390 pixels wide the customer screens swap the
 *  header navigation for the bottom tab bar. */
const NARROW_VIEWPORT = { width: 390, height: 844 }

const RUNNING_IN_CI = Boolean(process.env.CI)

export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  fullyParallel: true,
  // A stray `test.only` would silently skip every other test in the pipeline.
  forbidOnly: RUNNING_IN_CI,
  // I retry once in the pipeline to absorb a slow runner. Locally a failure
  // stays a failure, so I see a flaky test the first time it flakes.
  retries: RUNNING_IN_CI ? 1 : 0,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium-desktop',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'chromium-mobile',
      use: {
        ...devices['Desktop Chrome'],
        viewport: NARROW_VIEWPORT,
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
  webServer: {
    // I build straight before serving, so the tests can never pass against a
    // stale `dist` folder left over from an earlier change. For the same
    // reason I never reuse a server that is already running. If the port is
    // taken, the run stops and says so.
    command: `npx vite build && npx vite preview --host ${PREVIEW_HOST} --port ${PREVIEW_PORT} --strictPort`,
    url: BASE_URL,
    timeout: SERVER_START_TIMEOUT_MS,
    reuseExistingServer: false,
  },
})
