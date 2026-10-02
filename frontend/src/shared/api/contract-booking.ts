/**
 * The reservation wire types.
 *
 * They are built from the generated schema the way every other wire type is,
 * so a route, a field or a query parameter the backend changes stops the
 * application compiling until it follows. They live apart from contract.ts
 * only to keep each file a size that can be read in one sitting.
 *
 * Nothing imports this file but contract.ts. The application imports these
 * types from there, like every other wire type.
 */

import type {
  BodyOf,
  IsoDate,
  IsoTimestamp,
  JsonOf,
  Money,
  Paths,
  QueryOf,
  Refine,
  Schemas,
} from './contract-kit'

/** Where a reservation stands. The server moves it and the browser only reads it. */
export type ReservationStatus = Schemas['ReservationStatus']

/**
 * One model on a reservation, with the rates it was priced at.
 *
 * `allocatedCount` is how many units are set aside for the line. It is zero
 * until the reservation is held. `assetTags` is always empty for a customer,
 * who is never shown a tag.
 */
export type ReservationLine = Refine<
  Schemas['ReservationLineResponse'],
  { dailyRate: Money; weeklyRate: Money; depositPerUnit: Money; lineSubtotalExVat: Money }
>

/**
 * One reservation, as every reservation route answers.
 *
 * Every figure is the server's. `subtotalExVat` is the hire after the trade
 * discount, and the VAT is worked out on it, so the two add up to
 * `estimatedTotalIncVat`. The deposit is not in that total. `discountPercent`
 * is a string with two decimals like the money, for example "10.00".
 *
 * `to` is the return day, which is not charged. `holdExpiresAt` is null unless
 * the reservation is held.
 *
 * `canHold`, `canConfirm` and `canCancel` are worked out on the server as
 * well, for the person asking and the moment they asked. A screen offers an
 * action from its flag and from nothing else.
 */
export type Reservation = Refine<
  JsonOf<Paths['/api/reservations/{id}']['get']>,
  {
    from: IsoDate
    to: IsoDate
    lines: ReservationLine[]
    subtotalExVat: Money
    vatAmount: Money
    estimatedTotalIncVat: Money
    depositTotal: Money
    holdExpiresAt: IsoTimestamp | null
    confirmedAt: IsoTimestamp | null
    cancelledAt: IsoTimestamp | null
    createdAt: IsoTimestamp
  }
>

/** One line of the body `POST /api/reservations` accepts. */
export type ReservationLineRequest = Schemas['ReservationLineRequest']

/**
 * The body `POST /api/reservations` accepts.
 *
 * `customerProfileId` is for staff booking on behalf of a customer. A customer
 * booking for themselves leaves it null, and the notes too.
 */
export type CreateReservationRequest = Refine<
  BodyOf<Paths['/api/reservations']['post']>,
  { from: IsoDate; to: IsoDate }
>

/**
 * The body `POST /api/reservations/{id}/cancellation` accepts. The reason is
 * optional and is at most 200 characters.
 *
 * The route also takes no body at all, so the generated operation marks the
 * body as optional and `BodyOf` cannot read it. I take the schema by its name.
 */
export type CancelReservationRequest = Schemas['CancellationRequest']

/**
 * The query `GET /api/reservations` accepts.
 *
 * `status` is one status or none, and the API has no way to ask for every
 * status but one. `page` counts from 1, and the API uses a page size of 20
 * when none is named. `customerProfileId` and `branch` are for staff. A
 * customer only ever gets their own reservations, and is refused with a 403
 * for naming either, so the customer screens leave both out.
 */
export type ReservationListQuery = QueryOf<Paths['/api/reservations']['get']>

/** `GET /api/reservations`. Newest first. */
export type ReservationPage = Refine<
  JsonOf<Paths['/api/reservations']['get']>,
  { items: Reservation[] }
>
