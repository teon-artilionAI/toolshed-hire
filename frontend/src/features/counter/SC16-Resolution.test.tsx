/**
 * Tests for the owner's moves on SC-16, with the network replaced at `fetch`.
 *
 * Each open report offers "Send for repair" and "Resolve" to a signed in
 * administrator and to nobody else. Counter staff see the status and a
 * sentence that the owner resolves reports. Resolving asks for the outcome,
 * says what happens to the unit, and sends exactly the body the contract names
 * for each outcome. The server's answer replaces the report at once and a
 * notice that takes focus says what the move did.
 */

import { screen, waitFor, within } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { DamageReport, SessionUser } from '../../shared/api/contract'
import { jsonResponse, problemResponse } from '../../test/api-mock'
import type { ApiMock, RouteHandler, RouteTable } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import {
  DAMAGE_REPORTS_ROUTE,
  EARLIER_REPORT,
  QUARANTINED_AT_BELLVILLE,
  RESOLVED_REPORT,
  repairRoute,
  reportPage,
  resolutionRoute,
} from '../../test/damage-samples'
import { SCREEN_WAIT } from '../../test/render-app'
import { ADMIN, COUNTER_STAFF } from '../../test/session-samples'
import { OWNER_RESOLVES } from './SC16-Report-Entry'
import { openDamage, unitWith } from './SC16-test-kit'

const AT = `/counter/damage/${QUARANTINED_AT_BELLVILLE.assetTag}`

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

/** Open the unit with the earlier report on it, open, and these writes answering. */
async function openReports(account: SessionUser, routes: RouteTable = {}) {
  const opened = await openDamage(unitWith(QUARANTINED_AT_BELLVILLE, [EARLIER_REPORT, RESOLVED_REPORT], routes), AT, account)
  const entry = await screen.findByRole('article', { name: EARLIER_REPORT.reference }, SCREEN_WAIT)
  return { ...opened, entry }
}

/** Open the resolution form of the open report. */
async function startResolving(user: UserEvent, entry: HTMLElement): Promise<HTMLElement> {
  await user.click(within(entry).getByRole('button', { name: `Resolve ${EARLIER_REPORT.reference}` }))
  const form = within(entry).getByRole('form', { name: `Resolve ${EARLIER_REPORT.reference}` })
  expect(within(form).getByRole('heading', { name: `Resolve ${EARLIER_REPORT.reference}` })).toHaveFocus()
  return form
}

function answered(changes: Partial<DamageReport>): RouteHandler {
  return () => jsonResponse({ ...EARLIER_REPORT, ...changes })
}

/** The reports of the unit once the server has moved the open one on, which is
 *  what the list answers when the screen reads it again after the move. */
function listAfter(network: ApiMock, changes: Partial<DamageReport>): void {
  network.setRoute(DAMAGE_REPORTS_ROUTE, () => jsonResponse(reportPage([{ ...EARLIER_REPORT, ...changes }, RESOLVED_REPORT])))
}

describe('who sees the owner moves', () => {
  it('shows a signed in administrator both moves on an open report, and none on a closed one', async () => {
    await openReports(ADMIN)

    const open = screen.getByRole('article', { name: EARLIER_REPORT.reference })
    expect(within(open).getByRole('button', { name: `Send for repair ${EARLIER_REPORT.reference}` })).toBeVisible()
    expect(within(open).getByRole('button', { name: `Resolve ${EARLIER_REPORT.reference}` })).toBeVisible()
    const closed = screen.getByRole('article', { name: RESOLVED_REPORT.reference })
    expect(within(closed).queryAllByRole('button')).toHaveLength(0)
  })

  it('shows counter staff the status and that the owner resolves reports, with nothing to press', async () => {
    const { entry } = await openReports(COUNTER_STAFF)

    expect(within(entry).getByText('Open, unit in quarantine')).toBeVisible()
    expect(within(entry).getByText(OWNER_RESOLVES)).toBeVisible()
    expect(within(entry).queryAllByRole('button')).toHaveLength(0)
  })
})

describe('sending a report for repair', () => {
  it('sends one request with no body, and shows the report in the workshop', async () => {
    const { user, network, entry } = await openReports(ADMIN, {
      [repairRoute(EARLIER_REPORT.id)]: answered({ status: 'UNDER_REPAIR' }),
    })
    listAfter(network, { status: 'UNDER_REPAIR' })

    await user.click(within(entry).getByRole('button', { name: `Send for repair ${EARLIER_REPORT.reference}` }))

    const said = await screen.findByText(`${EARLIER_REPORT.reference} is sent for repair`, {}, SCREEN_WAIT)
    await waitFor(() => expect(said.closest('[tabindex="-1"]')).toHaveFocus())
    expect(network.requestsTo(repairRoute(EARLIER_REPORT.id))).toHaveLength(1)
    expect(network.requestsTo(repairRoute(EARLIER_REPORT.id))[0].body).toBeUndefined()
    const entryNow = screen.getByRole('article', { name: EARLIER_REPORT.reference })
    expect(within(entryNow).getByText('In the workshop')).toBeVisible()
    expect(within(entryNow).queryByRole('button', { name: /^Send for repair/ })).not.toBeInTheDocument()
    expect(within(entryNow).getByRole('button', { name: `Resolve ${EARLIER_REPORT.reference}` })).toBeVisible()
  })

  it('shows the server sentence when the report is no longer open', async () => {
    const detail = 'TSH-D-26-00012 is already under repair.'
    const { user, entry } = await openReports(ADMIN, {
      [repairRoute(EARLIER_REPORT.id)]: () => problemResponse(409, { detail }),
    })

    await user.click(within(entry).getByRole('button', { name: `Send for repair ${EARLIER_REPORT.reference}` }))

    const alert = await within(entry).findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('The report was not sent for repair')
    expect(alert).toHaveTextContent(detail)
  })
})

