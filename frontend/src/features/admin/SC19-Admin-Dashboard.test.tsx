/**
 * Tests for SC-19 Admin Dashboard, with the network replaced at `fetch`.
 *
 * The dashboard is one request for the whole business. Each test says how
 * that route answers and reads the page. Waiting, failed, loaded, the links
 * each figure carries, a branch's way into its diary, and the two ways the
 * figures are read again.
 */

import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AdminDashboard } from '../../shared/api/contract'
import { money, percent } from '../../shared/format'
import { SAMPLE_DATA_TITLE } from '../../shared/sample-data-notice'
import { jsonResponse, mockApi, neverAnswers, problemResponse } from '../../test/api-mock'
import type { ApiMock, RouteTable } from '../../test/api-mock'
import { TEST_NOW, TEST_TODAY } from '../../test/catalogue-samples'
import { DIARY_ROUTE, diaryOf, emptyDay } from '../../test/overview-samples'
import { SCREEN_WAIT, currentAddress, findScreenHeading, renderApp } from '../../test/render-app'
import { ADMIN_DASHBOARD_ROUTE, DASHBOARD } from '../../test/report-samples'
import { ADMIN, signedInAs } from '../../test/session-samples'

const HEADING = 'Business overview'

async function openDashboard(routes: RouteTable): Promise<ApiMock> {
  const network = mockApi({ ...signedInAs(ADMIN), ...routes })
  renderApp('/admin')
  await findScreenHeading(HEADING)
  return network
}

/** Wait for the loaded overview. */
function loaded(): Promise<HTMLElement> {
  return screen.findByRole('heading', { level: 2, name: 'Branch by branch' }, SCREEN_WAIT)
}

/** What one tile across the business today says, found by its label. */
function figure(label: string): string {
  const today = screen.getByRole('region', { name: 'Across the business today' })
  const tile = within(today).getByText(label, { exact: true }).closest('.card')
  if (!tile) throw new Error(`No figure is labelled ${label}.`)
  return tile.textContent ?? ''
}

function branchCard(name: string): HTMLElement {
  return screen.getByRole('article', { name })
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('while the figures load', () => {
  it('draws a skeleton and says what it is waiting for, with no sample data notice', async () => {
    await openDashboard({ [ADMIN_DASHBOARD_ROUTE]: neverAnswers })

    expect(await screen.findByText('Loading the business overview', {}, SCREEN_WAIT)).toBeInTheDocument()
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull()
    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
  })
})

describe('when the figures cannot be read', () => {
  it('says so with the reference, and reads them again on a retry', async () => {
    const network = await openDashboard({
      [ADMIN_DASHBOARD_ROUTE]: () => problemResponse(500, { requestId: 'req-overview-1' }),
    })

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('We could not load the business overview')
    expect(within(alert).getByText('req-overview-1')).toBeVisible()

    network.setRoute(ADMIN_DASHBOARD_ROUTE, () => jsonResponse(DASHBOARD))
    await userEvent.setup().click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await loaded()).toBeVisible()
  })
})

