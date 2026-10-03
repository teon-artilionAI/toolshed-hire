/**
 * The steps of the damage journey in counter.spec.ts, against the real
 * backend.
 *
 * A second hire is checked out, comes back one grade worse than it went out,
 * and the return screen shows the deposit waiting for a damage report. The
 * assistant follows the link to SC-16, files a report that charges the
 * customer an amount far under any replacement value, and goes back to the
 * return, which shows the deposit settled with the recovery withheld. Then the
 * owner signs in on a browser of their own and resolves the report as
 * repaired, which puts the unit back on the shelf for the next run.
 *
 * Each run takes a unit back a grade worse, and a repair does not raise the
 * grade again. A unit that went out at C, the lowest grade, is flagged for
 * damage instead, which quarantines it the same way, so the journey still
 * runs on a database an earlier run left it at C in.
 */

import { expect } from '@playwright/test'
import type { Browser, Page, TestInfo } from '@playwright/test'
import { blockingViolations } from './axe.ts'
import { RAND } from './booking.ts'
import { signInAsOwner } from './staff.ts'

/** The grades a unit is given, best first. */
const GRADES = ['A', 'B', 'C']

/** What the customer is charged. Every seeded model is worth far more, and
 *  every seeded deposit covers it. */
const RECOVERY_AMOUNT = '50.00'
const RECOVERY_SHOWN = /^R\s50[,.]00$/
const NOTHING = /^R\s0[,.]00$/

/** What the box for the amount says once it knows the replacement value of the unit. */
const REPLACEMENT_VALUE_NAMED = /replacement value of R\s[\d\s]+[,.]\d{2} copied onto the booking/

/** A damage report reference, for example TSH-D-26-00031. */
const DAMAGE_REFERENCE = /TSH-D-\d{2}-\d+/

const RETURN_HEADING = 'Return and condition inspection'
const DAMAGE_HEADING = 'Record damage'

/** The amount on one line of the deposit settlement on SC-15. */
async function settlementAmount(page: Page, line: string): Promise<string> {
  const row = page.getByRole('row', { name: new RegExp(`^${line}`) })
  await expect(row).toBeVisible()
  return RAND.exec(await row.innerText())?.[0] ?? ''
}

/**
 * SC-14 from the confirmed booking on SC-13. Every tag read, the agreement
 * signed, the equipment handed over, and the hire opened on SC-15.
 */
