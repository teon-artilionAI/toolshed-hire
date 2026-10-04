/**
 * A confirmed booking for today at the counter, made the way an assistant
 * makes one, for a journey that needs one to act on.
 *
 * It registers a walk in with a name nobody has used on SC-12 and books one
 * unit for today at the assistant's own branch on SC-13. A new walk in each
 * time keeps the strike a no show records away from every other customer, so
 * no run can put a seeded account on hold.
 *
 * counter.spec.ts walks the same screens and checks each step on the way. This
 * walks them without stopping, and leaves that checking to it.
 *
 * The journeys run in the same browser project, so all of them work at the
 * same branch. counter.spec.ts takes the last model free on the first page and
 * has its unit out on hire while it runs. The no show journey takes the model
 * before it, the damage journey the one before that, and the admin operations
 * journey the one before that, so no two of them take the same unit.
 */

import { expect } from '@playwright/test'
import type { Page } from '@playwright/test'
import { REFERENCE } from './booking.ts'

/** How many digits of the time go into a phone number, after its prefix. */
const PHONE_TIME_DIGITS = 8

/** What a booking is for. Each keeps its walk in and its model apart from
 *  every other journey's. */
export type BookingPurpose = 'noShow' | 'damage' | 'correction'

interface PurposeDetails {
  /** The word in the walk in's name. */
  word: string
  /** The digit after the leading zero of the walk in's number, in each project. */
  mobileDigit: string
  desktopDigit: string
  /** Counted back from the end of the models free at the branch. The last is
   *  the one counter.spec.ts takes. */
  modelsFromTheEnd: number
}

const PURPOSES: Record<BookingPurpose, PurposeDetails> = {
  noShow: { word: 'Noshow', mobileDigit: '5', desktopDigit: '6', modelsFromTheEnd: 2 },
  damage: { word: 'Damage', mobileDigit: '3', desktopDigit: '4', modelsFromTheEnd: 3 },
  correction: { word: 'Correction', mobileDigit: '1', desktopDigit: '2', modelsFromTheEnd: 4 },
}

const CONFIRMED_STEP = 'Step 4 of 4. The booking is confirmed'

/** What the booking was made for, to find it again on another screen. */
export interface CounterBooking {
  customerName: string
  reference: string
}

/** A full name and a mobile number nobody has used. The time keeps one run
 *  apart from the next, and the project keeps the two browsers of one run
 *  apart. The digit after the zero differs from counter.spec.ts and between
 *  purposes. */
function unusedWalkIn(projectName: string, purpose: PurposeDetails): { name: string; phone: string } {
  const mobile = projectName.includes('mobile')
  const stamp = String(Date.now())
  return {
    name: `${mobile ? 'Mobile' : 'Desktop'} ${purpose.word}${stamp}`,
    phone: `0${mobile ? purpose.mobileDigit : purpose.desktopDigit}${stamp.slice(-PHONE_TIME_DIGITS)}`,
  }
}

/**
 * Register a walk in and confirm a booking of one unit for them for today.
 *
 * The assistant must already be signed in.
 *
 * @param projectName The browser project, which decides the name and number.
 * @param purpose What the booking is for, which decides the model it takes.
 * @returns The walk in's name and the reference the API gave the booking.
 */
export async function bookForTodayAtTheCounter(
  page: Page,
  projectName: string,
  purpose: BookingPurpose = 'noShow',
): Promise<CounterBooking> {
  const details = PURPOSES[purpose]
  const { name, phone } = unusedWalkIn(projectName, details)

  // SC-12. The walk in, with no login, at the assistant's branch.
  await page.goto('/counter/customers')
  await expect(page.getByRole('heading', { level: 1, name: 'Find a customer' })).toBeVisible()
  await page.getByLabel('Full name').fill(name)
  await page.getByLabel('Mobile number').fill(phone)
  await page.getByLabel('Last four characters of the document number').fill('5083')
  await page.getByLabel('Billing address, first line').fill('12 Loop Street')
  await page.getByLabel('Billing suburb').fill('Gardens')
  await page.getByLabel('Postal code').fill('8001')
  await page.getByRole('button', { name: 'Add this customer' }).click()
  await expect(page.getByText(`${name} is on file`)).toBeVisible()
  await page.getByRole('link', { name: `New booking for ${name}` }).click()

  // SC-13. One unit, held and confirmed. A new booking goes out today unless
  // someone changes the dates, so these are left as they open.
  await expect(page.getByRole('heading', { level: 1, name: 'New booking' })).toBeVisible()
  const finder = page.getByRole('region', { name: 'Tools free at this branch' })
  const freeModels = /^\d+ models? (is|are) free at .+ for these dates\.$/
  await expect(finder.getByRole('status').filter({ hasText: freeModels })).toBeVisible()
  const addButtons = finder.getByRole('button', { name: /^Add / })
  const freeCount = await addButtons.count()
  expect(freeCount, `the branch needs ${details.modelsFromTheEnd} free models for today`).toBeGreaterThanOrEqual(
    details.modelsFromTheEnd,
  )
  await addButtons.nth(freeCount - details.modelsFromTheEnd).click()
  await expect(page.getByText(/^1 unit free at .+ for these dates$/)).toBeVisible()

  await page.getByRole('button', { name: 'Work out the cost' }).click()
  await page.getByRole('button', { name: 'Hold the equipment' }).click()
  await page.getByRole('button', { name: 'Confirm the booking' }).click()
  await expect(page.getByRole('heading', { level: 2, name: CONFIRMED_STEP })).toBeFocused()
  const confirmation = page.getByText(new RegExp(`^Booking ${REFERENCE.source} is confirmed$`))
  const reference = REFERENCE.exec(await confirmation.innerText())?.[0] ?? ''
  expect(reference).toMatch(REFERENCE)
  return { customerName: name, reference }
}
