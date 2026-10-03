/**
 * Tests for SC-18 Overdue and Late Fee Worklist, with the network replaced at
 * `fetch`.
 *
 * The worklist is one paged request for the overdue hires at the branch the
 * assistant works at. Waiting, failed, empty and loaded, then the pages, the
 * escalation queue, and recording a unit as lost, which asks first, sends one
 * request and shows what the server did.
 */

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { money } from '../../shared/format'
import { SAMPLE_DATA_TITLE } from '../../shared/sample-data-notice'
import { jsonResponse, mockApi, neverAnswers, problemResponse } from '../../test/api-mock'
import type { ApiMock, RouteTable } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import { RENTAL_ID, RENTAL_REFERENCE } from '../../test/counter-samples'
import { SCREEN_WAIT, findScreenHeading, renderApp } from '../../test/render-app'
import {
  AFTER_THE_LOSS,
  ESCALATED_HIRE,
  METERED,
  ODD_FEE_TODAY,
  OVERDUE_HIRE,
  RENTALS_ROUTE,
  lossRoute,
  rentalPage,
} from '../../test/rental-samples'
import { COUNTER_STAFF, signedInAs } from '../../test/session-samples'

const HEADING = 'Overdue and late fees'
const RECORD = 'Record as lost TSH-PC-0007'
const YES = 'Yes, record it as lost'

async function openWorklist(routes: RouteTable, at = '/counter/overdue'): Promise<{ user: UserEvent; network: ApiMock }> {
  const network = mockApi({ ...signedInAs(COUNTER_STAFF), ...routes })
  renderApp(at)
  await findScreenHeading(HEADING)
  return { user: userEvent.setup(), network }
}

function listing(...hires: Parameters<typeof rentalPage>): RouteTable {
  return { [RENTALS_ROUTE]: () => jsonResponse(rentalPage(...hires)) }
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('while the list loads', () => {
  it('says what it is waiting for', async () => {
    await openWorklist({ [RENTALS_ROUTE]: neverAnswers })

    expect(await screen.findByText('Reading the overdue hires at Bellville.', {}, SCREEN_WAIT)).toBeVisible()
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull()
    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
  })
})

describe('when the list cannot be read', () => {
  it('says so with the reference, and reads it again on a retry', async () => {
    const { user, network } = await openWorklist({ [RENTALS_ROUTE]: () => problemResponse(500, { requestId: 'req-overdue-1' }) })

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('We could not load the overdue hires')
    expect(within(alert).getByText('req-overdue-1')).toBeVisible()

    network.setRoute(RENTALS_ROUTE, () => jsonResponse(rentalPage([OVERDUE_HIRE])))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('list', { name: 'Overdue hires at Bellville' })).toBeVisible()
  })
})

