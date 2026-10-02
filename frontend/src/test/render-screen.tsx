/**
 * Renders a screen the way the application does, for tests.
 *
 * A screen needs a router and the server state cache around it. I give each
 * test its own cache, built by the same function the application uses, so a
 * test runs under the real retry and freshness rules and no answer leaks from
 * one test into the next.
 *
 * The address the router is on is written into the page by `CurrentAddress`,
 * so a test can check where a form or a link took the person.
 */

import type { ReactElement } from 'react'
import { render } from '@testing-library/react'
import type { RenderResult } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { createQueryClient } from '../shared/api/query-client'
import { CurrentAddress } from './current-address'

export function renderScreen(
  screen: ReactElement,
  options: {
    /** The route pattern the screen is mounted on, for example `/model/:slug`. */
    path: string
    /** The address the test opens, for example `/model/cp-100?from=2026-03-12`. */
    at: string
  },
): RenderResult {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[options.at]}>
        <CurrentAddress />
        <Routes>
          <Route path={options.path} element={screen} />
          {/* Anywhere else a screen sends the person. The address above says
              where, and this keeps the router from warning about no match. */}
          <Route path="*" element={<p>Another screen</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}
