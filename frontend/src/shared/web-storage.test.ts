/**
 * Tests for what the application leaves in web storage.
 *
 * Three things at most. The two session markers in `localStorage`, each a
 * fixed word, and the hire basket in `sessionStorage` under its one key. No
 * token is ever among them. This runs every path that handles a token with a
 * basket and a booking under way beside it, and looks at every write.
 *
 * As in session-store.test.ts, only `fetch` is replaced.
 */

import { describe, expect, it, vi } from 'vitest'
import { getCurrentUser } from './api/auth'
import { jsonResponse, mockApi, noContentResponse } from '../test/api-mock'
import {
  ACCESS_TOKEN,
  CUSTOMER,
  LOGIN_ROUTE,
  LOGOUT_ROUTE,
  ME_ROUTE,
  REFRESH_ROUTE,
  grantFor,
  meAccepting,
} from '../test/session-samples'
import { BASKET_STORAGE_KEY } from './basket-storage'
import { addToBasket, noteBookingUnderWay } from './basket-store'
import {
  MARKER_VALUE,
  SESSION_HINT_KEY,
  SESSION_MARKER_KEYS,
  SIGN_OUT_OWED_KEY,
} from './session-markers'
import { sessionSnapshot, signIn, signOut, startSession } from './session-store'

const RENEWED_TOKEN = 'renewed-access-token-2c8e4d6f'
const PASSWORD = 'a-password-typed-by-a-person'

function unreachable(): never {
  throw new TypeError('Failed to fetch')
}

/** Everything in `localStorage`, as plain keys and values. */
function stored(): Record<string, string> {
  return { ...window.localStorage }
}

describe('where the token is kept', () => {
  it('is never in web storage, a cookie or the snapshot, and storage holds two fixed markers and the basket at most', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem')
    const network = mockApi({
      [REFRESH_ROUTE]: () => jsonResponse(grantFor(CUSTOMER, RENEWED_TOKEN)),
      [LOGIN_ROUTE]: () => jsonResponse(grantFor(CUSTOMER)),
      [LOGOUT_ROUTE]: unreachable,
      [ME_ROUTE]: meAccepting(RENEWED_TOKEN),
    })

    // Every path that handles a token. Start-up, sign in, a renewal after a
    // refusal, a sign out the server never hears, and one it confirms.
    // The basket is the one other thing kept in web storage, so it is filled
    // and a booking is under way while the token is being handled.
    await startSession()
    await signIn(CUSTOMER.email, PASSWORD)
    addToBasket({
      modelSlug: 'cp-100-plate-compactor',
      quantity: 2,
      from: '2026-10-09',
      to: '2026-10-12',
      branchCode: 'CBD',
    })
    noteBookingUnderWay('5f0c2a9e-0000-4000-8000-000000000124')
    await getCurrentUser()
    const whileSignedIn = JSON.stringify(sessionSnapshot())
    const storedWhileSignedIn = stored()
    await signOut()
    const storedWhileOwed = stored()
    network.setRoute(LOGOUT_ROUTE, () => noContentResponse())
    await signIn(CUSTOMER.email, PASSWORD)
    await signOut()

    // Signed in, the hint and nothing else. After the failed sign out, the
    // marker that it is owed and nothing else. After the confirmed one, nothing.
    expect(storedWhileSignedIn).toEqual({ [SESSION_HINT_KEY]: MARKER_VALUE })
    expect(storedWhileOwed).toEqual({ [SIGN_OUT_OWED_KEY]: MARKER_VALUE })
    expect(stored()).toEqual({})
    // Every write to the lasting store was one of the two keys and the fixed
    // word. Every write to the store of the tab was the basket under its one
    // key, and no write to either held a token.
    const writes = setItem.mock.calls.map(([key, value], index) => ({
      key,
      value,
      toTabStorage: setItem.mock.contexts[index] === window.sessionStorage,
    }))
    expect(writes.some((write) => write.toTabStorage)).toBe(true)
    expect(writes.some((write) => !write.toTabStorage)).toBe(true)
    for (const { key, value, toTabStorage } of writes) {
      if (toTabStorage) {
        expect(key).toBe(BASKET_STORAGE_KEY)
      } else {
        expect(SESSION_MARKER_KEYS).toContain(key)
        expect(value).toBe(MARKER_VALUE)
      }
      expect(value).not.toContain(ACCESS_TOKEN)
      expect(value).not.toContain(RENEWED_TOKEN)
    }
    // The store of the tab holds the basket and nothing else. The basket names
    // models, dates, a branch and a booking, and no account.
    expect(Object.keys(window.sessionStorage)).toEqual([BASKET_STORAGE_KEY])
    const basketKept = window.sessionStorage.getItem(BASKET_STORAGE_KEY) ?? ''
    expect(basketKept).not.toContain(ACCESS_TOKEN)
    expect(basketKept).not.toContain(RENEWED_TOKEN)
    expect(basketKept).not.toContain(CUSTOMER.email)
    expect(Object.keys(JSON.parse(basketKept) as object).sort()).toEqual([
      'branchCode',
      'from',
      'lines',
      'reservationId',
      'setAside',
      'to',
      'version',
    ])
    expect(document.cookie).toBe('')
    expect(whileSignedIn).not.toContain(ACCESS_TOKEN)
    expect(whileSignedIn).not.toContain(RENEWED_TOKEN)
    setItem.mockRestore()
  })
})
