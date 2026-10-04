/**
 * Tests for the audit trail on SC-24, with the network replaced at `fetch`.
 *
 * The trail is one paged read. Waiting, failed, empty and loaded, the words an
 * event is written in, the filters in the address and in the query, the two
 * ways an event narrows the trail, a refusal under its filter, paging, and the
 * move to the notification log.
 */

import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SAMPLE_DATA_TITLE } from '../../shared/sample-data-notice'
import { jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import { AUDIT_ROUTE, CONFIRMED_EVENT, SWEEP_EVENT, auditPage } from '../../test/audit-samples'
import { TEST_NOW } from '../../test/catalogue-samples'
import { SCREEN_WAIT, currentAddress } from '../../test/render-app'
import { RESERVATION_ID } from '../../test/reservation-samples'
import { ADMIN } from '../../test/session-samples'
import { findEvents, lastAsked, openLog } from './SC24-test-kit'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

function event(name: RegExp | string): HTMLElement {
  return screen.getByRole('article', { name })
}

describe('while the trail loads', () => {
  it('draws a skeleton and shows no sample data notice', async () => {
    await openLog({ [AUDIT_ROUTE]: neverAnswers })

    expect(await screen.findByText('Loading the events.', {}, SCREEN_WAIT)).toBeInTheDocument()
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull()
    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
  })
})

describe('when the trail cannot be read', () => {
  it('says so with the reference, and reads it again on a retry', async () => {
    const { user, network } = await openLog({ [AUDIT_ROUTE]: () => problemResponse(500, { requestId: 'req-trail-1' }) })

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('We could not load the audit trail')
    expect(within(alert).getByText('req-trail-1')).toBeVisible()

    network.setRoute(AUDIT_ROUTE, () => jsonResponse(auditPage([CONFIRMED_EVENT])))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await findEvents()).toBeVisible()
  })
})

