/**
 * Tests for the notification log on SC-24, with the network replaced at
 * `fetch`.
 *
 * The log is one paged read with a status filter. Waiting, failed, empty and
 * loaded, the filter in the address and in the query, paging, and sending a
 * failed confirmation again. That asks first, posts once, shows the new
 * attempt and reads the log again, and shows the server's sentence on a 409
 * or a 403.
 */

import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createdResponse, jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import {
  FAILED_EMAIL,
  NOTIFICATIONS_ROUTE,
  RESENT_EMAIL,
  SENT_EMAIL,
  emailPage,
  resendRoute,
} from '../../test/audit-samples'
import { TEST_NOW } from '../../test/catalogue-samples'
import { SCREEN_WAIT, currentAddress } from '../../test/render-app'
import { findEmails, lastAsked, openLog } from './SC24-test-kit'

const LOG = '/admin/audit?view=notifications'
const FAILED_TITLE = `Booking confirmation for ${FAILED_EMAIL.reservationReference}`
const SEND_AGAIN = `Send again the booking confirmation for ${FAILED_EMAIL.reservationReference}`

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

function email(name: string): HTMLElement {
  return screen.getByRole('article', { name })
}

describe('reading the log', () => {
  it('draws a skeleton while it loads', async () => {
    await openLog({ [NOTIFICATIONS_ROUTE]: neverAnswers }, LOG)

    expect(await screen.findByText('Loading the emails.', {}, SCREEN_WAIT)).toBeInTheDocument()
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull()
  })

  it('says so with the reference when it cannot be read, and reads it again on a retry', async () => {
    const { user, network } = await openLog({ [NOTIFICATIONS_ROUTE]: () => problemResponse(500, { requestId: 'req-log-1' }) }, LOG)

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('We could not load the notification log')
    expect(within(alert).getByText('req-log-1')).toBeVisible()

    network.setRoute(NOTIFICATIONS_ROUTE, () => jsonResponse(emailPage([SENT_EMAIL])))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))
    expect(await findEmails()).toBeVisible()
  })

  it('shows each email with where it stands in words, and what went wrong with a failed one', async () => {
    const { network } = await openLog({}, LOG)
    await findEmails()

    expect(lastAsked(network, NOTIFICATIONS_ROUTE).toString()).toBe('page=1&pageSize=20')
    expect(screen.getByText('2 emails, newest first.')).toBeVisible()
    const failed = email(FAILED_TITLE)
    expect(within(failed).getByText('Did not go out', { selector: '.pill' })).toBeVisible()
    expect(within(failed).getByText(FAILED_EMAIL.lastError ?? '')).toBeVisible()
    expect(within(failed).getByText(FAILED_EMAIL.recipientEmail)).toBeVisible()
    expect(within(failed).getByRole('button', { name: SEND_AGAIN })).toBeVisible()

    const sent = email(`Booking confirmation for ${SENT_EMAIL.reservationReference}`)
    expect(within(sent).getByText('Sent', { selector: '.pill' })).toBeVisible()
    expect(within(sent).getByText('11 Mar 2026 at 16:02')).toBeVisible()
    expect(within(sent).queryByRole('button')).not.toBeInTheDocument()
  })

  it('says which failed email a re-send sends again', async () => {
    await openLog({ [NOTIFICATIONS_ROUTE]: () => jsonResponse(emailPage([RESENT_EMAIL, FAILED_EMAIL])) }, LOG)
    await findEmails()

    expect(screen.getByText('This sends again the email queued 11 Mar 2026 at 15:30, which did not go out.')).toBeVisible()
    expect(within(screen.getAllByRole('article')[0]).getByText('Waiting to be sent', { selector: '.pill' })).toBeVisible()
  })

  it('says so when nothing matches, and offers every email', async () => {
    const { user, network } = await openLog({ [NOTIFICATIONS_ROUTE]: () => jsonResponse(emailPage([])) }, `${LOG}&status=FAILED`)

    expect(await screen.findByText('No email matches', {}, SCREEN_WAIT)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Show every email' }))

    await waitFor(() => expect(currentAddress()).toBe(LOG))
    expect(lastAsked(network, NOTIFICATIONS_ROUTE).has('status')).toBe(false)
  })
})

