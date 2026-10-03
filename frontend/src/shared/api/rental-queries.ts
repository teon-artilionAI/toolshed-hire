/**
 * The hire reads, as cached queries.
 *
 * A hire the counter reads and the counter's lists of hires start with the
 * rentals segment. The customer's own hires start with the account segment,
 * because they are about the signed in person's own account. query-client.ts
 * treats both as never fresh, so a cached hire is always asked for again when a
 * screen uses it.
 *
 * The writes are not here. A screen calls the functions in rentals.ts for
 * those, one request for each press of a button, and then hands the answer to
 * `rememberRental`.
 */

import { queryOptions } from '@tanstack/react-query'
import type { QueryClient } from '@tanstack/react-query'
import type { MyRentalsQuery, Rental, RentalListQuery } from './contract'
import { ACCOUNT_KEY, ASSETS_KEY, COUNTER_KEY, RENTALS_KEY, RESERVATIONS_KEY } from './query-client'
import { getRental, listMyRentals, listRentals } from './rentals'

const DETAIL_SEGMENT = 'detail'
const LIST_SEGMENT = 'list'
const MY_RENTALS_SEGMENT = 'rentals'

export const rentalQueries = {
  /** One hire, by its key or its reference. */
  detail: (idOrReference: string) =>
    queryOptions({
      queryKey: [RENTALS_KEY, DETAIL_SEGMENT, idOrReference],
      queryFn: ({ signal }) => getRental(idOrReference, signal),
    }),

  /** One page of the hires that match, most overdue first. */
  list: (query: RentalListQuery) =>
    queryOptions({
      queryKey: [RENTALS_KEY, LIST_SEGMENT, query],
      queryFn: ({ signal }) => listRentals(query, signal),
    }),

  /** One page of the signed in customer's own hires, newest first. */
  mine: (query: MyRentalsQuery) =>
    queryOptions({
      queryKey: [ACCOUNT_KEY, MY_RENTALS_SEGMENT, query],
      queryFn: ({ signal }) => listMyRentals(query, signal),
    }),
}

/**
 * Put the hire a write answered with into the cache, and mark everything it
 * changed as out of date.
 *
 * The hire is kept under its key and its reference, because a screen can be
 * opened by either. A list is not patched. It is asked for again, because only
 * the server knows its order. A return also moves the reservation on, frees or
 * quarantines units and changes the counter's day, so those are asked for again
 * as well.
 */
export function rememberRental(client: QueryClient, rental: Rental): void {
  client.setQueryData(rentalQueries.detail(rental.id).queryKey, rental)
  client.setQueryData(rentalQueries.detail(rental.reference).queryKey, rental)
  void client.invalidateQueries({ queryKey: [RENTALS_KEY, LIST_SEGMENT] })
  void client.invalidateQueries({ queryKey: [COUNTER_KEY] })
  void client.invalidateQueries({ queryKey: [RESERVATIONS_KEY] })
  void client.invalidateQueries({ queryKey: [ASSETS_KEY] })
}

/** Mark one hire as out of date, so the screen showing it reads it again. A
 *  refusal that says the hire moved on since it was read calls this. */
export function forgetRental(client: QueryClient, idOrReference: string): void {
  void client.invalidateQueries({ queryKey: rentalQueries.detail(idOrReference).queryKey })
}
