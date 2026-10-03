/**
 * The seeded customers the browser tests sign in as, and the sign in itself.
 *
 * The password is never written here. It comes from `E2E_CUSTOMER_PASSWORD`,
 * and falls back to the password the development seed uses.
 *
 * The API counts every sign in attempt for an email address, the ones that
 * succeed as well, and allows ten in a fixed window of fifteen minutes. Every
 * spec that calls `signInAsCustomer` spends one of them in each browser
 * project. One run signs the first customer in six times and the second one
 * six times, so each stays inside the ten.
 */

import { expect } from '@playwright/test'
import type { Page } from '@playwright/test'
import { SIGN_IN } from './routes.ts'

/** The customer the seed creates first. Most journeys sign in as them. */
export const CUSTOMER_EMAIL = 'w.adonis@buildright.co.za'

/** The other customer the seed creates. A journey signs in as them to book
 *  beside the first, and to look at the first one's booking as a stranger. */
export const SECOND_CUSTOMER_EMAIL = 'nomsa.dlamini@example.com'

/** The password the seed gives every account when `SEED_PASSWORD` is unset.
 *  It exists in development only. The staff accounts fall back to it too. */
export const DEVELOPMENT_SEED_PASSWORD = 'toolshed-dev-password'

export const CUSTOMER_PASSWORD = process.env.E2E_CUSTOMER_PASSWORD ?? DEVELOPMENT_SEED_PASSWORD

/** Fill in the sign in form that is on the page and send it. */
export async function submitCustomerSignIn(page: Page, email: string = CUSTOMER_EMAIL): Promise<void> {
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(CUSTOMER_PASSWORD)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
}

/** Open the sign in screen and sign a seeded customer in. */
export async function signInAsCustomer(page: Page, email: string = CUSTOMER_EMAIL): Promise<void> {
  await page.goto(SIGN_IN.path)
  await expect(page.getByRole('heading', { level: 1, name: SIGN_IN.heading })).toBeVisible()
  await submitCustomerSignIn(page, email)
}
