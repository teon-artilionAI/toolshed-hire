/**
 * The session, for the screens.
 *
 * The session itself is in session-store.ts, outside React, and that is where
 * the access token stays. This provider subscribes to the store and hands the
 * screens what they may know, which is who is signed in and never the token.
 *
 * It does three things the store cannot, because they need the router and the
 * cache.
 *
 * It asks the store to find out, once, whether there is a session, and shows a
 * neutral loading state until the answer is in. No screen and no guard runs
 * before that, so nobody is sent to sign in while they are in fact signed in.
 *
 * It signs a person out. That goes to the catalogue first and ends the session
 * there. Ending it while a protected screen is still on the page would make
 * the guard send the person to sign in, a moment before they left anyway.
 *
 * It sends a person to sign in when the session ends underneath them on a
 * public screen. On a protected screen the guard in App.tsx does that, so
 * exactly one of the two acts.
 *
 * In both cases everything cached from the server is dropped, so the next
 * person at this browser is never shown what the last one loaded. Signing out
 * also empties the hire basket, for the same reason. A session that ends by
 * itself leaves the basket alone, because the same person is about to sign in
 * again and carry on with it.
 */

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import type { ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { clearBasket } from './basket-store'
import { CATALOGUE_PATH, SIGN_IN_PATH } from './navigation'
import { screenForPath, signInAddress } from './screen-access'
import {
  sessionSnapshot,
  signIn,
  signOut as endSession,
  startSession,
  subscribeToSession,
} from './session-store'
import { SessionContext } from './use-session'
import type { Session } from './use-session'

/** What is on the page while start-up finds out whether anyone is signed in.
 *  It names no screen and offers no control, because neither is known yet. */
function SessionLoading() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-md" aria-busy="true">
      <img src="/mark.png" alt="" className="h-12 w-12 animate-pulse" />
      <p role="status" className="text-sm text-slate-soft">
        Loading Toolshed Hire
      </p>
    </div>
  )
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const snapshot = useSyncExternalStore(subscribeToSession, sessionSnapshot)
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { pathname, search } = useLocation()
  const [signingOut, setSigningOut] = useState(false)
  const expiryHandled = useRef(false)

  useEffect(() => {
    void startSession()
  }, [])

  const signOut = useCallback(() => {
    setSigningOut(true)
    navigate(CATALOGUE_PATH)
  }, [navigate])

  useEffect(() => {
    if (!signingOut || pathname !== CATALOGUE_PATH) return
    void endSession().then(() => {
      queryClient.clear()
      clearBasket()
      setSigningOut(false)
    })
  }, [signingOut, pathname, queryClient])

  useEffect(() => {
    if (snapshot.endedBecause !== 'expired') {
      expiryHandled.current = false
      return
    }
    if (expiryHandled.current) return
    expiryHandled.current = true
    queryClient.clear()
    const screen = screenForPath(pathname)
    const guardSendsThem = screen !== undefined && !screen.publicAccess
    if (guardSendsThem || pathname === SIGN_IN_PATH) return
    navigate(signInAddress(`${pathname}${search}`))
  }, [snapshot.endedBecause, pathname, search, navigate, queryClient])

  const value = useMemo<Session>(
    () => ({
      status: snapshot.status,
      signedIn: snapshot.status === 'signedIn',
      user: snapshot.user,
      role: snapshot.user?.role ?? null,
      endedBecause: snapshot.endedBecause,
      signingOut,
      signIn,
      signOut,
    }),
    [snapshot, signingOut, signOut],
  )

  return (
    <SessionContext.Provider value={value}>
      {snapshot.status === 'checking' ? <SessionLoading /> : children}
    </SessionContext.Provider>
  )
}
