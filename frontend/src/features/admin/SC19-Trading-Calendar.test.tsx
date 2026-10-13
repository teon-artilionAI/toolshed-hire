/**
 * Tests for the trading calendar, the view of SC-19 at /admin/closure-days,
 * with the network replaced at `fetch`.
 *
 * The closed days are one read, grouped by month, the holidays offering
 * nothing and each closure offering to cancel it. Waiting, failed, empty and
 * loaded, the way in from the overview, the form's own checks, closing a day
 * after the bookings on it are listed, closing every branch on a day nobody
 * booked, a refusal under its field, a 409 and a 403 in the question,
 * cancelling a closure, and the view refused to anyone but the owner.
 */

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createdResponse, jsonResponse, mockApi, neverAnswers, problemResponse } from '../../test/api-mock'
import type { ApiMock, RouteTable } from '../../test/api-mock'
import {
  ADD_CLOSURE_ROUTE,
  CALENDAR_ROUTE,
  CBD_CLOSURE,
  COLLECTING,
  DAY_TO_CLOSE,
  DUE_BACK,
  ELECTION_DAY,
  IMPACT_ROUTE,
  STOCKTAKE,
  calendarOf,
  cancelClosureRoute,
  impactOf,
} from '../../test/calendar-samples'
import { TEST_NOW } from '../../test/catalogue-samples'
import { SCREEN_WAIT, findScreenHeading, renderApp } from '../../test/render-app'
import { ADMIN_DASHBOARD_ROUTE } from '../../test/report-samples'
import { ADMIN, BRANCHES_ROUTE, COUNTER_STAFF, signedInAs } from '../../test/session-samples'

const HEADING = 'Trading calendar'
const CALENDAR = '/admin/closure-days'
const REASON = 'Stocktake'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

async function openCalendar(routes: RouteTable = {}): Promise<{ user: UserEvent; network: ApiMock }> {
  const network = mockApi({
    ...signedInAs(ADMIN),
    [CALENDAR_ROUTE]: () => jsonResponse(calendarOf()),
    [IMPACT_ROUTE]: () => jsonResponse(impactOf()),
    ...routes,
  })
  renderApp(CALENDAR)
  await findScreenHeading(HEADING)
  return { user: userEvent.setup(), network }
}

function closedDaysRegion(): HTMLElement {
  return screen.getByRole('region', { name: 'Closed days in the next twelve months' })
}

function form(): HTMLElement {
  return screen.getByRole('form', { name: 'Close a day' })
}

/** Fill the form with a branch, the day to close and a reason, and send it. */
async function closeTheDay(user: UserEvent, branch = 'Cape Town CBD'): Promise<void> {
  await screen.findByRole('option', { name: 'Cape Town CBD' }, SCREEN_WAIT)
  await user.selectOptions(within(form()).getByLabelText('Branch'), branch)
  await user.type(within(form()).getByLabelText('Day to close'), DAY_TO_CLOSE)
  await user.type(within(form()).getByLabelText('Reason customers read'), REASON)
  await user.click(within(form()).getByRole('button', { name: 'Check the bookings and close the day' }))
}

