/**
 * The customer profile, as a cached query.
 *
 * The key starts with the account segment, and query-client.ts treats anything
 * under it as never fresh. A branch can put an account on hold and a link can
 * confirm an email address in another tab, so a cached profile is always asked
 * for again when a screen uses it.
 *
 * The write is not here. A screen calls `updateMyProfile` once for each press
 * of the save button and then hands the answer to `rememberProfile`.
 */

import { queryOptions } from '@tanstack/react-query'
import type { QueryClient } from '@tanstack/react-query'
import { getMyProfile } from './account'
import type { MyProfile } from './contract'
import { ACCOUNT_KEY } from './query-client'

const PROFILE_SEGMENT = 'profile'

export const accountQueries = {
  /** The signed in customer's own profile. */
  profile: () =>
    queryOptions({
      queryKey: [ACCOUNT_KEY, PROFILE_SEGMENT],
      queryFn: ({ signal }) => getMyProfile(signal),
    }),
}

/** Put the profile a write answered with into the cache. */
export function rememberProfile(client: QueryClient, profile: MyProfile): void {
  client.setQueryData(accountQueries.profile().queryKey, profile)
}
