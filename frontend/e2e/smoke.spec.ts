/**
 * Smoke tests for the public entry points.
 *
 * These prove the built application starts, draws the catalogue, and lets a
 * visitor who has not signed in reach the two places they go next. Every step
 * uses a control a visitor can see, so the same test covers the header
 * navigation on a desktop and the tab bar on a phone.
 */

import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { CATALOGUE_HOME, SEARCH, SIGN_IN } from './routes.ts'
import type { PublicRoute } from './routes.ts'

async function expectScreen(page: Page, route: PublicRoute): Promise<void> {
  await expect(page.getByRole('heading', { level: 1, name: route.heading })).toBeVisible()
}

test.describe('catalogue home', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(CATALOGUE_HOME.path)
  })

  test('loads and shows its main heading', async ({ page }) => {
    await expectScreen(page, CATALOGUE_HOME)
    await expect(page).toHaveTitle('Catalogue Home | Toolshed Hire')
  })

  test('takes a visitor to search through the primary navigation', async ({ page }) => {
    await page
      .getByRole('navigation', { name: 'Primary' })
      .getByRole('link', { name: 'Search' })
      .click()

    await expect(page).toHaveURL(/\/search/)
    await expectScreen(page, SEARCH)
  })

  test('takes a visitor to search with the dates they picked', async ({ page }) => {
    await expectScreen(page, CATALOGUE_HOME)
    await page.getByRole('button', { name: 'See what is free' }).click()

    await expect(page).toHaveURL(/\/search\?.*from=\d{4}-\d{2}-\d{2}.*to=\d{4}-\d{2}-\d{2}/)
    await expectScreen(page, SEARCH)
  })

  test('takes a visitor to sign in', async ({ page }) => {
    await page.getByRole('link', { name: 'Sign in', exact: true }).click()

    await expect(page).toHaveURL(/\/signin$/)
    await expectScreen(page, SIGN_IN)
  })
})

test('a visitor can open the search screen from its own address', async ({ page }) => {
  await page.goto(SEARCH.path)

  await expectScreen(page, SEARCH)
})
