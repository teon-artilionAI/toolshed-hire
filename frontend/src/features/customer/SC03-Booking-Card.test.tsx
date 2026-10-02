/**
 * Tests for the price on the booking card of SC-03, with the network replaced
 * at `fetch`.
 *
 * The price is the server's quote. Each test sets what the quote route sends
 * and reads the card the way a customer would. The figures in a sample do not
 * have to add up, and in one test they are made not to on purpose, because the
 * card is meant to show what it was sent and do no sum of its own.
 */

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, mockApi, neverAnswers, problemResponse } from '../../test/api-mock'
import type { ModelQuote } from '../../shared/api/contract'
import {
  DAILY_QUOTE,
  TEST_DEFAULT_RETURN,
  TEST_NOW,
  TEST_TEN_DAY_RETURN,
  TEST_TODAY,
  WEEKLY_QUOTE,
} from '../../test/catalogue-samples'
import { AVAILABILITY_ROUTE, QUOTE_ROUTE, SLUG, WORKING, lastQuestion, openModel } from './SC03-test-kit'

const PRICE_PANEL = 'Price for these dates'
const WORKING_OUT = 'Working out the price'
const ONE_MORE = 'One more CP 100 Plate Compactor'

/** The price panel, once the quote has arrived. */
function pricePanel(): Promise<HTMLElement> {
  return screen.findByRole('group', { name: PRICE_PANEL })
}

