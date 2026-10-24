/**
 * B4.6 signed-in staging browser network loss.
 *
 * The local database-termination and isolated Docker network-cut drills are
 * recorded separately. This is the remaining signed-in staging drill. It runs
 * only on the staging project, signs in with the staging environment's own
 * secret through the existing CI path, books one unit for today, loses the
 * browser network during checkout and again during the return, restores after
 * thirty seconds, and carries on without a second sign-in.
 *
 * The test skips with a clear reason when the branch is closed or within five
 * minutes of closing, because the checkout and return need an open trading
 * day. It does not use a mock, a clock change or an anonymous request.
 */

import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { bookForTodayAtTheCounter } from './counter-booking.ts'
import { signInAsStaff, staffFor } from './staff.ts'
import { note, onStaging } from './staging.ts'

const OFFLINE_MS = 30_000
const CLOSE_BUFFER_MINUTES = 5
const DASHBOARD_ROUTE = /\/api\/counter\/dashboard$/
const CHECKOUT_ROUTE = /\/api\/reservations\/[^/]+\/checkout$/
const RETURN_ROUTE = /\/api\/rentals\/[^/]+\/returns$/
const NETWORK_ERROR = /We could not reach Toolshed Hire/

interface TradingDay {
  opensAt: string | null
  closesAt: string | null
  closedKind: string | null
  closedReason: string | null
}

interface Dashboard {
  date: string
  trading: TradingDay
}

interface Rental {
  reference: string
  items: { returnedAt: string | null }[]
  charges: { type: string }[]
}

function clockMinutes(clock: string): number {
  const [hours, minutes] = clock.split(':').map(Number)
  return hours * 60 + minutes
}

function sastClock(): string {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Africa/Johannesburg',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(new Date())
}

function requireOpenBranch(trading: TradingDay, now: string): void {
  if (trading.closedKind !== null) {
    test.skip(true, `The branch is closed today (${trading.closedReason ?? trading.closedKind}).`)
    return
  }
  const opensAt = trading.opensAt
  const closesAt = trading.closesAt
  if (opensAt === null || closesAt === null) {
    test.skip(true, 'The branch has no opening hours today.')
    return
  }
  const current = clockMinutes(now)
  const opens = clockMinutes(opensAt)
  const closes = clockMinutes(closesAt)
  if (current < opens || current >= closes) {
    test.skip(true, `The branch is not open now (${now} SAST, ${opensAt} to ${closesAt}).`)
    return
  }
  if (closes - current < CLOSE_BUFFER_MINUTES) {
    test.skip(true, `The branch closes at ${closesAt}, less than ${CLOSE_BUFFER_MINUTES} minutes away.`)
  }
}

async function loseAndRestore(page: Page, action: () => Promise<void>): Promise<number> {
  const started = Date.now()
  await page.context().setOffline(true)
  await action()
  await expect(page.getByText(NETWORK_ERROR)).toBeVisible({ timeout: 20_000 })
  await page.waitForTimeout(OFFLINE_MS)
  await page.context().setOffline(false)
  return Date.now() - started
}

