/**
 * The catalogue journey, against the real backend.
 *
 * A visitor picks dates on the home screen, sees what is free, opens one
 * model, and reads its price, what the hire will cost and whether each branch
 * can supply it. That is SC-01, SC-02 and SC-03 end to end, through the real
 * API and a seeded database, under the same Content Security Policy a visitor
 * gets.
 *
 * These specs skip themselves when `/api/health` does not answer OK, so the
 * run still passes on a machine with no backend. They name no particular tool,
 * category or branch, because the seed can change. Where a spec needs to know
 * what the catalogue holds, it asks the API the same question the screen asks
 * and compares the two.
 */

import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { blockingViolations } from './axe.ts'
import { BACKEND_NEEDED, backendIsReachable } from './backend.ts'
import { asShown, quoteFromTheApi } from './quote.ts'
import { CATALOGUE_HOME, SEARCH } from './routes.ts'

/** The time zone the branches trade in. "Today" for a hire means today there. */
const BRANCH_TIME_ZONE = 'Africa/Johannesburg'

/** I book a week out, so the journey never trips over a hire that starts today. */
const COLLECT_IN_DAYS = 7
const HIRE_DAYS = 3

/** Longer than any hire the branches take online, so the API refuses it. */
const TOO_MANY_HIRE_DAYS = 40

/** CBD, BLV and SMW. Every one of them answers for every model. */
const BRANCH_COUNT = 3

/** What a branch says about a model. Free or not free, and never a count. */
const BRANCH_ANSWER = /: (Free|Not free)$/

/** How a stock count would read if one leaked onto a screen. The quantity the
 *  visitor asked for, "for 1 unit", is theirs and is not a stock count. */
const STOCK_COUNT = /\d+\s+(free|left|in stock|in the fleet)/i

/** Rand as the screens write it, for example "R 1 360,00". */
const RAND = /R\s[\d\s]+[,.]\d{2}/

const SEARCH_RESULTS = 'Search results'
const BRANCH_CARD_HEADING = 'At each branch for these dates'
const PRICE_PANEL = 'Price for these dates'
const REFUSED_SEARCH = 'We cannot search with those details'

/** What the specs read of a category, as `GET /api/catalogue/categories` sends it. */
interface CategoryOnTheWire {
  name: string
  parentCode: string | null
  modelCount: number
}

