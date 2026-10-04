/**
 * The owner's catalogue and pricing, against the real backend.
 *
 * The seeded owner signs in and opens the catalogue. They search for a seeded
 * model by its stock code, open it, raise its late fee by one rand and save,
 * which first says that bookings already made keep their rate, and see the
 * new fee in the list. Then they put the fee back to exactly what it was.
 * Last, they add a model of their own with a stock code no run has used,
 * publish it and hide it again. That is SC-20 end to end, under the same
 * Content Security Policy a visitor gets.
 *
 * Each browser project changes a different seeded model, so the two never
 * change the same fee at once. A model the spec adds is left in the catalogue
 * hidden, because nothing is ever deleted.
 *
 * It needs the admin catalogue routes, which a healthy backend may not have
 * yet, so `e2e/admin-catalogue-backend.ts` asks for them by name. When they
 * are not there the spec skips itself and the run still passes.
 */

import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { ADMIN_CATALOGUE_ROUTES_NEEDED, adminCatalogueRoutesArePresent } from './admin-catalogue-backend.ts'
import { blockingViolations } from './axe.ts'
import { signInAsOwner } from './staff.ts'

const CATALOGUE_HEADING = 'Catalogue and pricing'

/** The seeded model each browser project changes the late fee of. */
const MODEL_FOR_PROJECT: Record<string, string> = {
  'chromium-desktop': 'DR-BOSCH-GBH226',
  'chromium-mobile': 'BR-HILTI-TE1000AVR',
}

/** Said before any figure is saved. */
const BOOKINGS_KEEP_THEIR_RATE = 'Bookings already made keep the rate they were booked at.'

const CENTS_IN_A_RAND = 100
const ONE_RAND_IN_CENTS = 100
const DIGITS_IN_A_GROUP = 3

/** An amount as the API writes it, one rand more, worked out in whole cents. */
function oneRandMore(amount: string): string {
  const [rand, cents] = amount.split('.')
  const total = Number(rand) * CENTS_IN_A_RAND + Number(cents) + ONE_RAND_IN_CENTS
  return `${Math.floor(total / CENTS_IN_A_RAND)}.${String(total % CENTS_IN_A_RAND).padStart(2, '0')}`
}

/** How the screen writes an amount in rand, with any grouping and either decimal mark. */
function randPattern(amount: string): RegExp {
  const [rand, cents] = amount.split('.')
  const groups: string[] = []
  for (let end = rand.length; end > 0; end -= DIGITS_IN_A_GROUP) groups.unshift(rand.slice(Math.max(0, end - DIGITS_IN_A_GROUP), end))
  return new RegExp(`R\\s?${groups.join('\\s?')}[,.]${cents}`)
}

/** A stock code nobody has used, for this run and this browser project. */
function freshStockCode(projectName: string): string {
  const project = projectName.endsWith('mobile') ? 'M' : 'D'
  return `E2E-${project}-${Date.now().toString(36).toUpperCase()}`
}

function modelsRegion(page: Page): Locator {
  return page.getByRole('region', { name: 'The models' })
}

/** The row of the model with this stock code in the list on the screen. */
function rowOf(page: Page, sku: string): Locator {
  return modelsRegion(page).getByRole('row').filter({ has: page.getByRole('rowheader', { name: new RegExp(sku) }) })
}

async function searchFor(page: Page, sku: string): Promise<Locator> {
  await page.getByLabel('Search by name or stock code').fill(sku)
  await expect(page).toHaveURL(new RegExp(`/admin/catalogue\\?q=${sku}$`))
  const row = rowOf(page, sku)
  await expect(row).toHaveCount(1)
  return row
}

/**
 * Open the model, set its late fee from the one it has, say yes to the
 * question and see the new fee in the list.
 *
 * @returns The late fee the model had before.
 */
async function setLateFee(page: Page, row: Locator, next: (current: string) => string): Promise<string> {
  await row.getByRole('button', { name: /^Edit / }).click()
  const form = page.getByRole('form', { name: /^The details of / })
  const lateFee = form.getByLabel('Late fee per day, in rand')
  const current = await lateFee.inputValue()
  const wanted = next(current)
  await lateFee.fill(wanted)
  await form.getByRole('button', { name: 'Save the changes' }).click()
  await expect(page.getByRole('heading', { level: 3, name: /^Save the changes to .+\?$/ })).toBeFocused()
  await expect(page.getByText(BOOKINGS_KEEP_THEIR_RATE)).toBeVisible()
  expect(await blockingViolations(page)).toEqual([])
  await page.getByRole('button', { name: 'Yes, save the changes' }).click()
  await expect(page.getByText(/ is saved$/)).toBeVisible()
  await expect(row).toContainText(randPattern(wanted))
  return current
}

