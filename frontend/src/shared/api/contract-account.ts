/**
 * The registration and account wire types.
 *
 * They are built from the generated schema the way every other wire type is,
 * so a route, a field or a value the backend changes stops the application
 * compiling until it follows. They live apart from contract.ts only to keep
 * each file a size that can be read in one sitting.
 *
 * Nothing imports this file but contract.ts. The application imports these
 * types from there, like every other wire type.
 */

import type { AcceptedJsonOf, BodyOf, IsoDate, JsonOf, Paths, Refine, Schemas } from './contract-kit'

/** The identity documents the counter accepts. The backend calls this `IdDocType`. */
export type IdDocumentType = Schemas['IdDocType']

/** Whether a customer hires as a member of the public or as a trade account. */
export type CustomerType = Schemas['CustomerType']

/** Where a customer account stands. Only the branch changes it. */
export type AccountStatus = Schemas['AccountStatus']

/**
 * The body `POST /api/auth/register` accepts.
 *
 * `idDocumentLast4` is exactly four letters or digits. The whole document
 * number is never sent. `acceptsPrivacyNotice` can only be true, and the
 * generated type says so. The API refuses a member it does not know with a
 * 422, so nothing else may be added here.
 */
export type RegisterRequest = BodyOf<Paths['/api/auth/register']['post']>

/**
 * What register, the resend of a verification link and a password reset
 * request all answer with, under a 202.
 *
 * `emailDeliverable` is false when this environment only delivers email to one
 * address and the one in question is not it. It says nothing about whether the
 * address has an account.
 */
export type EmailDelivery = AcceptedJsonOf<Paths['/api/auth/register']['post']> &
  AcceptedJsonOf<Paths['/api/auth/email-verification/resend']['post']> &
  AcceptedJsonOf<Paths['/api/auth/password-reset/request']['post']>

/** The body `POST /api/auth/email-verification` accepts. */
export type VerifyEmailRequest = BodyOf<Paths['/api/auth/email-verification']['post']>

/** The body `POST /api/auth/password-reset/request` accepts. */
export type PasswordResetRequest = BodyOf<Paths['/api/auth/password-reset/request']['post']>

/** The body `POST /api/auth/password-reset/complete` accepts. */
export type CompletePasswordResetRequest = BodyOf<Paths['/api/auth/password-reset/complete']['post']>

/**
 * `GET /api/me/profile`, and what `PATCH /api/me/profile` answers with.
 *
 * `tradeDiscountPercent` is a string with two decimals like the money, for
 * example "10.00". `companyName` and `vatNumber` are null when the customer
 * gave none.
 */
export type MyProfile = Refine<
  JsonOf<Paths['/api/me/profile']['get']> & JsonOf<Paths['/api/me/profile']['patch']>,
  { memberSince: IsoDate }
>

/**
 * The body `PATCH /api/me/profile` accepts. Any of these and nothing else.
 *
 * A member that is left out is left as it is. The API refuses any other
 * member with a 422 that names it.
 *
 * The generated type lets every member be null, because the backend reads a
 * missing member and a null one the same way. Only `companyName` and
 * `vatNumber` mean anything as null, which is how they are cleared. The other
 * six are required on a profile, so the screens send them as text or not at
 * all, and here they can only be text.
 */
export type UpdateMyProfileRequest = Refine<
  BodyOf<Paths['/api/me/profile']['patch']>,
  {
    fullName?: string
    phone?: string
    billingAddressLine1?: string
    billingSuburb?: string
    billingCity?: string
    billingPostalCode?: string
  }
>
