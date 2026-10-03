/**
 * The browser's clock, started where the API's clock is when the API runs on
 * a pinned one.
 *
 * In the browser tests the API runs with `TEST_BUSINESS_TIME`, which starts its
 * clock at that time of day in Cape Town on today's date and lets it run on, so
 * a booking for today can go out at any hour. The hold step counts down to the
 * instant the API says a hold ends, and it counts with the browser's clock.
 * When the two clocks are hours apart the countdown is hours long, or already
 * at nought, and a hold the API still has looks lapsed.
 *
 * So when the same variable is set for this run, which the pipeline does for
 * the whole job, I start the browser's clock at that time of day on today's
 * date in Cape Town before the page loads, and let it run on. The API started a
 * little earlier, so its clock is a little ahead, and a hold shows a little
 * more time left than the API gives it and never less. Without the variable the
 * browser keeps the real time, which is the time the API keeps then too.
 */

import type { Page } from '@playwright/test'
import { dateFromToday } from './hire-dates.ts'

/** The variable the API reads its starting time of day from. */
const API_CLOCK_VARIABLE = 'TEST_BUSINESS_TIME'

/** A time of day the way the API reads the variable, `HH:MM` or `HH:MM:SS`. */
const TIME_OF_DAY = /^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$/

/** How long `HH:MM` is. A value this long has no seconds yet. */
const HOURS_AND_MINUTES_LENGTH = 5

/** South Africa keeps the one offset from UTC all year. */
const BRANCH_UTC_OFFSET = '+02:00'

/**
 * Start the browser's clock at the time the API's clock started at, when the
 * run says the API's clock is pinned. Call it before the page first loads.
 *
 * @throws Error when the variable is set to something the API would not read
 *   as a time of day.
 */
export async function startBrowserClockWithTheApi(page: Page): Promise<void> {
  const timeOfDay = process.env[API_CLOCK_VARIABLE]
  if (!timeOfDay) return
  if (!TIME_OF_DAY.test(timeOfDay)) {
    throw new Error(
      `${API_CLOCK_VARIABLE} is "${timeOfDay}", and the browser clock can only be started at a time of day ` +
        'such as 10:00. Set it to the value the API was started with.',
    )
  }
  const seconds = timeOfDay.length === HOURS_AND_MINUTES_LENGTH ? ':00' : ''
  await page.clock.install({ time: new Date(`${dateFromToday(0)}T${timeOfDay}${seconds}${BRANCH_UTC_OFFSET}`) })
}
