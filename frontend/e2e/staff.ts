/**
 * The seeded counter assistants the browser tests sign in as, and the sign in.
 *
 * The seed makes one counter assistant at the Cape Town CBD branch and one at
 * Bellville, in `backend/seeding/people.py`. Each browser project signs in as
 * a different one, so the two journeys of a run work at different counters
 * and never compete for the same unit.
 *
 * The password is never written here. It comes from `E2E_STAFF_PASSWORD`, and
 * falls back to the password the development seed gives every account.
 *
 * The API counts every sign in attempt for an email address and allows ten in
 * fifteen minutes. One run signs each assistant in three times, once for the
 * counter journey and once for each counter overview journey.
 */

import { expect } from '@playwright/test'
import type { Page } from '@playwright/test'
import { DEVELOPMENT_SEED_PASSWORD } from './customer.ts'
import { SIGN_IN } from './routes.ts'

/** The counter assistant at Cape Town CBD. */
export const CBD_COUNTER_EMAIL = 'elmarie@toolshedhire.co.za'

/** The counter assistant at Bellville. */
export const BLV_COUNTER_EMAIL = 'thabo@toolshedhire.co.za'

export const STAFF_PASSWORD = process.env.E2E_STAFF_PASSWORD ?? DEVELOPMENT_SEED_PASSWORD

/** Which assistant each browser project signs in as. */
const STAFF_FOR_PROJECT: Record<string, string> = {
  'chromium-desktop': CBD_COUNTER_EMAIL,
  'chromium-mobile': BLV_COUNTER_EMAIL,
}

/** The assistant a browser project signs in as. */
export function staffFor(projectName: string): string {
  return STAFF_FOR_PROJECT[projectName] ?? CBD_COUNTER_EMAIL
}

/** The heading of the counter's home, where an assistant lands after signing in. */
export const COUNTER_HOME_HEADING = 'Today at the counter'

/** Open the sign in screen and sign a seeded counter assistant in. */
export async function signInAsStaff(page: Page, email: string): Promise<void> {
  await page.goto(SIGN_IN.path)
  await expect(page.getByRole('heading', { level: 1, name: SIGN_IN.heading })).toBeVisible()
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(STAFF_PASSWORD)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1, name: COUNTER_HOME_HEADING })).toBeVisible()
}
