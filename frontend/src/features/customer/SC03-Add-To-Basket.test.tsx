/**
 * Tests for adding a tool to the hire basket from SC-03, with the network
 * replaced at `fetch`.
 *
 * The button only works when the branch said free and the quote came back,
 * both for what the card shows. A press that works says so. A press for other
 * dates or another branch than the basket asks which to keep and adds nothing
 * until the person has chosen.
 */

import { fireEvent, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, mockApi, neverAnswers, problemResponse } from '../../test/api-mock'
import {
  DAILY_QUOTE,
  MODEL_AVAILABILITY,
  TEST_DEFAULT_RETURN,
  TEST_NOW,
  TEST_TODAY,
  branchAnswers,
} from '../../test/catalogue-samples'
import { addToBasket, basketSnapshot } from '../../shared/basket-store'
import { AVAILABILITY_ROUTE, QUOTE_ROUTE, SLUG, WORKING, openModel } from './SC03-test-kit'

const ADD = 'Add to my hire basket'
const ADDED = 'Added to your hire basket'
const CONFLICT = 'Your basket is for other dates or another branch'
const RAMMER = 'bs-60-4-trench-rammer'

/** A basket that already holds another tool, for a later week at Bellville. */
const AT_BELLVILLE = { from: '2026-03-20', to: '2026-03-23', branchCode: 'BLV' }

function addButton(): HTMLElement {
  return screen.getByRole('button', { name: ADD })
}

/** The card once both answers are in and the tool can be added. */
async function readyToAdd(): Promise<HTMLElement> {
  await screen.findByText('Free at Cape Town CBD')
  await screen.findByRole('group', { name: 'Price for these dates' })
  return addButton()
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('when the tool can be added', () => {
  it('goes into the basket for the dates, the branch and the quantity on the card, and says so', async () => {
    const user = userEvent.setup()
    mockApi(WORKING)
    openModel()

    await user.click(await readyToAdd())

    expect(basketSnapshot()).toEqual({
      from: TEST_TODAY,
      to: TEST_DEFAULT_RETURN,
      branchCode: 'CBD',
      lines: [{ modelSlug: SLUG, quantity: 1 }],
      reservationId: null,
      setAside: null,
    })
    const notice = screen.getByText(ADDED).closest('[role="status"]')
    if (!(notice instanceof HTMLElement)) throw new Error('The confirmation is not a status region.')
    expect(notice).toHaveTextContent(
      '1 unit of CP 100 Plate Compactor for 12 Mar 2026 to 16 Mar 2026, collected from Cape Town CBD.',
    )
    expect(within(notice).getByRole('link', { name: 'Go to my basket' })).toHaveAttribute('href', '/basket')
  })

  it('adds the quantity chosen, and says what the basket holds when it is added again', async () => {
    const user = userEvent.setup()
    mockApi({
      ...WORKING,
      [AVAILABILITY_ROUTE]: () => jsonResponse({ ...MODEL_AVAILABILITY, quantity: 2 }),
      [QUOTE_ROUTE]: () => jsonResponse({ ...DAILY_QUOTE, quantity: 2 }),
    })
    openModel()
    await readyToAdd()
    await user.click(screen.getByRole('button', { name: 'One more CP 100 Plate Compactor' }))

    await user.click(await readyToAdd())
    expect(basketSnapshot().lines).toEqual([{ modelSlug: SLUG, quantity: 2 }])
    expect(screen.queryByText(/Your basket now holds/)).not.toBeInTheDocument()

    await user.click(addButton())
    expect(basketSnapshot().lines).toEqual([{ modelSlug: SLUG, quantity: 4 }])
    expect(screen.getByText('Your basket now holds 4 of this tool.')).toBeVisible()
  })
})

describe('when the tool cannot be added yet', () => {
  it('holds the basket back while the price is still on its way', async () => {
    mockApi({ ...WORKING, [QUOTE_ROUTE]: neverAnswers })
    openModel()

    await screen.findByText('Free at Cape Town CBD')

    expect(addButton()).toBeDisabled()
    expect(addButton()).toHaveAccessibleDescription(/once it shows as free at your branch and the price/)
  })

  it('holds the basket back when the price fails to load, though the branch is free', async () => {
    const user = userEvent.setup()
    const network = mockApi({ ...WORKING, [QUOTE_ROUTE]: () => problemResponse(500) })
    openModel()

    await screen.findByText('Free at Cape Town CBD')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not load the price for these dates')
    expect(addButton()).toBeDisabled()
    expect(basketSnapshot().lines).toEqual([])

    // Once the price is there, the tool can be added.
    network.setRoute(QUOTE_ROUTE, () => jsonResponse(DAILY_QUOTE))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await readyToAdd()).toBeEnabled()
  })

  it('holds the basket back when the price is there and the branch is not free', async () => {
    mockApi({
      ...WORKING,
      [AVAILABILITY_ROUTE]: () =>
        jsonResponse({ ...MODEL_AVAILABILITY, branches: branchAnswers(false, false, false) }),
    })
    openModel()

    await screen.findByRole('group', { name: 'Price for these dates' })
    await screen.findByText('Not free at Cape Town CBD for these dates')

    expect(addButton()).toBeDisabled()
  })

  it('holds the basket back when the API refuses the quantity for the price', async () => {
    mockApi({
      ...WORKING,
      [QUOTE_ROUTE]: () =>
        problemResponse(422, { errors: { fields: { 'query.quantity': 'Enter 10 or less.' } } }),
    })
    openModel()

    await screen.findByText('Enter 10 or less.')
    await screen.findByText('Free at Cape Town CBD')

    expect(addButton()).toBeDisabled()
  })
})

