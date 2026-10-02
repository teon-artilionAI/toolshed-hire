/**
 * Tests for SC-05, the register screen, with the network replaced at `fetch`.
 *
 * I open the whole application on `/register`, fill the form in the way a
 * person would, and say how the API answers. What these tests hold the screen
 * to is that it sends exactly what the contract asks for, that it says the
 * same thing whoever the address belongs to, and that it never leaves a
 * person waiting for an email that cannot come.
 *
 * This file is about the form and what it sends. What the screen says once
 * the API has answered is in SC05-Register-Answers.test.tsx. The rules of each
 * field are in register-form.test.ts, and where a verification link lands is
 * in SC05-Email-Verification.test.tsx.
 */

import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DELIVERABLE, REGISTER_ROUTE } from '../../test/account-samples'
import { acceptedResponse, neverAnswers } from '../../test/api-mock'
import { SAMPLE_DATA_TITLE } from '../../shared/sample-data-notice'
import { CHECK_YOUR_EMAIL_HEADING } from './SC05-Register'
import { EMAIL, PASSWORD, SUBMIT, fillInEverything, openRegister } from './SC05-test-kit'

describe('the registration form', () => {
  it('is connected, so it carries no notice about sample data or about being unavailable', async () => {
    await openRegister(() => acceptedResponse(DELIVERABLE))

    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
    expect(screen.queryByText(/not available yet/)).not.toBeInTheDocument()
  })

  it('asks for the last four characters of the document and says the counter checks the rest', async () => {
    await openRegister(() => acceptedResponse(DELIVERABLE))

    const lastFour = screen.getByLabelText('Last four characters of the document number')
    expect(lastFour).toHaveAttribute('maxlength', '4')
    expect(lastFour).toHaveAccessibleDescription(/The counter checks the full document at collection/)
    expect(screen.queryByLabelText(/ID number$/)).not.toBeInTheDocument()
  })

  it('links the privacy notice beside the acceptance box', async () => {
    await openRegister(() => acceptedResponse(DELIVERABLE))

    expect(screen.getByRole('checkbox', { name: /I have read the privacy notice and I accept it/ })).not.toBeChecked()
    const link = screen.getByRole('link', { name: 'Read the privacy notice (opens in a new tab)' })
    expect(link).toHaveAttribute('href', '/privacy')
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('offers the branches the API lists', async () => {
    await openRegister(() => acceptedResponse(DELIVERABLE))

    const options = within(screen.getByLabelText('Usual collection branch')).getAllByRole('option')
    expect(options.map((option) => option.textContent)).toEqual([
      'Cape Town CBD, Woodstock',
      'Bellville, Stikland',
      'Somerset West, Firgrove',
    ])
  })

  it('checks the answers before it asks the API, and ties each problem to its field', async () => {
    const { user, network } = await openRegister(() => acceptedResponse(DELIVERABLE))

    await user.click(screen.getByRole('button', { name: SUBMIT }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/We cannot open the account yet\. \d+ answers need fixing\./)
    expect(within(alert).getByRole('link', { name: /Give both|Tell us your full name/ })).toHaveAttribute(
      'href',
      '#fullName',
    )
    const email = screen.getByLabelText('Email address')
    expect(email).toBeInvalid()
    expect(email).toHaveAccessibleDescription(/We send booking confirmations by email, so we need one\./)
    expect(screen.getByRole('checkbox')).toHaveAccessibleDescription(/accept the privacy notice/)
    expect(network.requestsTo(REGISTER_ROUTE)).toHaveLength(0)
  })

  it('shows the password rule as twelve characters and holds a shorter one back', async () => {
    const { user, network } = await openRegister(() => acceptedResponse(DELIVERABLE))
    await fillInEverything(user)
    await user.clear(screen.getByLabelText('Password'))
    await user.type(screen.getByLabelText('Password'), 'eleven-char')
    await user.clear(screen.getByLabelText('Confirm password'))
    await user.type(screen.getByLabelText('Confirm password'), 'eleven-char')

    await user.click(screen.getByRole('button', { name: SUBMIT }))

    expect(screen.getByText('At least 12 characters.')).toBeVisible()
    expect(screen.getByLabelText('Password')).toHaveAccessibleDescription(
      /Passwords need at least 12 characters\. Yours has 11\./,
    )
    expect(network.requestsTo(REGISTER_ROUTE)).toHaveLength(0)
  })
})

describe('sending the form', () => {
  it('sends exactly what the contract asks for, once', async () => {
    const { user, network } = await openRegister(() => acceptedResponse(DELIVERABLE))
    await fillInEverything(user)

    await user.click(screen.getByRole('button', { name: SUBMIT }))

    await screen.findByRole('heading', { name: CHECK_YOUR_EMAIL_HEADING })
    const calls = network.requestsTo(REGISTER_ROUTE)
    expect(calls).toHaveLength(1)
    expect(calls[0].body).toEqual({
      email: EMAIL,
      password: PASSWORD,
      fullName: 'Thandi Mokoena',
      phone: '0824417719',
      idDocumentType: 'SA_ID',
      idDocumentLast4: '5083',
      billingAddressLine1: '12 Loop Street',
      billingSuburb: 'Gardens',
      billingCity: 'Cape Town',
      billingPostalCode: '8001',
      homeBranchCode: 'BLV',
      acceptsPrivacyNotice: true,
    })
  })

  it('sends the first branch the API lists when none was chosen', async () => {
    const { user, network } = await openRegister(() => acceptedResponse(DELIVERABLE))
    await fillInEverything(user)
    await user.selectOptions(screen.getByLabelText('Usual collection branch'), 'Cape Town CBD, Woodstock')

    await user.click(screen.getByRole('button', { name: SUBMIT }))

    await screen.findByRole('heading', { name: CHECK_YOUR_EMAIL_HEADING })
    expect(network.requestsTo(REGISTER_ROUTE)[0].body).toMatchObject({ homeBranchCode: 'CBD' })
  })

  it('disables the button while the request is in flight, so it cannot be sent twice', async () => {
    const { user, network } = await openRegister(neverAnswers)
    await fillInEverything(user)

    await user.click(screen.getByRole('button', { name: SUBMIT }))

    const button = await screen.findByRole('button', { name: 'Creating your account' })
    expect(button).toBeDisabled()
    expect(screen.getByText('Sending your details, please wait')).toBeInTheDocument()
    await user.type(screen.getByLabelText('Confirm password'), '{Enter}')
    expect(network.requestsTo(REGISTER_ROUTE)).toHaveLength(1)
  })
})