describe('reading the closed days', () => {
  it('groups the days by month, a holiday offering nothing and a closure offering to cancel it', async () => {
    await openCalendar()

    const march = await within(closedDaysRegion()).findByRole('region', { name: 'March 2026' }, SCREEN_WAIT)
    expect(within(closedDaysRegion()).getByText('4 closed days, public holidays included.')).toBeVisible()
    expect(within(march).getByText('Friday 20 March 2026')).toBeVisible()
    expect(within(march).getByText('Closure day, Bellville. Stocktake')).toBeVisible()
    expect(within(march).getByText('Public holiday, every branch. Human Rights Day')).toBeVisible()
    expect(within(march).getAllByRole('button')).toHaveLength(1)
    expect(within(march).getByRole('button', { name: 'Cancel the closure of Bellville on Friday 20 March 2026' })).toBeVisible()
    const may = within(closedDaysRegion()).getByRole('region', { name: 'May 2026' })
    expect(within(may).getByText(`Closure day, every branch. ${ELECTION_DAY.reason}`)).toBeVisible()
    expect(within(closedDaysRegion()).getByRole('region', { name: 'April 2026' })).toBeVisible()
  })

  it('draws a skeleton while it loads', async () => {
    await openCalendar({ [CALENDAR_ROUTE]: neverAnswers })

    expect(await within(closedDaysRegion()).findByText('Loading the closed days.')).toBeInTheDocument()
    expect(closedDaysRegion().querySelector('[aria-busy="true"]')).not.toBeNull()
  })

  it('says so with the reference when it cannot be read', async () => {
    await openCalendar({ [CALENDAR_ROUTE]: () => problemResponse(500, { requestId: 'req-calendar-1' }) })

    const alert = await within(closedDaysRegion()).findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('We could not load the closed days')
    expect(within(alert).getByText('req-calendar-1')).toBeVisible()
  })

  it('says when no day is closed', async () => {
    await openCalendar({ [CALENDAR_ROUTE]: () => jsonResponse(calendarOf([])) })

    expect(await screen.findByText('No day is closed in the next twelve months', {}, SCREEN_WAIT)).toBeVisible()
  })

  it('is reached from the business overview', async () => {
    mockApi({ ...signedInAs(ADMIN), [ADMIN_DASHBOARD_ROUTE]: neverAnswers, [CALENDAR_ROUTE]: () => jsonResponse(calendarOf()) })
    renderApp('/admin')
    await findScreenHeading('Business overview')

    await userEvent.setup().click(screen.getByRole('link', { name: 'Trading calendar' }))

    expect(await findScreenHeading(HEADING)).toBeVisible()
  })
})

