/**
 * The reservation reads, as cached queries.
 *
 * Every key starts with the reservations segment, and query-client.ts treats
 * anything under it as never fresh. A hold lapses by itself and the counter
 * can move a booking on, so a cached reservation is always asked for again
 * when a screen uses it.
 *
 * The writes are not here. A screen calls the functions in reservations.ts for
 * those, one request for each press of a button, and then tells the cache
 * what changed with `rememberReservation`.
 */

import { queryOptions } from '@tanstack/react-query'
import type { QueryClient } from '@tanstack/react-query'
import type { Reservation, ReservationListQuery } from './contract'
import { RESERVATIONS_KEY } from './query-client'
import { getReservation, listReservations } from './reservations'

const LIST_SEGMENT = 'list'
const DETAIL_SEGMENT = 'detail'

export const reservationQueries = {
  /** One page of the caller's own reservations, newest first. */
  list: (query: ReservationListQuery) =>
    queryOptions({
      queryKey: [RESERVATIONS_KEY, LIST_SEGMENT, query],
      queryFn: ({ signal }) => listReservations(query, signal),
    }),

  /** One reservation, by its UUID or its reference. */
  detail: (idOrReference: string) =>
    queryOptions({
      queryKey: [RESERVATIONS_KEY, DETAIL_SEGMENT, idOrReference],
      queryFn: ({ signal }) => getReservation(idOrReference, signal),
    }),
}

/**
 * Put the answer of a write into the cache, and mark every list as out of date.
 *
 * A reservation can be asked for by its UUID or by its reference, so the
 * answer is kept under both. A list is not patched. It is asked for again the
 * next time a screen shows it, because only the server knows its order and
 * which page the reservation now falls on.
 */
export function rememberReservation(client: QueryClient, reservation: Reservation): void {
  client.setQueryData(reservationQueries.detail(reservation.id).queryKey, reservation)
  client.setQueryData(reservationQueries.detail(reservation.reference).queryKey, reservation)
  void client.invalidateQueries({ queryKey: [RESERVATIONS_KEY, LIST_SEGMENT] })
}
