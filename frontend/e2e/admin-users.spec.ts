/**
 * The owner's staff accounts and customer holds, against the real backend.
 *
 * The seeded owner signs in and opens user management. They open a counter
 * staff account with an address no run has used at a branch, which first says
 * the person chooses their own password from a link, and find it in the list.
 * What the screen says once the account is open depends on whether the answer
 * said the link can reach the address, so the spec reads that flag and expects
 * the matching words. The address is at `example.com`, which a demonstration
 * never delivers to.
 * Then they deactivate it with a reason, which first says the person is signed
 * out everywhere at once, reactivate it, and open the customer holds. That is
 * SC-23 end to end, under the same Content Security Policy a visitor gets.
 *
 * Each browser project opens its own account at a different branch, so the
 * two never change the same account. The account is left on file and active,
 * because nothing is ever deleted. Nobody ever signs in with it, and it has
 * no password until somebody uses its link.
 *
 * It needs the user management routes, which a healthy backend may not have
 * yet, so `e2e/admin-users-backend.ts` asks for them by name. When they are
 * not there the spec skips itself and the run still passes.
 */

import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { USER_ROUTES_NEEDED, userRoutesArePresent } from './admin-users-backend.ts'
import { blockingViolations } from './axe.ts'
import { signInAsOwner } from './staff.ts'

const USERS_HEADING = 'Users, roles and account holds'

/** Where the screen opens a staff account. */
const USERS_PATH = '/api/admin/users'

/** The branch each browser project opens its account at, by its code. */
const BRANCH_FOR_PROJECT: Record<string, string> = {
  'chromium-desktop': 'CBD',
  'chromium-mobile': 'BLV',
}

const DEACTIVATION_REASON = 'Browser test, the contract has ended.'

/** A name and an address nobody has used, for this run and this browser project. */
function freshPerson(projectName: string): { fullName: string; email: string } {
  const project = projectName.endsWith('mobile') ? 'mobile' : 'desktop'
  const stamp = Date.now().toString(36)
  return { fullName: `Browser Test ${project} ${stamp}`, email: `e2e.staff.${project}.${stamp}@example.com` }
}

function accountSection(page: Page, fullName: string): Locator {
  return page.getByRole('region', { name: `Account of ${fullName}` })
}

/** SC-23. A counter staff account of the run's own, opened at a branch. */
async function openAnAccount(page: Page, person: { fullName: string; email: string }, branchCode: string): Promise<void> {
  await page.getByRole('button', { name: 'Add a staff account' }).click()
  const form = page.getByRole('form', { name: 'The new staff account' })
  await form.getByLabel('Full name').fill(person.fullName)
  await form.getByLabel('Work email').fill(person.email)
  await expect(form.getByLabel('Role')).toHaveValue('COUNTER_STAFF')
  await form.getByLabel('Branch they work at').selectOption(branchCode)
  await expect(form.getByLabel(/password/i)).toHaveCount(0)
  await form.getByRole('button', { name: 'Create the account' }).click()

  // The question promises no more than that a link is sent, because only the
  // answer says whether it can reach the person.
  await expect(page.getByRole('heading', { level: 4, name: `Create an account for ${person.fullName}?` })).toBeFocused()
  await expect(page.getByText(/A link to choose their own password is sent to/)).toContainText(
    `${person.email}. This demonstration delivers email to one address only, so the answer says whether the link can reach them.`,
  )
  expect(await blockingViolations(page)).toEqual([])
  const created = page.waitForResponse(
    (response) => response.request().method() === 'POST' && new URL(response.url()).pathname === USERS_PATH,
  )
  await page.getByRole('button', { name: 'Yes, create it' }).click()
  const answer = await created
  expect(answer.status()).toBe(201)
  const { emailDeliverable } = (await answer.json()) as { emailDeliverable?: unknown }
  expect(typeof emailDeliverable, `${USERS_PATH} answered without an emailDeliverable flag`).toBe('boolean')

  // The outcome promises the link only when the answer said it can arrive,
  // which it cannot where the API runs without an email provider.
  const title = `${person.fullName} has a staff account`
  if (emailDeliverable === true) {
    await expect(page.getByText(title, { exact: true })).toBeVisible()
    await expect(page.getByText(`a link sent to ${person.email}`)).toBeVisible()
  } else {
    await expect(page.getByText(`${title}, but the link could not be sent`, { exact: true })).toBeVisible()
    await expect(
      page.getByText(`This demonstration delivers email to one address only, and ${person.email} is not it`),
    ).toBeVisible()
    await expect(page.getByText(`a link sent to ${person.email}`)).toHaveCount(0)
  }
}

