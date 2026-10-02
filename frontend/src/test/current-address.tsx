/**
 * Writes the address the router is on into the page, for tests.
 *
 * A test can then check where a form or a link took the person by reading the
 * page, without reaching into the router.
 *
 * The fragment is written out apart from the path and the query. A link in an
 * email carries its token there, and a test checks that the screen took it out.
 */

import { useLocation } from 'react-router-dom'

/** The test id of the element that holds the current address. */
export const ADDRESS_TEST_ID = 'current-address'

/** The test id of the element that holds the fragment of the current address. */
export const FRAGMENT_TEST_ID = 'current-fragment'

export function CurrentAddress() {
  const { pathname, search, hash } = useLocation()
  // Plain elements on purpose. An `output` element is a status region, and it
  // would turn up in every test that looks for what the screen announces.
  return (
    <>
      <code data-testid={ADDRESS_TEST_ID}>{`${pathname}${search}`}</code>
      <code data-testid={FRAGMENT_TEST_ID}>{hash}</code>
    </>
  )
}
