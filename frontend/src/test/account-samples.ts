/**
 * Sample answers for the registration and account routes, shaped the way the
 * contract describes them.
 *
 * A customer profile, the two answers about whether an email can be
 * delivered, the refusals the routes send, and the routes themselves by name.
 * They are test data only. No screen imports them.
 */

import type { EmailDelivery, MyProfile } from '../shared/api/contract'
import { problemResponse } from './api-mock'
import { CUSTOMER } from './session-samples'

export const REGISTER_ROUTE = 'POST /api/auth/register'
export const VERIFY_ROUTE = 'POST /api/auth/email-verification'
export const RESEND_ROUTE = 'POST /api/auth/email-verification/resend'
export const RESET_REQUEST_ROUTE = 'POST /api/auth/password-reset/request'
export const RESET_COMPLETE_ROUTE = 'POST /api/auth/password-reset/complete'
export const PROFILE_ROUTE = 'GET /api/me/profile'
export const PROFILE_UPDATE_ROUTE = 'PATCH /api/me/profile'

/** A token as a link carries it. Long and odd on purpose, so a test can search
 *  for it and know a match is no accident. */
export const LINK_TOKEN = 'link-token-4b7e91c2d5a8f306'

export const DELIVERABLE: EmailDelivery = { emailDeliverable: true }
export const NOT_DELIVERABLE: EmailDelivery = { emailDeliverable: false }

/** The profile of the signed in sample customer, with a confirmed address. */
export const PROFILE: MyProfile = {
  fullName: CUSTOMER.fullName,
  email: CUSTOMER.email,
  emailVerified: true,
  phone: '0824417719',
  customerType: 'INDIVIDUAL',
  companyName: null,
  vatNumber: null,
  idDocumentType: 'SA_ID',
  idDocumentLast4: '5083',
  billingAddressLine1: '12 Loop Street',
  billingSuburb: 'Gardens',
  billingCity: 'Cape Town',
  billingPostalCode: '8001',
  accountStatus: 'ACTIVE',
  tradeDiscountPercent: '0.00',
  noShowCount: 0,
  homeBranchCode: 'CBD',
  memberSince: '2026-02-14',
}

export const UNVERIFIED_PROFILE: MyProfile = { ...PROFILE, emailVerified: false }

/** The 400 a verification link gets when it is unknown, used or expired. */
export function verificationLinkInvalid(): Response {
  return problemResponse(400, {
    slug: 'verification-link-invalid',
    detail: 'The verification link is not valid.',
  })
}

/** The 400 a reset link gets when it is unknown, used or expired. */
export function resetLinkInvalid(): Response {
  return problemResponse(400, { slug: 'reset-link-invalid', detail: 'The reset link is not valid.' })
}

/** The 429 a throttled route answers with, naming the wait in seconds. */
export function throttled(retryAfterSeconds: number): Response {
  return problemResponse(429, {
    slug: 'too-many-attempts',
    detail: 'Too many attempts.',
    headers: { 'Retry-After': String(retryAfterSeconds) },
  })
}

/** The 422 a route answers with, naming each refused member of the body. */
export function refusedFields(fields: Record<string, string>): Response {
  return problemResponse(422, {
    slug: 'validation-error',
    detail: 'The request was not valid.',
    errors: {
      fields: Object.fromEntries(
        Object.entries(fields).map(([name, message]) => [`body.${name}`, message]),
      ),
    },
  })
}
