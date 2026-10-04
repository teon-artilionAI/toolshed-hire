/**
 * The counter's reads, as cached queries.
 *
 * A customer key starts with the customers segment and a checkout key with the
 * reservations segment, and query-client.ts treats both as never fresh. An
 * account can be put on hold at another counter, and a reservation can be
 * collected a moment after it was read, so a cached answer is always asked for
 * again when a screen uses it.
 *
 * The dashboard and the diary start with the counter segment, and the locator
 * with the assets segment. Both are never fresh as well, so a screen left open
 * all day reads them again whenever the window comes back into focus.
 *
 * The writes are not here. A screen calls the functions in customers.ts,
 * checkout.ts and reservations.ts for those, one request for each press of a
 * button, and then tells the cache what changed.
 */

import { queryOptions } from '@tanstack/react-query'
import type { QueryClient } from '@tanstack/react-query'
import { getCheckout } from './checkout'
import type { CustomerSearchQuery, CustomerSummary, DiaryQuery, LocatorQuery, Reservation } from './contract'
import { getBranchDiary, getCounterDashboard } from './counter-overview'
import { getCustomer, searchCustomers } from './customers'
import { locateUnits } from './locator'
import { ASSETS_KEY, COUNTER_KEY, CUSTOMERS_KEY, RESERVATIONS_KEY } from './query-client'
import { rememberReservation } from './reservation-queries'

const SEARCH_SEGMENT = 'search'
const DETAIL_SEGMENT = 'detail'
const CHECKOUT_SEGMENT = 'checkout'
const DASHBOARD_SEGMENT = 'dashboard'
const DIARY_SEGMENT = 'diary'
const LOCATOR_SEGMENT = 'locator'

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

export const overviewQueries = {
  /** What is due today at one branch. */
  dashboard: (branchCode: string) =>
    queryOptions({
      queryKey: [COUNTER_KEY, DASHBOARD_SEGMENT, branchCode],
      queryFn: ({ signal }) => getCounterDashboard({ branchCode }, signal),
    }),

  /** One day of the diary at one branch, or up to seven days in a row. */
  diary: (query: DiaryQuery) =>
    queryOptions({
      queryKey: [COUNTER_KEY, DIARY_SEGMENT, query],
      queryFn: ({ signal }) => getBranchDiary(query, signal),
    }),
}

export const locatorQueries = {
  /** One page of the units whose tag or model matches, at every branch. */
  search: (query: LocatorQuery) =>
    queryOptions({
      queryKey: [ASSETS_KEY, LOCATOR_SEGMENT, query],
      queryFn: ({ signal }) => locateUnits(query, signal),
    }),
}

/**
 * Put a reservation the no show has just answered with into the cache, and
 * mark the counter's day as out of date. The booking now reads as a no show,
 * its units are free again, and the dashboard and the diary say otherwise
 * until they are asked again.
 */
export function rememberNoShow(client: QueryClient, reservation: Reservation): void {
  rememberReservation(client, reservation)
  forgetCounterDay(client)
}

/** Mark the dashboard and every day of the diary as out of date, so each is
 *  asked again the next time a screen shows it, or now when one is showing. */
export function forgetCounterDay(client: QueryClient): void {
  void client.invalidateQueries({ queryKey: [COUNTER_KEY] })
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

/**
 * Mark what a change to the units of a booking touches as out of date, after a
 * unit is released or a replacement is found. The checkout of the booking and
 * its detail read differently, a unit moved on or off the shelf for the
 * locator, and the counter's day counts the booking another way.
 */
export function forgetAfterAllocationChange(client: QueryClient): void {
  void client.invalidateQueries({ queryKey: [RESERVATIONS_KEY] })
  void client.invalidateQueries({ queryKey: [ASSETS_KEY] })
  forgetCounterDay(client)
}
