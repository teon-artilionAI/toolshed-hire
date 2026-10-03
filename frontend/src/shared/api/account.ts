/**
 * The registration, verification, password reset and profile routes.
 *
 * Seven calls. A visitor registers, confirms their email address from a link,
 * asks for a password reset link and chooses a new password from it. A signed
 * in person asks for the verification link again. A customer reads their own
 * profile and corrects it.
 *
 * Three of them answer the same way whether or not the email address has an
 * account. That is on purpose, and nothing here or above it may try to tell
 * the two apart.
 *
 * A token from a link passes through here once, in the body of a request. It
 * is never put in an address, and the client logs the method and the path of a
 * request and never its body, so the token reaches no log.
 *
 * The four public routes switch off the client's renewal rule. None of them
 * needs a session, so a refusal from one is never cured by a new token.
 */

import { api } from './client'
import type {
  AccountStatus,
  CompletePasswordResetRequest,
  CustomerType,
  EmailDelivery,
  IdDocumentType,
  MyProfile,
  PasswordResetRequest,
  RegisterRequest,
  UpdateMyProfileRequest,
  VerifyEmailRequest,
} from './contract'
import {
  readCount,
  readDate,
  readFlag,
  readNullableText,
  readObject,
  readOneOf,
  readPercent,
  readText,
} from './read'

const REGISTER_ENDPOINT = '/auth/register'
const VERIFICATION_ENDPOINT = '/auth/email-verification'
const VERIFICATION_RESEND_ENDPOINT = '/auth/email-verification/resend'
const RESET_REQUEST_ENDPOINT = '/auth/password-reset/request'
const RESET_COMPLETE_ENDPOINT = '/auth/password-reset/complete'
const PROFILE_ENDPOINT = '/me/profile'

/** The fewest characters a password may have. The API refuses a shorter one. */
export const MIN_PASSWORD_LENGTH = 12

/** How many characters of the identity document number are kept. */
export const ID_DOCUMENT_LAST_LENGTH = 4

/** How long a verification link works, in hours. */
export const VERIFICATION_LINK_HOURS = 24

/** How long a password reset link works, in minutes. */
export const RESET_LINK_MINUTES = 60

/** How the `type` of the 400 ends when a verification link is unknown, used or expired. */
export const VERIFICATION_LINK_INVALID = 'verification-link-invalid'

/** How the `type` of the 400 ends when a reset link is unknown, used or expired. */
export const RESET_LINK_INVALID = 'reset-link-invalid'

/** The identity documents the API accepts, in the order a menu lists them. */
export const ID_DOCUMENT_TYPES: readonly IdDocumentType[] = ['SA_ID', 'PASSPORT', 'DRIVING_LICENCE']

/** Whether a customer hires as a member of the public or as a trade account. */
export const CUSTOMER_TYPES: readonly CustomerType[] = ['INDIVIDUAL', 'TRADE']

/** Where a customer account can stand. */
export const ACCOUNT_STATUSES: readonly AccountStatus[] = ['ACTIVE', 'ON_HOLD', 'BLACKLISTED']

const PUBLIC_ROUTE = { skipSessionRenewal: true } as const

function readEmailDelivery(value: unknown, path: string): EmailDelivery {
  const record = readObject(value, path, 'an email delivery answer')
  return { emailDeliverable: readFlag(record, 'emailDeliverable', path) }
}

function readMyProfile(value: unknown, path: string): MyProfile {
  const record = readObject(value, path, 'a customer profile')
  return {
    fullName: readText(record, 'fullName', path),
    email: readText(record, 'email', path),
    emailVerified: readFlag(record, 'emailVerified', path),
    phone: readText(record, 'phone', path),
    customerType: readOneOf(record, 'customerType', path, CUSTOMER_TYPES),
    companyName: readNullableText(record, 'companyName', path),
    vatNumber: readNullableText(record, 'vatNumber', path),
    idDocumentType: readOneOf(record, 'idDocumentType', path, ID_DOCUMENT_TYPES),
    idDocumentLast4: readText(record, 'idDocumentLast4', path),
    billingAddressLine1: readText(record, 'billingAddressLine1', path),
    billingSuburb: readText(record, 'billingSuburb', path),
    billingCity: readText(record, 'billingCity', path),
    billingPostalCode: readText(record, 'billingPostalCode', path),
    accountStatus: readOneOf(record, 'accountStatus', path, ACCOUNT_STATUSES),
    tradeDiscountPercent: readPercent(record, 'tradeDiscountPercent', path),
    noShowCount: readCount(record, 'noShowCount', path),
    homeBranchCode: readText(record, 'homeBranchCode', path),
    memberSince: readDate(record, 'memberSince', path),
  }
}

/**
 * POST /api/auth/register. Always 202, whether or not the address is new.
 *
 * @throws ApiError with status 422 naming each refused field, and 429 when the
 *   caller must wait, with `retryAfterSeconds` saying for how long.
 */
export function registerCustomer(body: RegisterRequest): Promise<EmailDelivery> {
  return api.post(REGISTER_ENDPOINT, body, readEmailDelivery, PUBLIC_ROUTE)
}

/**
 * POST /api/auth/email-verification. 204 when the link was good.
 *
 * @param token The token from the link. It is sent once and kept nowhere.
 * @throws ApiError with status 400 and a type ending `verification-link-invalid`
 *   when the link is unknown, used or expired. The API does not say which.
 */
export function verifyEmail(token: string): Promise<void> {
  const body: VerifyEmailRequest = { token }
  return api.post(VERIFICATION_ENDPOINT, body, () => undefined, PUBLIC_ROUTE)
}

/**
 * POST /api/auth/email-verification/resend, for the signed in account.
 *
 * It does nothing for an account that is already verified, and answers the
 * same way.
 *
 * @throws ApiError with status 429 when the account has asked too often.
 */
export function resendVerification(): Promise<EmailDelivery> {
  return api.post(VERIFICATION_RESEND_ENDPOINT, undefined, readEmailDelivery)
}

/** POST /api/auth/password-reset/request. Always 202, whoever the address belongs to. */
export function requestPasswordReset(email: string): Promise<EmailDelivery> {
  const body: PasswordResetRequest = { email }
  return api.post(RESET_REQUEST_ENDPOINT, body, readEmailDelivery, PUBLIC_ROUTE)
}

/**
 * POST /api/auth/password-reset/complete. 204 when the password was changed,
 * and then every session of the account has been ended.
 *
 * @param token The token from the link. It is sent once and kept nowhere.
 * @throws ApiError with status 400 and a type ending `reset-link-invalid` when
 *   the link is unknown, used or expired, and 422 when the password is too short.
 */
export function completePasswordReset(token: string, newPassword: string): Promise<void> {
  const body: CompletePasswordResetRequest = { token, newPassword }
  return api.post(RESET_COMPLETE_ENDPOINT, body, () => undefined, PUBLIC_ROUTE)
}

/**
 * GET /api/me/profile. The signed in customer's own profile.
 *
 * @throws ApiError with status 404 when a customer account has no customer
 *   profile, and 403 for a member of staff, whose role the route does not
 *   admit. No staff screen asks for it.
 */
export function getMyProfile(signal?: AbortSignal): Promise<MyProfile> {
  return api.get(PROFILE_ENDPOINT, readMyProfile, { signal })
}

/**
 * PATCH /api/me/profile. Sends only what changed and gets the whole profile back.
 *
 * @throws ApiError with status 422 naming each refused field.
 */
export function updateMyProfile(changes: UpdateMyProfileRequest): Promise<MyProfile> {
  return api.patch(PROFILE_ENDPOINT, changes, readMyProfile)
}