test.describe('the owner manages staff accounts against the real backend', () => {
  test.beforeEach(async ({ request }) => {
    test.skip(!(await userRoutesArePresent(request)), USER_ROUTES_NEEDED)
  })

  test('the owner opens a counter staff account, deactivates it, reactivates it and opens the customer holds', async ({
    page,
  }, testInfo) => {
    await signInAsOwner(page)
    await page.goto('/admin/users')
    await expect(page.getByRole('heading', { level: 1, name: USERS_HEADING })).toBeVisible()
    await expect(page.getByText('This screen still shows sample data')).toHaveCount(0)
    await expect(page.getByRole('region', { name: 'The staff accounts' }).getByRole('status').first()).toHaveText(
      /^\d+ accounts? match(es)?\.$/,
    )
    expect(await blockingViolations(page)).toEqual([])

    const person = freshPerson(testInfo.project.name)
    await openAnAccount(page, person, BRANCH_FOR_PROJECT[testInfo.project.name] ?? BRANCH_FOR_PROJECT['chromium-desktop'])

    await page.getByLabel('Search by name or email').fill(person.email)
    await expect(page).toHaveURL(/\/admin\/users\?q=/)
    const row = page
      .getByRole('region', { name: 'The staff accounts' })
      .getByRole('row')
      .filter({ has: page.getByRole('rowheader', { name: new RegExp(person.fullName) }) })
    await expect(row.getByText('Counter staff', { exact: true })).toBeVisible()
    await expect(row.getByText('Can sign in', { exact: true })).toBeVisible()
    await expect(row.getByText('Never signed in', { exact: true })).toBeVisible()

    await row.getByRole('button', { name: `Open the account of ${person.fullName}` }).click()
    const account = accountSection(page, person.fullName)
    await account.getByRole('button', { name: 'Deactivate the account' }).click()
    await expect(page.getByText(/is signed out everywhere at once, on every device/)).toBeVisible()
    await account.getByLabel('Why').fill(DEACTIVATION_REASON)
    expect(await blockingViolations(page)).toEqual([])
    await account.getByRole('button', { name: 'Yes, deactivate it' }).click()
    await expect(page.getByText(`${person.fullName} can no longer sign in`, { exact: true })).toBeVisible()
    await expect(row.getByText('Deactivated', { exact: true })).toBeVisible()

    await account.getByRole('button', { name: 'Reactivate the account' }).click()
    await account.getByRole('button', { name: 'Yes, reactivate it' }).click()
    await expect(page.getByText(`${person.fullName} can sign in again`, { exact: true })).toBeVisible()
    await expect(row.getByText('Can sign in', { exact: true })).toBeVisible()

    await page.getByRole('link', { name: 'Customer holds' }).click()
    await expect(page.getByRole('heading', { level: 2, name: 'Customer holds' })).toBeFocused()
    await expect(page).toHaveURL(/\/admin\/users\?view=customers&status=ON_HOLD$/)
    await expect(page.getByRole('region', { name: 'The customers' }).getByRole('status').first()).toHaveText(
      /^\d+ customers?, account on hold\.$/,
    )
    expect(await blockingViolations(page)).toEqual([])
  })
})
