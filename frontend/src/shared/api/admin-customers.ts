/**
 * The owner's customer holds. Listing the customers by their standing and
 * moving a customer between good standing, on hold and blacklisted.
 *
 * Both routes are for an administrator, and the API refuses anyone else with a
 * 403. A customer reads as the same `CustomerSummary` the counter uses, read by
 * the reader in customers.ts, so the two can never drift apart.
 *
 * The standing is the one thing a move changes. A customer who is not in good
 * standing cannot make a new booking, and releasing a hold leaves the count of
 * bookings they did not collect as it is. Those rules are the server's. Asking
 * for the standing a customer already has changes nothing and answers with the
 * customer as they are. The write is sent once for each press of a button and
 * never repeated by the client.
 */

import { api } from './client'
import type { AdminCustomerPage, AdminCustomerQuery, CustomerStandingRequest, CustomerWithStanding } from './contract'
import { readCustomerSummary } from './customers'
import { readCount, readList, readObject } from './read'

const CUSTOMERS_ENDPOINT = '/admin/customers'

/** How many customers a page of the holds holds. */
export const CUSTOMER_HOLD_PAGE_SIZE = 20

function readHoldPage(value: unknown, path: string): AdminCustomerPage {
  const record = readObject(value, path, 'a page of customers')
  return {
    items: readList(record, 'items', path, readCustomerSummary),
    page: readCount(record, 'page', path),
    pageSize: readCount(record, 'pageSize', path),
    total: readCount(record, 'total', path),
  }
}

/**
 * GET /api/admin/customers. One page of the customers that match, filtered by
 * their standing.
 *
 * @throws ApiError with status 422 naming a filter the server refused, and
 *   403 for anyone but an administrator.
 */
export function listCustomerHolds(query: AdminCustomerQuery, signal?: AbortSignal): Promise<AdminCustomerPage> {
  return api.get(CUSTOMERS_ENDPOINT, readHoldPage, { query, signal })
}

/**
 * POST /api/admin/customers/{id}/status. Moves the customer to the standing
 * named, with the reason, and answers with the customer as they now stand.
 *
 * @throws ApiError with status 422 naming `accountStatus` or `reason`, 404 when
 *   no customer has the key, and 403 for anyone but an administrator.
 */
export function setCustomerStanding(id: string, body: CustomerStandingRequest): Promise<CustomerWithStanding> {
  return api.post(`${CUSTOMERS_ENDPOINT}/${encodeURIComponent(id)}/status`, body, readCustomerSummary)
}
