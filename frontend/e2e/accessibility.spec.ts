/**
 * Automated accessibility checks for the public screens.
 *
 * These run with or without the backend. The catalogue home and the search
 * read from the API, so with no backend this scans them in their failed state,
 * and with one it scans them loaded. Both have to be clean. The model screen
 * needs a real model to open, so its scan is in catalogue.spec.ts with the
 * other specs that need the backend.
 *
 * The registration form reads the branches for its menu, so with no backend
 * it is scanned with that one menu in its failed state. The privacy notice
 * reads nothing and is the same either way.
 */

import { expect, test } from '@playwright/test'
import { blockingViolations } from './axe.ts'
import { CATALOGUE_HOME, PRIVACY, REGISTER, SEARCH, SIGN_IN } from './routes.ts'

/** A region that is still waiting on the API. */
const BUSY_REGION = '[aria-busy="true"]'

for (const route of [CATALOGUE_HOME, SEARCH, SIGN_IN, REGISTER, PRIVACY]) {
  test(`${route.path} has no serious or critical accessibility violations`, async ({ page }) => {
    await page.goto(route.path)
    await expect(page.getByRole('heading', { level: 1, name: route.heading })).toBeVisible()
    // I wait for every loading region to settle, so the scan sees real content
    // or the error state and never a skeleton, which is hidden from it anyway.
    await expect(page.locator(BUSY_REGION)).toHaveCount(0)

    expect(await blockingViolations(page)).toEqual([])
  })
}
