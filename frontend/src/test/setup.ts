/**
 * Runs once before every test file.
 *
 * I register the jest-dom matchers here, so a component test can say
 * `toBeVisible` or `toHaveAccessibleName` and fail with a message about the
 * page rather than about a raw DOM node.
 *
 * I also unmount whatever a test rendered. Testing Library only does that by
 * itself when the test functions are globals, and this project imports them
 * instead, so without this line one test would find the markup the previous
 * test left behind.
 */

import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => {
  cleanup()
})
