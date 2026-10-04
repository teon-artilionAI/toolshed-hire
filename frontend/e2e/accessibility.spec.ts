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
 * assistant and a customer with a booking, the counter's dashboard, diary and
 * locator need a day with something on it and units to find, the return
 * screen and the overdue worklist need a hire partly back and units long
 * overdue, and the damage screen needs a unit with reports on it. The spec
 * answers the API for those itself, through counter-answers.ts, so all nine
 * are scanned loaded every time. The new booking is scanned again with a tool
 * on it, the checkout again with every problem of its form on the screen, the
 * diary again with the no show question open and its problem showing, the
 * return again with its question open, the worklist again with the question
 * about a lost unit open, and the damage screen again with every problem of
 * its form showing, then with the amount to recover and its question open.
 *
 * The owner's dashboard and report need a signed in owner, three branches and
 * rows. Their answers are in admin-answers.ts, so both are scanned loaded every
 * time, the report once by model and once by unit, and again with a refusal of
 * its period under the field. The audit trail and the notification log are
 * scanned loaded the same way, from audit-answers.ts, and the log again with
 * the question before a failed email is sent again. The catalogue is scanned
 * loaded from catalogue-answers.ts, with its form closed and open, then again
 * with the question before a new figure is saved, and with the question
 * before a model is hidden and the category form open. The asset register
 * is scanned loaded from asset-answers.ts, with no unit open and with one
 * open, then again with the question before a unit is retired and its reason
 * refused, and with the registration form showing every problem it holds
 * back. The staff accounts and the customer holds are scanned loaded from
 * user-answers.ts, and again with their forms and questions open in
 * user-management.spec.ts.
 *
 * The owner's corrections only show for an administrator, so the return
 * screen is scanned again as the owner with a reversal asked, and the checkout
 * as the owner on a booking short of a unit with a release asked. Those
 * answers are in owner-answers.ts.
 */

import { expect, test } from '@playwright/test'
import { ADMIN_SCREENS, ASSET_REGISTER_HEADING, AUDIT_LOG_HEADING, CATALOGUE_HEADING, openAdminScreen } from './admin-answers.ts'
import { blockingViolations } from './axe.ts'
import { COUNTER_SCREENS, openCounterScreen } from './counter-answers.ts'
import { OWNER_COUNTER_SCREENS } from './owner-answers.ts'
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

for (const screen of ADMIN_SCREENS) {
  test(`${screen.path} has no serious or critical accessibility violations`, async ({ page }) => {
    await openAdminScreen(page, screen)
    await expect(page.locator(BUSY_REGION)).toHaveCount(0)

    expect(await blockingViolations(page)).toEqual([])
  })
}

test('the report with a refusal under its period has no serious or critical accessibility violations', async ({
  page,
}) => {
  const [, report] = ADMIN_SCREENS
  await openAdminScreen(page, report)

  // A route added later is asked first, so from here the report is refused.
  await page.route('**/api/admin/reports/utilisation?*', (route) =>
    route.fulfill({
      status: 422,
      contentType: 'application/problem+json',
      body: JSON.stringify({
        type: 'https://toolshedhire.co.za/problems/validation',
        title: 'Unprocessable Content',
        status: 422,
        detail: 'The period was refused.',
        errors: { fields: { 'query.to': 'The period may be 366 days at most.' } },
      }),
    }),
  )
  await page.getByLabel('Break the figures down by').selectOption('category')
  await expect(page.getByText('The period may be 366 days at most.')).toBeVisible()

  expect(await blockingViolations(page)).toEqual([])
})

test('the notification log with the question before sending again has no serious or critical accessibility violations', async ({
  page,
}) => {
  const log = ADMIN_SCREENS.find((screen) => screen.heading === AUDIT_LOG_HEADING && screen.path.includes('notifications'))
  if (log === undefined) throw new Error('ADMIN_SCREENS has no notification log to open.')
  await openAdminScreen(page, log)

  await page.getByRole('button', { name: /^Send again / }).click()
  await expect(page.getByRole('heading', { level: 4, name: /^Send the booking confirmation for .+ again\?$/ })).toBeFocused()

  expect(await blockingViolations(page)).toEqual([])
})

/** The catalogue from the list the scans share, with its form open or closed. */
function catalogueScreen(formOpen: boolean) {
  const found = ADMIN_SCREENS.find((screen) => screen.heading === CATALOGUE_HEADING && screen.path.includes('model=') === formOpen)
  if (found === undefined) throw new Error('ADMIN_SCREENS has no catalogue to open.')
  return found
}

test('the catalogue with the question before a new figure is saved has no serious or critical accessibility violations', async ({
  page,
}) => {
  await openAdminScreen(page, catalogueScreen(true))
  const form = page.getByRole('form', { name: /^The details of / })

  await form.getByLabel('Late fee per day, in rand').fill('988.65')
  await form.getByRole('button', { name: 'Save the changes' }).click()
  await expect(page.getByRole('heading', { level: 3, name: /^Save the changes to .+\?$/ })).toBeFocused()

  expect(await blockingViolations(page)).toEqual([])
})

