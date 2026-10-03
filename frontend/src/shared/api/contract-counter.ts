/**
 * The counter wire types.
 *
 * The customer lookup, the walk in, the checkout and the rental routes. They
 * are built from the generated schema the way every other wire type is, so a
 * route, a field or a value the backend changes stops the application
 * compiling until it follows. They live apart from contract.ts only to keep
 * each file a size that can be read in one sitting.
 *
 * Nothing imports this file but contract.ts. The application imports these
 * types from there, like every other wire type.
 */

import type {
  BodyOf,
  CreatedJsonOf,
  IsoDate,
  IsoTimestamp,
  JsonOf,
  Money,
  Paths,
  QueryOf,
  Refine,
  Schemas,
} from './contract-kit'

/**
 * One customer as the counter sees them, from the lookup, the walk in and the
 * single customer route.
 *
 * `email` is null for a walk in, who has no login. `tradeDiscountPercent` is a
 * string with two decimals like the money, for example "10.00".
 */
export type CustomerSummary = JsonOf<Paths['/api/customers/{id}']['get']> &
  CreatedJsonOf<Paths['/api/customers']['post']>

/** `GET /api/customers`. Best match first. */
export type CustomerPage = Refine<JsonOf<Paths['/api/customers']['get']>, { items: CustomerSummary[] }>

/**
 * The query `GET /api/customers` accepts.
 *
 * `q` is required and is two to eighty characters once the spaces around it
 * are gone. It is matched against the name, the phone number and the email
 * address at once.
 */
export type CustomerSearchQuery = QueryOf<Paths['/api/customers']['get']>

/**
 * The body `POST /api/customers` accepts. A walk in, with no login.
 *
 * `idDocumentLast4` is exactly four letters or digits. The whole document
 * number is never sent. `companyName` is required for a trade account and
 * null otherwise. `branchCode` is null for counter staff, whose own branch is
 * used, and names the branch for an administrator, who has none. The API
 * refuses a member it does not know with a 422.
 */
export type RegisterWalkInRequest = BodyOf<Paths['/api/customers']['post']>

/** How a unit looks, A being the best. */
export type ConditionGrade = Schemas['ConditionGrade']

/** Who is collecting, as the checkout route names them. */
export type CheckoutCustomer = Schemas['CheckoutCustomerResponse']

/**
 * One unit set aside for the reservation, ready to hand over.
 *
 * `conditionGrade` is the grade the unit has now. `hourMeter` is the last
 * reading on file, and null for a unit with no hour meter.
 */
export type CheckoutUnit = Refine<Schemas['CheckoutUnitResponse'], { depositPerUnit: Money }>

/**
 * `GET /api/reservations/{id}/checkout`. What the counter needs to hand the
 * equipment over.
 *
 * `canCheckOut` is the server's answer for this person at this moment. When
 * it is false, `refusal` is the sentence that says why. `rentalId` is set once
 * the reservation has been collected. Every figure is the server's.
 */
export type ReservationCheckout = Refine<
  JsonOf<Paths['/api/reservations/{id}/checkout']['get']>,
  {
    from: IsoDate
    to: IsoDate
    units: CheckoutUnit[]
    hireTotalIncVat: Money
    depositTotal: Money
  }
>

/**
 * What was recorded about one unit as it went out.
 *
 * `accessoriesOut` is at most 200 characters and `hourMeterOut` is a whole
 * number of hours. Each is null when there is nothing to record, and the
 * screens always send both so the body reads the same for every unit.
 */
export type CheckoutItemRequest = Refine<
  Schemas['CheckoutItemRequest'],
  { accessoriesOut: string | null; hourMeterOut: number | null }
>

/**
 * The body `POST /api/reservations/{id}/checkout` accepts.
 *
 * Every allocation of the reservation exactly once. The generated type lets
 * `agreementSigned` be false, and the API refuses that with a 422, so here it
 * can only be true.
 */
export type CheckoutRequest = Refine<
  BodyOf<Paths['/api/reservations/{id}/checkout']['post']>,
  { items: CheckoutItemRequest[]; agreementSigned: true }
>

/** Where a hire stands. */
export type RentalStatus = Schemas['RentalStatus']

/** Whether a returned item still needs its damage looked at. */
export type DamageAssessment = Schemas['DamageAssessment']

/**
 * What the deposit is still waiting on before it can be settled. It is
 * `ITEMS_OUT` while any unit is out, so a hire that has just opened says so,
 * and null once nothing is waiting. The backend calls this `SettlementWait`.
 */
export type SettlementWaitingOn = Schemas['SettlementWait']

/** What a charge is for. */
export type ChargeType = Schemas['ChargeType']

/** Where a charge stands. A settled charge is never edited. */
export type ChargeStatus = Schemas['ChargeStatus']

/**
 * One unit on a hire.
 *
 * `assetTag` is null for a customer, who is never shown one. `daysLateToday`
 * and `lateFeeToday` are what the late fee policy gives if the item came back
 * today, worked out on the server.
 */
export type RentalItem = Refine<
  Schemas['RentalItemResponse'],
  { returnedAt: IsoTimestamp | null; lateFeePerDay: Money; lateFeeToday: Money }
>

/** One charge on a hire. A release of a deposit is a negative amount. */
export type RentalCharge = Refine<
  Schemas['ChargeResponse'],
  { amountExVat: Money; vatAmount: Money; amountIncVat: Money; raisedAt: IsoTimestamp }
>

/**
 * One hire, from the checkout and the rental routes. Every figure is the
 * server's.
 *
 * The checkout answers 201 with the new hire, and 200 with the hire it made
 * before when the reservation is already out. The document describes only the
 * 201 body, so that and the rental route are what this is built from.
 */
export type Rental = Refine<
  JsonOf<Paths['/api/rentals/{id}']['get']> &
    CreatedJsonOf<Paths['/api/reservations/{id}/checkout']['post']>,
  {
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
  }
>