export async function checkOutAndOpenTheHire(page: Page): Promise<void> {
  await page.getByRole('link', { name: 'Check out now' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Checkout and deposit' })).toBeVisible()
  const tags = page.getByRole('checkbox', { name: /I have read the tag on the unit/ })
  // The heading is there before the units are read, and `all` does not wait,
  // so the first unit has to be on the screen before the tags are ticked.
  await expect(tags.first()).toBeVisible()
  for (const tag of await tags.all()) await tag.check()
  await page.getByRole('checkbox', { name: /read the hire agreement and signed it/ }).check()
  await page.getByRole('button', { name: 'Check out the equipment' }).click()
  await page.getByRole('button', { name: 'Yes, hand it over' }).click()
  await expect(page.getByText(/^Hire TSH-H-\d{2}-\d{6} is open$/)).toBeVisible()
  await page.getByRole('link', { name: 'Open the hire' }).click()
  await expect(page.getByRole('heading', { level: 1, name: RETURN_HEADING })).toBeVisible()
}

/**
 * SC-15. The unit comes back one grade worse, or flagged when it went out at
 * the lowest grade, and the deposit waits for a damage report.
 *
 * @returns The tag of the unit, from the link to its damage report.
 */
export async function takeItBackWorse(page: Page): Promise<string> {
  await page.getByRole('checkbox', { name: /is back on the counter\. Take it back now\.$/ }).check()
  const grade = page.getByLabel('Condition coming back')
  const worse = GRADES[GRADES.indexOf(await grade.inputValue()) + 1]
  if (worse === undefined) await page.getByRole('checkbox', { name: /^Flag for damage/ }).check()
  else await grade.selectOption(worse)
  await page.getByRole('button', { name: 'Take the ticked units back' }).click()
  await page.getByRole('button', { name: 'Yes, take them back' }).click()

  // The notice of what the return did says the same thing in a sentence of its
  // own, so these two are matched whole.
  await expect(page.getByText('The deposit is waiting for a damage report', { exact: true })).toBeVisible()
  await expect(page.getByText('Waiting for a damage report.', { exact: true })).toBeVisible()
  expect(await blockingViolations(page)).toEqual([])
  const link = page.getByRole('link', { name: /^Record the damage to / })
  const tag = (await link.innerText()).replace('Record the damage to', '').trim()
  await link.click()
  return tag
}

/**
 * SC-16. A minor report that charges the customer, asked in words and filed.
 *
 * @returns The reference of the report.
 */
export async function fileAChargeableReport(page: Page, tag: string): Promise<string> {
  await expect(page.getByRole('heading', { level: 1, name: DAMAGE_HEADING })).toBeVisible()
  await expect(page.getByText('This unit came back on a hire')).toBeVisible()
  await expect(page.getByText(`${tag}, `, { exact: false }).first()).toBeVisible()
  const form = page.getByRole('form', { name: 'What happened' })
  await form.getByRole('radio', { name: /^Minor/ }).check()
  await form.getByLabel('Describe the damage').fill('Guard bent where it bolts to the housing. The unit still runs.')
  await form.getByLabel('Estimated repair cost, in rand').fill('80.00')
  const decision = form.getByRole('group', { name: 'Is the customer charged for this damage?' })
  await expect(decision.getByRole('radio', { checked: true })).toHaveCount(0)
  await decision.getByRole('radio', { name: /^Charge the customer/ }).check()
  const recovery = form.getByLabel('Amount to recover from the customer, in rand, including VAT')
  await recovery.fill(RECOVERY_AMOUNT)
  // The hire named in the address gives the cap before any report exists.
  await expect(recovery).toHaveAccessibleDescription(REPLACEMENT_VALUE_NAMED)
  expect(await blockingViolations(page)).toEqual([])

  await form.getByRole('button', { name: 'Record the damage and quarantine the unit' }).click()
  await expect(page.getByRole('heading', { level: 2, name: `File this damage report for ${tag}?` })).toBeFocused()
  await expect(page.getByText(/cannot be booked until the owner resolves the report\.$/)).toBeVisible()
  await page.getByRole('button', { name: 'Yes, file the report' }).click()

  const filed = page.getByText(/^Damage report TSH-D-\d{2}-\d+ is filed$/)
  await expect(filed).toBeVisible()
  const reference = DAMAGE_REFERENCE.exec(await filed.innerText())?.[0] ?? ''
  expect(reference).toMatch(DAMAGE_REFERENCE)
  expect(await blockingViolations(page)).toEqual([])
  return reference
}

/** Back on SC-15, read afresh. The deposit is settled with the recovery withheld. */
export async function seeTheRecoveryWithheld(page: Page): Promise<void> {
  await page.getByRole('link', { name: /^Back to the return of TSH-H-/ }).click()
  await expect(page.getByRole('heading', { level: 1, name: RETURN_HEADING })).toBeVisible()
  await expect(page.getByText(/^TSH-H-\d{2}-\d{6} is settled$/)).toBeVisible()
  await expect(page.getByText('The deposit is waiting for a damage report')).toHaveCount(0)
  await expect(page.getByText('The damage report is filed.')).toBeVisible()
  expect(await settlementAmount(page, 'Withheld from the deposit')).toMatch(RECOVERY_SHOWN)
  expect(await settlementAmount(page, 'Balance due')).toMatch(NOTHING)
  await expect(page.getByText(/^Recovery charge\./)).toBeVisible()
  await expect(page.getByText('Back and settled', { exact: true })).toBeVisible()
  expect(await blockingViolations(page)).toEqual([])
}

/**
 * The owner, on a browser of their own, resolves the report as repaired on
 * SC-16. Nobody but an administrator is offered that.
 */
export async function ownerResolves(browser: Browser, testInfo: TestInfo, tag: string, reference: string): Promise<void> {
  const context = await browser.newContext({ baseURL: testInfo.project.use.baseURL })
  try {
    const page = await context.newPage()
    await signInAsOwner(page)
    await page.goto(`/counter/damage/${encodeURIComponent(tag)}`)
    await expect(page.getByRole('heading', { level: 1, name: DAMAGE_HEADING })).toBeVisible()
    const report = page.getByRole('article', { name: reference })
    await report.getByRole('button', { name: `Resolve ${reference}` }).click()
    const form = report.getByRole('form', { name: `Resolve ${reference}` })
    await form.getByRole('radio', { name: /^Repaired/ }).check()
    await form.getByLabel('Actual repair cost, in rand').fill('45.00')
    await form.getByLabel('Notes').fill('Guard straightened and refitted.')
    await expect(form.getByText(`${tag} goes back on the shelf`, { exact: false })).toBeVisible()
    expect(await blockingViolations(page)).toEqual([])
    await form.getByRole('button', { name: 'Resolve as repaired' }).click()

    await expect(page.getByText(`${reference} is resolved`)).toBeVisible()
    await expect(report.getByText('Resolved, repaired')).toBeVisible()
    await expect(report.getByRole('button')).toHaveCount(0)
  } finally {
    await context.close()
  }
}