describe('the business today', () => {
  it('asks once and shows the totals the server sent, not a sum of the branches', async () => {
    const network = await openDashboard({ [ADMIN_DASHBOARD_ROUTE]: () => jsonResponse(DASHBOARD) })
    await loaded()

    expect(network.requestsTo(ADMIN_DASHBOARD_ROUTE)).toHaveLength(1)
    expect(screen.getByText(/^Every branch, 12 Mar 2026\. Read at 08:00\.$/)).toBeVisible()
    expect(figure('Collections due today')).toContain('5')
    expect(figure('Out on hire')).toContain('31')
    expect(figure('On the shelf')).toContain('351')
    expect(figure('Overdue now')).toContain('Past the day they were due back')
    expect(figure('Quarantined')).toContain('3')
    expect(figure('In the workshop')).toContain('1')
  })

  it('shows each branch with what is due today and where its fleet stands', async () => {
    await openDashboard({ [ADMIN_DASHBOARD_ROUTE]: () => jsonResponse(DASHBOARD) })
    await loaded()

    expect(screen.getAllByRole('article')).toHaveLength(3)
    const cbd = branchCard('Cape Town CBD')
    expect(within(cbd).getByText('2 collections, 1 return, 1 overdue')).toBeVisible()
    const fleet = within(cbd).getByText('On the shelf').closest('div')
    expect(fleet).toHaveTextContent('120')
    expect(within(branchCard('Bellville')).getByText('1 collection, 0 returns, 0 overdue')).toBeVisible()
  })

  it('shows the month so far as the server sent it, and links it to the report for the same period', async () => {
    await openDashboard({ [ADMIN_DASHBOARD_ROUTE]: () => jsonResponse(DASHBOARD) })
    await loaded()

    const month = screen.getByRole('region', { name: 'This month so far' })
    const links = within(month).getAllByRole('link')
    expect(links[0]).toHaveTextContent(percent('12.40'))
    expect(links[1]).toHaveTextContent(money('23456.78'))
    expect(links[1]).toHaveTextContent('Gross contribution this month')
    for (const link of links) {
      expect(link).toHaveAttribute('href', '/admin/reports?from=2026-03-01&to=2026-03-13&groupBy=model')
    }
  })

  it('links what waits on the owner to the screens where it is dealt with', async () => {
    await openDashboard({ [ADMIN_DASHBOARD_ROUTE]: () => jsonResponse(DASHBOARD) })
    await loaded()

    const waiting = screen.getByRole('region', { name: 'Waiting on you' })
    expect(within(waiting).getByRole('link', { name: /Open damage reports 3/ })).toHaveAttribute('href', '/admin/assets')
    expect(within(waiting).getByRole('link', { name: /Customers on hold 1/ })).toHaveAttribute('href', '/admin/users?view=customers&status=ON_HOLD')
    expect(within(waiting).getByRole('link', { name: /Failed notifications 0/ })).toHaveAttribute('href', '/admin/audit?view=notifications&status=FAILED')
    expect(within(waiting).getByText('Every email went out')).toBeVisible()
  })

  it('says in words when the month had no serviceable days and its contribution is below zero', async () => {
    const lean: AdminDashboard = {
      ...DASHBOARD,
      monthToDate: { ...DASHBOARD.monthToDate, utilisationPercent: null, grossContribution: '-310.50' },
    }
    await openDashboard({ [ADMIN_DASHBOARD_ROUTE]: () => jsonResponse(lean) })
    await loaded()

    const month = screen.getByRole('region', { name: 'This month so far' })
    expect(within(month).getByText('No serviceable days')).toBeVisible()
    expect(within(month).getByText(/^Below zero\./)).toBeVisible()
    expect(within(month).queryByText(/profit/i)).toHaveTextContent(/not profit/i)
  })

  it('says so when the server lists no branch', async () => {
    await openDashboard({ [ADMIN_DASHBOARD_ROUTE]: () => jsonResponse({ ...DASHBOARD, branches: [] }) })

    expect(await screen.findByText('No branch is listed', {}, SCREEN_WAIT)).toBeVisible()
  })
})

describe("a branch's diary", () => {
  it('chooses the branch for the tab and opens its diary on it', async () => {
    const network = await openDashboard({
      [ADMIN_DASHBOARD_ROUTE]: () => jsonResponse(DASHBOARD),
      [DIARY_ROUTE]: () => jsonResponse(diaryOf([emptyDay(TEST_TODAY)])),
    })
    await loaded()

    await userEvent.setup().click(screen.getByRole('link', { name: /Open the diary at Bellville/ }))

    await findScreenHeading('Branch diary')
    expect(currentAddress()).toBe('/counter/diary')
    await waitFor(() => expect(network.requestsTo(DIARY_ROUTE).length).toBeGreaterThan(0))
    expect(network.requestsTo(DIARY_ROUTE)[0].query.get('branchCode')).toBe('BLV')
  })
})

describe('reading the figures again', () => {
  it('reads them again on the refresh button', async () => {
    const network = await openDashboard({ [ADMIN_DASHBOARD_ROUTE]: () => jsonResponse(DASHBOARD) })
    await loaded()

    network.setRoute(ADMIN_DASHBOARD_ROUTE, () =>
      jsonResponse({ ...DASHBOARD, totals: { ...DASHBOARD.totals, onHire: 32 } }),
    )
    await userEvent.setup().click(screen.getByRole('button', { name: 'Refresh' }))

    await waitFor(() => expect(figure('Out on hire')).toContain('32'))
    expect(network.requestsTo(ADMIN_DASHBOARD_ROUTE)).toHaveLength(2)
  })

  it('reads them again when the window comes back into focus', async () => {
    const network = await openDashboard({ [ADMIN_DASHBOARD_ROUTE]: () => jsonResponse(DASHBOARD) })
    await loaded()
    expect(network.requestsTo(ADMIN_DASHBOARD_ROUTE)).toHaveLength(1)

    fireEvent(window, new Event('visibilitychange'))

    await waitFor(() => expect(network.requestsTo(ADMIN_DASHBOARD_ROUTE)).toHaveLength(2))
  })
})
