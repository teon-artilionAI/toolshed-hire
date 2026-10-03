/**
 * Tests for SC-10 Counter Dashboard, with the network replaced at `fetch`.
 *
 * The dashboard is one request for the branch the assistant works at. Each
 * test says how that route answers and reads the page. Waiting, failed, a
 * quiet day and a busy one, then the links each entry carries, a list the
 * server cut short, and the two ways the figures are read again.
 */

import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CounterDashboard, SessionUser } from '../../shared/api/contract'
import { money } from '../../shared/format'
import { SAMPLE_DATA_TITLE } from '../../shared/sample-data-notice'
import { jsonResponse, mockApi, neverAnswers, problemResponse } from '../../test/api-mock'
import type { ApiMock, RouteTable } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import { RENTAL_ID, RENTAL_REFERENCE } from '../../test/counter-samples'
import {
  DASHBOARD,
  DASHBOARD_ROUTE,
  ODD_LATE_FEE,
  OVERDUE_REFERENCE,
  OVERDUE_RENTAL_ID,
  QUIET_DASHBOARD,
} from '../../test/overview-samples'
import { SCREEN_WAIT, findScreenHeading, renderApp } from '../../test/render-app'
import { REFERENCE } from '../../test/reservation-samples'
import { ADMIN, COUNTER_STAFF, signedInAs } from '../../test/session-samples'

const HEADING = 'Today at the counter'

async function openDashboard(routes: RouteTable, account: SessionUser = COUNTER_STAFF): Promise<ApiMock> {
  const network = mockApi({ ...signedInAs(account), ...routes })
  renderApp('/counter')
  await findScreenHeading(HEADING)
  return network
}

/** What one figure across the top says, found by its label. */
function figure(label: string): string {
  const tile = screen.getByText(label).closest('.card')
  if (!tile) throw new Error(`No figure is labelled ${label}.`)
  return tile.textContent ?? ''
}

function list(name: string): HTMLElement {
  return screen.getByRole('list', { name })
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('while the figures load', () => {
  it('draws a skeleton and says what it is waiting for', async () => {
    await openDashboard({ [DASHBOARD_ROUTE]: neverAnswers })

    expect(await screen.findByText('Loading today at Bellville', {}, SCREEN_WAIT)).toBeInTheDocument()
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull()
    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
  })
})

describe('when the figures cannot be read', () => {
  it('says so with the reference, and reads them again on a retry', async () => {
    const network = await openDashboard({
      [DASHBOARD_ROUTE]: () => problemResponse(500, { requestId: 'req-dashboard-1' }),
    })

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent("We could not load today's figures for Bellville")
    expect(within(alert).getByText('req-dashboard-1')).toBeVisible()

    network.setRoute(DASHBOARD_ROUTE, () => jsonResponse(DASHBOARD))
    await userEvent.setup().click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText('Out on hire')).toBeVisible()
  })
})

describe('a quiet day', () => {
  it('shows the figures and says nothing is due, with the way to the diary', async () => {
    await openDashboard({ [DASHBOARD_ROUTE]: () => jsonResponse(QUIET_DASHBOARD) })

    expect(await screen.findByText('Nothing is due at Bellville today', {}, SCREEN_WAIT)).toBeVisible()
    expect(figure('Collections due today')).toContain('0')
    expect(figure('Out on hire')).toContain('3')
    expect(figure('Overdue now')).toContain('Nothing is late')
    expect(screen.getByRole('link', { name: 'Open the diary' })).toHaveAttribute('href', '/counter/diary')
    expect(screen.queryByRole('list', { name: 'Collections due today' })).not.toBeInTheDocument()
  })
})