describe('when the basket is for other dates or another branch', () => {
  beforeEach(() => {
    addToBasket({ modelSlug: RAMMER, quantity: 1, ...AT_BELLVILLE })
  })

  it('asks which to keep, moves focus to the question, and adds nothing', async () => {
    const user = userEvent.setup()
    mockApi(WORKING)
    openModel()

    await user.click(await readyToAdd())

    const question = screen.getByRole('group', { name: CONFLICT })
    expect(screen.getByRole('heading', { name: CONFLICT })).toHaveFocus()
    expect(question).toHaveTextContent(
      'Your basket is for 20 Mar 2026 to 23 Mar 2026, collected from Bellville.',
    )
    expect(question).toHaveTextContent(
      'This tool is for 12 Mar 2026 to 16 Mar 2026, collected from Cape Town CBD.',
    )
    expect(basketSnapshot()).toEqual({
      ...AT_BELLVILLE,
      lines: [{ modelSlug: RAMMER, quantity: 1 }],
      reservationId: null,
      setAside: null,
    })
    expect(screen.queryByText(ADDED)).not.toBeInTheDocument()
  })

  it('puts the card on the dates and the branch of the basket when the person keeps the basket', async () => {
    const user = userEvent.setup()
    mockApi(WORKING)
    openModel()
    await user.click(await readyToAdd())

    await user.click(
      screen.getByRole('button', {
        name: 'Keep my basket, and check this tool for its dates and branch',
      }),
    )

    expect(screen.getByLabelText('Collect on')).toHaveValue(AT_BELLVILLE.from)
    expect(screen.getByLabelText('Bring back on')).toHaveValue(AT_BELLVILLE.to)
    expect(screen.getByLabelText('Collect from')).toHaveDisplayValue('Bellville')
    expect(screen.queryByRole('group', { name: CONFLICT })).not.toBeInTheDocument()
    expect(screen.getByText(/now match your basket/)).toBeVisible()
    // Nothing was added. The tool is checked for those dates first.
    expect(basketSnapshot().lines).toEqual([{ modelSlug: RAMMER, quantity: 1 }])
  })

  it('moves the whole basket and adds the tool when the person chooses these dates', async () => {
    const user = userEvent.setup()
    mockApi(WORKING)
    openModel()
    await user.click(await readyToAdd())

    await user.click(
      screen.getByRole('button', { name: 'Move my whole basket to these dates and this branch' }),
    )

    expect(basketSnapshot()).toEqual({
      from: TEST_TODAY,
      to: TEST_DEFAULT_RETURN,
      branchCode: 'CBD',
      lines: [
        { modelSlug: RAMMER, quantity: 1 },
        { modelSlug: SLUG, quantity: 1 },
      ],
      reservationId: null,
      setAside: null,
    })
    expect(screen.getByText(ADDED)).toBeVisible()
    expect(screen.queryByRole('group', { name: CONFLICT })).not.toBeInTheDocument()
  })

  it('leaves everything as it was when the person decides not to add it', async () => {
    const user = userEvent.setup()
    mockApi(WORKING)
    openModel()
    await user.click(await readyToAdd())

    await user.click(screen.getByRole('button', { name: 'Do not add this tool' }))

    expect(screen.queryByRole('group', { name: CONFLICT })).not.toBeInTheDocument()
    expect(basketSnapshot().lines).toEqual([{ modelSlug: RAMMER, quantity: 1 }])
  })

  it('takes the question down when the dates on the card change', async () => {
    const user = userEvent.setup()
    mockApi(WORKING)
    openModel()
    await user.click(await readyToAdd())
    expect(screen.getByRole('group', { name: CONFLICT })).toBeVisible()

    fireEvent.change(screen.getByLabelText('Bring back on'), { target: { value: '2026-03-14' } })

    expect(screen.queryByRole('group', { name: CONFLICT })).not.toBeInTheDocument()
  })
})