describe('a loaded trail', () => {
  it('asks for the first page, newest first, and says nobody can change it', async () => {
    const { network } = await openLog()
    await findEvents()

    expect(lastAsked(network, AUDIT_ROUTE).toString()).toBe('page=1&pageSize=20')
    expect(screen.getByText('2 events match, newest first.')).toBeVisible()
    expect(screen.getByText('Nobody can change this record')).toBeVisible()
    expect(screen.queryByRole('button', { name: /edit|delete|remove/i })).not.toBeInTheDocument()
    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
  })

  it('says when, who and in what role, and what happened in words', async () => {
    await openLog()
    await findEvents()

    const confirmed = event('Reservation confirmed')
    expect(within(confirmed).getByText('12 Mar 2026 at 07:45')).toBeVisible()
    expect(within(confirmed).getByText(`By ${ADMIN.fullName}, administrator.`)).toBeVisible()
    expect(within(confirmed).getByText(/^Booking/)).toHaveTextContent(`Booking ${RESERVATION_ID}`)

    const swept = event('Hire became overdue')
    expect(within(swept).getByText('By the system, with no person behind it.')).toBeVisible()
    expect(within(swept).queryByRole('button', { name: /^Only what/ })).not.toBeInTheDocument()
  })

  it('lists the fields that changed in words, and never as raw JSON', async () => {
    await openLog()
    await findEvents()

    const list = within(event('Reservation confirmed')).getByLabelText('What changed')
    expect(within(list).getByText('Status')).toBeVisible()
    expect(within(list).getByText('Was held. Now confirmed.')).toBeVisible()
    expect(within(list).getByText('Was 12 Mar 2026 at 08:15. Now nothing.')).toBeVisible()
    expect(within(list).getByText('Asset tags')).toBeVisible()
    expect(within(list).getByText('Set to TSH-PC-0007, TSH-PC-0011.')).toBeVisible()
    const swept = within(event('Hire became overdue')).getByLabelText('What changed')
    expect(within(swept).getByText('Set to held 5555.55; withheld 0.00.')).toBeVisible()
    expect(document.body.textContent).not.toMatch(/[{[]"/)
  })

  it('says so when nothing was recorded', async () => {
    await openLog({ [AUDIT_ROUTE]: () => jsonResponse(auditPage([])) })

    expect(await screen.findByText('Nothing was recorded that matches', {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByText('Nothing has been recorded yet.')).toBeVisible()
  })
})

describe('the filters', () => {
  it('apply together, live in the address and are sent under the names the API takes', async () => {
    const { user, network } = await openLog()
    await findEvents()

    await user.selectOptions(screen.getByLabelText('Kind of record'), 'reservation')
    await user.type(screen.getByLabelText('Record key'), ` ${RESERVATION_ID} `)
    await user.type(screen.getByLabelText('Action'), 'reservation.confirmed')
    await user.type(screen.getByLabelText('From'), '2026-03-01')
    await user.type(screen.getByLabelText('To'), '2026-03-12')
    expect(network.requestsTo(AUDIT_ROUTE)).toHaveLength(1)

    await user.click(screen.getByRole('button', { name: 'Show these events' }))

    await waitFor(() => expect(network.requestsTo(AUDIT_ROUTE)).toHaveLength(2))
    expect(lastAsked(network, AUDIT_ROUTE).toString()).toBe(
      `entityType=reservation&entityId=${RESERVATION_ID}&action=reservation.confirmed&from=2026-03-01&to=2026-03-12&page=1&pageSize=20`,
    )
    expect(currentAddress()).toBe(
      `/admin/audit?entityType=reservation&entityId=${RESERVATION_ID}&action=reservation.confirmed&from=2026-03-01&to=2026-03-12`,
    )
  })

  it('send a record only by its key, and say so under the box when given a reference', async () => {
    const { user, network } = await openLog()
    await findEvents()
    const box = screen.getByLabelText('Record key')

    await user.type(box, 'TSH-R-26-000124')
    await user.click(screen.getByRole('button', { name: 'Show these events' }))

    expect(box).toHaveAccessibleDescription(/A booking or hire reference is not a key\./)
    expect(box).toHaveFocus()
    expect(network.requestsTo(AUDIT_ROUTE)).toHaveLength(1)
    expect(currentAddress()).toBe('/admin/audit')

    await user.clear(box)
    expect(box).not.toHaveAccessibleDescription(/is not a key/)
  })

  it('offer every kind of record the backend writes, and nothing it never writes', async () => {
    await openLog()
    await findEvents()

    const kinds = within(screen.getByLabelText('Kind of record')).getAllByRole('option').map((option) => option.getAttribute('value'))
    expect(kinds).toEqual([
      '',
      'reservation',
      'rental',
      'charge',
      'notification',
      'asset',
      'damage_report',
      'customer_profile',
      'user_account',
    ])
  })

  it('are read from the address, so a reload shows the same events', async () => {
    const { network } = await openLog({}, '/admin/audit?entityType=reservation&page=2')
    await findEvents()

    expect(lastAsked(network, AUDIT_ROUTE).toString()).toBe('entityType=reservation&page=2&pageSize=20')
    expect(screen.getByLabelText('Kind of record')).toHaveValue('reservation')
  })

  it('narrow to one record, or to one person, from an event', async () => {
    const { user, network } = await openLog()
    await findEvents()

    await user.click(within(event('Reservation confirmed')).getByRole('button', { name: /^Only this booking/ }))
    await waitFor(() => expect(lastAsked(network, AUDIT_ROUTE).get('entityId')).toBe(RESERVATION_ID))
    expect(lastAsked(network, AUDIT_ROUTE).get('entityType')).toBe('reservation')
    expect(screen.getByLabelText('Record key')).toHaveValue(RESERVATION_ID)

    await user.click(await screen.findByRole('button', { name: `Only what ${ADMIN.fullName} did` }, SCREEN_WAIT))
    await waitFor(() => expect(lastAsked(network, AUDIT_ROUTE).get('actorUserId')).toBe(ADMIN.id))
    expect(await screen.findByText(`Only what ${ADMIN.fullName} did.`, {}, SCREEN_WAIT)).toBeVisible()

    await user.click(screen.getByRole('button', { name: 'Show everybody' }))
    await waitFor(() => expect(lastAsked(network, AUDIT_ROUTE).has('actorUserId')).toBe(false))
    expect(currentAddress()).toBe(`/admin/audit?entityType=reservation&entityId=${RESERVATION_ID}`)
  })

  it('put a refusal under the filter it names, and list one with no filter of its own', async () => {
    const refused = problemResponse(422, {
      errors: { fields: { 'query.to': 'The end of the range is before its start.', 'query.actorUserId': 'Not an account key.' } },
    })
    await openLog({ [AUDIT_ROUTE]: () => refused }, '/admin/audit?from=2026-03-12&to=2026-03-01&actorUserId=nobody')

    expect(await screen.findByText('The trail cannot be read with those filters', {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByLabelText('To')).toHaveAccessibleDescription(/The end of the range is before its start\./)
    expect(screen.getByText('Not an account key.')).toBeVisible()
  })

  it('clear back to the whole trail', async () => {
    const { user, network } = await openLog({ [AUDIT_ROUTE]: () => jsonResponse(auditPage([])) }, '/admin/audit?action=nothing.here')
    await screen.findByText('Nothing was recorded that matches', {}, SCREEN_WAIT)

    await user.click(within(screen.getByRole('region', { name: 'The events' })).getByRole('button', { name: 'Clear the filters' }))

    await waitFor(() => expect(currentAddress()).toBe('/admin/audit'))
    expect(lastAsked(network, AUDIT_ROUTE).toString()).toBe('page=1&pageSize=20')
  })
})

describe('paging', () => {
  it('asks for the next page, keeps it in the address and moves focus to the events', async () => {
    const { user, network } = await openLog({ [AUDIT_ROUTE]: () => jsonResponse(auditPage([CONFIRMED_EVENT], { total: 45 })) })
    await findEvents()

    await user.click(screen.getByRole('button', { name: 'Next' }))

    await waitFor(() => expect(lastAsked(network, AUDIT_ROUTE).get('page')).toBe('2'))
    expect(currentAddress()).toBe('/admin/audit?page=2')
    expect(screen.getByRole('region', { name: 'The events' })).toHaveFocus()
  })

  it('offers the first page when the address is past the end', async () => {
    await openLog({ [AUDIT_ROUTE]: () => jsonResponse(auditPage([], { page: 9, total: 3 })) }, '/admin/audit?page=9')

    expect(await screen.findByText('That page is past the end of the trail', {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByRole('button', { name: 'Go to the first page' })).toBeVisible()
  })
})

describe('the two parts of the log', () => {
  it('marks the trail as current, and moves to the notification log with focus on its heading', async () => {
    const { user } = await openLog()
    await findEvents()
    const parts = screen.getByRole('navigation', { name: 'Parts of the log' })
    expect(within(parts).getByRole('link', { name: 'Audit trail' })).toHaveAttribute('aria-current', 'page')

    await user.click(within(parts).getByRole('link', { name: 'Notification log' }))

    expect(currentAddress()).toBe('/admin/audit?view=notifications')
    await waitFor(() => expect(screen.getByRole('heading', { level: 2, name: 'Notification log' })).toHaveFocus())
    expect(within(parts).getByRole('link', { name: 'Notification log' })).toHaveAttribute('aria-current', 'page')
  })

  it('keeps the system event apart from the person, with no way to narrow to nobody', async () => {
    await openLog({ [AUDIT_ROUTE]: () => jsonResponse(auditPage([SWEEP_EVENT])) })
    await findEvents()

    expect(screen.queryAllByRole('button', { name: /^Only what/ })).toHaveLength(0)
    expect(screen.getByRole('button', { name: /^Only this hire/ })).toBeVisible()
  })
})
