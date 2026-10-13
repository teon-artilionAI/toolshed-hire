/**
 * Tests for removing a customer's personal details on SC-23 (#113), with the
 * network replaced at `fetch`.
 *
 * The question says what is removed, what stays and that it cannot be undone,
 * and asks why. A reason that is too short is held back, a good one is sent
 * once and trimmed, and the notice names who the customer was. A 409, a 403
 * and a 422 each show where they belong, the answer is disabled in flight, and
 * putting the question away gives focus back. A customer whose details were
 * removed offers nothing and says on which day that was.
 */

import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import type { RouteTable } from '../../test/api-mock'
import { BLACKLISTED, CUSTOMER_HOLDS_ROUTE, anonymiseRoute, anonymised, holdPage } from '../../test/admin-user-samples'
import { TEST_NOW } from '../../test/catalogue-samples'
import { ON_HOLD, THANDI } from '../../test/counter-samples'
import { SCREEN_WAIT } from '../../test/render-app'
import { HOLDS, findCustomer, lastBody, openUsers } from './SC23-test-kit'

const REASON = 'Asked by email to remove every detail we hold.'

const FORMER = anonymised(ON_HOLD)

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

/** Open the holds and the question for the customer on hold. */
async function askToAnonymise(routes: RouteTable = {}) {
  const opened = await openUsers(routes, HOLDS)
  const entry = await findCustomer(ON_HOLD.displayName)
  await opened.user.click(within(entry).getByRole('button', { name: /^Anonymise/ }))
  return { ...opened, entry }
}