describe('when nothing is overdue', () => {
  it('says so in words', async () => {
    await openWorklist(listing([]))

    expect(await screen.findByText('Nothing is overdue at Bellville', {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.queryByText(/Escalation queue/)).not.toBeInTheDocument()
  })
})

describe('the overdue hires', () => {
  it('are asked for at the branch the assistant works at, overdue only, a page at a time', async () => {
    const { network } = await openWorklist(listing([OVERDUE_HIRE]))
    await screen.findByRole('list', { name: 'Overdue hires at Bellville' }, SCREEN_WAIT)

    const asked = network.requestsTo(RENTALS_ROUTE)[0].query
    expect(asked.get('branchCode')).toBe('BLV')
    expect(asked.get('overdueOnly')).toBe('true')
    expect(asked.get('page')).toBe('1')
    expect(asked.get('pageSize')).toBe('20')
  })

  it('show the customer, the due date, the days late and the fee of each unit as the server sent them', async () => {
    await openWorklist(listing([OVERDUE_HIRE]))

    const list = await screen.findByRole('list', { name: 'Overdue hires at Bellville' }, SCREEN_WAIT)
    expect(screen.getByText('1 hire is overdue at Bellville, most overdue first.')).toBeVisible()
    expect(within(list).getByText('Thandi Mokoena')).toBeVisible()
    expect(within(list).getByText('0824417719')).toBeVisible()
    expect(within(list).getByText('Was due back 13 Mar 2026')).toBeVisible()
    expect(within(list).getByText('2 days late', { selector: '.pill' })).toBeVisible()
    const units = within(list).getByRole('list', { name: `Units still out on ${RENTAL_REFERENCE}` })
    expect(within(units).getAllByRole('listitem')).toHaveLength(2)
    expect(within(units).getAllByText(money(ODD_FEE_TODAY))).toHaveLength(2)
    expect(within(list).getByRole('link', { name: `Take the return ${RENTAL_REFERENCE}` })).toHaveAttribute(
      'href',
      `/counter/return/${RENTAL_ID}`,
    )
    expect(screen.queryByRole('button', { name: /Ring the customer/ })).not.toBeInTheDocument()
    expect(screen.queryByText(/no hire against them/i)).not.toBeInTheDocument()
  })

  it('moves between the pages the server counts, and keeps the page in the address', async () => {
    const { user, network } = await openWorklist(listing([OVERDUE_HIRE], { total: 45 }))
    await screen.findByRole('list', { name: 'Overdue hires at Bellville' }, SCREEN_WAIT)

    await user.click(screen.getByRole('button', { name: 'Next' }))

    await waitFor(() => expect(network.requestsTo(RENTALS_ROUTE).at(-1)?.query.get('page')).toBe('2'))
  })
})

describe('the escalation queue', () => {
  it('says when nothing on the page is more than fourteen days late', async () => {
    await openWorklist(listing([OVERDUE_HIRE]))

    expect(await screen.findByText('Nothing on this page is more than 14 days late.', {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.queryByRole('button', { name: /^Record as lost/ })).not.toBeInTheDocument()
  })

  it('lists each unit more than fourteen days late, with the way to record it as lost', async () => {
    await openWorklist(listing([ESCALATED_HIRE]))

    const queue = await screen.findByRole('list', { name: 'Units in the escalation queue' }, SCREEN_WAIT)
    expect(within(queue).getAllByRole('listitem')).toHaveLength(2)
    expect(within(queue).getByText(`TSH-PC-0007 on ${RENTAL_REFERENCE}`)).toBeVisible()
    expect(within(queue).getAllByText('16 days late')).toHaveLength(2)
    expect(within(queue).getByRole('button', { name: RECORD })).toBeVisible()
  })
})

describe('recording a unit as lost', () => {
  it('says in words what will happen, and sends nothing until asked', async () => {
    const { user, network } = await openWorklist({ ...listing([ESCALATED_HIRE]), [lossRoute(METERED.id)]: () => jsonResponse(AFTER_THE_LOSS) })

    await user.click(await screen.findByRole('button', { name: RECORD }, SCREEN_WAIT))

    const question = screen.getByText(/^Recording TSH-PC-0007 as lost charges 14 days of late fee/)
    expect(question).toHaveFocus()
    expect(question).toHaveTextContent('forfeits the deposit for this unit')
    expect(question).toHaveTextContent('raises a recovery charge of up to its replacement value')
    expect(question).toHaveTextContent('marks the unit as lost')
    expect(screen.getByRole('button', { name: YES })).toHaveAccessibleDescription(/marks the unit as lost/)
    expect(network.requestsTo(lossRoute(METERED.id))).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: 'Keep it on the list' }))
    expect(screen.getByRole('button', { name: RECORD })).toHaveFocus()
  })

  it('sends one request with no body, shows what the server charged, and reads the list again', async () => {
    const { user, network } = await openWorklist({ ...listing([ESCALATED_HIRE]), [lossRoute(METERED.id)]: () => jsonResponse(AFTER_THE_LOSS) })
    await user.click(await screen.findByRole('button', { name: RECORD }, SCREEN_WAIT))

    await user.click(screen.getByRole('button', { name: YES }))

    const said = await screen.findByText(`TSH-PC-0007 on ${RENTAL_REFERENCE} is recorded as lost`, {}, SCREEN_WAIT)
    await waitFor(() => expect(said.closest('[tabindex="-1"]')).toHaveFocus())
    const notice = said.closest('[role="status"]') as HTMLElement
    expect(within(notice).getByText(/Deposit forfeited\. Deposit forfeited for TSH-PC-0007/)).toBeVisible()
    expect(within(notice).getByText(new RegExp(`Recovery charge\\. Recovery of TSH-PC-0007 ${money('8888.88')}`))).toBeVisible()
    expect(within(notice).getByText(/Balance due R 6 543[,.]21/)).toBeVisible()
    expect(network.requestsTo(lossRoute(METERED.id))).toHaveLength(1)
    expect(network.requestsTo(lossRoute(METERED.id))[0].body).toBeUndefined()
    await waitFor(() => expect(network.requestsTo(RENTALS_ROUTE)).toHaveLength(2))
  })

  it('shows the server sentence when the unit is not that late any more', async () => {
    const detail = 'TSH-PC-0007 is back, so it cannot be recorded as lost.'
    const { user } = await openWorklist({
      ...listing([ESCALATED_HIRE]),
      [lossRoute(METERED.id)]: () => problemResponse(409, { detail }),
    })
    await user.click(await screen.findByRole('button', { name: RECORD }, SCREEN_WAIT))

    await user.click(screen.getByRole('button', { name: YES }))

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('TSH-PC-0007 was not recorded as lost')
    expect(alert).toHaveTextContent(detail)
  })
})
