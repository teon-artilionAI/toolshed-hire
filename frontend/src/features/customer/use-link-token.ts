/**
 * The token a link in an email carries.
 *
 * A verification link ends `#verify=<token>` and a reset link ends
 * `#reset=<token>`. The token rides in the fragment because a browser never
 * sends the fragment to a server, so it cannot land in a server log or in the
 * `Referer` of the next request.
 *
 * The screen takes the token out of the address the moment it is on the page.
 * The history entry is replaced, so the back button does not bring the token
 * back either. From then on the token lives in the state of the screen that
 * is using it and nowhere else. It is not logged, not put in web storage and
 * not kept once the API has answered for it.
 */

import { useCallback, useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

/** The name a verification link gives its token. */
export const VERIFY_LINK_NAME = 'verify'

/** The name a password reset link gives its token. */
export const RESET_LINK_NAME = 'reset'

/** A value as it was before it was written into an address. */
function decoded(raw: string): string {
  try {
    return decodeURIComponent(raw)
  } catch (cause) {
    // A stray percent sign that is not an escape. I hand the text on as it
    // stands, and the API says whether it is a token it knows.
    if (cause instanceof URIError) return raw
    throw cause
  }
}

/**
 * Read one named token out of the fragment of an address.
 *
 * @param hash The fragment with or without its leading `#`.
 * @param name The name before the equals sign, for example `verify`.
 * @returns The token, or null when the fragment does not carry one.
 */
export function readLinkToken(hash: string, name: string): string | null {
  const prefix = `${name}=`
  const fragment = hash.startsWith('#') ? hash.slice(1) : hash
  const part = fragment.split('&').find((piece) => piece.startsWith(prefix))
  if (part === undefined) return null
  const token = decoded(part.slice(prefix.length))
  return token === '' ? null : token
}

export interface LinkToken {
  /** The token the link carried, or null when there was none or it was spent. */
  token: string | null
  /** Drop the token. Called once the API has answered for it. */
  forget: () => void
}

/**
 * Take the named token out of the address and hold it for the screen.
 *
 * @param name The name before the equals sign in the fragment.
 */
export function useLinkToken(name: string): LinkToken {
  const { hash, pathname, search } = useLocation()
  const navigate = useNavigate()
  const arriving = readLinkToken(hash, name)
  const [held, setHeld] = useState<string | null>(arriving)

  // A link opened while the screen was already on the page.
  if (arriving !== null && arriving !== held) setHeld(arriving)

  useEffect(() => {
    if (arriving === null) return
    navigate({ pathname, search }, { replace: true })
  }, [arriving, navigate, pathname, search])

  const forget = useCallback(() => setHeld(null), [])
  return { token: held, forget }
}
