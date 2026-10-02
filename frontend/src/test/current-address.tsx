/**
 * Writes the address the router is on into the page, for tests.
 *
 * A test can then check where a form or a link took the person by reading the
 * page, without reaching into the router.
 */

import { useLocation } from 'react-router-dom'

/** The test id of the element that holds the current address. */
export const ADDRESS_TEST_ID = 'current-address'

export function CurrentAddress() {
  const { pathname, search } = useLocation()
  // A plain element on purpose. An `output` element is a status region, and it
  // would turn up in every test that looks for what the screen announces.
  return <code data-testid={ADDRESS_TEST_ID}>{`${pathname}${search}`}</code>
}
