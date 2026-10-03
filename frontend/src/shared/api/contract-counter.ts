/**
 * The counter wire types, written by hand.
 *
 * The customer lookup, the walk in, the checkout and the rental routes are
 * agreed and are not in the OpenAPI document yet, so these are the only wire
 * types not built from the generated file. Every name in them is the one the
 * agreed contract uses. Once the routes are in the document, run
 * `npm run api:types` and rebuild these from the generated file, the way
 * contract-booking.ts does, so a route the backend changes stops the
 * application compiling.
 *
 * The words a charge, a rental or an item can be in are the backend's own
 * enumerations, which the contract only gives examples of.
 *
 * Nothing imports this file but contract.ts. The application imports these
 * types from there, like every other wire type.
 */

import type { AccountStatus, CustomerType, IdDocumentType } from './contract-account'
import type { ReservationStatus } from './contract-booking'
import type { IsoDate, IsoTimestamp, Money } from './contract-kit'

/**
 * One customer as the counter sees them, from the lookup, the walk in and the
 * single customer route.
 *
 * `email` is null for a walk in, who has no login. `tradeDiscountPercent` is a
 * string with two decimals like the money, for example "10.00".
 */
export interface CustomerSummary {
  id: string
  displayName: string
  email: string | null
  phone: string
  hasLogin: boolean
  emailVerified: boolean
  customerType: CustomerType
  companyName: string | null
  idDocumentType: IdDocumentType
  idDocumentLast4: string
  billingSuburb: string
  billingCity: string
  accountStatus: AccountStatus
  tradeDiscountPercent: string
  noShowCount: number
  homeBranchCode: string
}

/** `GET /api/customers`. Best match first. */
export interface CustomerPage {
  items: CustomerSummary[]
  page: number
  pageSize: number
  total: number
}

/**
 * The query `GET /api/customers` accepts.
 *
 * `q` is required and is two to eighty characters. It is matched against the
 * name, the phone number and the email address at once.
 */
export interface CustomerSearchQuery {
  q: string
  page?: number
  pageSize?: number
}

/**
 * The body `POST /api/customers` accepts. A walk in, with no login.
 *
 * `idDocumentLast4` is exactly four letters or digits. The whole document
 * number is never sent. `companyName` is required for a trade account and
 * null otherwise. `branchCode` is null for counter staff, whose own branch is
 * used, and names the branch for an administrator, who has none.
 */
export interface RegisterWalkInRequest {
  displayName: string
  phone: string
  idDocumentType: IdDocumentType
  idDocumentLast4: string
  billingAddressLine1: string
  billingSuburb: string
  billingCity: string
  billingPostalCode: string
  customerType: CustomerType
  companyName: string | null
  vatNumber: string | null
  branchCode: string | null
}

/** How a unit looks, A being the best. The backend calls this `ConditionGrade`. */
export type ConditionGrade = 'A' | 'B' | 'C'

/** Who is collecting, as the checkout route names them. */
export interface CheckoutCustomer {
  id: string
  displayName: string
  phone: string
  idDocumentType: IdDocumentType
  idDocumentLast4: string
  accountStatus: AccountStatus
}

/**
 * One unit set aside for the reservation, ready to hand over.
 *
 * `conditionGrade` is the grade the unit has now. `hourMeter` is the last
 * reading on file, and null for a unit with no hour meter.
 */
export interface CheckoutUnit {
  allocationId: string
  assetTag: string
  modelName: string
  modelSlug: string
  conditionGrade: ConditionGrade
  hourMeter: number | null
  depositPerUnit: Money
}

/**
 * `GET /api/reservations/{id}/checkout`. What the counter needs to hand the
 * equipment over.
 *
 * `canCheckOut` is the server's answer for this person at this moment. When
 * it is false, `refusal` is the sentence that says why. `rentalId` is set once
 * the reservation has been collected. Every figure is the server's.
 */