describe('closing a day', () => {
  it('lists the bookings on the day first, says they are not cancelled, and closes it once asked', async () => {
    const { user, network } = await openCalendar({ [ADD_CLOSURE_ROUTE]: () => createdResponse(CBD_CLOSURE) })
    const calendarReads = network.requestsTo(CALENDAR_ROUTE).length
    const branchReads = network.requestsTo(BRANCHES_ROUTE).length

    await closeTheDay(user)

    const question = await screen.findByRole('heading', { level: 3, name: 'Close Cape Town CBD on Friday 27 March 2026?' }, SCREEN_WAIT)
    expect(question).toHaveFocus()
    expect(network.requestsTo(IMPACT_ROUTE).at(-1)?.query.toString()).toBe(`day=${DAY_TO_CLOSE}&branchCode=CBD`)
    expect(screen.getByText('3 bookings and hires fall on that day.')).toBeVisible()
    const bookings = screen.getByRole('list', { name: 'Bookings and hires on that day' })
    expect(within(bookings).getAllByRole('listitem')).toHaveLength(3)
    expect(within(bookings).getByRole('link', { name: COLLECTING.customerPhone })).toHaveAttribute('href', 'tel:0824417719')
    expect(within(bookings).getByText(COLLECTING.reference).closest('li')).toHaveTextContent('Collects on that day.')
    const hire = within(bookings).getByText(DUE_BACK.reference).closest('li')
    expect(hire).toHaveTextContent(`${DUE_BACK.customerName} ${DUE_BACK.customerPhone}`)
    expect(hire).toHaveTextContent('24 Mar to 27 Mar. Out on hire, and due back that day.')
    expect(screen.getByText(/Closing the day changes none of these\. Ring each customer/)).toBeVisible()
    expect(network.requestsTo(ADD_CLOSURE_ROUTE)).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: 'Yes, close the day' }))

    const outcome = await screen.findByText('Cape Town CBD is closed on Friday 27 March 2026', {}, SCREEN_WAIT)
    expect(outcome.closest('[tabindex="-1"]')).toHaveFocus()
    expect(network.requestsTo(ADD_CLOSURE_ROUTE).at(-1)?.body).toEqual({ branchCode: 'CBD', day: DAY_TO_CLOSE, reason: REASON })
    await waitFor(() => expect(network.requestsTo(CALENDAR_ROUTE).length).toBeGreaterThan(calendarReads))
    await waitFor(() => expect(network.requestsTo(BRANCHES_ROUTE).length).toBeGreaterThan(branchReads))
    expect(within(form()).getByLabelText('Reason customers read')).toHaveValue('')
  })

  it('closes every branch on a day nobody booked, saying there are no bookings', async () => {
    const everywhere = { ...CBD_CLOSURE, branchCode: null }
    const { user, network } = await openCalendar({
      [IMPACT_ROUTE]: () => jsonResponse(impactOf([])),
      [ADD_CLOSURE_ROUTE]: () => createdResponse(everywhere),
    })

    await closeTheDay(user, 'Every branch')

    expect(await screen.findByRole('heading', { level: 3, name: 'Close every branch on Friday 27 March 2026?' }, SCREEN_WAIT)).toHaveFocus()
    expect(screen.getByText('No booking or hire falls on that day.')).toBeVisible()
    expect(network.requestsTo(IMPACT_ROUTE).at(-1)?.query.toString()).toBe(`day=${DAY_TO_CLOSE}`)
    await user.click(screen.getByRole('button', { name: 'Yes, close the day' }))

    expect(await screen.findByText('Every branch is closed on Friday 27 March 2026', {}, SCREEN_WAIT)).toBeVisible()
    expect(network.requestsTo(ADD_CLOSURE_ROUTE).at(-1)?.body).toEqual({ branchCode: null, day: DAY_TO_CLOSE, reason: REASON })
  })

  it('holds back an empty form, puts each problem under its field and moves focus to the first', async () => {
    const { user, network } = await openCalendar()

    await user.click(within(form()).getByRole('button', { name: 'Check the bookings and close the day' }))

    expect(within(form()).getByLabelText('Branch')).toHaveFocus()
    expect(within(form()).getByLabelText('Branch')).toHaveAccessibleDescription('Choose a branch, or every branch.')
    expect(within(form()).getByLabelText('Day to close')).toHaveAccessibleDescription(expect.stringContaining('Choose the day to close.'))
    expect(within(form()).getByLabelText('Reason customers read')).toHaveAccessibleDescription(expect.stringContaining('Write the reason.'))
    expect(network.requestsTo(IMPACT_ROUTE)).toHaveLength(0)
  })

  it('counts the characters of the reason that are left', async () => {
    const { user } = await openCalendar()

    await user.type(within(form()).getByLabelText('Reason customers read'), REASON)

    expect(within(form()).getByLabelText('Reason customers read')).toHaveAccessibleDescription(expect.stringContaining('111 characters left of 120.'))
  })

  it('puts a day the server refuses under the day, back on the form', async () => {
    const refusal = () => problemResponse(422, { errors: { fields: { 'body.day': 'Choose today or a later day.' } } })
    const { user } = await openCalendar({ [ADD_CLOSURE_ROUTE]: refusal })
    await closeTheDay(user)
    await user.click(await screen.findByRole('button', { name: 'Yes, close the day' }, SCREEN_WAIT))

    await waitFor(() => expect(within(form()).getByLabelText('Day to close')).toHaveAccessibleDescription(expect.stringContaining('Choose today or a later day.')))
    expect(within(form()).getByLabelText('Reason customers read')).toHaveValue(REASON)
  })

  it('puts a branch the server refuses when it is asked for the bookings under the branch', async () => {
    const refusal = () => problemResponse(422, { errors: { fields: { 'query.branchCode': 'We do not have a branch with that code.' } } })
    const { user } = await openCalendar({ [IMPACT_ROUTE]: refusal })

    await closeTheDay(user)

    await waitFor(() => expect(within(form()).getByLabelText('Branch')).toHaveAccessibleDescription('We do not have a branch with that code.'))
  })

  it.each([
    [409, 'Every branch is already closed on Friday 27 March 2026 (Election day). Cancel that closure first.'],
    [403, 'Only an administrator may close a day.'],
  ])('shows the sentence of a %i in the question', async (status, detail) => {
    const { user } = await openCalendar({ [ADD_CLOSURE_ROUTE]: () => problemResponse(status, { detail }) })
    await closeTheDay(user)

    await user.click(await screen.findByRole('button', { name: 'Yes, close the day' }, SCREEN_WAIT))

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('Friday 27 March 2026 was not closed')
    expect(alert).toHaveTextContent(detail)
  })

  it('goes back to the form with what was typed, and gives focus to its button', async () => {
    const { user } = await openCalendar()
    await closeTheDay(user)

    await user.click(await screen.findByRole('button', { name: 'Go back and change it' }, SCREEN_WAIT))

    await waitFor(() => expect(within(form()).getByRole('button', { name: 'Check the bookings and close the day' })).toHaveFocus())
    expect(within(form()).getByLabelText('Reason customers read')).toHaveValue(REASON)
  })
})

