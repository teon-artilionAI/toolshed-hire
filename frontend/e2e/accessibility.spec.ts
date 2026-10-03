/**
 * Automated accessibility checks for the public screens and the counter's
 * booking screens.
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
 *
 * The counter's customer lookup, new booking and checkout need a signed in
 * assistant and a customer with a booking, and the counter's dashboard, diary
 * and locator need a day with something on it and units to find. The spec
 * answers the API for those itself, through counter-answers.ts, so all six are
 * scanned loaded every time. The new booking is scanned again with a tool on
 * it, the checkout again with every problem of its form on the screen, and the
 * diary again with the no show question open and its problem showing.
 */

import { expect, test } from '@playwright/test'
import { blockingViolations } from './axe.ts'
import { COUNTER_SCREENS, openCounterScreen } from './counter-answers.ts'
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

for (const screen of COUNTER_SCREENS) {
  test(`${screen.path} has no serious or critical accessibility violations`, async ({ page }) => {
    await openCounterScreen(page, screen)
    await expect(page.locator(BUSY_REGION)).toHaveCount(0)

    expect(await blockingViolations(page)).toEqual([])
  })
}

test('a new booking with a tool on it has no serious or critical accessibility violations', async ({ page }) => {
  const [, booking] = COUNTER_SCREENS
  await openCounterScreen(page, booking)

  await page.getByRole('region', { name: 'Tools free at this branch' }).getByRole('button', { name: /^Add / }).click()
  await expect(page.getByText(/^1 unit free at Cape Town CBD for these dates$/)).toBeVisible()

  expect(await blockingViolations(page)).toEqual([])
})

test('a checkout with every problem on the screen has no serious or critical accessibility violations', async ({
  page,
}) => {
  const [, , checkout] = COUNTER_SCREENS
  await openCounterScreen(page, checkout)

  await page.getByRole('button', { name: 'Check out the equipment' }).click()
  await expect(page.getByText(/Nothing has gone out yet\. 3 answers need fixing\./)).toBeVisible()

  expect(await blockingViolations(page)).toEqual([])
})

test('the diary with the no show question open has no serious or critical accessibility violations', async ({
  page,
}) => {
  const diary = COUNTER_SCREENS.find((screen) => screen.heading === 'Branch diary')
  if (diary === undefined) throw new Error('COUNTER_SCREENS has no branch diary to open.')
  await openCounterScreen(page, diary)

  await page.getByRole('button', { name: /^Mark as no show / }).click()
  await page.getByRole('button', { name: 'Yes, mark as no show' }).click()
  await expect(page.getByText(/Say why in a few words/)).toBeVisible()

  expect(await blockingViolations(page)).toEqual([])
})
