/**
 * The owner's trading calendar, the view of SC-19 at /admin/closure-days, with
 * its questions open, scanned for accessibility and measured on a phone 360
 * pixels wide.
 *
 * The calendar is scanned and measured loaded in accessibility.spec.ts and
 * narrow-screens.spec.ts, from the list of the owner's screens they share.
 * The journey is checked here. The owner closes a day at Cape Town CBD, which
 * first lists the two bookings that start or end on it and says they are not
 * cancelled, and finds it on the calendar. Then they cancel the Bellville
 * closure, which asks first. A day the server refuses comes back under the day
 * on the form. The calendar with no closed day and with the API down is
 * scanned as well, the states the other owner's screens are scanned in.
 *
 * Like those specs it answers the API itself, from calendar-answers.ts through
 * admin-answers.ts, so it runs with or without a backend and never depends on
 * what a database holds. The answers here remember what was closed and what
 * was cancelled, so the calendar read after each change shows it.
 */

import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { ADMIN_SCREENS, openAdminScreen } from './admin-answers.ts'
import type { AdminScreen } from './admin-answers.ts'
import { Answered, problem } from './answered.ts'
import { blockingViolations, reportedViolations } from './axe.ts'
import { BELLVILLE_CLOSURE_ID, CBD_CLOSURE, DAY_TO_CLOSE, closedDays } from './calendar-answers.ts'
import { dayInWords } from './hire-dates.ts'
import { NARROW_PHONE, ROUNDING_PIXELS, sidewaysOverflow } from './overflow.ts'

const CALENDAR_ROUTE = 'GET /api/admin/closure-days'
const ADD_ROUTE = 'POST /api/admin/closure-days'
const CANCEL_ROUTE = `POST /api/admin/closure-days/${BELLVILLE_CLOSURE_ID}/cancel`
const CLOSE_QUESTION = `Close Cape Town CBD on ${dayInWords(DAY_TO_CLOSE)}?`

/** A page of nothing, the way the calendar answers when no day is closed. */
const NOTHING_CLOSED = { items: [] }

/** The API down, the way the proxy answers when the backend is not there. */
const API_DOWN = problem(503, 'service-unavailable', 'The service is not available.')

function calendarView(): AdminScreen {
  const found = ADMIN_SCREENS.find((screen) => screen.id === 'VIEW-01')
  if (found === undefined) throw new Error('ADMIN_SCREENS has no trading calendar to open.')
  return found
}

/** Fill the form for a stocktake at Cape Town CBD on the day, and send it. */
async function askToClose(page: Page): Promise<void> {
  const form = page.getByRole('form', { name: 'Close a day' })
  await form.getByLabel('Branch').selectOption({ label: 'Cape Town CBD' })
  await form.getByLabel('Day to close').fill(DAY_TO_CLOSE)
  await form.getByLabel('Reason customers read').fill('Stocktake')
  await form.getByRole('button', { name: 'Check the bookings and close the day' }).click()
}

/** The calendar's answers, which remember a closure added and one cancelled. */
function rememberingAnswers(): Record<string, unknown> {
  let days = closedDays()
  return {
    [CALENDAR_ROUTE]: () => ({ items: days }),
    [ADD_ROUTE]: () => {
      days = [...days, { day: DAY_TO_CLOSE, branchCode: 'CBD', reason: 'Stocktake', kind: 'closure', closureId: CBD_CLOSURE.id }]
      days.sort((first, second) => first.day.localeCompare(second.day))
      return new Answered(201, CBD_CLOSURE)
    },
    [CANCEL_ROUTE]: () => {
      const bellville = days.find((day) => day.closureId === BELLVILLE_CLOSURE_ID)
      days = days.filter((day) => day.closureId !== BELLVILLE_CLOSURE_ID)
      return { ...CBD_CLOSURE, id: BELLVILLE_CLOSURE_ID, branchCode: 'BLV', day: bellville?.day, cancelledAt: '2026-10-13T08:05:00+02:00' }
    },
  }
}

