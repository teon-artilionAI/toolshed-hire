/**
 * The registration and account wire types.
 *
 * These are the one set of wire types I wrote by hand. The routes they
 * describe are agreed and are being built, and they are not in the OpenAPI
 * document yet, so there is nothing to generate them from. Every name, every
 * member and every word in a union below is the one the agreed contract uses.
 * Once the routes are in the document these become types built from the
 * generated schema, the way contract-booking.ts builds the reservation types,
 * and a name that drifted stops the application compiling.
 *
 * Nothing imports this file but contract.ts. The application imports these
 * types from there, like every other wire type.
 */

import type { IsoDate } from './contract-kit'

/** The identity documents the counter accepts. */
export type IdDocumentType = 'SA_ID' | 'PASSPORT' | 'DRIVING_LICENCE'

/** Whether a customer hires as a member of the public or as a trade account. */
export type CustomerType = 'INDIVIDUAL' | 'TRADE'

/** Where a customer account stands. Only the branch changes it. */
export type AccountStatus = 'ACTIVE' | 'ON_HOLD' | 'BLACKLISTED'

/**
 * The body `POST /api/auth/register` accepts.
 *
 * `idDocumentLast4` is exactly four letters or digits. The whole document
 * number is never sent. `acceptsPrivacyNotice` must be true. The API refuses a
 * member it does not know with a 422, so nothing else may be added here.
 */
export interface RegisterRequest {
  email: string
  password: string
  fullName: string
  phone: string
  idDocumentType: IdDocumentType
  idDocumentLast4: string
  billingAddressLine1: string
  billingSuburb: string
  billingCity: string
  billingPostalCode: string
  homeBranchCode: string
  acceptsPrivacyNotice: boolean
}

/**
 * What register, the resend of a verification link and a password reset
 * request all answer with, under a 202.
 *
 * `emailDeliverable` is false when this environment only delivers email to one
 * address and the one in question is not it. It says nothing about whether the
 * address has an account.
 */
export interface EmailDelivery {
  emailDeliverable: boolean
}

/** The body `POST /api/auth/email-verification` accepts. */
export interface VerifyEmailRequest {
  token: string
}

/** The body `POST /api/auth/password-reset/request` accepts. */
export interface PasswordResetRequest {
  email: string
}

/** The body `POST /api/auth/password-reset/complete` accepts. */
export interface CompletePasswordResetRequest {
  token: string
  newPassword: string
}

/**
 * `GET /api/me/profile`, and what `PATCH /api/me/profile` answers with.
 *
 * `tradeDiscountPercent` is a string with two decimals like the money, for
 * example "10.00". `companyName` and `vatNumber` are null when the customer
 * gave none.
 */
export interface MyProfile {
  fullName: string
  email: string
  emailVerified: boolean
  phone: string
  customerType: CustomerType
  companyName: string | null
  vatNumber: string | null
  idDocumentType: IdDocumentType
  idDocumentLast4: string
  billingAddressLine1: string
  billingSuburb: string
  billingCity: string
  billingPostalCode: string
  accountStatus: AccountStatus
  tradeDiscountPercent: string
  noShowCount: number
  homeBranchCode: string
  memberSince: IsoDate
}

/**
 * The body `PATCH /api/me/profile` accepts. Any of these and nothing else.
 *
 * A member that is left out is left as it is. The API refuses any other
 * member with a 422 that names it.
 */
export interface UpdateMyProfileRequest {
  fullName?: string
  phone?: string
  billingAddressLine1?: string
  billingSuburb?: string
  billingCity?: string
  billingPostalCode?: string
  companyName?: string | null
  vatNumber?: string | null
}
