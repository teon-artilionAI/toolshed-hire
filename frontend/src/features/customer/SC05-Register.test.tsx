/**
 * Tests for SC-05, the register screen, while registration is not available.
 *
 * The form is on the page so its questions and its checks can be seen. What
 * these tests hold it to is that it never says an account was created.
 */

import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { mockApi } from '../../test/api-mock'
import { findScreenHeading, renderApp } from '../../test/render-app'
import { SIGNED_OUT } from '../../test/session-samples'

const UNAVAILABLE = 'Creating an account online is not available yet'
const FAKE_SUCCESS = /account is ready|welcome to toolshed hire|we have sent a confirmation/i

async function openRegister(): Promise<UserEvent> {
  renderApp('/register')
  await findScreenHeading('Create your hire account')
  return userEvent.setup()
}

async function fillInEverything(user: UserEvent): Promise<void> {
  await user.type(screen.getByLabelText('Full name'), 'Thandi Mokoena')
  await user.type(screen.getByLabelText('Email address'), 'thandi@example.co.za')
  await user.type(screen.getByLabelText('Mobile number'), '0824417719')
  await user.type(screen.getByLabelText(/number$/, { selector: '#idDocNumber' }), '8703155800085')
  await user.type(screen.getByLabelText('Billing suburb'), 'Salt River')
  await user.type(screen.getByLabelText('Billing city'), 'Cape Town')
  await user.type(screen.getByLabelText('Password'), 'a-long-password-1')
  await user.type(screen.getByLabelText('Confirm password'), 'a-long-password-1')
  await user.click(screen.getByRole('checkbox'))
}

describe('the register screen', () => {
  it('says before anyone types that an account cannot be created here yet', async () => {
    mockApi(SIGNED_OUT)

    await openRegister()

    expect(screen.getByText(UNAVAILABLE)).toBeVisible()
    expect(screen.getByText(/no account is opened/)).toBeVisible()
  })

  it('answers a form that passes every check with the same statement, not a success', async () => {
    const network = mockApi(SIGNED_OUT)
    const user = await openRegister()
    await fillInEverything(user)
    const requestsBefore = network.requests.length

    await user.click(screen.getByRole('button', { name: 'Check my answers' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We have not opened an account')
    expect(alert).toHaveTextContent('Nothing was saved and nothing was sent')
    expect(screen.queryByText(FAKE_SUCCESS)).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Create your hire account')
    expect(network.requests).toHaveLength(requestsBefore)
  })

  it('still points out the answers that need fixing', async () => {
    mockApi(SIGNED_OUT)
    const user = await openRegister()

    await user.click(screen.getByRole('button', { name: 'Check my answers' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/We cannot open the account yet/)
    expect(screen.queryByText('We have not opened an account')).not.toBeInTheDocument()
  })
})
