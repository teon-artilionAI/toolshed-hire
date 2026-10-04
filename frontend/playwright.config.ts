import { defineConfig, devices } from '@playwright/test'
import type { PlaywrightTestProject, ReporterDescription } from '@playwright/test'
import {
  STAGING_PROJECT,
  STAGING_TAG,
  missingStagingVariables,
  projectsAskedFor,
  stagingAddress,
} from './e2e/staging-run.ts'

/**
 * Playwright configuration for the browser and accessibility tests.
 *
 * I run these against the production build served by `vite preview`, not
 * against the dev server. The bundle a visitor receives is the thing worth
 * testing, and a screen that works under `dev` and breaks once it is built is
 * exactly the defect a browser test exists to catch.
 *
 * A third project, `staging`, runs the journeys tagged `@staging` against the
 * deployed staging site instead, as the pipeline does after each staging
 * deploy. It is there only when `STAGING_URL` is set, it starts no preview
 * server when it is the only project asked for, and it needs both staging
 * passwords in the environment. Asking for it without all three stops the run
 * at once and names what is missing. The names are in e2e/staging-run.ts.
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

/** A journey on staging crosses the internet to a server that may be waking
 *  up, so it gets longer than the default thirty seconds, and so does each
 *  thing it waits to see. */
const STAGING_TEST_TIMEOUT_MS = 240_000
const STAGING_EXPECT_TIMEOUT_MS = 20_000
const STAGING_NAVIGATION_TIMEOUT_MS = 60_000

const PROJECTS_ASKED_FOR = projectsAskedFor(process.argv)
const STAGING_ASKED_FOR = PROJECTS_ASKED_FOR.includes(STAGING_PROJECT)

/** Only staging was asked for, so there is nothing local to serve. */
const ONLY_STAGING = STAGING_ASKED_FOR && PROJECTS_ASKED_FOR.every((name) => name === STAGING_PROJECT)

if (STAGING_ASKED_FOR) {
  const missing = missingStagingVariables(process.env)
  if (missing.length > 0) {
    throw new Error(
      `The ${STAGING_PROJECT} project needs ${missing.join(' and ')} in the environment, and ` +
        `${missing.length === 1 ? 'it is' : 'they are'} not set. Set ${missing.length === 1 ? 'it' : 'them'} ` +
        'and run it again. It has no fallback, so it never signs in to staging with a development password.',
    )
  }
}

const STAGING_URL = stagingAddress(process.env)

/**
 * The deployed staging site, running only the journeys tagged for it.
 *
 * It records no trace and no video. Playwright writes what each step typed
 * into a trace, and the journeys type the real staging passwords, so a trace
 * would put a password in a file. A screenshot of a failure is kept, because
 * a password box shows only dots.
 */
function stagingProject(baseURL: string): PlaywrightTestProject {
  return {
    name: STAGING_PROJECT,
    grep: new RegExp(STAGING_TAG),
    timeout: STAGING_TEST_TIMEOUT_MS,
    expect: { timeout: STAGING_EXPECT_TIMEOUT_MS },
    use: {
      ...devices['Desktop Chrome'],
      baseURL,
      navigationTimeout: STAGING_NAVIGATION_TIMEOUT_MS,
      trace: 'off',
      video: 'off',
      screenshot: 'only-on-failure',
    },
  }
}

/** The HTML report names every step with what it typed, so it is left out of
 *  any run the staging project is in, and the list on the console is all. */
const REPORTERS: ReporterDescription[] =
  STAGING_URL === undefined
    ? [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]]
    : [['list']]

export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  fullyParallel: true,
  // A stray `test.only` would silently skip every other test in the pipeline.
  forbidOnly: RUNNING_IN_CI,
  // I retry once in the pipeline to absorb a slow runner. Locally a failure
  // stays a failure, so I see a flaky test the first time it flakes.
  retries: RUNNING_IN_CI ? 1 : 0,
  reporter: REPORTERS,
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
    ...(STAGING_URL === undefined ? [] : [stagingProject(STAGING_URL)]),
  ],
  webServer: ONLY_STAGING
    ? undefined
    : {
        // I build straight before serving, so the tests can never pass against
        // a stale `dist` folder left over from an earlier change. For the same
        // reason I never reuse a server that is already running. If the port
        // is taken, the run stops and says so.
        command: `npx vite build && npx vite preview --host ${PREVIEW_HOST} --port ${PREVIEW_PORT} --strictPort`,
        url: BASE_URL,
        timeout: SERVER_START_TIMEOUT_MS,
        reuseExistingServer: false,
      },
})
