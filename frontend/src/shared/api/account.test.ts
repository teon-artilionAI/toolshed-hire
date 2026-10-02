/**
 * Tests for the registration and account routes, with the network replaced at
 * `fetch`.
 *
 * Each call is made the way a screen makes it. What is checked is the address
 * and the body that went out, and that a body which breaks the contract is
 * refused at the boundary and not handed to a screen.
 */

import { describe, expect, it } from 'vitest'
import {
  DELIVERABLE,
  LINK_TOKEN,
  NOT_DELIVERABLE,
  PROFILE,
  PROFILE_ROUTE,
  PROFILE_UPDATE_ROUTE,
  REGISTER_ROUTE,
  RESEND_ROUTE,
  RESET_COMPLETE_ROUTE,
  RESET_REQUEST_ROUTE,
  VERIFY_ROUTE,
  verificationLinkInvalid,
} from '../../test/account-samples'
import { acceptedResponse, jsonResponse, mockApi, noContentResponse } from '../../test/api-mock'
import { failureOf } from '../../test/session-samples'
import {
  VERIFICATION_LINK_INVALID,
  completePasswordReset,
  getMyProfile,
  registerCustomer,
  requestPasswordReset,
  resendVerification,
  updateMyProfile,
  verifyEmail,
} from './account'
import type { RegisterRequest } from './contract'
import { problemTypeEndsWith } from './session-seam'

const REGISTRATION: RegisterRequest = {
  email: 'a@b.co.za',
  password: 'at least twelve characters',
  fullName: 'Thandi Mokoena',
  phone: '0824417719',
  idDocumentType: 'SA_ID',
  idDocumentLast4: '5083',
  billingAddressLine1: '12 Loop Street',
  billingSuburb: 'Gardens',
  billingCity: 'Cape Town',
  billingPostalCode: '8001',
  homeBranchCode: 'CBD',
  acceptsPrivacyNotice: true,
}

describe('the routes that answer the same way for every address', () => {
  it('posts a registration as it stands and reads the 202', async () => {
    const network = mockApi({ [REGISTER_ROUTE]: () => acceptedResponse(NOT_DELIVERABLE) })

    await expect(registerCustomer(REGISTRATION)).resolves.toEqual({ emailDeliverable: false })
    expect(network.requestsTo(REGISTER_ROUTE)[0].body).toEqual(REGISTRATION)
  })

  it('posts a reset request with the address alone', async () => {
    const network = mockApi({ [RESET_REQUEST_ROUTE]: () => acceptedResponse(DELIVERABLE) })

    await expect(requestPasswordReset('a@b.co.za')).resolves.toEqual({ emailDeliverable: true })
    expect(network.requestsTo(RESET_REQUEST_ROUTE)[0].body).toEqual({ email: 'a@b.co.za' })
  })

  it('posts a resend with no body', async () => {
    const network = mockApi({ [RESEND_ROUTE]: () => acceptedResponse(DELIVERABLE) })

    await expect(resendVerification()).resolves.toEqual({ emailDeliverable: true })
    expect(network.requestsTo(RESEND_ROUTE)[0].body).toBeUndefined()
  })

  it('refuses an answer that does not say whether the email can be delivered', async () => {
    mockApi({ [REGISTER_ROUTE]: () => acceptedResponse({ sent: true }) })

    const failure = await failureOf(registerCustomer(REGISTRATION))

    expect(failure.kind).toBe('malformed')
    expect(failure.detail).toContain('emailDeliverable')
  })
})

describe('the routes that take the token of a link', () => {
  it('sends the token in the body and never in the address', async () => {
    const network = mockApi({
      [VERIFY_ROUTE]: () => noContentResponse(),
      [RESET_COMPLETE_ROUTE]: () => noContentResponse(),
    })

    await expect(verifyEmail(LINK_TOKEN)).resolves.toBeUndefined()
    await expect(completePasswordReset(LINK_TOKEN, 'a-new-password')).resolves.toBeUndefined()

    const [verification] = network.requestsTo(VERIFY_ROUTE)
    const [completion] = network.requestsTo(RESET_COMPLETE_ROUTE)
    expect(verification.body).toEqual({ token: LINK_TOKEN })
    expect(completion.body).toEqual({ token: LINK_TOKEN, newPassword: 'a-new-password' })
    for (const request of network.requests) {
      expect(`${request.path}?${request.query.toString()}`).not.toContain(LINK_TOKEN)
    }
  })

  it('throws the 400 of a dead link with its type, so a screen can tell it apart', async () => {
    mockApi({ [VERIFY_ROUTE]: verificationLinkInvalid })

    const failure = await failureOf(verifyEmail(LINK_TOKEN))

    expect(failure.status).toBe(400)
    expect(problemTypeEndsWith(failure, VERIFICATION_LINK_INVALID)).toBe(true)
  })
})

describe('the profile routes', () => {
  it('reads the profile the API sends', async () => {
    mockApi({ [PROFILE_ROUTE]: () => jsonResponse(PROFILE) })

    await expect(getMyProfile()).resolves.toEqual(PROFILE)
  })

  it('patches with only what it was given, and reads the profile that comes back', async () => {
    const updated = { ...PROFILE, phone: '0835550199' }
    const network = mockApi({ [PROFILE_UPDATE_ROUTE]: () => jsonResponse(updated) })

    await expect(updateMyProfile({ phone: '0835550199' })).resolves.toEqual(updated)
    expect(network.requestsTo(PROFILE_UPDATE_ROUTE)[0].body).toEqual({ phone: '0835550199' })
  })

  it.each([
    ['a status the contract does not know', { accountStatus: 'SUSPENDED' }, 'accountStatus'],
    ['a customer type the contract does not know', { customerType: 'STAFF' }, 'customerType'],
    ['a discount that is a number', { tradeDiscountPercent: 10 }, 'tradeDiscountPercent'],
    ['a date that is not one', { memberSince: 'yesterday' }, 'memberSince'],
    ['a missing verification flag', { emailVerified: undefined }, 'emailVerified'],
  ])('refuses a profile with %s', async (_what, change, field) => {
    mockApi({ [PROFILE_ROUTE]: () => jsonResponse({ ...PROFILE, ...change }) })

    const failure = await failureOf(getMyProfile())

    expect(failure.kind).toBe('malformed')
    expect(failure.detail).toContain(field)
  })
})
