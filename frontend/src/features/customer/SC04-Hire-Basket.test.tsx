/**
 * Tests for the basket itself on SC-04, before anything is asked of the
 * reservation routes, with the network replaced at `fetch`.
 *
 * What the basket shows, how it changes, the count in the header, and who is
 * offered what. A visitor is sent to sign in and brought back. Staff are told
 * to book at the counter. The steps of a booking have their own file,
 * SC04-Booking-Review.test.tsx.
 */

import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { addToBasket, basketSnapshot } from '../../shared/basket-store'
import { jsonResponse, mockApi, problemResponse } from '../../test/api-mock'
import { TEST_DEFAULT_RETURN, TEST_NOW, TEST_TODAY, TRENCH_RAMMER } from '../../test/catalogue-samples'
import { currentAddress, findScreenHeading, renderApp } from '../../test/render-app'
import {
  BASKET_READS,
  COMPACTOR_SLUG,
  CREATE_ROUTE,
  IN_THE_BASKET,
  MODEL_ROUTE,
} from '../../test/reservation-samples'
import {
  COUNTER_STAFF,
  CUSTOMER,
  LOGIN_ROUTE,
  SIGNED_OUT,
  grantFor,
  signedInAs,
} from '../../test/session-samples'
import { BASKET_HEADING, BASKET_STEP, REVIEW, openBasket, stepHeading } from './SC04-test-kit'

const RAMMER_ROUTE = `GET /api/catalogue/models/${TRENCH_RAMMER.slug}`
const RAMMER_DETAIL = { ...TRENCH_RAMMER, longDescription: null, lateFeePerDay: '250.00' }
const COMPACTOR = 'CP 100 Plate Compactor'