/** The figure shown against one term in the price panel. */
function figure(panel: HTMLElement, term: string | RegExp): HTMLElement {
  const value = within(panel).getByText(term).nextElementSibling
  if (!(value instanceof HTMLElement)) throw new Error(`No figure is shown for "${term}".`)
  return value
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('a quote charged by the day', () => {
  it('asks the API to price the dates in the address and one unit', async () => {
    const network = mockApi(WORKING)
    openModel()

    await pricePanel()
    const asked = lastQuestion(network, QUOTE_ROUTE)
    expect(asked.get('from')).toBe(TEST_TODAY)
    expect(asked.get('to')).toBe(TEST_DEFAULT_RETURN)
    expect(asked.get('quantity')).toBe('1')
  })

  it('says how the price is made up, then the subtotal, the VAT and the total', async () => {
    mockApi(WORKING)
    openModel()

    const panel = await pricePanel()
    expect(within(panel).getByText('4 days at the daily rate')).toBeVisible()
    expect(within(panel).getByText(/^R 340[,.]00 a day\.$/)).toBeVisible()
    expect(figure(panel, 'Hire before VAT')).toHaveTextContent(/^R 1.360[,.]00$/)
    expect(figure(panel, 'VAT at 15%')).toHaveTextContent(/^R 204[,.]00$/)
    expect(figure(panel, 'Total with VAT')).toHaveTextContent(/^R 1.564[,.]00$/)
    expect(within(panel).queryByText(/Discount/)).not.toBeInTheDocument()
  })

  it('shows the deposit apart from the total, and says it comes back', async () => {
    mockApi(WORKING)
    openModel()

    const panel = await pricePanel()
    expect(figure(panel, 'Deposit')).toHaveTextContent(/^R 1.500[,.]00$/)
    expect(
      within(panel).getByText(
        'The deposit is held when you collect the equipment and returned to you after you bring it back.',
      ),
    ).toBeVisible()
    expect(
      within(panel).getByText(/^Late fee of R 220[,.]00 per day past the return date\.$/),
    ).toBeVisible()
  })
})

describe('a quote charged by the week', () => {
  it('counts the weeks and the days left over, and prices each unit', async () => {
    const user = userEvent.setup()
    const network = mockApi({
      ...WORKING,
      [QUOTE_ROUTE]: (request) =>
        jsonResponse(request.query.get('quantity') === '2' ? WEEKLY_QUOTE : DAILY_QUOTE),
    })
    openModel(`/model/${SLUG}?from=${TEST_TODAY}&to=${TEST_TEN_DAY_RETURN}`)

    await pricePanel()
    await user.click(screen.getByRole('button', { name: ONE_MORE }))

    expect(await screen.findByText('2 units, each for 1 week and 3 days')).toBeVisible()
    const panel = await pricePanel()
    expect(
      within(panel).getByText(
        /^R 1.360[,.]00 a week and R 340[,.]00 a day, which is R 2.380[,.]00 for each unit before VAT\.$/,
      ),
    ).toBeVisible()
    expect(figure(panel, 'Hire before VAT')).toHaveTextContent(/^R 4.760[,.]00$/)
    expect(figure(panel, 'VAT at 15%')).toHaveTextContent(/^R 714[,.]00$/)
    expect(figure(panel, 'Total with VAT')).toHaveTextContent(/^R 5.474[,.]00$/)
    expect(figure(panel, 'Deposit')).toHaveTextContent(/^R 3.000[,.]00$/)
    const asked = lastQuestion(network, QUOTE_ROUTE)
    expect(asked.get('to')).toBe(TEST_TEN_DAY_RETURN)
    expect(asked.get('quantity')).toBe('2')
  })

  it('says whole weeks plainly when no days are left over', async () => {
    const twoWeeks: ModelQuote = {
      ...WEEKLY_QUOTE,
      hireDays: 14,
      quantity: 1,
      perUnit: { ...WEEKLY_QUOTE.perUnit, wholeWeeks: 2, remainderDays: 0, amountExVat: '2720.00' },
    }
    mockApi({ ...WORKING, [QUOTE_ROUTE]: () => jsonResponse(twoWeeks) })
    openModel()

    const panel = await pricePanel()
    expect(within(panel).getByText('2 weeks at the weekly rate')).toBeVisible()
    expect(within(panel).getByText(/^R 1.360[,.]00 a week\.$/)).toBeVisible()
  })
})

describe('where the figures come from', () => {
  it('shows what the server sent and does no sum of its own', async () => {
    // None of these follow from the rates or from each other. A card that
    // worked anything out for itself could not arrive at them.
    const sent: ModelQuote = {
      ...DAILY_QUOTE,
      subtotalExVat: '1111.11',
      discountPercent: '12.50',
      discountAmount: '22.22',
      vatAmount: '333.33',
      totalIncVat: '4444.44',
      depositTotal: '5555.55',
      lateFeePerDay: '66.66',
    }
    mockApi({ ...WORKING, [QUOTE_ROUTE]: () => jsonResponse(sent) })
    openModel()

    const panel = await pricePanel()
    expect(figure(panel, 'Hire before VAT')).toHaveTextContent(/^R 1.111[,.]11$/)
    expect(figure(panel, /^Discount of 12[,.]5%$/)).toHaveTextContent(/^-R 22[,.]22$/)
    expect(figure(panel, 'VAT at 15%')).toHaveTextContent(/^R 333[,.]33$/)
    expect(figure(panel, 'Total with VAT')).toHaveTextContent(/^R 4.444[,.]44$/)
    expect(figure(panel, 'Deposit')).toHaveTextContent(/^R 5.555[,.]55$/)
    expect(within(panel).getByText(/^Late fee of R 66[,.]66 per day/)).toBeVisible()
  })

  it('takes the old price down while the new one is on its way', async () => {
    const user = userEvent.setup()
    const network = mockApi({
      ...WORKING,
      [QUOTE_ROUTE]: (request) =>
        request.query.get('quantity') === '2' ? neverAnswers() : jsonResponse(DAILY_QUOTE),
    })
    openModel()

    await pricePanel()
    await user.click(screen.getByRole('button', { name: ONE_MORE }))

    expect(await screen.findByText(WORKING_OUT)).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: PRICE_PANEL })).not.toBeInTheDocument()
    expect(screen.queryByText('Total with VAT')).not.toBeInTheDocument()
    expect(lastQuestion(network, QUOTE_ROUTE).get('quantity')).toBe('2')
  })
})

