/**
 * The owner's asset register, against the real backend.
 *
 * The seeded owner signs in and opens the register. They register a unit with
 * a tag no run has used, choosing its model by searching for a seeded one,
 * commission it, send it for repair with a reason, commission it again, and
 * retire it with a reason, which first says that its row and its history are
 * kept. Then they find it in the register by its tag, standing as retired,
 * and open it to read the history of every move. That is SC-21 end to end,
 * under the same Content Security Policy a visitor gets.
 *
 * Each browser project registers its unit at a different branch with a tag of
 * its own, so the two never move the same unit. The unit is left on the
 * register retired, because nothing is ever deleted.
 *
 * It needs the asset register routes, which a healthy backend may not have
 * yet, so `e2e/admin-assets-backend.ts` asks for them by name. When they are
 * not there the spec skips itself and the run still passes.
 */

import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { ASSET_REGISTER_ROUTES_NEEDED, assetRegisterRoutesArePresent } from './admin-assets-backend.ts'
import { blockingViolations } from './axe.ts'
import { dateFromToday } from './hire-dates.ts'
import { signInAsOwner } from './staff.ts'

const REGISTER_HEADING = 'Asset register'

/** The seeded model every run registers a unit of, found by its stock code. */
const SEEDED_MODEL = 'DR-BOSCH-GBH226'

/** The branch each browser project registers its unit at. */
const BRANCH_FOR_PROJECT: Record<string, string> = {
  'chromium-desktop': 'CBD',
  'chromium-mobile': 'BLV',
}

/** A week ago, comfortably before today in branch time whatever the hour. */
const BOUGHT_DAYS_AGO = -7

const REPAIR_REASON = 'Browser test, the chuck sticks.'
const RETIREMENT_REASON = 'Browser test, beyond economical repair.'

/** The moves the journey makes after the registration, one history entry each. */
const MOVES_MADE = 4

/** A tag nobody has used, for this run and this browser project. Sixteen
 *  characters at most, capitals and digits with single hyphens. */
function freshTag(projectName: string): string {
  const project = projectName.endsWith('mobile') ? 'M' : 'D'
  return `E2E-${project}-${Date.now().toString(36).toUpperCase()}`
}

function unitSection(page: Page, tag: string): Locator {
  return page.getByRole('region', { name: `Unit ${tag}` })
}

/** SC-21. A unit of the run's own, registered at intake. */
async function registerAUnit(page: Page, tag: string, branchCode: string): Promise<void> {
  await page.getByRole('button', { name: 'Register a unit', exact: true }).first().click()
  const form = page.getByRole('form', { name: 'The new unit' })
  await form.getByLabel('Asset tag', { exact: true }).fill(tag)
  await form.getByLabel('Find the model by name or stock code').fill(SEEDED_MODEL)
  const menu = form.getByLabel('Model', { exact: true })
  const option = menu.locator('option').filter({ hasText: SEEDED_MODEL }).first()
  await expect(option).toBeAttached()
  await menu.selectOption({ label: (await option.textContent()) ?? SEEDED_MODEL })
  await form.getByLabel('Branch it belongs to').selectOption(branchCode)
  await form.getByLabel('Bought on').fill(dateFromToday(BOUGHT_DAYS_AGO))
  await form.getByLabel('Cost, in rand').fill('3980.00')
  await form.getByRole('button', { name: 'Register the unit' }).click()

  await expect(page.getByRole('heading', { level: 3, name: `Register ${tag}?` })).toBeFocused()
  expect(await blockingViolations(page)).toEqual([])
  await page.getByRole('button', { name: 'Yes, register it' }).click()
  await expect(page.getByText(`${tag} is registered at intake`)).toBeVisible()
  await expect(page).toHaveURL(new RegExp(`/admin/assets\\?asset=${tag}$`))
}

/** SC-21. One move of the unit, with a reason where one is asked. */
async function move(page: Page, tag: string, action: string, answer: string, reason: string | null, outcome: string): Promise<void> {
  const unit = unitSection(page, tag)
  await unit.getByRole('region', { name: 'Move it through its life' }).getByRole('button', { name: action }).click()
  if (reason !== null) await unit.getByLabel('Why').fill(reason)
  await unit.getByRole('button', { name: answer }).click()
  await expect(page.getByText(outcome, { exact: true })).toBeVisible()
}

test.describe('the owner keeps the asset register against the real backend', () => {
  test.beforeEach(async ({ request }) => {
    test.skip(!(await assetRegisterRoutesArePresent(request)), ASSET_REGISTER_ROUTES_NEEDED)
  })

  test('the owner registers a unit, moves it through its life, retires it and finds it with its history', async ({
    page,
  }, testInfo) => {
    await signInAsOwner(page)
    await page.goto('/admin/assets')
    await expect(page.getByRole('heading', { level: 1, name: REGISTER_HEADING })).toBeVisible()
    await expect(page.getByText('This screen still shows sample data')).toHaveCount(0)
    await expect(page.getByRole('region', { name: 'The units' }).getByRole('status').first()).toHaveText(
      /^\d+ units? match(es)?, in tag order\.$/,
    )
    expect(await blockingViolations(page)).toEqual([])

    const tag = freshTag(testInfo.project.name)
    await registerAUnit(page, tag, BRANCH_FOR_PROJECT[testInfo.project.name] ?? BRANCH_FOR_PROJECT['chromium-desktop'])
    await move(page, tag, 'Commission it', 'Yes, commission it', null, `${tag} is now on the shelf`)
    await move(page, tag, 'Send it for repair', 'Yes, send it for repair', REPAIR_REASON, `${tag} is now in the workshop`)
    await move(page, tag, 'Commission it', 'Yes, commission it', null, `${tag} is now on the shelf`)

    const unit = unitSection(page, tag)
    await unit.getByRole('button', { name: 'Retire it' }).click()
    await expect(page.getByText(/Its row and its whole history are kept/)).toBeVisible()
    expect(await blockingViolations(page)).toEqual([])
    await unit.getByLabel('Why').fill(RETIREMENT_REASON)
    await unit.getByRole('button', { name: 'Yes, retire it' }).click()
    await expect(page.getByText(`${tag} is retired`, { exact: true })).toBeVisible()

    await unit.getByRole('button', { name: 'Close the unit' }).click()
    await page.getByLabel('Search by tag, serial number or model').fill(tag)
    await expect(page).toHaveURL(new RegExp(`/admin/assets\\?q=${tag}$`))
    const row = page
      .getByRole('region', { name: 'The units' })
      .getByRole('row')
      .filter({ has: page.getByRole('rowheader', { name: new RegExp(tag) }) })
    await expect(row.getByText('Retired from the fleet', { exact: true })).toBeVisible()

    await row.getByRole('link', { name: `Open ${tag}` }).click()
    const history = unitSection(page, tag).getByRole('list', { name: `The history of ${tag}` })
    await expect(history.getByRole('listitem').filter({ hasText: /^Register/ })).toHaveCount(MOVES_MADE + 1)
    await expect(history).toContainText(RETIREMENT_REASON)
    await expect(history).toContainText(REPAIR_REASON)
    expect(await blockingViolations(page)).toEqual([])
  })
})