/** The count beside the basket in the header, read the way it is announced. */
function basketLink(units: number): HTMLElement {
  return screen.getByRole('link', { name: `Basket, ${units} ${units === 1 ? 'item' : 'items'}` })
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('an empty basket', () => {
  it('says so and points to the catalogue', async () => {
    mockApi(signedInAs(CUSTOMER))
    renderApp('/basket')
    await findScreenHeading(BASKET_HEADING)

    expect(screen.getByText('Your basket is empty')).toBeVisible()
    expect(screen.getByRole('link', { name: 'Browse the catalogue' })).toHaveAttribute('href', '/')
    expect(screen.queryByRole('button', { name: REVIEW })).not.toBeInTheDocument()
    expect(basketLink(0)).toBeVisible()
  })
})

describe('a basket with something in it', () => {
  it('shows the dates, the branch and each tool by the name the catalogue gives it', async () => {
    await openBasket(BASKET_READS)

    expect(await screen.findByRole('link', { name: COMPACTOR })).toHaveAttribute(
      'href',
      `/model/${COMPACTOR_SLUG}?from=${TEST_TODAY}&to=${TEST_DEFAULT_RETURN}&branch=CBD`,
    )
    expect(screen.getByText(/^R 340[,.]00 per day, R 1.500[,.]00 deposit each$/)).toBeVisible()
    expect(screen.getByLabelText('Collect on')).toHaveValue(TEST_TODAY)
    expect(screen.getByLabelText('Bring back on')).toHaveValue(TEST_DEFAULT_RETURN)
    await waitFor(() =>
      expect(screen.getByLabelText('Collect from')).toHaveDisplayValue('Cape Town CBD'),
    )
    expect(screen.getByLabelText('How many')).toHaveValue(2)
  })

  it('shows no price of its own, because the server has not priced anything yet', async () => {
    await openBasket(BASKET_READS)
    await screen.findByRole('link', { name: COMPACTOR })

    expect(screen.queryByText(/Total with VAT/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Hire before VAT/)).not.toBeInTheDocument()
  })

  it('counts every unit in the header, and follows a change of quantity', async () => {
    const user = userEvent.setup()
    await openBasket(BASKET_READS)
    await screen.findByRole('link', { name: COMPACTOR })
    expect(basketLink(2)).toBeVisible()

    await user.click(screen.getByRole('button', { name: `One more ${COMPACTOR}` }))

    expect(basketLink(3)).toBeVisible()
    expect(basketSnapshot().lines).toEqual([{ modelSlug: COMPACTOR_SLUG, quantity: 3 }])
  })

  it('takes a tool out, and is empty when the last one goes', async () => {
    const user = userEvent.setup()
    addToBasket({ ...IN_THE_BASKET, modelSlug: TRENCH_RAMMER.slug, quantity: 1 })
    await openBasket({ ...BASKET_READS, [RAMMER_ROUTE]: () => jsonResponse(RAMMER_DETAIL) })
    await screen.findByRole('link', { name: TRENCH_RAMMER.name })

    await user.click(
      screen.getByRole('button', { name: `Remove ${TRENCH_RAMMER.name} from the basket` }),
    )
    expect(screen.queryByRole('link', { name: TRENCH_RAMMER.name })).not.toBeInTheDocument()
    expect(basketLink(2)).toBeVisible()

    await user.click(screen.getByRole('button', { name: `Remove ${COMPACTOR} from the basket` }))
    expect(screen.getByText('Your basket is empty')).toBeVisible()
    expect(basketLink(0)).toBeVisible()
  })

  it('moves the whole basket when the dates or the branch are changed', async () => {
    const user = userEvent.setup()
    await openBasket(BASKET_READS)
    await waitFor(() =>
      expect(screen.getByLabelText('Collect from')).toHaveDisplayValue('Cape Town CBD'),
    )

    fireEvent.change(screen.getByLabelText('Bring back on'), { target: { value: '2026-03-20' } })
    await user.selectOptions(screen.getByLabelText('Collect from'), 'Bellville')

    expect(basketSnapshot()).toMatchObject({ from: TEST_TODAY, to: '2026-03-20', branchCode: 'BLV' })
  })

  it('holds the booking back while a date is missing, and says which', async () => {
    await openBasket(BASKET_READS)

    fireEvent.change(screen.getByLabelText('Bring back on'), { target: { value: '' } })

    expect(screen.getByText('Choose a return date.')).toBeVisible()
    expect(screen.getByLabelText('Bring back on')).toBeInvalid()
    expect(screen.getByRole('button', { name: REVIEW })).toBeDisabled()
  })

  it('says so on the line when the catalogue no longer has the tool', async () => {
    await openBasket({ ...BASKET_READS, [MODEL_ROUTE]: () => problemResponse(404) })

    expect(await screen.findByRole('alert')).toHaveTextContent('We no longer hire this tool.')
    expect(screen.getByText(COMPACTOR_SLUG)).toBeVisible()
    expect(screen.getByRole('button', { name: 'Remove this tool from the basket' })).toBeEnabled()
  })
})

describe('who is offered what', () => {
  it('asks a visitor to sign in, with the way back to the basket, and asks the API nothing', async () => {
    const network = await openBasket(BASKET_READS, null)

    expect(screen.getByRole('link', { name: 'Sign in to review and book' })).toHaveAttribute(
      'href',
      '/signin?next=%2Fbasket',
    )
    expect(screen.queryByRole('button', { name: REVIEW })).not.toBeInTheDocument()
    expect(network.requestsTo(CREATE_ROUTE)).toHaveLength(0)
  })

  it('brings a visitor back to the same basket once they have signed in', async () => {
    const user = userEvent.setup()
    addToBasket(IN_THE_BASKET)
    mockApi({
      ...signedInAs(CUSTOMER),
      ...SIGNED_OUT,
      ...BASKET_READS,
      [LOGIN_ROUTE]: () => jsonResponse(grantFor(CUSTOMER)),
    })
    renderApp('/basket')
    await findScreenHeading(BASKET_HEADING)

    await user.click(screen.getByRole('link', { name: 'Sign in to review and book' }))
    await findScreenHeading('Sign in to Toolshed Hire')
    await user.type(screen.getByLabelText('Email address'), CUSTOMER.email)
    await user.type(screen.getByLabelText('Password'), 'a-password-typed-by-a-person')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await findScreenHeading(BASKET_HEADING)
    expect(currentAddress()).toBe('/basket')
    expect(await screen.findByRole('link', { name: COMPACTOR })).toBeVisible()
    expect(screen.getByRole('button', { name: REVIEW })).toBeEnabled()
    expect(basketSnapshot().lines).toEqual([{ modelSlug: COMPACTOR_SLUG, quantity: 2 }])
  })

  it('offers a customer the review', async () => {
    await openBasket(BASKET_READS)

    expect(screen.getByRole('button', { name: REVIEW })).toBeEnabled()
    expect(await stepHeading(BASKET_STEP)).toBeVisible()
  })

  it('tells staff to book at the counter, and offers no way to book here', async () => {
    const network = await openBasket(BASKET_READS, COUNTER_STAFF)

    const notice = screen
      .getByText('Booking online is for customer accounts')
      .closest('[role="status"]')
    expect(notice).toHaveTextContent('Book for a customer from the counter')
    expect(screen.queryByRole('button', { name: REVIEW })).not.toBeInTheDocument()
    expect(
      within(screen.getByRole('main')).queryByRole('link', { name: /Sign in/ }),
    ).not.toBeInTheDocument()
    expect(network.requestsTo(CREATE_ROUTE)).toHaveLength(0)
  })
})

describe('signing out', () => {
  it('empties the basket, so the next person at this browser does not inherit it', async () => {
    const user = userEvent.setup()
    await openBasket(BASKET_READS)
    await screen.findByRole('link', { name: COMPACTOR })

    await user.click(screen.getByRole('button', { name: /Sign out/ }))

    await findScreenHeading('Hire tools and plant across Cape Town')
    await waitFor(() => expect(basketSnapshot().lines).toEqual([]))
    expect(window.sessionStorage).toHaveLength(0)
  })
})
