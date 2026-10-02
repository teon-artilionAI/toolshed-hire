/**
 * Runs once before every test file.
 *
 * I register the jest-dom matchers here, so a component test can say
 * `toBeVisible` or `toHaveAccessibleName` and fail with a message about the
 * page rather than about a raw DOM node.
 *
 * I also unmount whatever a test rendered. Testing Library only does that by
 * itself when the test functions are globals, and this project imports them
 * instead, so without this line one test would find the markup the previous
 * test left behind.
 *
 * The API client writes a structured line to the console for every request it
 * makes, and the session writes one for every change of state. That is what I
 * want in a browser and noise in a test run, so I drop the lines whose event
 * name starts with `api.` or `session.` and let everything else through. A
 * warning from React still prints.
 *
 * After each test I put back anything a test replaced on the global object,
 * such as `fetch`, and return the clock to real time. I also put the session
 * back to how it starts, because it lives in a module and would otherwise
 * carry a signed in account from one test into the next. Web storage is
 * emptied for the same reason, because the session keeps its two markers
 * there.
 *
 * Every test starts in a browser that has held a session before, which means
 * the session hint is set and start-up asks the API whether there is a
 * session. Almost every test says how that question is answered, so this is
 * the starting point that fits them. A test about a first visit removes the
 * hint itself.
 */

import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach, vi } from 'vitest'
import type { MockInstance } from 'vitest'
import { MARKER_VALUE, SESSION_HINT_KEY } from '../shared/session-markers'
import { resetSessionForTests } from '../shared/session-store'

/** The prefixes of the event names the API client and the session log. */
const QUIET_EVENT_PREFIXES = ['api.', 'session.']

const CONSOLE_LEVELS = ['info', 'warn', 'error'] as const

let consoleSpies: MockInstance[] = []

beforeEach(() => {
  window.localStorage.setItem(SESSION_HINT_KEY, MARKER_VALUE)
  consoleSpies = CONSOLE_LEVELS.map((level) => {
    const original = console[level].bind(console)
    return vi.spyOn(console, level).mockImplementation((...args: unknown[]) => {
      const [first] = args
      if (typeof first === 'string' && QUIET_EVENT_PREFIXES.some((prefix) => first.startsWith(prefix))) {
        return
      }
      original(...args)
    })
  })
})

afterEach(() => {
  cleanup()
  resetSessionForTests()
  window.localStorage.clear()
  window.sessionStorage.clear()
  consoleSpies.forEach((spy) => spy.mockRestore())
  vi.unstubAllGlobals()
  vi.useRealTimers()
})
