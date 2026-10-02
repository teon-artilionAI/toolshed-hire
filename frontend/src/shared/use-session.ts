/**
 * What a screen may ask about the person using it.
 *
 * A screen reads the session through `useSession` and never through the store,
 * so every screen sees the same answer and none of them can reach the access
 * token. The provider that fills this in is in session.tsx.
 */

import { createContext, useContext } from 'react'
import type { SessionUser } from './api/contract'
import type { SessionStatus } from './session-store'
import type { Role } from './types'

export interface Session {
  /** `checking` until start-up has asked the server whether there is a session. */
  status: SessionStatus
  signedIn: boolean
  /** The signed in account as the API describes it, or null when signed out. */
  user: SessionUser | null
  /** The role of the signed in account, or null when nobody is signed in. */
  role: Role | null
  /** `expired` when the session ended underneath the person. Null otherwise. */
  endedBecause: 'expired' | null
  /** True from the moment the person asks to sign out until they are. */
  signingOut: boolean
  /**
   * Sign in with the email address and password that were typed.
   *
   * @throws ApiError when the sign in is refused or the API cannot be reached.
   */
  signIn: (email: string, password: string) => Promise<SessionUser>
  /** Sign out, drop everything cached from the server, empty the hire basket,
   *  and go to the catalogue. */
  signOut: () => void
}

export const SessionContext = createContext<Session | undefined>(undefined)

export function useSession(): Session {
  const session = useContext(SessionContext)
  if (!session) {
    throw new Error(
      'useSession was called outside SessionProvider. Wrap the router in <SessionProvider> in App.tsx.',
    )
  }
  return session
}
