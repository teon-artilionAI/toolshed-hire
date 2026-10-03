/**
 * The returns and settlement wire types.
 *
 * Taking equipment back, recording a unit as lost, paying a balance, and the
 * two lists of hires, one for the counter and one for the customer. Every one
 * of these routes answers with a `Rental`, or a page of them, and that type is
 * in contract-counter.ts.
 *
 * They are built from the generated schema the way every other wire type is,
 * so a route, a field or a value the backend changes stops the application
 * compiling until it follows. They live apart from contract.ts only to keep
 * each file a size that can be read in one sitting.
 *
 * Nothing imports this file but contract.ts. The application imports these
 * types from there, like every other wire type.
 */

import type { BodyOf, JsonOf, Paths, QueryOf, Refine, Schemas } from './contract-kit'
import type { Rental } from './contract-counter'

/**
 * One unit coming back, in the body of `POST /api/rentals/{id}/returns`.
 *
 * `hourMeterIn` is a whole number of hours, and null for a unit with no meter.
 * `accessoriesIn` is at most 200 characters and `notes` at most 1000. Each is
 * null when there is nothing to record. The generated type lets the three be
 * left out, and the screens always send every member so the body reads the
 * same for each unit, so here each is present. `flaggedForDamage` sends a unit
 * to quarantine even when its grade is no worse than it went out, once the
 * damage change lands. Until then the API accepts it and puts every unit back
 * on the shelf.
 */
export type ReturnItemRequest = Refine<
  Schemas['ReturnItemRequest'],
  { hourMeterIn: number | null; accessoriesIn: string | null; notes: string | null }
>

/**
 * The body `POST /api/rentals/{id}/returns` accepts. One or more units that
 * are still out, each once. The API refuses a unit already back with a 409.
 * It refuses a unit listed twice, a unit not on the hire, or a meter that reads
 * less than it did going out, with a 422 that names the field.
 */
export type ReturnRequest = Refine<
  BodyOf<Paths['/api/rentals/{id}/returns']['post']>,
  { items: ReturnItemRequest[] }
>

/**
 * The body `POST /api/rentals/{id}/balance-payment` accepts. The reference of
 * the payment the customer made at the counter, 1 to 40 characters once the
 * spaces around it are gone. The payment is simulated, and nothing reaches a
 * bank.
 */
export type BalancePaymentRequest = BodyOf<Paths['/api/rentals/{id}/balance-payment']['post']>

/**
 * The query `GET /api/rentals` accepts, for staff.
 *
 * Every filter may be left out, and the API reads a null one as left out.
 * `overdueOnly` keeps only the hires with a unit out past its due date.
 * `page` counts from 1 and `pageSize` is 1 to 50. The generated type lets the
 * page and its size be left out, and the screens always send both, so here
 * they are required.
 */
export type RentalListQuery = Refine<QueryOf<Paths['/api/rentals']['get']>, { page: number; pageSize: number }>

/**
 * The query `GET /api/me/rentals` accepts. The customer's own hires only. The
 * screen always sends the page and its size, so here both are required.
 */
export type MyRentalsQuery = Refine<QueryOf<Paths['/api/me/rentals']['get']>, { page: number; pageSize: number }>

/**
 * A page of hires, from `GET /api/rentals` for staff, most overdue first and
 * then newest, and from `GET /api/me/rentals` for a customer, newest first.
 * A customer's hires carry no asset tag on any unit. Both routes send the one
 * shape, so this is built from the two of them.
 */
export type RentalPage = Refine<
  JsonOf<Paths['/api/rentals']['get']> & JsonOf<Paths['/api/me/rentals']['get']>,
  { items: Rental[] }
>
