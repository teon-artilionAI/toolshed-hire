/**
 * The seeded counter assistants the browser tests sign in as, and the sign in.
 *
 * The seed makes one counter assistant at the Cape Town CBD branch and one at
 * Bellville, in `backend/seeding/people.py`. Each browser project signs in as
 * a different one, so the two journeys of a run work at different counters
 * and never compete for the same unit.
 *
 * The password is never written here. It comes from `E2E_STAFF_PASSWORD`, and
 * on a local project falls back to the password the development seed gives
 * every account. The staging project has no fallback, see staging.ts.
 *
 * The seed also makes one administrator, the owner, who resolves the damage
 * report the damage journey files, so the unit goes back on the shelf, who
 * reads the dashboard and the report in the reporting spec, who reads the
 * audit trail and reverses a charge in the admin operations spec, who
 * changes a late fee and adds a model in the admin catalogue spec, who
 * registers a unit and moves it through its lifecycle in the asset register
 * spec, who opens, deactivates and reactivates a staff account in the user
 * management spec, and who reads the dashboard, the report, the register and
 * the trail in the release journeys.
 *
 * The API counts every sign in attempt for an email address and allows ten in
 * fifteen minutes unless `LOGIN_ATTEMPTS_PER_EMAIL` says otherwise. One run
 * signs each assistant in six times, once for each counter journey, each
 * counter overview journey, the admin operations journey and the counter
 * journey of the release, and the owner fourteen times, once for the damage
 * journey, the reporting spec, the admin operations spec, the admin catalogue
 * spec, the asset register spec, the user management spec and the release
 * journeys in each browser project. That is more than the default allowance,
 * so a run against a local backend needs the same raised limit the pipeline
 * sets, or the owner's eleventh sign in is refused. The staging project signs
 * the assistant at Cape Town CBD in once and the owner once.
 */

import { expect } from '@playwright/test'
import type { Page } from '@playwright/test'
import { DEVELOPMENT_SEED_PASSWORD } from './customer.ts'
import { SIGN_IN } from './routes.ts'
import { STAFF_PASSWORD_VARIABLE, STAGING_PROJECT } from './staging-run.ts'
import { passwordFrom } from './staging.ts'

/** The counter assistant at Cape Town CBD. */
export const CBD_COUNTER_EMAIL = 'elmarie@toolshedhire.co.za'

/** The counter assistant at Bellville. */
export const BLV_COUNTER_EMAIL = 'thabo@toolshedhire.co.za'

/** The administrator, who is the owner. */
export const ADMIN_EMAIL = 'marius@toolshedhire.co.za'

/** The password of the seeded staff and the owner, for the project that is running. */
function staffPassword(): string {
  return passwordFrom(STAFF_PASSWORD_VARIABLE, DEVELOPMENT_SEED_PASSWORD)
}

/** Which assistant each browser project signs in as. */
const STAFF_FOR_PROJECT: Record<string, string> = {
  'chromium-desktop': CBD_COUNTER_EMAIL,
  'chromium-mobile': BLV_COUNTER_EMAIL,
  [STAGING_PROJECT]: CBD_COUNTER_EMAIL,
}

/** The assistant a browser project signs in as. */
export function staffFor(projectName: string): string {
  return STAFF_FOR_PROJECT[projectName] ?? CBD_COUNTER_EMAIL
}

/** The heading of the counter's home, where an assistant lands after signing in. */
export const COUNTER_HOME_HEADING = 'Today at the counter'

/** The heading of the owner's home, where an administrator lands after signing in. */
export const ADMIN_HOME_HEADING = 'Business overview'

/** Open the sign in screen and sign a seeded member of staff in, and wait for
 *  the home they land on. */
async function signInAs(page: Page, email: string, homeHeading: string): Promise<void> {
  await page.goto(SIGN_IN.path)
  await expect(page.getByRole('heading', { level: 1, name: SIGN_IN.heading })).toBeVisible()
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(staffPassword())
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1, name: homeHeading })).toBeVisible()
}

/** Open the sign in screen and sign a seeded counter assistant in. */
export async function signInAsStaff(page: Page, email: string): Promise<void> {
  await signInAs(page, email, COUNTER_HOME_HEADING)
}

/** Open the sign in screen and sign the seeded owner in. */
export async function signInAsOwner(page: Page): Promise<void> {
  await signInAs(page, ADMIN_EMAIL, ADMIN_HOME_HEADING)
}