describe('resolving a report', () => {
  it('needs an outcome and, for a repair, the cost, and says what happens to the unit', async () => {
    const { user, network, entry } = await openReports(ADMIN)
    const form = await startResolving(user, entry)
    expect(within(form).getAllByRole('radio').filter((radio) => (radio as HTMLInputElement).checked)).toHaveLength(0)

    await user.click(within(form).getByRole('button', { name: 'Resolve the report' }))
    expect(within(form).getByRole('alert')).toHaveTextContent('1 answer needs fixing.')

    await user.click(within(form).getByRole('radio', { name: /^Repaired/ }))
    expect(within(form).getByText(/^TSH-PC-0007 goes back on the shelf and can be booked again/)).toBeVisible()
    await user.click(within(form).getByRole('button', { name: 'Resolve as repaired' }))

    expect(within(form).getByLabelText('Actual repair cost, in rand')).toHaveAccessibleDescription(/Enter what the repair actually cost/)
    expect(network.requestsTo(resolutionRoute(EARLIER_REPORT.id))).toHaveLength(0)
  })

  it('sends a repair with its cost and notes, and shows the report resolved', async () => {
    const resolved: Partial<DamageReport> = {
      status: 'RESOLVED',
      actualRepairCost: '380.00',
      resolvedAt: '2026-03-12T09:00:00+02:00',
      resolutionNotes: 'New grip fitted.',
    }
    const { user, network, entry } = await openReports(ADMIN, { [resolutionRoute(EARLIER_REPORT.id)]: answered(resolved) })
    listAfter(network, resolved)
    const form = await startResolving(user, entry)
    await user.click(within(form).getByRole('radio', { name: /^Repaired/ }))
    await user.type(within(form).getByLabelText('Actual repair cost, in rand'), '380')
    await user.type(within(form).getByLabelText('Notes'), '  New grip fitted. ')

    await user.click(within(form).getByRole('button', { name: 'Resolve as repaired' }))

    expect(await screen.findByText(`${EARLIER_REPORT.reference} is resolved`, {}, SCREEN_WAIT)).toBeVisible()
    expect(network.requestsTo(resolutionRoute(EARLIER_REPORT.id))[0].body).toEqual({
      outcome: 'RESOLVED',
      actualRepairCost: '380.00',
      resolutionNotes: 'New grip fitted.',
    })
    const entryNow = screen.getByRole('article', { name: EARLIER_REPORT.reference })
    expect(within(entryNow).getByText('Resolved, repaired')).toBeVisible()
    expect(within(entryNow).queryAllByRole('button')).toHaveLength(0)
  })

  it('sends a write off with no cost and no notes, and says the unit leaves the fleet', async () => {
    const { user, network, entry } = await openReports(ADMIN, {
      [resolutionRoute(EARLIER_REPORT.id)]: answered({ status: 'WRITTEN_OFF', resolvedAt: '2026-03-12T09:00:00+02:00' }),
    })
    const form = await startResolving(user, entry)
    await user.click(within(form).getByRole('radio', { name: /^Written off/ }))
    expect(within(form).getByText(/^TSH-PC-0007 is retired from the fleet today and can never be hired again/)).toBeVisible()

    await user.click(within(form).getByRole('button', { name: 'Write the unit off' }))

    expect(await screen.findByText(`${EARLIER_REPORT.reference} is written off`, {}, SCREEN_WAIT)).toBeVisible()
    expect(network.requestsTo(resolutionRoute(EARLIER_REPORT.id))[0].body).toEqual({
      outcome: 'WRITTEN_OFF',
      actualRepairCost: null,
      resolutionNotes: null,
    })
  })

  it('shows the server sentence when a write off is refused while the unit is booked', async () => {
    const detail = 'TSH-PC-0007 is set aside for a booking, so it cannot be written off.'
    const { user, entry } = await openReports(ADMIN, {
      [resolutionRoute(EARLIER_REPORT.id)]: () => problemResponse(409, { detail }),
    })
    const form = await startResolving(user, entry)
    await user.click(within(form).getByRole('radio', { name: /^Written off/ }))

    await user.click(within(form).getByRole('button', { name: 'Write the unit off' }))

    const alert = await within(form).findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('The report was not resolved')
    expect(alert).toHaveTextContent(detail)
  })

  it('puts a refused cost under the cost', async () => {
    const { user, entry } = await openReports(ADMIN, {
      [resolutionRoute(EARLIER_REPORT.id)]: () =>
        problemResponse(422, { errors: { fields: { 'body.actual_repair_cost': 'A repair cost cannot be less than R0.00.' } } }),
    })
    const form = await startResolving(user, entry)
    await user.click(within(form).getByRole('radio', { name: /^Repaired/ }))
    await user.type(within(form).getByLabelText('Actual repair cost, in rand'), '0')

    await user.click(within(form).getByRole('button', { name: 'Resolve as repaired' }))

    await waitFor(() =>
      expect(within(form).getByLabelText('Actual repair cost, in rand')).toHaveAccessibleDescription(/cannot be less than R0\.00/),
    )
  })
})
