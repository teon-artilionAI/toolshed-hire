/**
 * Tests for opening a staff account on SC-23, with the network replaced at
 * `fetch`.
 *
 * The form takes exactly the five fields of the route and never a password.
 * The branch is asked for counter staff and hidden for an administrator. It
 * asks first, sends the body once, says the person chooses their own password
 * from a link, says plainly when the link could not be delivered, puts a 422
 * under its field, shows the server's sentence on a 403, and reads the list
 * again.
 */

import { screen, waitFor, within } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createdResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import { OPEN_ACCOUNT_ROUTE, USERS_ROUTE } from '../../test/admin-user-samples'
import type { AdminUser } from '../../shared/api/contract'
import { TEST_NOW } from '../../test/catalogue-samples'
import { SCREEN_WAIT } from '../../test/render-app'
import { lastBody, openUsers } from './SC23-test-kit'

const LINDIWE: AdminUser = {
  id: '0b0f6f3e-1111-4a2b-9c3d-000000000009',
  email: 'lindiwe@toolshedhire.co.za',
  fullName: 'Lindiwe Dube',
  phone: '0825550199',
  role: 'COUNTER_STAFF',
  branchCode: 'SMW',
  isActive: true,
  emailVerified: false,
  lastLoginAt: null,
  lockedUntil: null,
  createdAt: '2026-03-12T08:00:00+02:00',
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

function theForm(): HTMLElement {
  return screen.getByRole('form', { name: 'The new staff account' })
}

async function openTheForm(user: UserEvent): Promise<HTMLElement> {
  await user.click(await screen.findByRole('button', { name: 'Add a staff account' }, SCREEN_WAIT))
  expect(await screen.findByRole('heading', { level: 3, name: 'A new staff account' }, SCREEN_WAIT)).toHaveFocus()
  return theForm()
}

async function fillIn(user: UserEvent, form: HTMLElement, branch: string | null = 'Somerset West') {
  await user.type(within(form).getByLabelText('Full name'), LINDIWE.fullName)
  await user.type(within(form).getByLabelText('Work email'), LINDIWE.email)
  await user.type(within(form).getByLabelText('Phone number, if they have one'), '0825550199')
  if (branch !== null) await user.selectOptions(within(form).getByLabelText('Branch they work at'), branch)
}

describe('the form that opens a staff account', () => {
  it('asks for exactly the fields of the route and never for a password', async () => {
    const { user } = await openUsers()
    const form = await openTheForm(user)

    expect(within(form).getAllByRole('textbox').map((box) => box.getAttribute('name'))).toEqual([
      'new-staff-fullName',
      'new-staff-email',
      'new-staff-phone',
    ])
    expect(within(form).getByLabelText('Role')).toHaveValue('COUNTER_STAFF')
    expect(within(form).getByLabelText('Branch they work at')).toBeVisible()
    expect(within(form).queryByLabelText(/password/i)).not.toBeInTheDocument()
  })

  it('hides the branch for an administrator', async () => {
    const { user } = await openUsers()
    const form = await openTheForm(user)

    await user.selectOptions(within(form).getByLabelText('Role'), 'Admin and owner')

    expect(within(form).queryByLabelText('Branch they work at')).not.toBeInTheDocument()
  })

  it('holds back counter staff with no branch, says why, and sends nothing', async () => {
    const { user, network } = await openUsers()
    const form = await openTheForm(user)
    await fillIn(user, form, null)

    await user.click(within(form).getByRole('button', { name: 'Create the account' }))

    expect(await screen.findByText(/Nothing has been saved yet\. 1 answer needs fixing\./)).toBeVisible()
    expect(within(form).getByLabelText('Branch they work at')).toHaveAccessibleDescription(
      'Choose the branch they work at. Counter staff work at one branch.',
    )
    expect(network.requestsTo(OPEN_ACCOUNT_ROUTE)).toHaveLength(0)
  })
})

describe('opening the account', () => {
  it('asks first, sends the five fields, says the person chooses their own password, and reads the list again', async () => {
    const { user, network } = await openUsers({
      [OPEN_ACCOUNT_ROUTE]: () => createdResponse({ user: LINDIWE, emailDeliverable: true }),
    })
    const form = await openTheForm(user)
    await fillIn(user, form)
    const listReads = network.requestsTo(USERS_ROUTE).length

    await user.click(within(form).getByRole('button', { name: 'Create the account' }))
    expect(screen.getByRole('heading', { level: 4, name: `Create an account for ${LINDIWE.fullName}?` })).toHaveFocus()
    expect(screen.getByText(/They will work as counter staff at Somerset West\./)).toBeVisible()
    expect(screen.getByText(/A link to choose their own password is sent to/)).toHaveTextContent(
      `${LINDIWE.email}. This demonstration delivers email to one address only, so the answer says whether the link can reach them.`,
    )
    expect(network.requestsTo(OPEN_ACCOUNT_ROUTE)).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Yes, create it' }))

    const outcome = await screen.findByText(`${LINDIWE.fullName} has a staff account`, {}, SCREEN_WAIT)
    expect(outcome.closest('[tabindex="-1"]')).toHaveFocus()
    expect(screen.getByText(/sets their own password from a link sent to lindiwe@toolshedhire\.co\.za/)).toBeVisible()
    expect(lastBody(network, OPEN_ACCOUNT_ROUTE)).toEqual({
      email: LINDIWE.email,
      fullName: LINDIWE.fullName,
      phone: '0825550199',
      role: 'COUNTER_STAFF',
      branchCode: 'SMW',
    })
    expect(screen.queryByRole('form', { name: 'The new staff account' })).not.toBeInTheDocument()
    await waitFor(() => expect(network.requestsTo(USERS_ROUTE).length).toBeGreaterThan(listReads))
  })

  it('sends an administrator with no branch and no phone', async () => {
    const admin = { ...LINDIWE, role: 'ADMIN' as const, branchCode: null, phone: null }
    const { user, network } = await openUsers({ [OPEN_ACCOUNT_ROUTE]: () => createdResponse({ user: admin, emailDeliverable: true }) })
    const form = await openTheForm(user)
    await user.type(within(form).getByLabelText('Full name'), admin.fullName)
    await user.type(within(form).getByLabelText('Work email'), admin.email)
    await user.selectOptions(within(form).getByLabelText('Role'), 'Admin and owner')

    await user.click(within(form).getByRole('button', { name: 'Create the account' }))
    expect(screen.getByText(/They will work as admin and owner across every branch\./)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Yes, create it' }))

    await screen.findByText(`${admin.fullName} has a staff account`, {}, SCREEN_WAIT)
    expect(lastBody(network, OPEN_ACCOUNT_ROUTE)).toEqual({
      email: admin.email,
      fullName: admin.fullName,
      phone: null,
      role: 'ADMIN',
      branchCode: null,
    })
  })

  it('says plainly when the link could not be delivered', async () => {
    const { user } = await openUsers({ [OPEN_ACCOUNT_ROUTE]: () => createdResponse({ user: LINDIWE, emailDeliverable: false }) })
    const form = await openTheForm(user)
    await fillIn(user, form)
    await user.click(within(form).getByRole('button', { name: 'Create the account' }))

    await user.click(screen.getByRole('button', { name: 'Yes, create it' }))

    expect(await screen.findByText(`${LINDIWE.fullName} has a staff account, but the link could not be sent`, {}, SCREEN_WAIT)).toBeVisible()
    expect(
      screen.getByText(
        `This demonstration delivers email to one address only, and ${LINDIWE.email} is not it, so the link to choose a password will not arrive.`,
      ),
    ).toBeVisible()
    expect(screen.queryByText(/a link sent to/)).not.toBeInTheDocument()
  })

  it('puts an address another account has under the email box, and goes back to the form', async () => {
    const refusal = () =>
      problemResponse(422, { errors: { fields: { 'body.email': 'Another account already signs in with that address.' } } })
    const { user } = await openUsers({ [OPEN_ACCOUNT_ROUTE]: refusal })
    const form = await openTheForm(user)
    await fillIn(user, form)
    await user.click(within(form).getByRole('button', { name: 'Create the account' }))

    await user.click(screen.getByRole('button', { name: 'Yes, create it' }))

    await waitFor(() =>
      expect(within(theForm()).getByLabelText('Work email')).toHaveAccessibleDescription(
        expect.stringContaining('Another account already signs in with that address.'),
      ),
    )
    expect(screen.queryByRole('heading', { level: 4 })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Another account already signs in with that address.' })).toHaveAttribute(
      'href',
      '#new-staff-email',
    )
  })

  it('shows the sentence of a 403 in the question', async () => {
    const detail = 'Only an administrator may open a staff account.'
    const { user } = await openUsers({ [OPEN_ACCOUNT_ROUTE]: () => problemResponse(403, { detail }) })
    const form = await openTheForm(user)
    await fillIn(user, form)
    await user.click(within(form).getByRole('button', { name: 'Create the account' }))

    await user.click(screen.getByRole('button', { name: 'Yes, create it' }))

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('The account was not created')
    expect(alert).toHaveTextContent(detail)
  })

  it('disables the answer while the request is in flight, so it is sent once', async () => {
    const { user, network } = await openUsers({ [OPEN_ACCOUNT_ROUTE]: neverAnswers })
    const form = await openTheForm(user)
    await fillIn(user, form)
    await user.click(within(form).getByRole('button', { name: 'Create the account' }))

    await user.click(screen.getByRole('button', { name: 'Yes, create it' }))

    const waiting = await screen.findByRole('button', { name: 'Creating the account' })
    expect(waiting).toBeDisabled()
    await user.click(waiting)
    expect(network.requestsTo(OPEN_ACCOUNT_ROUTE)).toHaveLength(1)
  })

  it('closes the form and gives focus back to the button that opened it', async () => {
    const { user } = await openUsers()
    const form = await openTheForm(user)

    await user.click(within(form).getByRole('button', { name: 'Close the form' }))

    expect(screen.queryByRole('form', { name: 'The new staff account' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add a staff account' })).toHaveFocus()
  })
})