test.describe('the owner closes a day and opens another again', () => {
  test('closing a day lists its bookings first, cancelling asks first, and neither has serious or critical accessibility violations', async ({
    page,
  }) => {
    await openAdminScreen(page, calendarView(), rememberingAnswers())

    await askToClose(page)
    await expect(page.getByRole('heading', { level: 3, name: CLOSE_QUESTION })).toBeFocused()
    await expect(page.getByText('2 bookings start or end on that day.')).toBeVisible()
    await expect(page.getByText(/Closing the day does not cancel these bookings/)).toBeVisible()
    expect(await blockingViolations(page)).toEqual([])

    await page.getByRole('button', { name: 'Yes, close the day' }).click()
    await expect(page.getByText(`Cape Town CBD is closed on ${dayInWords(DAY_TO_CLOSE)}`)).toBeVisible()
    await expect(page.getByRole('button', { name: `Cancel the closure of Cape Town CBD on ${dayInWords(DAY_TO_CLOSE)}` })).toBeVisible()

    await page.getByRole('button', { name: /^Cancel the closure of Bellville on / }).click()
    await expect(page.getByRole('heading', { level: 4, name: /^Open Bellville again on / })).toBeFocused()
    expect(await blockingViolations(page)).toEqual([])

    await page.getByRole('button', { name: 'Yes, cancel the closure' }).click()
    await expect(page.getByText(/^Bellville is open again on /)).toBeVisible()
    await expect(page.getByRole('button', { name: /^Cancel the closure of Bellville on / })).toHaveCount(0)
  })

  test('a day the server refuses comes back under the day, with no serious or critical accessibility violations', async ({
    page,
  }) => {
    const sentence = 'Choose today or a later day. A day that has passed cannot be closed.'
    await openAdminScreen(page, calendarView(), {
      [ADD_ROUTE]: problem(422, 'request-validation-failure', 'Some of the details were not accepted.', {
        fields: { 'body.day': sentence },
      }),
    })

    await askToClose(page)
    await page.getByRole('button', { name: 'Yes, close the day' }).click()

    const form = page.getByRole('form', { name: 'Close a day' })
    await expect(form.getByLabel('Day to close')).toHaveAccessibleDescription(new RegExp(sentence))
    await expect(form.getByLabel('Reason customers read')).toHaveValue('Stocktake')
    expect(await blockingViolations(page)).toEqual([])
  })
})

test.describe('the trading calendar with nothing to list or nothing to read', () => {
  test('with no closed day it has no serious or critical accessibility violations', async ({ page }) => {
    await openAdminScreen(page, { ...calendarView(), loaded: 'No day is closed in the next twelve months' }, {
      [CALENDAR_ROUTE]: NOTHING_CLOSED,
    })
    expect(await reportedViolations(page, 'the trading calendar with no closed day')).toEqual([])
  })

  test('with the API down it has no serious or critical accessibility violations', async ({ page }) => {
    await openAdminScreen(page, { ...calendarView(), loaded: /^We could not load the closed days/ }, {
      [CALENDAR_ROUTE]: API_DOWN,
    })
    expect(await reportedViolations(page, 'the trading calendar with the API down')).toEqual([])
  })
})

test.describe('the trading calendar on a phone 360 pixels wide', () => {
  test.use({ viewport: NARROW_PHONE })

  test('the question with its bookings and the question before a cancel fit, with nothing to scroll sideways', async ({
    page,
  }) => {
    await openAdminScreen(page, calendarView())

    await askToClose(page)
    await expect(page.getByRole('heading', { level: 3, name: CLOSE_QUESTION })).toBeVisible()
    expect(await sidewaysOverflow(page)).toBeLessThanOrEqual(ROUNDING_PIXELS)

    await page.getByRole('button', { name: 'Go back and change it' }).click()
    await page.getByRole('button', { name: /^Cancel the closure of Bellville on / }).click()
    await expect(page.getByRole('heading', { level: 4, name: /^Open Bellville again on / })).toBeVisible()
    expect(await sidewaysOverflow(page)).toBeLessThanOrEqual(ROUNDING_PIXELS)
  })
})
