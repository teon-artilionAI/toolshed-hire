/**
 * Tests for SC-09 My Account, with the network replaced at `fetch`.
 *
 * The profile is the server's. Each test says how the profile routes answer,
 * opens the screen as the signed in customer, and reads it the way a person
 * would. Loading, failed, no profile and loaded, and then the notice an
 * unconfirmed email address gets. Correcting the profile is in
 * SC09-Profile-Edit.test.tsx, and what the files share is in SC09-test-kit.tsx.
 */

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import {
  DELIVERABLE,
  NOT_DELIVERABLE,
  PROFILE,
  PROFILE_ROUTE,
  RESEND_ROUTE,
  UNVERIFIED_PROFILE,
  throttled,
} from '../../test/account-samples'
import { acceptedResponse, jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import { ACCESS_TOKEN, bearerOf } from '../../test/session-samples'
import { SAMPLE_DATA_TITLE } from '../../shared/sample-data-notice'
import { DEMONSTRATION_EMAIL_REASON, WITHOUT_THE_LINK } from './email-delivery-note'
import { EMAIL_UNCONFIRMED_TITLE, LINK_SENT_AGAIN_TITLE } from './email-verification-notice'
import { NO_HIRES_YET, NO_PROFILE_TITLE } from './SC09-My-Account'
import { detail, openAccount, startEditing, withProfile } from './SC09-test-kit'

describe('while the profile is loading', () => {
  it('says so and shows no detail', async () => {
    await openAccount({ [PROFILE_ROUTE]: neverAnswers })

    expect(screen.getByText('Loading your account')).toBeInTheDocument()
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull()
    expect(screen.queryByText('Email address')).not.toBeInTheDocument()
    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
  })
})

describe('when the profile fails to load', () => {
  it('says so in plain words with the reference, and loads on a retry', async () => {
    const { user, network } = await openAccount({
      [PROFILE_ROUTE]: () => problemResponse(500, { requestId: 'req-profile-7' }),
    })

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not load your account')
    expect(within(alert).getByText('req-profile-7')).toBeVisible()
    expect(alert).not.toHaveTextContent('500')

    network.setRoute(PROFILE_ROUTE, () => jsonResponse(PROFILE))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText('Your details')).toBeVisible()
    expect(detail('Name')).toHaveTextContent(PROFILE.fullName)
  })
})

describe('an account with no customer profile', () => {
  it('is told so plainly, and is not shown an error', async () => {
    await openAccount({ [PROFILE_ROUTE]: () => problemResponse(404, { slug: 'not-found' }) })

    expect(await screen.findByText(NO_PROFILE_TITLE)).toBeVisible()
    expect(screen.getByText(/Staff accounts do not have one/)).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit my details' })).not.toBeInTheDocument()
  })
})

