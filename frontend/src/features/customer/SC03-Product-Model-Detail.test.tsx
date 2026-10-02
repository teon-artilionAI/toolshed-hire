/**
 * Tests for SC-03 Product Model Detail, with the network replaced at `fetch`.
 *
 * The screen is opened on the address of one model. Each test sets how the
 * model, the branches, the availability and the quote routes answer, and then
 * reads the page the way a customer would. The price on the booking card has
 * its own file, SC03-Booking-Card.test.tsx.
 */

import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, mockApi, neverAnswers, problemResponse } from '../../test/api-mock'
import {
  MODEL_AVAILABILITY,
  PLATE_COMPACTOR_DETAIL,
  TEST_DEFAULT_RETURN,
  TEST_NOW,
  TEST_TODAY,
  branchAnswers,
} from '../../test/catalogue-samples'
import { MODEL_PLACEHOLDER_TEST_ID } from './model-picture'
import {
  AVAILABILITY_ROUTE,
  DATED,
  MODEL_ROUTE,
  QUOTE_ROUTE,
  WORKING,
  lastQuestion,
  openModel,
} from './SC03-test-kit'

/** The value shown against one term in the price and specification list. */
function specification(term: string): HTMLElement {
  const value = screen.getByText(term).nextElementSibling
  if (!(value instanceof HTMLElement)) throw new Error(`No value is shown for "${term}".`)
  return value
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('while the model is loading', () => {
  it('announces that it is loading and shows nothing about the tool yet', () => {
    mockApi({ ...WORKING, [MODEL_ROUTE]: neverAnswers })
    openModel()

    expect(screen.getByRole('status')).toHaveTextContent('Loading this tool')
    expect(screen.queryByRole('heading', { level: 1 })).not.toBeInTheDocument()
  })
})

describe('once the model has loaded', () => {
  it('asks the API for the model in the address', async () => {
    const network = mockApi(WORKING)
    openModel()

    expect(await screen.findByRole('heading', { level: 1, name: 'CP 100 Plate Compactor' })).toBeVisible()
    expect(network.requestsTo(MODEL_ROUTE)).toHaveLength(1)
    expect(screen.getByText('Wacker Neuson. Compaction.')).toBeVisible()
    expect(screen.getByText('The handle folds so it fits in a bakkie.')).toBeVisible()
  })

  it('shows every price field', async () => {
    mockApi(WORKING)
    openModel()

    await screen.findByRole('heading', { level: 1, name: 'CP 100 Plate Compactor' })
    expect(specification('Hire rate')).toHaveTextContent(/^R 340[,.]00 per day$/)
    expect(specification('Weekly rate')).toHaveTextContent(/^R 1.360[,.]00 per week$/)
    expect(specification('Refundable deposit')).toHaveTextContent(/^R 1.500[,.]00$/)
    expect(specification('Late fee')).toHaveTextContent(/^R 220[,.]00 per day past the return date$/)
    expect(specification('Hire length')).toHaveTextContent('1 to 28 days')
    expect(specification('Catalogue number')).toHaveTextContent('PC-WACKER-CP100')
  })

  it('asks about the dates in the address and one unit', async () => {
    const network = mockApi(WORKING)
    openModel('/model/cp-100-plate-compactor?from=2026-03-20&to=2026-03-23')

    await screen.findByText('Free at Cape Town CBD')
    const asked = lastQuestion(network, AVAILABILITY_ROUTE)
    expect(asked.get('from')).toBe('2026-03-20')
    expect(asked.get('to')).toBe('2026-03-23')
    expect(asked.get('quantity')).toBe('1')
  })

  it('says free or not free at every branch, and never a count', async () => {
    mockApi(WORKING)
    openModel()

    const heading = await screen.findByRole('heading', { name: 'At each branch for these dates' })
    const card = heading.closest('section')
    if (!card) throw new Error('The branch card is not a section.')
    await waitFor(() =>
      expect(within(card).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
        'Cape Town CBD: Free',
        'Bellville: Not free',
        'Somerset West: Not free',
      ]),
    )
    expect(document.body).not.toHaveTextContent(/\d+ free/i)
    expect(document.body).not.toHaveTextContent(/in the fleet/i)
  })

  it('stands a placeholder in for the photograph, called by the name of the tool', async () => {
    mockApi(WORKING)
    openModel()

    const picture = await screen.findByRole('figure', { name: 'CP 100 Plate Compactor' })
    expect(within(picture).getByTestId(MODEL_PLACEHOLDER_TEST_ID)).toBeInTheDocument()
    expect(within(picture).queryByRole('img')).not.toBeInTheDocument()
  })

  it('offers the basket for the first branch when it is free there and priced', async () => {
    mockApi(WORKING)
    openModel()

    await screen.findByText('Free at Cape Town CBD')
    await screen.findByRole('group', { name: 'Price for these dates' })
    expect(screen.getByRole('button', { name: 'Add to my hire basket' })).toBeEnabled()
  })

  it('asks again when the quantity changes', async () => {
    const user = userEvent.setup()
    const network = mockApi(WORKING)
    openModel()

    await screen.findByText('Free at Cape Town CBD')
    await user.click(screen.getByRole('button', { name: 'One more CP 100 Plate Compactor' }))

    await waitFor(() =>
      expect(lastQuestion(network, AVAILABILITY_ROUTE).get('quantity')).toBe('2'),
    )
  })

  it('asks again when a date changes', async () => {
    const network = mockApi(WORKING)
    openModel()

    await screen.findByText('Free at Cape Town CBD')
    fireEvent.change(screen.getByLabelText('Bring back on'), { target: { value: '2026-03-14' } })

    await waitFor(() =>
      expect(lastQuestion(network, AVAILABILITY_ROUTE).get('to')).toBe('2026-03-14'),
    )
  })

  it('links back to the search for the same dates', async () => {
    mockApi(WORKING)
    openModel()

    expect(await screen.findByRole('link', { name: 'Back to results' })).toHaveAttribute(
      'href',
      `/search?from=${TEST_TODAY}&to=${TEST_DEFAULT_RETURN}`,
    )
  })
})