test('the catalogue with a model being hidden and a category being added has no serious or critical accessibility violations', async ({
  page,
}) => {
  await openAdminScreen(page, catalogueScreen(false))

  await page.getByRole('button', { name: /^Hide / }).first().click()
  await expect(page.getByRole('heading', { level: 3, name: /^Hide .+ from customers\?$/ })).toBeFocused()
  expect(await blockingViolations(page)).toEqual([])

  await page.getByRole('region', { name: 'Categories' }).getByRole('button', { name: 'Add a category' }).click()
  await expect(page.getByRole('heading', { level: 3, name: 'Add a category' })).toBeFocused()
  expect(await blockingViolations(page)).toEqual([])
})

/** The asset register from the list the scans share, with a unit open or not. */
function registerScreen(unitOpen: boolean) {
  const found = ADMIN_SCREENS.find(
    (screen) => screen.heading === ASSET_REGISTER_HEADING && screen.path.includes('asset=') === unitOpen,
  )
  if (found === undefined) throw new Error('ADMIN_SCREENS has no asset register to open.')
  return found
}

test('a unit with the question before it is retired and its reason refused has no serious or critical accessibility violations', async ({
  page,
}) => {
  await openAdminScreen(page, registerScreen(true))
  const moves = page.getByRole('region', { name: 'Move it through its life' })

  await moves.getByRole('button', { name: 'Retire it' }).click()
  await expect(page.getByRole('heading', { level: 4, name: /^Retire .+\?$/ })).toBeFocused()
  await page.getByRole('button', { name: 'Yes, retire it' }).click()
  await expect(page.getByText('Write the reason, so whoever reads the history of this unit later knows why.')).toBeVisible()

  expect(await blockingViolations(page)).toEqual([])
})

test('the registration of a unit with every problem it holds back has no serious or critical accessibility violations', async ({
  page,
}) => {
  await openAdminScreen(page, registerScreen(false))

  await page.getByRole('button', { name: 'Register a unit' }).first().click()
  const form = page.getByRole('form', { name: 'The new unit' })
  await form.getByRole('button', { name: 'Register the unit' }).click()
  await expect(page.getByText(/Nothing has been saved yet\. 3 answers need fixing\./)).toBeVisible()

  expect(await blockingViolations(page)).toEqual([])
})

for (const owner of OWNER_COUNTER_SCREENS) {
  test(`${owner.name} has no serious or critical accessibility violations`, async ({ page }) => {
    await openCounterScreen(page, owner.screen, owner.instead)
    await expect(page.locator(BUSY_REGION)).toHaveCount(0)
    expect(await blockingViolations(page)).toEqual([])

    await owner.ask(page)
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

/** A counter screen from the list the scans share, by its heading. */
function counterScreen(heading: string) {
  const found = COUNTER_SCREENS.find((screen) => screen.heading === heading)
  if (found === undefined) throw new Error(`COUNTER_SCREENS has no screen headed ${heading} to open.`)
  return found
}

test('a return with its question open has no serious or critical accessibility violations', async ({ page }) => {
  await openCounterScreen(page, counterScreen('Return and condition inspection'))

  await page.getByRole('checkbox', { name: /^TSH-PC-0012 is back on the counter/ }).check()
  await page.getByRole('button', { name: 'Take the ticked units back' }).click()
  await expect(page.getByRole('heading', { level: 2, name: /^Take these units back from / })).toBeFocused()

  expect(await blockingViolations(page)).toEqual([])
})

test('the overdue worklist with a loss question open has no serious or critical accessibility violations', async ({
  page,
}) => {
  await openCounterScreen(page, counterScreen('Overdue and late fees'))

  await page.getByRole('button', { name: /^Record as lost / }).first().click()
  await expect(page.getByRole('button', { name: 'Yes, record it as lost' })).toBeVisible()

  expect(await blockingViolations(page)).toEqual([])
})

test('a damage report with its problems, its amount and its question has no serious or critical accessibility violations', async ({
  page,
}) => {
  await openCounterScreen(page, counterScreen('Record damage'))
  const form = page.getByRole('form', { name: 'What happened' })

  await form.getByRole('button', { name: 'Record the damage and quarantine the unit' }).click()
  await expect(page.getByText(/Nothing has been filed yet\. 4 answers need fixing\./)).toBeVisible()
  expect(await blockingViolations(page)).toEqual([])

  await form.getByRole('radio', { name: /^Major/ }).check()
  await form.getByLabel('Describe the damage').fill('Base plate cracked across the weld.')
  await form.getByLabel('Estimated repair cost, in rand').fill('1450.00')
  await form.getByRole('radio', { name: /^Charge the customer/ }).check()
  await form.getByLabel('Amount to recover from the customer, in rand, including VAT').fill('1150.00')
  expect(await blockingViolations(page)).toEqual([])

  await form.getByRole('button', { name: 'Record the damage and quarantine the unit' }).click()
  await expect(page.getByRole('heading', { level: 2, name: /^File this damage report for / })).toBeFocused()
  expect(await blockingViolations(page)).toEqual([])
})