/** A date some days from today in branch time, as `YYYY-MM-DD`. */
function dateFromToday(days: number): string {
  const parts = new Map(
    new Intl.DateTimeFormat('en-ZA', {
      timeZone: BRANCH_TIME_ZONE,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    })
      .formatToParts(new Date())
      .map((part) => [part.type, part.value]),
  )
  const date = new Date(`${parts.get('year')}-${parts.get('month')}-${parts.get('day')}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

const COLLECT_ON = dateFromToday(COLLECT_IN_DAYS)
const RETURN_ON = dateFromToday(COLLECT_IN_DAYS + HIRE_DAYS)
const RETURN_TOO_LATE = dateFromToday(COLLECT_IN_DAYS + TOO_MANY_HIRE_DAYS)
const DATED_SEARCH = `${SEARCH.path}?from=${COLLECT_ON}&to=${RETURN_ON}`

/** A name as a pattern that matches it and nothing else. */
function literal(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** The first model in the search results, once the search has answered. */
async function firstResult(page: Page): Promise<{ row: Locator; name: string }> {
  const results = page.getByRole('region', { name: SEARCH_RESULTS })
  await expect(results.getByRole('status').first()).toHaveText(/\d+ models? match/)
  const row = results
    .getByRole('listitem')
    .filter({ has: page.getByRole('heading', { level: 3 }) })
    .first()
  const name = await row.getByRole('heading', { level: 3 }).innerText()
  return { row, name }
}

/** The value shown against one term in the price list on the detail screen. */
function priceOf(page: Page, term: string): Locator {
  return page.locator('dt', { hasText: term }).locator('xpath=following-sibling::dd[1]')
}

/** The figure shown against one term in the price panel of the booking card. */
function quotedFigure(page: Page, term: string): Locator {
  return page
    .getByRole('group', { name: PRICE_PANEL })
    .locator('dt', { hasText: term })
    .locator('xpath=following-sibling::dd[1]')
}

/** The slug of the model whose screen the page is on. */
function slugOnScreen(page: Page): string {
  return new URL(page.url()).pathname.split('/').pop() ?? ''
}

test.describe('the catalogue against the real backend', () => {
  test.beforeEach(async ({ request }) => {
    test.skip(!(await backendIsReachable(request)), BACKEND_NEEDED)
  })

  test('a visitor searches for dates, opens a model and sees its price and each branch', async ({
    page,
    request,
  }) => {
    // SC-01. Pick the dates and search.
    await page.goto(CATALOGUE_HOME.path)
    await expect(page.getByRole('heading', { level: 1, name: CATALOGUE_HOME.heading })).toBeVisible()
    await page.getByLabel('Collect on').fill(COLLECT_ON)
    await page.getByLabel('Bring back on').fill(RETURN_ON)
    await page.getByRole('button', { name: 'See what is free' }).click()

    // SC-02. The search is in the address and the results answer for it.
    await expect(page).toHaveURL(new RegExp(`/search\\?from=${COLLECT_ON}&to=${RETURN_ON}`))
    await expect(page.getByRole('heading', { level: 1, name: SEARCH.heading })).toBeVisible()
    const { row, name } = await firstResult(page)
    await expect(row).toContainText(RAND)
    const answers = row.getByRole('list', { name: `${name} at each branch` }).getByRole('listitem')
    await expect(answers).toHaveCount(BRANCH_COUNT)
    for (const answer of await answers.all()) await expect(answer).toHaveText(BRANCH_ANSWER)
    await expect(page.getByRole('region', { name: SEARCH_RESULTS })).not.toContainText(STOCK_COUNT)

    // SC-03. The model the visitor chose, its prices, and every branch.
    await row.getByRole('link', { name: /See dates and book/ }).click()
    await expect(page).toHaveURL(new RegExp(`/model/[^/?]+\\?from=${COLLECT_ON}&to=${RETURN_ON}`))
    await expect(page.getByRole('heading', { level: 1, name })).toBeVisible()
    await expect(priceOf(page, 'Hire rate')).toHaveText(RAND)
    await expect(priceOf(page, 'Hire rate')).toContainText('per day')
    await expect(priceOf(page, 'Weekly rate')).toHaveText(RAND)
    await expect(priceOf(page, 'Refundable deposit')).toHaveText(RAND)
    await expect(priceOf(page, 'Late fee')).toHaveText(RAND)

    const branchCard = page.locator('section', {
      has: page.getByRole('heading', { name: BRANCH_CARD_HEADING }),
    })
    const branches = branchCard.getByRole('listitem')
    await expect(branches).toHaveCount(BRANCH_COUNT)
    for (const branch of await branches.all()) await expect(branch).toHaveText(BRANCH_ANSWER)
    await expect(page.getByRole('main')).not.toContainText(STOCK_COUNT)
    await expect(page.getByText(/^(Free at|Not free at) /).first()).toBeVisible()

    // The cost of the hire is the server's quote. I ask the API the question
    // the screen asked and the two have to agree to the cent.
    const asked = { slug: slugOnScreen(page), from: COLLECT_ON, to: RETURN_ON }
    const forOne = await quoteFromTheApi(request, { ...asked, quantity: 1 })
    await expect(quotedFigure(page, 'Total with VAT')).toHaveText(asShown(forOne.totalIncVat))
    await expect(quotedFigure(page, 'Deposit')).toHaveText(asShown(forOne.depositTotal))

    // A second unit is priced by the server too, and the screen follows it.
    await page.getByRole('button', { name: `One more ${name}` }).click()
    const forTwo = await quoteFromTheApi(request, { ...asked, quantity: 2 })
    expect(forTwo.totalIncVat).not.toBe(forOne.totalIncVat)
    await expect(quotedFigure(page, 'Total with VAT')).toHaveText(asShown(forTwo.totalIncVat))
    await expect(quotedFigure(page, 'Deposit')).toHaveText(asShown(forTwo.depositTotal))
  })

  test('a reload brings the same search back', async ({ page }) => {
    await page.goto(`${DATED_SEARCH}&sort=dailyRateDesc`)
    const before = await firstResult(page)

    await page.reload()

    const after = await firstResult(page)
    expect(after.name).toBe(before.name)
    await expect(page.getByLabel('Collect on')).toHaveValue(COLLECT_ON)
    await expect(page.getByLabel('Bring back on')).toHaveValue(RETURN_ON)
    await expect(page.getByLabel('Sort by')).toHaveValue('dailyRateDesc')
  })

  test('a date the API refuses is explained under its field, and nothing crashes', async ({
    page,
  }) => {
    await page.goto(`${SEARCH.path}?from=not-a-date&to=${RETURN_ON}`)

    await expect(page.getByRole('heading', { level: 1, name: SEARCH.heading })).toBeVisible()
    await expect(page.getByLabel('Collect on')).toHaveAttribute('aria-invalid', 'true')
    await expect(page.getByLabel('Bring back on')).not.toHaveAttribute('aria-invalid', 'true')
    await expect(page.getByRole('alert')).toContainText(REFUSED_SEARCH)
  })

  test('a hire the API finds too long is explained under the return date', async ({ page }) => {
    await page.goto(`${SEARCH.path}?from=${COLLECT_ON}&to=${RETURN_TOO_LATE}`)

    await expect(page.getByLabel('Bring back on')).toHaveAttribute('aria-invalid', 'true')
    await expect(page.getByLabel('Collect on')).not.toHaveAttribute('aria-invalid', 'true')
    // The message found its field, so the notice has nothing left over to list.
    const notice = page.getByRole('alert')
    await expect(notice).toContainText(REFUSED_SEARCH)
    await expect(notice.getByRole('listitem')).toHaveCount(0)
  })

  test('the home screen offers each top level category once, with the count the API gives it', async ({
    page,
    request,
  }) => {
    const answer = await request.get('/api/catalogue/categories')
    const { items } = (await answer.json()) as { items: CategoryOnTheWire[] }
    const expected = items
      .filter((category) => category.parentCode === null && category.modelCount > 0)
      .map((category) => `${category.name} ${category.modelCount}`)

    await page.goto(CATALOGUE_HOME.path)
    const tiles = page.getByRole('region', { name: 'Browse by job' }).getByRole('link')
    await expect(tiles).toHaveCount(expected.length)
    const shown = (await tiles.allInnerTexts()).map((text) =>
      text.replace(/\s+/g, ' ').replace(/ models?$/, '').trim(),
    )
    expect(shown).toEqual(expected)
  })

  test('choosing a branch lists only what is free at that branch', async ({ page }) => {
    await page.goto(DATED_SEARCH)
    await firstResult(page)
    // Exact, because every row also carries a list labelled "... at each branch".
    const branch = page.getByLabel('Branch', { exact: true })
    // The first option is "Any branch". The one after it is a real branch.
    const branchName = (await branch.getByRole('option').nth(1).innerText()).trim()

    await branch.selectOption({ label: branchName })

    await expect(page).toHaveURL(/[?&]branch=[A-Z]+/)
    const results = page.getByRole('region', { name: SEARCH_RESULTS })
    await expect(results.getByRole('status').first()).toHaveText(
      new RegExp(`^\\d+ models? (is|are) free at ${literal(branchName)} for ${HIRE_DAYS} days\\.`),
    )
    const rows = results.getByRole('listitem').filter({ has: page.getByRole('heading', { level: 3 }) })
    const answers = results.getByText(new RegExp(`^${literal(branchName)}: `))
    await expect(answers).toHaveCount(await rows.count())
    for (const answer of await answers.all()) await expect(answer).toHaveText(`${branchName}: Free`)
  })

  test('the loaded home screen has no serious or critical accessibility violations', async ({
    page,
  }) => {
    await page.goto(CATALOGUE_HOME.path)
    await expect(page.getByRole('link', { name: /See dates and book/ }).first()).toBeVisible()
    await expect(page.getByRole('region', { name: 'Browse by job' }).getByRole('link').first()).toBeVisible()

    expect(await blockingViolations(page)).toEqual([])
  })

  test('the loaded search results have no serious or critical accessibility violations', async ({
    page,
  }) => {
    await page.goto(DATED_SEARCH)
    await firstResult(page)

    expect(await blockingViolations(page)).toEqual([])
  })

  test('the loaded model screen has no serious or critical accessibility violations', async ({
    page,
  }) => {
    await page.goto(DATED_SEARCH)
    const { row, name } = await firstResult(page)
    await row.getByRole('link', { name: /See dates and book/ }).click()
    await expect(page.getByRole('heading', { level: 1, name })).toBeVisible()
    await expect(page.getByText(/^(Free at|Not free at) /).first()).toBeVisible()
    await expect(quotedFigure(page, 'Total with VAT')).toBeVisible()

    expect(await blockingViolations(page)).toEqual([])
  })
})