describe('when the chosen branch cannot supply it', () => {
  it('says so, holds back the basket and offers a branch that can', async () => {
    const user = userEvent.setup()
    mockApi(WORKING)
    openModel(`${DATED}&branch=BLV`)

    expect(await screen.findByText('Not free at Bellville for these dates')).toBeVisible()
    expect(screen.getByText('Cape Town CBD can supply it for the same dates.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Add to my hire basket' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Collect from Cape Town CBD instead' }))

    expect(await screen.findByText('Free at Cape Town CBD')).toBeVisible()
    expect(screen.getByLabelText('Collect from')).toHaveDisplayValue('Cape Town CBD')
    expect(screen.getByRole('button', { name: 'Add to my hire basket' })).toBeEnabled()
  })

  it('says so plainly when no branch has it free', async () => {
    mockApi({
      ...WORKING,
      [AVAILABILITY_ROUTE]: () =>
        jsonResponse({ ...MODEL_AVAILABILITY, branches: branchAnswers(false, false, false) }),
    })
    openModel()

    expect(await screen.findByText('Not free at Cape Town CBD for these dates')).toBeVisible()
    expect(screen.getByText(/No other branch can supply it for these dates either/)).toBeVisible()
    expect(screen.queryByRole('button', { name: /Collect from .* instead/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add to my hire basket' })).toBeDisabled()
  })
})

describe('when the address names no model we hire', () => {
  it('says the tool cannot be found and points back to the search', async () => {
    mockApi({
      ...WORKING,
      'GET /api/catalogue/models/no-such-tool': () => problemResponse(404),
      'GET /api/catalogue/models/no-such-tool/availability': () => problemResponse(404),
      'GET /api/catalogue/models/no-such-tool/quote': () => problemResponse(404),
    })
    openModel('/model/no-such-tool')

    expect(
      await screen.findByRole('heading', { level: 1, name: 'We cannot find that tool' }),
    ).toBeVisible()
    expect(screen.getByText('no-such-tool')).toBeVisible()
    expect(screen.getByRole('link', { name: 'Back to the search' })).toHaveAttribute('href', '/search')
  })
})

describe('when the model fails to load', () => {
  it('says so in plain words with the reference, and loads it on a retry', async () => {
    const user = userEvent.setup()
    const network = mockApi({
      ...WORKING,
      [MODEL_ROUTE]: () => problemResponse(500, { requestId: 'req-model-3' }),
    })
    openModel()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not load this tool')
    expect(within(alert).getByText('req-model-3')).toBeVisible()
    expect(alert).not.toHaveTextContent('500')

    network.setRoute(MODEL_ROUTE, () => jsonResponse(PLATE_COMPACTOR_DETAIL))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('heading', { level: 1, name: 'CP 100 Plate Compactor' })).toBeVisible()
  })
})

describe('when the availability check fails', () => {
  it('keeps the tool on the page, holds back the basket and offers a retry', async () => {
    const user = userEvent.setup()
    const network = mockApi({
      ...WORKING,
      [AVAILABILITY_ROUTE]: () => problemResponse(500, { requestId: 'req-availability-5' }),
    })
    openModel()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not load what is free for these dates')
    expect(within(alert).getByText('req-availability-5')).toBeVisible()
    expect(screen.getByRole('heading', { level: 1, name: 'CP 100 Plate Compactor' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Add to my hire basket' })).toBeDisabled()

    network.setRoute(AVAILABILITY_ROUTE, () => jsonResponse(MODEL_AVAILABILITY))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText('Free at Cape Town CBD')).toBeVisible()
  })

  it('shows the message for each date the API refuses, under that date', async () => {
    const refusal = () =>
      problemResponse(422, {
        errors: {
          fields: {
            'query.from': 'The hire has to start today or later.',
            'query.to': 'The return date has to be after the start date.',
          },
        },
      })
    mockApi({ ...WORKING, [AVAILABILITY_ROUTE]: refusal, [QUOTE_ROUTE]: refusal })
    openModel('/model/cp-100-plate-compactor?from=2026-03-01&to=2026-02-20')

    expect(await screen.findByText('The hire has to start today or later.')).toBeVisible()
    expect(screen.getByText('The return date has to be after the start date.')).toBeVisible()
    expect(screen.getByLabelText('Collect on')).toBeInvalid()
    expect(screen.getByRole('alert')).toHaveTextContent('We cannot check those details')
    expect(screen.getByRole('button', { name: 'Add to my hire basket' })).toBeDisabled()
  })

  it('does not crash on a date that is not a date', async () => {
    const refusal = () =>
      problemResponse(422, {
        errors: { fields: { 'query.from': 'Enter a valid date, in the form YYYY-MM-DD.' } },
      })
    mockApi({ ...WORKING, [AVAILABILITY_ROUTE]: refusal, [QUOTE_ROUTE]: refusal })
    openModel('/model/cp-100-plate-compactor?from=banana&to=2026-03-16')

    expect(await screen.findByText('Enter a valid date, in the form YYYY-MM-DD.')).toBeVisible()
    expect(screen.getByRole('heading', { level: 1, name: 'CP 100 Plate Compactor' })).toBeVisible()
  })
})