describe('the loaded profile', () => {
  it('is asked for with the token of the session', async () => {
    const { network } = await openAccount(withProfile(PROFILE))
    await screen.findByText('Your details')

    expect(bearerOf(network.requestsTo(PROFILE_ROUTE)[0])).toBe(ACCESS_TOKEN)
  })

  it('shows what the server sent, and only the last four of the document', async () => {
    await openAccount(withProfile(PROFILE))
    await screen.findByText('Your details')

    expect(screen.getByText(`${PROFILE.fullName}, with Toolshed Hire since 14 Feb 2026.`)).toBeVisible()
    expect(detail('Name')).toHaveTextContent('Wesley Adonis')
    expect(detail('Email address')).toHaveTextContent(PROFILE.email)
    expect(detail('Mobile number')).toHaveTextContent('0824417719')
    expect(detail('Billing address')).toHaveTextContent('12 Loop Street, Gardens, Cape Town, 8001')
    expect(detail('South African ID')).toHaveTextContent('Ending 5083')
    // The profile carries the code of the branch, and the name comes from the branch list.
    await waitFor(() =>
      expect(detail('Usual collection branch')).toHaveTextContent('Cape Town CBD, Woodstock'),
    )
    expect(screen.queryByText('Company', { selector: 'dt' })).not.toBeInTheDocument()
    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
  })

  it('shows the standing, the discount and the customer type read only, and says the branch changes them', async () => {
    await openAccount(
      withProfile({
        ...PROFILE,
        customerType: 'TRADE',
        companyName: 'BuildRight Construction',
        vatNumber: '4123456789',
        tradeDiscountPercent: '12.50',
        noShowCount: 1,
      }),
    )
    await screen.findByText('Your details')

    expect(detail('Account standing')).toHaveTextContent('Good standing')
    expect(detail('Customer type')).toHaveTextContent('Trade account')
    expect(detail('Trade discount')).toHaveTextContent(/^12[,.]5%$/)
    expect(detail('Bookings not collected')).toHaveTextContent('1')
    expect(detail('Company')).toHaveTextContent('BuildRight Construction')
    expect(screen.getByText(/The branch changes your account standing, your discount and your customer type/)).toBeVisible()

    await startEditing(userEvent.setup())
    for (const label of [/standing/i, /discount/i, /customer type/i, /email address/i, /document/i]) {
      expect(screen.queryByLabelText(label)).not.toBeInTheDocument()
    }
  })

  it('says an account on hold cannot book', async () => {
    await openAccount(withProfile({ ...PROFILE, accountStatus: 'ON_HOLD' }))

    expect(await screen.findByText('This account cannot book at the moment')).toBeVisible()
    expect(detail('Account standing')).toHaveTextContent('On hold')
  })

  it('shows no sample hire or charge, and says when they will appear', async () => {
    await openAccount(withProfile(PROFILE))
    await screen.findByText('Your details')

    expect(screen.getByText(NO_HIRES_YET)).toBeVisible()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByText(/TSH-H-|Deposit held|R \d/)).not.toBeInTheDocument()
  })
})

describe('an email address that is not confirmed', () => {
  it('is not mentioned to an account that has confirmed it', async () => {
    await openAccount(withProfile(PROFILE))
    await screen.findByText('Your details')

    expect(screen.queryByText(EMAIL_UNCONFIRMED_TITLE)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Send the link again' })).not.toBeInTheDocument()
  })

  it('is said at the top, and the link is sent again once on request', async () => {
    const { user, network } = await openAccount(
      withProfile(UNVERIFIED_PROFILE, { [RESEND_ROUTE]: () => acceptedResponse(DELIVERABLE) }),
    )

    expect(await screen.findByText(EMAIL_UNCONFIRMED_TITLE)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Send the link again' }))

    expect(await screen.findByText(LINK_SENT_AGAIN_TITLE)).toBeVisible()
    expect(screen.queryByText(DEMONSTRATION_EMAIL_REASON)).not.toBeInTheDocument()
    const calls = network.requestsTo(RESEND_ROUTE)
    expect(calls).toHaveLength(1)
    expect(calls[0].body).toBeUndefined()
    expect(bearerOf(calls[0])).toBe(ACCESS_TOKEN)
  })

  it('says plainly when the link cannot reach the address, and what can still be done', async () => {
    const { user } = await openAccount(
      withProfile(UNVERIFIED_PROFILE, { [RESEND_ROUTE]: () => acceptedResponse(NOT_DELIVERABLE) }),
    )

    await user.click(await screen.findByRole('button', { name: 'Send the link again' }))

    expect(await screen.findByText(DEMONSTRATION_EMAIL_REASON)).toBeVisible()
    expect(screen.getByText(WITHOUT_THE_LINK)).toBeVisible()
    expect(screen.queryByText(LINK_SENT_AGAIN_TITLE)).not.toBeInTheDocument()
  })

  it('says how long to wait when the link has been asked for too often', async () => {
    const { user } = await openAccount(withProfile(UNVERIFIED_PROFILE, { [RESEND_ROUTE]: () => throttled(300) }))

    await user.click(await screen.findByRole('button', { name: 'Send the link again' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Too many attempts')
    expect(alert).toHaveTextContent('Wait 5 minutes and try again.')
    expect(screen.getByRole('button', { name: 'Send the link again' })).toBeEnabled()
  })

  it('disables the button while the request is in flight', async () => {
    const { user, network } = await openAccount(withProfile(UNVERIFIED_PROFILE, { [RESEND_ROUTE]: neverAnswers }))

    await user.click(await screen.findByRole('button', { name: 'Send the link again' }))

    expect(await screen.findByRole('button', { name: 'Sending the link' })).toBeDisabled()
    expect(network.requestsTo(RESEND_ROUTE)).toHaveLength(1)
  })
})
