/**
 * The counter's reads, as cached queries.
 *
 * A customer key starts with the customers segment and a checkout key with the
 * reservations segment, and query-client.ts treats both as never fresh. An
 * account can be put on hold at another counter, and a reservation can be
 * collected a moment after it was read, so a cached answer is always asked for
 * again when a screen uses it.
 *
 * The writes are not here. A screen calls the functions in customers.ts and
 * checkout.ts for those, one request for each press of a button, and then
 * tells the cache what changed.
 */

import { queryOptions } from '@tanstack/react-query'
import type { QueryClient } from '@tanstack/react-query'
import { getCheckout } from './checkout'
import type { CustomerSearchQuery, CustomerSummary } from './contract'
import { getCustomer, searchCustomers } from './customers'
import { CUSTOMERS_KEY, RESERVATIONS_KEY } from './query-client'

const SEARCH_SEGMENT = 'search'
const DETAIL_SEGMENT = 'detail'
const CHECKOUT_SEGMENT = 'checkout'

export const customerQueries = {
  /** One page of the customers who match a search, best match first. */
  search: (query: CustomerSearchQuery) =>
    queryOptions({
      queryKey: [CUSTOMERS_KEY, SEARCH_SEGMENT, query],
      queryFn: ({ signal }) => searchCustomers(query, signal),
    }),

  /** One customer, by their key. */
  detail: (id: string) =>
    queryOptions({
      queryKey: [CUSTOMERS_KEY, DETAIL_SEGMENT, id],
      queryFn: ({ signal }) => getCustomer(id, signal),
    }),
}

export const checkoutQueries = {
  /** What the counter needs to hand a reservation over, by its key or reference. */
  detail: (idOrReference: string) =>
    queryOptions({
      queryKey: [RESERVATIONS_KEY, CHECKOUT_SEGMENT, idOrReference],
      queryFn: ({ signal }) => getCheckout(idOrReference, signal),
    }),
}

/**
 * Put a customer the API has just answered with into the cache, and mark every
 * search as out of date, because a new walk in now matches some of them.
 */
export function rememberCustomer(client: QueryClient, customer: CustomerSummary): void {
  client.setQueryData(customerQueries.detail(customer.id).queryKey, customer)
  void client.invalidateQueries({ queryKey: [CUSTOMERS_KEY, SEARCH_SEGMENT] })
}

/**
 * Mark everything about reservations as out of date after a handover. The
 * reservation is now collected, so its checkout, its detail and every list
 * that shows it read differently.
 */
export function forgetReservationsAfterCheckout(client: QueryClient): void {
  void client.invalidateQueries({ queryKey: [RESERVATIONS_KEY] })
}
