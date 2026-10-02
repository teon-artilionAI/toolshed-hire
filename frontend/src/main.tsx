/**
 * Application entry point.
 *
 * The one server state cache is made here and handed to the whole tree, so
 * every screen that asks for the same data shares one request and one answer.
 * Its retry and freshness rules are in shared/api/query-client.ts.
 */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App'
import { createQueryClient } from './shared/api/query-client'

const container = document.getElementById('root')

if (!container) {
  throw new Error(
    'Toolshed Hire could not start: index.html has no element with id "root" to mount into.',
  )
}

const queryClient = createQueryClient()

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
