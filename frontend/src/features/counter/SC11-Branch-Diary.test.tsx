/**
 * Tests for SC-11 Branch Diary, with the network replaced at `fetch`.
 *
 * The diary is one request for the days on the screen. Each test says how the
 * diary route answers and reads the page. Waiting, failed, empty and full,
 * then the links each entry carries, then moving a day and a week at a time
 * with the day in the address. The no show is in SC11-No-Show.test.tsx.
 */

import { screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SAMPLE_DATA_TITLE } from '../../shared/sample-data-notice'
import { neverAnswers, problemResponse } from '../../test/api-mock'
import { TEST_NOW, TEST_TODAY } from '../../test/catalogue-samples'
import { RENTAL_ID, RENTAL_REFERENCE } from '../../test/counter-samples'
import {
  COLLECTED_TODAY,
  DIARY_ROUTE,
  DUE_BACK,
  DUE_OUT,
  MONDAY_OF_NEXT_WEEK,
  MONDAY_OF_THIS_WEEK,
} from '../../test/overview-samples'
import { SCREEN_WAIT, currentAddress } from '../../test/render-app'
import { REFERENCE, SECOND_REFERENCE } from '../../test/reservation-samples'
import { diaryAnswering, lastDiaryAsked, openDiary } from './SC11-test-kit'

const TODAY_HEADING = /^Thursday 12 March 2026/

/** Today at Bellville, with two bookings going out and one hire coming back. */
const BUSY_TODAY = diaryAnswering([
  { date: TEST_TODAY, collections: [DUE_OUT, COLLECTED_TODAY], returns: [DUE_BACK] },
])

function day(name: RegExp): HTMLElement {
  return screen.getByRole('region', { name })
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('while the diary loads', () => {
  it('draws a skeleton and says what it is waiting for', async () => {
    await openDiary({ [DIARY_ROUTE]: neverAnswers })

    expect(await screen.findByText('Loading the diary', {}, SCREEN_WAIT)).toBeInTheDocument()
    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
  })
})

describe('when the diary cannot be read', () => {
  it('says so with the reference, and reads it again on a retry', async () => {
    const { user, network } = await openDiary({
      [DIARY_ROUTE]: () => problemResponse(500, { requestId: 'req-diary-1' }),
    })

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('We could not load the diary')
    expect(within(alert).getByText('req-diary-1')).toBeVisible()

    network.setRoute(DIARY_ROUTE, BUSY_TODAY)
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('heading', { level: 2, name: TODAY_HEADING })).toBeVisible()
  })
})