test('a signed-in counter checkout and return survive a browser network loss', { tag: '@staging' }, async ({
  page,
  request,
}, testInfo) => {
  test.skip(!onStaging(), 'This drill runs on the staging project only.')

  const health = await request.get('/api/health')
  expect(health.ok()).toBe(true)
  const healthBody = (await health.json()) as {
    environment: string
    revision: string
    databaseReachable: boolean
  }
  expect(healthBody.environment).toBe('staging')
  expect(healthBody.databaseReachable).toBe(true)
  expect(healthBody.revision).toMatch(/^toolshed-api-staging-/)

  const dashboardResponse = page.waitForResponse(
    (response) => DASHBOARD_ROUTE.test(new URL(response.url()).pathname) && response.ok(),
  )
  await signInAsStaff(page, staffFor(testInfo.project.name))
  const dashboard = (await (await dashboardResponse).json()) as Dashboard
  const now = sastClock()
  requireOpenBranch(dashboard.trading, now)

  note(
    `B4.6 staging drill starting on revision ${healthBody.revision} at ${dashboard.date} ${now} SAST, ` +
      `branch hours ${dashboard.trading.opensAt} to ${dashboard.trading.closesAt}.`,
  )

  await bookForTodayAtTheCounter(page, testInfo.project.name, 'b46')
  await page.getByRole('link', { name: 'Check out now' }).click()
  await expect(
    page.getByRole('heading', { level: 2, name: /^Step 1 of 3\. Check each unit and take the deposit$/ }),
  ).toBeVisible()

  for (const tag of await page.getByRole('checkbox', { name: /I have read the tag on the unit/ }).all()) {
    await tag.check()
  }
  await page.getByRole('checkbox', { name: /read the hire agreement and signed it/ }).check()

  await page.getByRole('button', { name: 'Check out the equipment' }).click()
  await expect(page.getByRole('button', { name: 'Yes, hand it over' })).toBeVisible()
  const checkoutOfflineMs = await loseAndRestore(page, async () => {
    await page.getByRole('button', { name: 'Yes, hand it over' }).click()
  })
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()

  const checkoutResponse = page.waitForResponse(
    (response) => response.request().method() === 'POST' && CHECKOUT_ROUTE.test(new URL(response.url()).pathname),
  )
  if (await page.getByRole('button', { name: 'Yes, hand it over' }).isVisible()) {
    await page.getByRole('button', { name: 'Yes, hand it over' }).click()
  } else {
    await page.getByRole('button', { name: 'Check out the equipment' }).click()
    await page.getByRole('button', { name: 'Yes, hand it over' }).click()
  }
  const checkoutAnswer = await checkoutResponse
  expect(checkoutAnswer.ok()).toBe(true)
  const checkout = (await checkoutAnswer.json()) as Rental
  expect(checkout.reference).toMatch(/^TSH-H-\d{2}-\d{6}$/)
  expect(checkout.items).toHaveLength(1)
  expect(checkout.charges.map((charge) => charge.type)).toEqual(
    expect.arrayContaining(['HIRE', 'DEPOSIT_HOLD']),
  )

  await expect(
    page.getByRole('heading', {
      level: 2,
      name: /^Step 3 of 3\. The equipment is out on hire TSH-H-\d{2}-\d{6}$/,
    }),
  ).toBeFocused()
  await page.getByRole('link', { name: 'Open the hire' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Return and condition inspection' })).toBeVisible()

  await page.getByRole('checkbox', { name: /is back on the counter\. Take it back now\.$/ }).check()
  await page.getByRole('button', { name: 'Take the ticked units back' }).click()
  await expect(page.getByRole('button', { name: 'Yes, take them back' })).toBeVisible()
  const returnOfflineMs = await loseAndRestore(page, async () => {
    await page.getByRole('button', { name: 'Yes, take them back' }).click()
  })
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()

  const returnResponse = page.waitForResponse(
    (response) => response.request().method() === 'POST' && RETURN_ROUTE.test(new URL(response.url()).pathname),
  )
  if (await page.getByRole('button', { name: 'Yes, take them back' }).isVisible()) {
    await page.getByRole('button', { name: 'Yes, take them back' }).click()
  } else {
    await page.getByRole('button', { name: 'Take the ticked units back' }).click()
    await page.getByRole('button', { name: 'Yes, take them back' }).click()
  }
  const returnAnswer = await returnResponse
  expect(returnAnswer.ok()).toBe(true)
  const returned = (await returnAnswer.json()) as Rental
  expect(returned.reference).toBe(checkout.reference)
  expect(returned.items).toHaveLength(1)
  expect(returned.items.every((item) => item.returnedAt !== null)).toBe(true)
  expect(returned.charges.map((charge) => charge.type)).toEqual(
    expect.arrayContaining(['DEPOSIT_RELEASE']),
  )

  await expect(page.getByText(/^Every unit on TSH-H-\d{2}-\d{6} is back$/)).toBeVisible()
  await expect(page.getByText(/was released in full\. Nothing is due\.$/)).toBeVisible()

  note(
    `B4.6 staging drill passed for ${checkout.reference}. ` +
      `Offline checkout ${(checkoutOfflineMs / 1000).toFixed(1)} s, offline return ${(returnOfflineMs / 1000).toFixed(1)} s. ` +
      'The session survived both losses without a second sign-in. Checkout and return each returned one item for the same rental.',
  )
})