describe('a busy day', () => {
  it('asks for the branch the assistant works at and shows the five figures as the server counts them', async () => {
    const network = await openDashboard({ [DASHBOARD_ROUTE]: () => jsonResponse(DASHBOARD) })

    await screen.findByRole('list', { name: 'Collections due today' }, SCREEN_WAIT)
    expect(network.requestsTo(DASHBOARD_ROUTE)[0].query.get('branchCode')).toBe('BLV')
    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
    expect(screen.getByText(/^Bellville, 12 Mar 2026\. Read at 08:00\.$/)).toBeVisible()
    expect(figure('Collections due today')).toContain('1')
    expect(figure('Returns due today')).toContain('1')
    expect(figure('Overdue now')).toContain('Past the day they were due back')
    expect(figure('Out on hire')).toContain('14')
    expect(figure('Quarantined')).toContain('2')
    expect(figure('Quarantined')).toContain('Withdrawn from hire until inspected')
    expect(screen.queryByText(/reallocat/i)).not.toBeInTheDocument()
  })

  it('links each collection to its checkout and each return to the return of its hire', async () => {
    await openDashboard({ [DASHBOARD_ROUTE]: () => jsonResponse(DASHBOARD) })

    const going = await screen.findByRole('list', { name: 'Collections due today' }, SCREEN_WAIT)
    expect(within(going).getByText('2 x CP 100 Plate Compactor')).toBeVisible()
    expect(within(going).getByRole('link', { name: `Check out ${REFERENCE}` })).toHaveAttribute(
      'href',
      `/counter/checkout/${REFERENCE}`,
    )
    expect(within(list('Returns due today')).getByText('1 of 2 units still out')).toBeVisible()
    expect(within(list('Returns due today')).getByRole('link', { name: `Take the return ${RENTAL_REFERENCE}` })).toHaveAttribute(
      'href',
      `/counter/return/${RENTAL_ID}`,
    )
    expect(within(list('Overdue hires')).getByRole('link', { name: `Take the return ${OVERDUE_REFERENCE}` })).toHaveAttribute(
      'href',
      `/counter/return/${OVERDUE_RENTAL_ID}`,
    )
  })

  it('shows the days late and the late fee exactly as the server sent them', async () => {
    await openDashboard({ [DASHBOARD_ROUTE]: () => jsonResponse(DASHBOARD) })

    const late = await screen.findByRole('list', { name: 'Overdue hires' }, SCREEN_WAIT)
    expect(within(late).getByText('2 days late')).toBeVisible()
    expect(within(late).getByText(money(ODD_LATE_FEE))).toBeVisible()
    expect(within(late).getByText(/Was due back 10 Mar 2026, 1 unit still out/)).toBeVisible()
  })

  it('says so in words when one list is empty and another is not', async () => {
    const noReturns: CounterDashboard = { ...DASHBOARD, counts: { ...DASHBOARD.counts, returnsDue: 0 }, returnsDue: [] }
    await openDashboard({ [DASHBOARD_ROUTE]: () => jsonResponse(noReturns) })

    expect(await screen.findByText('Nothing is due back today.', {}, SCREEN_WAIT)).toBeVisible()
    expect(list('Collections due today')).toBeVisible()
  })

  it('says how many it shows when the server cut a list short', async () => {
    const busy: CounterDashboard = { ...DASHBOARD, counts: { ...DASHBOARD.counts, collectionsDue: 63 } }
    await openDashboard({ [DASHBOARD_ROUTE]: () => jsonResponse(busy) })

    expect(await screen.findByText('Showing the first 1 of 63.', {}, SCREEN_WAIT)).toBeVisible()
  })
})

describe('reading the figures again', () => {
  it('reads them again on the refresh button', async () => {
    const network = await openDashboard({ [DASHBOARD_ROUTE]: () => jsonResponse(DASHBOARD) })
    await screen.findByRole('list', { name: 'Collections due today' }, SCREEN_WAIT)

    network.setRoute(DASHBOARD_ROUTE, () =>
      jsonResponse({ ...DASHBOARD, counts: { ...DASHBOARD.counts, onHire: 15 } }),
    )
    await userEvent.setup().click(screen.getByRole('button', { name: 'Refresh' }))

    await waitFor(() => expect(figure('Out on hire')).toContain('15'))
    expect(network.requestsTo(DASHBOARD_ROUTE)).toHaveLength(2)
  })

  it('reads them again when the window comes back into focus', async () => {
    const network = await openDashboard({ [DASHBOARD_ROUTE]: () => jsonResponse(DASHBOARD) })
    await screen.findByRole('list', { name: 'Collections due today' }, SCREEN_WAIT)
    expect(network.requestsTo(DASHBOARD_ROUTE)).toHaveLength(1)

    fireEvent(window, new Event('visibilitychange'))

    await waitFor(() => expect(network.requestsTo(DASHBOARD_ROUTE)).toHaveLength(2))
  })
})

describe('an administrator', () => {
  it('chooses a branch first, and the figures are asked for that branch', async () => {
    const network = await openDashboard({ [DASHBOARD_ROUTE]: () => jsonResponse(DASHBOARD) }, ADMIN)

    await userEvent.setup().click(await screen.findByRole('button', { name: /Cape Town CBD/ }, SCREEN_WAIT))

    await screen.findByRole('list', { name: 'Collections due today' }, SCREEN_WAIT)
    expect(network.requestsTo(DASHBOARD_ROUTE)[0].query.get('branchCode')).toBe('CBD')
  })
})