describe('a day with nothing on it', () => {
  it('says so and offers the arrows', async () => {
    await openDiary({ [DIARY_ROUTE]: diaryAnswering() })

    expect(await screen.findByText('Nothing goes out or comes back on this day', {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByRole('button', { name: 'Next day' })).toBeVisible()
  })
})

describe('today in the diary', () => {
  it('asks for today at the branch the assistant works at, and names the day', async () => {
    const { network } = await openDiary({ [DIARY_ROUTE]: BUSY_TODAY })

    const today = await screen.findByRole('heading', { level: 2, name: TODAY_HEADING }, SCREEN_WAIT)
    expect(today).toHaveTextContent('Today')
    const asked = network.requestsTo(DIARY_ROUTE)[0].query
    expect(asked.get('branchCode')).toBe('BLV')
    expect(lastDiaryAsked(network)).toBe(`${TEST_TODAY} for 1`)
    expect(screen.getByText('Thursday 12 March 2026 at Bellville.')).toBeVisible()
    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
  })

  it('shows each entry with its status in words and the way forward', async () => {
    await openDiary({ [DIARY_ROUTE]: BUSY_TODAY })
    await screen.findByRole('heading', { level: 2, name: TODAY_HEADING }, SCREEN_WAIT)

    const going = screen.getByRole('list', { name: /^Going out on Thursday 12 March 2026/ })
    expect(within(going).getByText('Booked, not collected yet')).toBeVisible()
    expect(within(going).getByText('Collected')).toBeVisible()
    expect(within(going).getByRole('link', { name: `Check out ${REFERENCE}` })).toHaveAttribute(
      'href',
      `/counter/checkout/${REFERENCE}`,
    )
    expect(within(going).getByRole('link', { name: `Open the hire ${SECOND_REFERENCE}` })).toHaveAttribute(
      'href',
      `/counter/checkout/${SECOND_REFERENCE}`,
    )
    expect(within(going).getByRole('button', { name: `Mark as no show ${REFERENCE}` })).toBeVisible()
    expect(within(going).queryByRole('button', { name: `Mark as no show ${SECOND_REFERENCE}` })).not.toBeInTheDocument()

    const back = screen.getByRole('list', { name: /^Coming back on Thursday 12 March 2026/ })
    expect(within(back).getByText('Out with the customer')).toBeVisible()
    expect(within(back).getByText('1 of 2 units still out')).toBeVisible()
    expect(within(back).getByRole('link', { name: `Open the hire ${RENTAL_REFERENCE}` })).toHaveAttribute(
      'href',
      `/counter/return/${RENTAL_ID}`,
    )
  })

  it('offers no checkout for a booking that starts on a later day', async () => {
    const later = { ...DUE_OUT, from: '2026-03-13', canMarkNoShow: false }
    await openDiary({ [DIARY_ROUTE]: diaryAnswering([{ date: '2026-03-13', collections: [later], returns: [] }]) }, '/counter/diary?date=2026-03-13')

    expect(await screen.findByText('Booked, not collected yet', {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.queryByRole('link', { name: `Check out ${REFERENCE}` })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Mark as no show/ })).not.toBeInTheDocument()
    expect(day(/^Friday 13 March 2026/)).toHaveTextContent('Nothing is due back on this day.')
  })
})

describe('moving through the diary', () => {
  it('goes a day at a time with the day in the address, and back to today', async () => {
    const { user, network } = await openDiary({ [DIARY_ROUTE]: diaryAnswering() })
    await screen.findByText('Nothing goes out or comes back on this day', {}, SCREEN_WAIT)

    await user.click(screen.getByRole('button', { name: 'Next day' }))
    expect(currentAddress()).toBe('/counter/diary?date=2026-03-13')
    expect(await screen.findByText('Friday 13 March 2026 at Bellville.')).toBeVisible()
    expect(lastDiaryAsked(network)).toBe('2026-03-13 for 1')

    await user.click(screen.getByRole('button', { name: 'Previous day' }))
    await user.click(screen.getByRole('button', { name: 'Previous day' }))
    expect(currentAddress()).toBe('/counter/diary?date=2026-03-11')

    await user.click(screen.getByRole('button', { name: 'Back to today' }))
    expect(currentAddress()).toBe('/counter/diary')
    expect(lastDiaryAsked(network)).toBe(`${TEST_TODAY} for 1`)
  })

  it('shows a whole week from Monday, moves a week at a time, and opens one day of it', async () => {
    const nextWednesday = { date: '2026-03-18', collections: [], returns: [{ ...DUE_BACK, dueBackOn: '2026-03-18' }] }
    const twoWeeks = diaryAnswering([
      { date: TEST_TODAY, collections: [DUE_OUT, COLLECTED_TODAY], returns: [DUE_BACK] },
      nextWednesday,
    ])
    const { user, network } = await openDiary({ [DIARY_ROUTE]: twoWeeks })
    await screen.findByRole('heading', { level: 2, name: TODAY_HEADING }, SCREEN_WAIT)

    await user.click(screen.getByRole('button', { name: 'Whole week' }))
    expect(screen.getByRole('button', { name: 'Whole week' })).toHaveAttribute('aria-pressed', 'true')
    expect(currentAddress()).toBe('/counter/diary?view=week')
    expect(await screen.findByRole('heading', { level: 2, name: /^Sunday 15 March 2026/ })).toBeVisible()
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(7)
    expect(lastDiaryAsked(network)).toBe(`${MONDAY_OF_THIS_WEEK} for 7`)
    expect(screen.getByText('The week starting Monday 9 March 2026 at Bellville.')).toBeVisible()

    await user.click(screen.getByRole('button', { name: 'Next week' }))
    expect(currentAddress()).toBe('/counter/diary?date=2026-03-19&view=week')
    expect(await screen.findByRole('heading', { level: 2, name: /^Monday 16 March 2026/ })).toBeVisible()
    expect(lastDiaryAsked(network)).toBe(`${MONDAY_OF_NEXT_WEEK} for 7`)

    await user.click(screen.getByRole('button', { name: 'Open this day Wednesday 18 March 2026' }))
    expect(currentAddress()).toBe('/counter/diary?date=2026-03-18')
    expect(await screen.findByText('Wednesday 18 March 2026 at Bellville.')).toBeVisible()
    expect(lastDiaryAsked(network)).toBe('2026-03-18 for 1')
  })

  it('keeps the day and the view from the address on a reload', async () => {
    const { network } = await openDiary({ [DIARY_ROUTE]: diaryAnswering() }, '/counter/diary?date=2026-03-20&view=week')

    expect(await screen.findByText('The week starting Monday 16 March 2026 at Bellville.', {}, SCREEN_WAIT)).toBeVisible()
    expect(lastDiaryAsked(network)).toBe(`${MONDAY_OF_NEXT_WEEK} for 7`)
  })

  it('falls back to today for a date in the address that is not a day', async () => {
    const { network } = await openDiary({ [DIARY_ROUTE]: diaryAnswering() }, '/counter/diary?date=2026-02-30&view=month')

    expect(await screen.findByText('Thursday 12 March 2026 at Bellville.', {}, SCREEN_WAIT)).toBeVisible()
    expect(lastDiaryAsked(network)).toBe(`${TEST_TODAY} for 1`)
  })
})
