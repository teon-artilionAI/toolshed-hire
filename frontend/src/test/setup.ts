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
 * makes. That is what I want in a browser and noise in a test run, so I drop
 * the lines whose event name starts with `api.` and let everything else
 * through. A warning from React still prints.
 *
 * After each test I put back anything a test replaced on the global object,
 * such as `fetch`, and return the clock to real time.
 */

import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach, vi } from 'vitest'
import type { MockInstance } from 'vitest'

/** The prefix of every event name the API client logs. */
const API_EVENT_PREFIX = 'api.'

const CONSOLE_LEVELS = ['info', 'warn', 'error'] as const

let consoleSpies: MockInstance[] = []

beforeEach(() => {
  consoleSpies = CONSOLE_LEVELS.map((level) => {
    const original = console[level].bind(console)
    return vi.spyOn(console, level).mockImplementation((...args: unknown[]) => {
      const [first] = args
      if (typeof first === 'string' && first.startsWith(API_EVENT_PREFIX)) return
      original(...args)
    })
  })
})

afterEach(() => {
  cleanup()
  consoleSpies.forEach((spy) => spy.mockRestore())
  vi.unstubAllGlobals()
  vi.useRealTimers()
})