/** SC-20. A seeded model's late fee one rand up, and back to exactly what it was. */
async function changeALateFeeAndBack(page: Page, sku: string): Promise<void> {
  const row = await searchFor(page, sku)
  const before = await setLateFee(page, row, oneRandMore)
  await setLateFee(page, row, () => before)
}

/** The first category in the form's menu that is switched on. */
async function aCategoryInUse(menu: Locator): Promise<string> {
  const labels = await menu.locator('option').allTextContents()
  const label = labels.find((text) => text !== 'Choose a category' && !text.endsWith('(switched off)'))
  if (label === undefined) throw new Error('The catalogue offers no category that is switched on to add a model to.')
  return label
}

/** SC-20. A model of the run's own, added hidden, then published and hidden again. */
async function addPublishAndHide(page: Page, sku: string): Promise<void> {
  await page.getByRole('button', { name: 'Add a model', exact: true }).first().click()
  const form = page.getByRole('form', { name: 'The new model' })
  const fields: [string, string][] = [
    ['Stock code', sku],
    ['Name', `Browser test model ${sku}`],
    ['Name in the web address', sku.toLowerCase()],
    ['Manufacturer', 'Toolshed browser tests'],
    ['Model number', sku],
    ['Short description', 'Made by the browser tests and left hidden. Safe to ignore.'],
    ['Daily rate, in rand', '100.00'],
    ['Weekly rate, in rand', '400.00'],
    ['Deposit, in rand', '500.00'],
    ['Late fee per day, in rand', '20.00'],
    ['Replacement value, in rand', '1000.00'],
    ['Shortest hire, in days', '1'],
    ['Longest hire, in days', '7'],
  ]
  for (const [label, value] of fields) await form.getByLabel(label, { exact: true }).fill(value)
  const menu = form.getByLabel('Category it sits in')
  await menu.selectOption({ label: await aCategoryInUse(menu) })
  await form.getByRole('button', { name: 'Add the model' }).click()
  await expect(page.getByRole('heading', { level: 3, name: /^Add .+ to the catalogue\?$/ })).toBeFocused()
  await page.getByRole('button', { name: 'Yes, add it' }).click()

  await expect(page.getByText(/ is in the catalogue$/)).toBeVisible()
  await expect(page).toHaveURL(new RegExp(`/admin/catalogue\\?q=${sku}$`))
  const row = rowOf(page, sku)
  await expect(row.getByText('Hidden', { exact: true })).toBeVisible()

  await row.getByRole('button', { name: /^Publish / }).click()
  await expect(page.getByRole('heading', { level: 3, name: /^Publish .+\?$/ })).toBeFocused()
  expect(await blockingViolations(page)).toEqual([])
  await page.getByRole('button', { name: 'Yes, publish it' }).click()
  await expect(page.getByText(/ is published$/)).toBeVisible()
  await expect(row.getByText('Published', { exact: true })).toBeVisible()

  await row.getByRole('button', { name: /^Hide / }).click()
  await page.getByRole('button', { name: 'Yes, hide it' }).click()
  await expect(page.getByText(/ is hidden from customers$/)).toBeVisible()
  await expect(row.getByText('Hidden', { exact: true })).toBeVisible()
}

test.describe('the owner keeps the catalogue against the real backend', () => {
  test.beforeEach(async ({ request }) => {
    test.skip(!(await adminCatalogueRoutesArePresent(request)), ADMIN_CATALOGUE_ROUTES_NEEDED)
  })

  test('the owner changes a late fee by one rand and back, and adds, publishes and hides a model of their own', async ({
    page,
  }, testInfo) => {
    await signInAsOwner(page)
    await page.goto('/admin/catalogue')
    await expect(page.getByRole('heading', { level: 1, name: CATALOGUE_HEADING })).toBeVisible()
    await expect(page.getByText('This screen still shows sample data')).toHaveCount(0)
    await expect(modelsRegion(page).getByRole('status').first()).toHaveText(/^\d+ models? match(es)?\.$/)
    await expect(page.getByRole('region', { name: 'Categories' }).getByRole('table')).toBeVisible()
    expect(await blockingViolations(page)).toEqual([])

    const seeded = MODEL_FOR_PROJECT[testInfo.project.name] ?? MODEL_FOR_PROJECT['chromium-desktop']
    await changeALateFeeAndBack(page, seeded)
    await addPublishAndHide(page, freshStockCode(testInfo.project.name))
  })
})