describe('the status filter and the pages', () => {
  it('asks for one status as it is chosen and keeps it in the address', async () => {
    const { user, network } = await openLog({}, LOG)
    await findEmails()

    await user.selectOptions(screen.getByLabelText('Which emails'), 'FAILED')

    await waitFor(() => expect(lastAsked(network, NOTIFICATIONS_ROUTE).get('status')).toBe('FAILED'))
    expect(currentAddress()).toBe(`${LOG}&status=FAILED`)
  })

  it('opens on the failed emails from the link on the dashboard', async () => {
    const { network } = await openLog({}, `${LOG}&status=FAILED`)
    await findEmails()

    expect(lastAsked(network, NOTIFICATIONS_ROUTE).toString()).toBe('status=FAILED&page=1&pageSize=20')
    expect(screen.getByLabelText('Which emails')).toHaveValue('FAILED')
    expect(screen.getByText('2 emails that did not go out, newest first.')).toBeVisible()
  })

  it('asks for the next page and keeps it in the address', async () => {
    const { user, network } = await openLog({ [NOTIFICATIONS_ROUTE]: () => jsonResponse(emailPage([SENT_EMAIL], { total: 41 })) }, LOG)
    await findEmails()

    await user.click(screen.getByRole('button', { name: 'Page 3' }))

    await waitFor(() => expect(lastAsked(network, NOTIFICATIONS_ROUTE).get('page')).toBe('3'))
    expect(currentAddress()).toBe(`${LOG}&page=3`)
    expect(screen.getByRole('region', { name: 'The emails' })).toHaveFocus()
  })
})

describe('sending a failed confirmation again', () => {
  it('asks first in words, then posts once with no body, shows the new attempt and reads the log again', async () => {
    const { user, network } = await openLog({ [resendRoute(FAILED_EMAIL.id)]: () => createdResponse(RESENT_EMAIL) }, LOG)
    await findEmails()

    await user.click(screen.getByRole('button', { name: SEND_AGAIN }))

    const question = screen.getByRole('heading', { level: 4, name: `Send the booking confirmation for ${FAILED_EMAIL.reservationReference} again?` })
    expect(question).toHaveFocus()
    expect(screen.getByText(/This failed attempt stays in the log as it is/)).toBeVisible()
    expect(network.requestsTo(resendRoute(FAILED_EMAIL.id))).toHaveLength(0)
    const reads = network.requestsTo(NOTIFICATIONS_ROUTE).length

    network.setRoute(NOTIFICATIONS_ROUTE, () => jsonResponse(emailPage([RESENT_EMAIL, FAILED_EMAIL])))
    await user.click(screen.getByRole('button', { name: 'Yes, send it again' }))

    expect(await screen.findByText(`The booking confirmation for ${FAILED_EMAIL.reservationReference} is sent again`, {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByText(/The new attempt to w\.adonis@buildright\.co\.za is waiting to be sent\./)).toBeVisible()
    expect(network.requestsTo(resendRoute(FAILED_EMAIL.id))).toHaveLength(1)
    expect(network.requestsTo(resendRoute(FAILED_EMAIL.id))[0].body).toBeUndefined()
    await waitFor(() => expect(network.requestsTo(NOTIFICATIONS_ROUTE).length).toBeGreaterThan(reads))
    expect(await screen.findByText(/^This sends again the email queued/, {}, SCREEN_WAIT)).toBeVisible()
  })

  it('disables the answer while the request is in flight, so it is sent once', async () => {
    const { user, network } = await openLog({ [resendRoute(FAILED_EMAIL.id)]: neverAnswers }, LOG)
    await findEmails()
    await user.click(screen.getByRole('button', { name: SEND_AGAIN }))

    await user.click(screen.getByRole('button', { name: 'Yes, send it again' }))

    const waiting = await screen.findByRole('button', { name: 'Sending it again' })
    expect(waiting).toBeDisabled()
    await user.click(waiting)
    expect(network.requestsTo(resendRoute(FAILED_EMAIL.id))).toHaveLength(1)
  })

  it.each([
    [409, 'This email did not fail, so there is nothing to send again.'],
    [403, 'Only the owner can send an email again.'],
  ])('shows the server sentence for a %i', async (status, detail) => {
    const { user } = await openLog({ [resendRoute(FAILED_EMAIL.id)]: () => problemResponse(status, { detail }) }, LOG)
    await findEmails()
    await user.click(screen.getByRole('button', { name: SEND_AGAIN }))

    await user.click(screen.getByRole('button', { name: 'Yes, send it again' }))

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('The email was not sent again')
    expect(alert).toHaveTextContent(detail)
  })

  it('puts the question away and gives focus back to its button', async () => {
    const { user } = await openLog({}, LOG)
    await findEmails()
    await user.click(screen.getByRole('button', { name: SEND_AGAIN }))

    await user.click(screen.getByRole('button', { name: 'Keep it as it is' }))

    expect(screen.getByRole('button', { name: SEND_AGAIN })).toHaveFocus()
  })
})