describe('while the quote is loading', () => {
  it('announces that the price is being worked out and shows no figure', async () => {
    mockApi({ ...WORKING, [QUOTE_ROUTE]: neverAnswers })
    openModel()

    const waiting = await screen.findByText(WORKING_OUT)
    expect(waiting).toHaveAttribute('role', 'status')
    expect(screen.queryByText('Total with VAT')).not.toBeInTheDocument()
    // The rest of the card does not wait for the price.
    expect(await screen.findByText('Free at Cape Town CBD')).toBeVisible()
  })
})

describe('when the quote fails to load', () => {
  it('says so with the reference, shows no figure, and prices it on a retry', async () => {
    const user = userEvent.setup()
    const network = mockApi({
      ...WORKING,
      [QUOTE_ROUTE]: () => problemResponse(500, { requestId: 'req-quote-7' }),
    })
    openModel()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not load the price for these dates')
    expect(within(alert).getByText('req-quote-7')).toBeVisible()
    expect(alert).not.toHaveTextContent('500')
    expect(screen.queryByText('Total with VAT')).not.toBeInTheDocument()

    network.setRoute(QUOTE_ROUTE, () => jsonResponse(DAILY_QUOTE))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(figure(await pricePanel(), 'Total with VAT')).toHaveTextContent(/^R 1.564[,.]00$/)
  })
})

describe('when the quote arrives in the wrong shape', () => {
  it.each([
    ['a total that is a number', { ...DAILY_QUOTE, totalIncVat: 1564 }],
    ['a total with one decimal', { ...DAILY_QUOTE, totalIncVat: '1564.0' }],
    ['a basis it has not heard of', { ...DAILY_QUOTE, perUnit: { ...DAILY_QUOTE.perUnit, basis: 'monthly' } }],
    ['a VAT rate that is not a rate', { ...DAILY_QUOTE, vatRate: 'standard' }],
  ])('treats %s as a failure and shows no figure', async (_what, body) => {
    mockApi({ ...WORKING, [QUOTE_ROUTE]: () => jsonResponse(body) })
    openModel()

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'We could not load the price for these dates',
    )
    expect(screen.queryByText('Total with VAT')).not.toBeInTheDocument()
  })
})

describe('when the API refuses the dates or the quantity', () => {
  it('puts the message under the date it is about, once, and shows no price', async () => {
    const refusal = () =>
      problemResponse(422, {
        errors: { fields: { 'query.to': 'A hire can be at most 28 days.' } },
      })
    mockApi({ ...WORKING, [AVAILABILITY_ROUTE]: refusal, [QUOTE_ROUTE]: refusal })
    openModel(`/model/${SLUG}?from=${TEST_TODAY}&to=2026-05-01`)

    expect(await screen.findByText('A hire can be at most 28 days.')).toBeVisible()
    expect(screen.getByLabelText('Bring back on')).toBeInvalid()
    expect(screen.getByLabelText('Collect on')).not.toBeInvalid()
    expect(screen.getByRole('alert')).toHaveTextContent('We cannot check those details')
    expect(screen.getByText('The price shows here once the details above are accepted.')).toBeVisible()
    expect(screen.queryByRole('group', { name: PRICE_PANEL })).not.toBeInTheDocument()
  })

  it('puts a refused quantity beside the quantity, when only the quote refuses', async () => {
    mockApi({
      ...WORKING,
      [QUOTE_ROUTE]: () =>
        problemResponse(422, { errors: { fields: { 'query.quantity': 'Enter 10 or less.' } } }),
    })
    openModel()

    const message = await screen.findByText('Enter 10 or less.')
    expect(message).toBeVisible()
    expect(screen.getByLabelText('How many')).toBeInvalid()
    expect(screen.getByLabelText('How many')).toHaveAccessibleDescription('Enter 10 or less.')
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('We cannot check those details'),
    )
    expect(screen.queryByText('Total with VAT')).not.toBeInTheDocument()
  })
})
