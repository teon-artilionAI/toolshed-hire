/**
 * Renders the whole application on one address, for tests.
 *
 * A test of the guards, the shell or the sign in screen needs the real router,
 * the real session provider and the real cache around it, because the thing
 * under test is how they work together. So this renders `App` itself, the way
 * main.tsx does, on a router that keeps its history in memory.
 *
 * Start-up asks the API whether there is a session. A test says how that is
 * answered with the route tables in session-samples.ts, and then waits for
 * whatever a person would see.
 */

import { render, screen } from '@testing-library/react'
import type { RenderResult } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import type { QueryClient } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import App from '../App'
import { createQueryClient } from '../shared/api/query-client'
import { ADDRESS_TEST_ID, CurrentAddress, FRAGMENT_TEST_ID } from './current-address'

/**
 * How long a test waits for a screen. Each screen is its own module and is
 * loaded on first use, which takes longer in a test run than the default wait.
 */
export const SCREEN_WAIT = { timeout: 5000 }

export interface RenderedApp extends RenderResult {
  /** The cache the application was given, for a test that looks inside it. */
  queryClient: QueryClient
}

/** @param at The address to open, for example `/counter` or `/signin?next=/account`. */
export function renderApp(at: string): RenderedApp {
  const queryClient = createQueryClient()
  const rendered = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[at]}>
        <CurrentAddress />
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...rendered, queryClient }
}

/** The address the application is on, path and query string. */
export function currentAddress(): string {
  return screen.getByTestId(ADDRESS_TEST_ID).textContent ?? ''
}

/** The fragment of the address the application is on, with its `#`, or an
 *  empty string when there is none. */
export function currentFragment(): string {
  return screen.getByTestId(FRAGMENT_TEST_ID).textContent ?? ''
}

/** Wait for the top level heading of a screen, which proves it has loaded. */
export function findScreenHeading(name: string | RegExp): Promise<HTMLElement> {
  return screen.findByRole('heading', { level: 1, name }, SCREEN_WAIT)
}
