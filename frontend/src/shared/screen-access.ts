/**
 * Who may open which screen, and where a person lands.
 *
 * Every rule here reads the screen inventory in navigation.ts. Nothing here
 * keeps a list of its own, so a screen added to the inventory is guarded, is
 * offered in the right menu and is a valid place to land without another edit.
 *
 * These rules decide what the interface offers. They are not what keeps the
 * data safe. The API checks the role on every request, and a person who gets
 * past a rule here still gets a refusal there.
 */

import { matchPath } from 'react-router-dom'
import { ROLE_HOME, SCREENS, SIGN_IN_PATH } from './navigation'
import type { ScreenDef } from './navigation'
import type { Role } from './types'

/**
 * The areas each role reaches, in the order its menu lists them.
 *
 * A customer reaches the customer screens and nothing else. Counter staff
 * reach the counter. An admin reaches the admin area and the counter as well,
 * because the owner also serves at it.
 */
export const AREAS_FOR_ROLE: Record<Role, readonly Role[]> = {
  customer: ['customer'],
  counter: ['counter'],
  admin: ['admin', 'counter'],
}

/** The query parameter that carries where to go once signed in. */
export const NEXT_PARAMETER = 'next'

/**
 * - `allowed`: show the screen.
 * - `signInNeeded`: nobody is signed in and the screen is not public.
 * - `wrongRole`: somebody is signed in, and their role does not reach it.
 */
export type ScreenAccess = 'allowed' | 'signInNeeded' | 'wrongRole'

/**
 * Decide whether a person may open a screen.
 *
 * @param screen The screen from the inventory.
 * @param role The role of the signed in person, or null when nobody is.
 */
export function accessTo(screen: ScreenDef, role: Role | null): ScreenAccess {
  if (screen.publicAccess) return 'allowed'
  if (role === null) return 'signInNeeded'
  return AREAS_FOR_ROLE[role].includes(screen.role) ? 'allowed' : 'wrongRole'
}

/** The screen an address belongs to, or undefined when it matches none. */
export function screenForPath(pathname: string): ScreenDef | undefined {
  return SCREENS.find((screen) => matchPath({ path: screen.path, end: true }, pathname) !== null)
}

/**
 * The primary navigation for a person.
 *
 * @param role The role of the signed in person, or null when nobody is. A
 *   visitor gets the customer menu, because that is who a visitor is.
 * @returns The menu screens of every area the role reaches, area by area.
 */
export function navFor(role: Role | null): ScreenDef[] {
  return AREAS_FOR_ROLE[role ?? 'customer'].flatMap((area) =>
    SCREENS.filter((screen) => screen.role === area && screen.inNav),
  )
}

/**
 * The sign in address that remembers where the person was going.
 *
 * @param from The path and query they were on, for example `/reservations`.
 */
export function signInAddress(from: string): string {
  return `${SIGN_IN_PATH}?${NEXT_PARAMETER}=${encodeURIComponent(from)}`
}

/** The path of an address inside this application, or null for anything else.
 *  A value that starts with two slashes names another site, so it is refused. */
function localPathOf(address: string): string | null {
  if (!address.startsWith('/') || address.startsWith('//') || address.includes('\\')) return null
  return address.split(/[?#]/)[0]
}

/**
 * Where a person lands after signing in.
 *
 * They go where they were trying to get to, when that is a screen of this
 * application that their role may open. Otherwise they go to the home of their
 * role. The address comes from the query string, which anybody can write, so
 * it is only ever followed when it names a screen in the inventory.
 *
 * @param role The role that has just signed in.
 * @param next The address they were on, or null when there was none.
 */
export function landingFor(role: Role, next: string | null): string {
  const path = next === null ? null : localPathOf(next)
  if (next === null || path === null) return ROLE_HOME[role]
  const screen = screenForPath(path)
  if (!screen || screen.path === SIGN_IN_PATH) return ROLE_HOME[role]
  return accessTo(screen, role) === 'allowed' ? next : ROLE_HOME[role]
}
