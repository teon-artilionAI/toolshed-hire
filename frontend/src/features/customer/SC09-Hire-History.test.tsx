/**
 * Tests for the hire history on SC-09, with the network replaced at `fetch`.
 *
 * The history is the customer's own hires, one page at a time, read once the
 * profile has loaded. Loading, failed, empty and loaded, then the pages. A hire
 * shows what was hired without any tag, every charge, and where the deposit
 * stands, all as the server sent them, and a deposit given back never shows a
 * bare minus sign.
 */

import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PROFILE } from '../../test/account-samples'
import { jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import { SCREEN_WAIT } from '../../test/render-app'
import {
  CUSTOMER_HIRE,
  CUSTOMER_LATE_FEE_DESCRIPTION,
  MY_RENTALS_ROUTE,
  RELEASE_CHARGE,
  rentalPage,
} from '../../test/rental-samples'
import { ACCESS_TOKEN, bearerOf } from '../../test/session-samples'
import { HISTORY_PAGE_SIZE, NO_HIRES_TITLE } from './SC09-Hire-History'
import { openAccount, withProfile } from './SC09-test-kit'

/** The history, once its line above the list has said it loaded. */
async function findHistory(): Promise<HTMLElement> {
  return screen.findByRole('region', { name: 'Your hires' }, SCREEN_WAIT)
}

/** The value against one term of the deposit of a hire. */
function deposit(hire: HTMLElement, term: string): string {
  const value = within(hire).getByText(term, { selector: 'dt' }).nextElementSibling
  return value?.textContent ?? ''
}

describe('while the hires load', () => {
  it('says so, and shows no hire', async () => {
    await openAccount(withProfile(PROFILE, { [MY_RENTALS_ROUTE]: neverAnswers }))

    const history = await findHistory()
    expect(within(history).getByText('Loading your hires.')).toBeVisible()
    expect(history.querySelector('[aria-busy="true"]')).not.toBeNull()
  })
})

describe('when the hires cannot be read', () => {
  it('says so with the reference, and reads them again on a retry', async () => {
    const { user, network } = await openAccount(
      withProfile(PROFILE, { [MY_RENTALS_ROUTE]: () => problemResponse(500, { requestId: 'req-hires-2' }) }),
    )

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('We could not load your hire history')
    expect(within(alert).getByText('req-hires-2')).toBeVisible()

    network.setRoute(MY_RENTALS_ROUTE, () => jsonResponse(rentalPage([CUSTOMER_HIRE], { pageSize: HISTORY_PAGE_SIZE })))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('article', { name: CUSTOMER_HIRE.reference })).toBeVisible()
  })
})

describe('a customer with no hires yet', () => {
  it('is told so, and pointed at their bookings', async () => {
    await openAccount(withProfile(PROFILE))

    const history = await findHistory()
    expect(await within(history).findByText(NO_HIRES_TITLE)).toBeVisible()
    expect(within(history).getByText('You have no hires yet.')).toBeVisible()
    expect(within(history).getByRole('link', { name: 'See my bookings' })).toHaveAttribute('href', '/reservations')
  })
})

describe('the hires', () => {
  it('are asked for a page at a time with the token of the session', async () => {
    const { network } = await openAccount(
      withProfile(PROFILE, { [MY_RENTALS_ROUTE]: () => jsonResponse(rentalPage([CUSTOMER_HIRE], { pageSize: HISTORY_PAGE_SIZE })) }),
    )
    await screen.findByRole('article', { name: CUSTOMER_HIRE.reference }, SCREEN_WAIT)

    const asked = network.requestsTo(MY_RENTALS_ROUTE)[0]
    expect(asked.query.get('page')).toBe('1')
    expect(asked.query.get('pageSize')).toBe(String(HISTORY_PAGE_SIZE))
    expect(bearerOf(asked)).toBe(ACCESS_TOKEN)
  })

  it('show each hire with its branch, dates, status in words, models, charges and deposit, and no tag', async () => {
    await openAccount(
      withProfile(PROFILE, { [MY_RENTALS_ROUTE]: () => jsonResponse(rentalPage([CUSTOMER_HIRE], { pageSize: HISTORY_PAGE_SIZE })) }),
    )

    const hire = await screen.findByRole('article', { name: CUSTOMER_HIRE.reference }, SCREEN_WAIT)
    expect(within(hire).getByText('From Bellville')).toBeVisible()
    expect(within(hire).getByText(/^Collected 12 Mar 2026, due back 13 Mar 2026\. Returned 12 Mar 2026 at 10:15\.$/)).toBeVisible()
    expect(within(hire).getByText('Returned and settled')).toBeVisible()
    expect(within(hire).getByText('2 x CP 100 Plate Compactor')).toBeVisible()
    expect(within(hire).getByText(new RegExp(`^Late return\\. ${CUSTOMER_LATE_FEE_DESCRIPTION}`))).toBeVisible()
    expect(within(hire).getByText(/^R 4 999[,.]99 returned to you$/)).toBeVisible()
    expect(RELEASE_CHARGE.amountIncVat.startsWith('-')).toBe(true)
    expect(hire.textContent).not.toMatch(/-\s?R\s\d|R\s-\d/)
    expect(deposit(hire, 'Held')).toMatch(/^R 5 555[,.]55$/)
    expect(deposit(hire, 'Kept for charges')).toMatch(/^R 444[,.]44$/)
    expect(deposit(hire, 'Returned to you')).toMatch(/^R 4 999[,.]99$/)
    expect(deposit(hire, 'Balance due')).toMatch(/^R 0[,.]00$/)
  })

  it('never show an asset tag or a serial number', async () => {
    await openAccount(
      withProfile(PROFILE, { [MY_RENTALS_ROUTE]: () => jsonResponse(rentalPage([CUSTOMER_HIRE], { pageSize: HISTORY_PAGE_SIZE })) }),
    )

    const history = await findHistory()
    await within(history).findByRole('article', { name: CUSTOMER_HIRE.reference })
    for (const item of CUSTOMER_HIRE.items) expect(item.assetTag).toBeNull()
    expect(history.textContent).not.toMatch(/TSH-PC-|TSH-DR-/)
    expect(within(history).getByText('2 x CP 100 Plate Compactor')).toBeVisible()
  })

  it('move between the pages the server counts, and keep the page in the address', async () => {
    const { user, network } = await openAccount(
      withProfile(PROFILE, {
        [MY_RENTALS_ROUTE]: () => jsonResponse(rentalPage([CUSTOMER_HIRE], { pageSize: HISTORY_PAGE_SIZE, total: 7 })),
      }),
    )
    await screen.findByRole('article', { name: CUSTOMER_HIRE.reference }, SCREEN_WAIT)
    expect(screen.getByText('7 hires on your account, newest first.')).toBeVisible()

    await user.click(screen.getByRole('button', { name: 'Page 2' }))

    await waitFor(() => expect(network.requestsTo(MY_RENTALS_ROUTE).at(-1)?.query.get('page')).toBe('2'))
  })
})
