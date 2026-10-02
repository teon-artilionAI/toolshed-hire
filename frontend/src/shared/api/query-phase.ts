/**
 * Which of the shared states a query is in.
 *
 * The cache describes a query with two fields, and reading them straight in a
 * screen invites a mistake. The one I care most about is a refetch that fails
 * while an older answer is still cached. The cache keeps the old answer, and a
 * screen that only asks "is there data" would go on showing it. For
 * availability that is a stale promise, so a failed query is always reported
 * as failed here, whatever is still cached.
 */

import type { UseQueryResult } from '@tanstack/react-query'

/**
 * - `idle`: the query is switched off, so there is nothing to wait for.
 * - `loading`: a request is in flight and there is no good answer to show yet.
 * - `failed`: the last request failed and nothing is in flight.
 * - `ready`: the last request succeeded. A refetch may be running behind it.
 */
export type QueryPhase = 'idle' | 'loading' | 'failed' | 'ready'

export function queryPhase(query: Pick<UseQueryResult, 'status' | 'fetchStatus'>): QueryPhase {
  if (query.status === 'success') return 'ready'
  if (query.fetchStatus === 'fetching') return 'loading'
  if (query.status === 'error') return 'failed'
  return 'idle'
}
