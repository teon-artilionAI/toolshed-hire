/**
 * Tests for asking for a password reset link on SC-06, with the network
 * replaced at `fetch`.
 *
 * The state is reached from the sign in form and from `?reset=1`. I open the
 * whole application on it, say how the API answers, and read the page. What
 * these tests hold the screen to is one message after a request, whoever the
 * address belongs to.
 *
 * Choosing a new password from the link is in SC06-Password-Reset-Link.test.tsx.
 */

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import {
  DELIVERABLE,
  NOT_DELIVERABLE,
  RESET_REQUEST_ROUTE,
  refusedFields,
  throttled,
} from '../../test/account-samples'
import { acceptedResponse, mockApi, neverAnswers } from '../../test/api-mock'
import type { ApiMock, RouteHandler } from '../../test/api-mock'
import { findScreenHeading, renderApp } from '../../test/render-app'
import { SIGNED_OUT } from '../../test/session-samples'
import { DEMONSTRATION_EMAIL_REASON } from './email-delivery-note'
import { RESET_SENT_MESSAGE } from './password-reset-panels'

const SIGN_IN_HEADING = 'Sign in to Toolshed Hire'
const REQUEST_HEADING = 'Reset your password'
const EMAIL = 'someone@example.co.za'

async function openRequest(route: RouteHandler): Promise<{ user: UserEvent; network: ApiMock }> {
  const network = mockApi({ ...SIGNED_OUT, [RESET_REQUEST_ROUTE]: route })
  renderApp('/signin?reset=1')
  await findScreenHeading(REQUEST_HEADING)
  return { user: userEvent.setup(), network }
}

describe('asking for a reset link', () => {
  it('is reached from the sign in form, and focus moves to its heading', async () => {
    mockApi(SIGNED_OUT)
    renderApp('/signin')
    await findScreenHeading(SIGN_IN_HEADING)
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Forgotten your password?' }))

    const heading = await findScreenHeading(REQUEST_HEADING)
    await waitFor(() => expect(heading.closest('[tabindex="-1"]')).toHaveFocus())
    expect(screen.getByLabelText('Email address')).toBeVisible()

    await user.click(screen.getByRole('button', { name: 'Back to sign in' }))
    expect(await findScreenHeading(SIGN_IN_HEADING)).toBeVisible()
  })

  it('posts the address once and shows the one message, whoever it belongs to', async () => {
    const { user, network } = await openRequest(() => acceptedResponse(DELIVERABLE))

    await user.type(screen.getByLabelText('Email address'), `  ${EMAIL} `)
    await user.click(screen.getByRole('button', { name: 'Send me a reset link' }))

    const heading = await screen.findByRole('heading', { name: 'Check your email' })
    await waitFor(() => expect(heading).toHaveFocus())
    expect(screen.getByText(RESET_SENT_MESSAGE)).toBeVisible()
    expect(screen.queryByText(DEMONSTRATION_EMAIL_REASON)).not.toBeInTheDocument()
    // Nothing says whether the address has an account.
    expect(screen.queryByText(/no account|not registered|we found/i)).not.toBeInTheDocument()
    const calls = network.requestsTo(RESET_REQUEST_ROUTE)
    expect(calls).toHaveLength(1)
    expect(calls[0].body).toEqual({ email: EMAIL })

    await user.click(screen.getByRole('button', { name: 'Back to sign in' }))
    expect(await findScreenHeading(SIGN_IN_HEADING)).toBeVisible()
  })

  it('shows the same message with the demonstration note when the email cannot be delivered', async () => {
    const { user } = await openRequest(() => acceptedResponse(NOT_DELIVERABLE))

    await user.type(screen.getByLabelText('Email address'), EMAIL)
    await user.click(screen.getByRole('button', { name: 'Send me a reset link' }))

    expect(await screen.findByText(RESET_SENT_MESSAGE)).toBeVisible()
    expect(screen.getByText(DEMONSTRATION_EMAIL_REASON)).toBeVisible()
    expect(screen.getByText('Your password has not changed.')).toBeVisible()
  })

  it('checks the address before it asks the API', async () => {
    const { user, network } = await openRequest(() => acceptedResponse(DELIVERABLE))

    await user.click(screen.getByRole('button', { name: 'Send me a reset link' }))
    expect(screen.getByText('Enter the email address on your account.')).toBeVisible()

    await user.type(screen.getByLabelText('Email address'), 'someone.example.co.za')
    expect(screen.getByLabelText('Email address')).toHaveAccessibleDescription(/missing an @ or a domain/)
    expect(network.requestsTo(RESET_REQUEST_ROUTE)).toHaveLength(0)
  })

  it('disables the button while the request is in flight', async () => {
    const { user, network } = await openRequest(neverAnswers)
    await user.type(screen.getByLabelText('Email address'), EMAIL)

    await user.click(screen.getByRole('button', { name: 'Send me a reset link' }))

    expect(await screen.findByRole('button', { name: 'Sending the link' })).toBeDisabled()
    await user.type(screen.getByLabelText('Email address'), '{Enter}')
    expect(network.requestsTo(RESET_REQUEST_ROUTE)).toHaveLength(1)
  })

  it('says how long to wait after a 429', async () => {
    const { user } = await openRequest(() => throttled(600))
    await user.type(screen.getByLabelText('Email address'), EMAIL)

    await user.click(screen.getByRole('button', { name: 'Send me a reset link' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Too many attempts')
    expect(alert).toHaveTextContent('Wait 10 minutes and try again.')
    expect(screen.queryByText(RESET_SENT_MESSAGE)).not.toBeInTheDocument()
  })

  it('puts a refusal of the address under the field', async () => {
    const { user } = await openRequest(() => refusedFields({ email: 'That is not an email address.' }))
    await user.type(screen.getByLabelText('Email address'), EMAIL)

    await user.click(screen.getByRole('button', { name: 'Send me a reset link' }))

    await waitFor(() =>
      expect(screen.getByLabelText('Email address')).toHaveAccessibleDescription(/That is not an email address\./),
    )
  })

  it('shows the shared error state when the API cannot be reached, and can try again', async () => {
    const { user, network } = await openRequest(() => {
      throw new TypeError('Failed to fetch')
    })
    await user.type(screen.getByLabelText('Email address'), EMAIL)

    await user.click(screen.getByRole('button', { name: 'Send me a reset link' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not ask for a reset link')
    network.setRoute(RESET_REQUEST_ROUTE, () => acceptedResponse(DELIVERABLE))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText(RESET_SENT_MESSAGE)).toBeVisible()
  })
})