describe('cancelling a closure', () => {
  const cancelButton = 'Cancel the closure of Bellville on Friday 20 March 2026'

  it('asks first, cancels it once asked and reads the calendar again', async () => {
    const cancelled = { ...CBD_CLOSURE, id: STOCKTAKE.closureId ?? '', branchCode: 'BLV', day: STOCKTAKE.day, cancelledAt: '2026-03-12T08:00:00+02:00' }
    const route = cancelClosureRoute(STOCKTAKE.closureId ?? '')
    const { user, network } = await openCalendar({ [route]: () => jsonResponse(cancelled) })
    await user.click(await screen.findByRole('button', { name: cancelButton }, SCREEN_WAIT))
    const reads = network.requestsTo(CALENDAR_ROUTE).length

    expect(screen.getByRole('heading', { level: 4, name: 'Open Bellville again on Friday 20 March 2026?' })).toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'Yes, cancel the closure' }))

    const outcome = await screen.findByText('Bellville is open again on Friday 20 March 2026', {}, SCREEN_WAIT)
    expect(outcome.closest('[tabindex="-1"]')).toHaveFocus()
    expect(network.requestsTo(route)).toHaveLength(1)
    await waitFor(() => expect(network.requestsTo(CALENDAR_ROUTE).length).toBeGreaterThan(reads))
  })

  it('shows the sentence of a 409', async () => {
    const route = cancelClosureRoute(STOCKTAKE.closureId ?? '')
    const { user } = await openCalendar({ [route]: () => problemResponse(409, { detail: 'This closure was cancelled already.' }) })
    await user.click(await screen.findByRole('button', { name: cancelButton }, SCREEN_WAIT))

    await user.click(screen.getByRole('button', { name: 'Yes, cancel the closure' }))

    expect(await screen.findByRole('alert', {}, SCREEN_WAIT)).toHaveTextContent('This closure was cancelled already.')
  })

  it('keeps it closed and gives focus back to its button', async () => {
    const { user, network } = await openCalendar()
    await user.click(await screen.findByRole('button', { name: cancelButton }, SCREEN_WAIT))

    await user.click(screen.getByRole('button', { name: 'Keep it closed' }))

    await waitFor(() => expect(screen.getByRole('button', { name: cancelButton })).toHaveFocus())
    expect(network.requests.some((request) => request.method === 'POST' && request.path.endsWith('/cancel'))).toBe(false)
  })
})

describe('who may open it', () => {
  it('refuses counter staff, who are told so and never reach the calendar', async () => {
    const network = mockApi({ ...signedInAs(COUNTER_STAFF), [CALENDAR_ROUTE]: () => jsonResponse(calendarOf()) })
    renderApp(CALENDAR)

    expect(await screen.findByRole('heading', { level: 1, name: 'You do not have access to this screen' }, SCREEN_WAIT)).toBeVisible()
    expect(network.requestsTo(CALENDAR_ROUTE)).toHaveLength(0)
  })
})