export interface ReservationCheckout {
  reservationId: string
  reference: string
  status: ReservationStatus
  branchCode: string
  branchName: string
  customer: CheckoutCustomer
  from: IsoDate
  to: IsoDate
  hireDays: number
  units: CheckoutUnit[]
  hireTotalIncVat: Money
  depositTotal: Money
  canCheckOut: boolean
  refusal: string | null
  rentalId: string | null
}

/** What was recorded about one unit as it went out. */
export interface CheckoutItemRequest {
  allocationId: string
  conditionOut: ConditionGrade
  /** At most 200 characters, or null when nothing was noted. */
  accessoriesOut: string | null
  /** A whole number of hours, or null for a unit with no hour meter. */
  hourMeterOut: number | null
}

/**
 * The body `POST /api/reservations/{id}/checkout` accepts.
 *
 * Every allocation of the reservation exactly once. `agreementSigned` can only
 * be true, and the API refuses anything else with a 422.
 */
export interface CheckoutRequest {
  items: CheckoutItemRequest[]
  agreementSigned: true
}

/** Where a hire stands. */
export type RentalStatus = 'OPEN' | 'OVERDUE' | 'PARTIALLY_RETURNED' | 'RETURNED' | 'SETTLED'

/** Whether a returned item still needs its damage looked at. */
export type DamageAssessment = 'NOT_NEEDED' | 'REQUIRED' | 'DONE'

/** What the deposit is still waiting on before it can be settled. */
export type SettlementWaitingOn = 'ITEMS_OUT' | 'DAMAGE_ASSESSMENT' | 'BALANCE_PAYMENT'

/** What a charge is for. */
export type ChargeType =
  | 'HIRE'
  | 'DEPOSIT_HOLD'
  | 'DEPOSIT_RELEASE'
  | 'DEPOSIT_FORFEIT'
  | 'LATE_FEE'
  | 'DAMAGE_RECOVERY'
  | 'CLEANING'
  | 'ADJUSTMENT'

/** Where a charge stands. A settled charge is never edited. */
export type ChargeStatus = 'PENDING' | 'SETTLED' | 'WAIVED' | 'REVERSED'

/**
 * One unit on a hire.
 *
 * `assetTag` is null for a customer, who is never shown one. `daysLateToday`
 * and `lateFeeToday` are what the late fee policy gives if the item came back
 * today, worked out on the server.
 */
export interface RentalItem {
  id: string
  assetTag: string | null
  modelName: string
  modelSlug: string
  conditionOut: ConditionGrade
  conditionIn: ConditionGrade | null
  hourMeterOut: number | null
  hourMeterIn: number | null
  accessoriesOut: string | null
  accessoriesIn: string | null
  returnedAt: IsoTimestamp | null
  daysLate: number
  lateFeePerDay: Money
  daysLateToday: number
  lateFeeToday: Money
  damageAssessment: DamageAssessment
}

/** One charge on a hire. A release of a deposit is a negative amount. */
export interface RentalCharge {
  id: string
  type: ChargeType
  description: string
  amountExVat: Money
  vatRate: string
  vatAmount: Money
  amountIncVat: Money
  status: ChargeStatus
  raisedAt: IsoTimestamp
  rentalItemId: string | null
}

/** One hire, from the checkout and the rental routes. Every figure is the server's. */
export interface Rental {
  id: string
  reference: string
  status: RentalStatus
  reservationId: string
  reservationReference: string
  branchCode: string
  branchName: string
  customerProfileId: string
  customerName: string
  customerPhone: string
  from: IsoDate
  dueBackOn: IsoDate
  checkedOutAt: IsoTimestamp
  returnedAt: IsoTimestamp | null
  items: RentalItem[]
  charges: RentalCharge[]
  depositHeld: Money
  depositWithheld: Money
  depositRefunded: Money
  balanceDue: Money
  settledAt: IsoTimestamp | null
  agreementSigned: boolean
  canReturn: boolean
  settlementWaitingOn: SettlementWaitingOn | null
}
