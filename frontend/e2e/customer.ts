/**
 * The seeded customers the browser tests sign in as, and the sign in itself.
 *
 * The password is never written here. It comes from `E2E_CUSTOMER_PASSWORD`,
 * and on a local project falls back to the password the development seed
 * uses. The staging project has no fallback, see staging.ts.
 *
 * The API counts every sign in attempt for an email address, the ones that
 * succeed as well, and allows ten in a fixed window of fifteen minutes. Every
 * spec that calls `signInAsCustomer` spends one of them in each browser
 * project. One run signs the first customer in eight times and the second one
 * six times, so each stays inside the ten. The first is signed in twice more
 * when the counter journey of the release finds the branch closed and the
 * customer cancels the booking, which makes ten, the most the window allows.
 * On the staging project the release journeys sign the first customer in
 * once, or twice when the branch has closed.
 */

import { expect } from '@playwright/test'
import type { Page } from '@playwright/test'
import { SIGN_IN } from './routes.ts'
import { CUSTOMER_PASSWORD_VARIABLE } from './staging-run.ts'
import { passwordFrom } from './staging.ts'

/** The customer the seed creates first. Most journeys sign in as them. */
export const CUSTOMER_EMAIL = 'w.adonis@buildright.co.za'

/** The other customer the seed creates. A journey signs in as them to book
 *  beside the first, and to look at the first one's booking as a stranger. */
export const SECOND_CUSTOMER_EMAIL = 'nomsa.dlamini@example.com'

/** The password the seed gives every account when `SEED_PASSWORD` is unset.
 *  It exists in development only. The staff accounts fall back to it too. */
export const DEVELOPMENT_SEED_PASSWORD = 'toolshed-dev-password'

/** The password of the seeded customers, for the project that is running. */
function customerPassword(): string {
  return passwordFrom(CUSTOMER_PASSWORD_VARIABLE, DEVELOPMENT_SEED_PASSWORD)
}

/** Fill in the sign in form that is on the page and send it. */
export async function submitCustomerSignIn(page: Page, email: string = CUSTOMER_EMAIL): Promise<void> {
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(customerPassword())
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
}

/** What the sign in said about the account that a journey goes on to need. */
export interface SignedInCustomer {
  /** Whether this environment can deliver email to the customer's address.
   *  A backend that does not send the flag yet counts as false, the way the
   *  screens read it. */
  emailDeliverable: boolean
}

const LOGIN_PATH = '/api/auth/login'

/** Open the sign in screen and sign a seeded customer in. */
export async function signInAsCustomer(page: Page, email: string = CUSTOMER_EMAIL): Promise<SignedInCustomer> {
  await page.goto(SIGN_IN.path)
  await expect(page.getByRole('heading', { level: 1, name: SIGN_IN.heading })).toBeVisible()
  const answered = page.waitForResponse(
    (response) => response.request().method() === 'POST' && new URL(response.url()).pathname === LOGIN_PATH,
  )
  await submitCustomerSignIn(page, email)
  const answer = await answered
  if (!answer.ok()) return { emailDeliverable: false }
  const body = (await answer.json()) as { user?: { emailDeliverable?: unknown } }
  return { emailDeliverable: body.user?.emailDeliverable === true }
}