describe('the question before a customer is anonymised', () => {
  it('says what is removed, what stays and that it cannot be undone, with focus on its heading', async () => {
    const { entry } = await askToAnonymise()

    expect(screen.getByRole('heading', { level: 4, name: `Anonymise ${ON_HOLD.displayName}?` })).toHaveFocus()
    expect(within(entry).getByText(/^Their name, phone number, email address, address and ID digits are removed, and they can no longer sign in\.$/)).toBeVisible()
    expect(within(entry).getByText('Their hires, charges and deposits are kept for 5 years as financial records.')).toBeVisible()
    expect(within(entry).getByText('This cannot be undone.')).toBeVisible()
    expect(within(entry).getByRole('button', { name: 'Yes, anonymise' })).toHaveAccessibleDescription(/This cannot be undone\./)
    expect(within(entry).getByLabelText('Why')).toHaveAccessibleDescription(expect.stringContaining('audit trail'))
  })

  it('holds back a reason that is too short, without a request', async () => {
    const { user, network, entry } = await askToAnonymise()

    await user.type(within(entry).getByLabelText('Why'), 'Gone')
    await user.click(within(entry).getByRole('button', { name: 'Yes, anonymise' }))

    expect(within(entry).getByLabelText('Why')).toHaveAccessibleDescription(expect.stringContaining('Write at least 5 characters. This has 4.'))
    expect(network.requestsTo(anonymiseRoute(ON_HOLD.id))).toHaveLength(0)
  })

  it('sends one request with the trimmed reason, names who they were, and shows them anonymised once read again', async () => {
    let removed = false
    const { user, network, entry } = await askToAnonymise({
      [CUSTOMER_HOLDS_ROUTE]: () => jsonResponse(holdPage(removed ? [FORMER, THANDI, BLACKLISTED] : undefined)),
      [anonymiseRoute(ON_HOLD.id)]: () => {
        removed = true
        return jsonResponse(FORMER)
      },
    })

    await user.type(within(entry).getByLabelText('Why'), `  ${REASON}  `)
    await user.click(within(entry).getByRole('button', { name: 'Yes, anonymise' }))

    const outcome = await screen.findByText(`The personal details of ${ON_HOLD.displayName} were removed`, {}, SCREEN_WAIT)
    expect(outcome.closest('[tabindex="-1"]')).toHaveFocus()
    expect(
      screen.getByText(
        'They are listed as Former customer from now on. Their hires, charges and deposits are kept for 5 years as financial records. The audit trail keeps the reason.',
      ),
    ).toBeVisible()
    expect(network.requestsTo(anonymiseRoute(ON_HOLD.id))).toHaveLength(1)
    expect(lastBody(network, anonymiseRoute(ON_HOLD.id))).toEqual({ reason: REASON })
    const former = await findCustomer('Former customer')
    expect(within(former).getByText(/^Their personal details were removed on 13 Oct 2026\./)).toBeVisible()
  })

  it.each([
    [409, 'This customer still has a booking still open and a hire not yet settled, so their details cannot be removed yet. Finish what is open first.'],
    [403, 'Only an administrator may remove the details of a customer.'],
  ])('shows the sentence of a %i under the question', async (status, detail) => {
    const { user, entry } = await askToAnonymise({ [anonymiseRoute(ON_HOLD.id)]: () => problemResponse(status, { detail }) })
    await user.type(within(entry).getByLabelText('Why'), REASON)

    await user.click(within(entry).getByRole('button', { name: 'Yes, anonymise' }))

    const alert = await within(entry).findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent(`The personal details of ${ON_HOLD.displayName} were not removed`)
    expect(alert).toHaveTextContent(detail)
    expect(within(entry).getByRole('button', { name: 'Yes, anonymise' })).toBeEnabled()
  })

  it('puts a refused reason under its box', async () => {
    const refusal = () => problemResponse(422, { errors: { fields: { 'body.reason': 'Give a reason of 5 to 200 characters.' } } })
    const { user, entry } = await askToAnonymise({ [anonymiseRoute(ON_HOLD.id)]: refusal })
    await user.type(within(entry).getByLabelText('Why'), REASON)

    await user.click(within(entry).getByRole('button', { name: 'Yes, anonymise' }))

    await waitFor(() =>
      expect(within(entry).getByLabelText('Why')).toHaveAccessibleDescription(expect.stringContaining('5 to 200 characters')),
    )
    expect(within(entry).queryByRole('alert')).not.toBeInTheDocument()
  })

  it('disables both buttons while the request is in flight, so it is sent once', async () => {
    const { user, network, entry } = await askToAnonymise({ [anonymiseRoute(ON_HOLD.id)]: neverAnswers })
    await user.type(within(entry).getByLabelText('Why'), REASON)

    await user.click(within(entry).getByRole('button', { name: 'Yes, anonymise' }))

    const waiting = await within(entry).findByRole('button', { name: 'Anonymising' })
    expect(waiting).toBeDisabled()
    expect(within(entry).getByRole('button', { name: 'Keep their details' })).toBeDisabled()
    await user.click(waiting)
    expect(network.requestsTo(anonymiseRoute(ON_HOLD.id))).toHaveLength(1)
  })

  it('puts the question away unanswered and gives focus back to its button', async () => {
    const { user, network, entry } = await askToAnonymise()

    await user.click(within(entry).getByRole('button', { name: 'Keep their details' }))

    await waitFor(() => expect(within(entry).getByRole('button', { name: /^Anonymise/ })).toHaveFocus())
    expect(network.requestsTo(anonymiseRoute(ON_HOLD.id))).toHaveLength(0)
  })
})

describe('a customer whose details were removed', () => {
  it('offers no move and no anonymising, and says on which day the details were removed', async () => {
    await openUsers({ [CUSTOMER_HOLDS_ROUTE]: () => jsonResponse(holdPage([anonymised(BLACKLISTED), THANDI])) }, HOLDS)

    const former = await findCustomer('Former customer')
    expect(within(former).queryByRole('button')).not.toBeInTheDocument()
    expect(
      within(former).getByText(
        /^Their personal details were removed on 0?13 Oct 2026\. Their hires, charges and deposits are kept for 5 years as financial records\.$/,
      ),
    ).toBeVisible()
    expect(within(former).getAllByText('Removed')).toHaveLength(2)
    expect(within(former).queryByText(/anonymised\.invalid/)).not.toBeInTheDocument()
    expect(within(await findCustomer(THANDI.displayName)).getByRole('button', { name: /^Anonymise/ })).toBeVisible()
  })
})
