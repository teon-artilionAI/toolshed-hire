/**
 * The customer routes the counter uses.
 *
 * Three calls, all for staff. A counter assistant looks a customer up by name,
 * phone number or email address, reads one by their key, and registers a walk
 * in who has no login. Each function makes one call and reads the body into
 * its contract type.
 *
 * The walk in is sent once for each press of the button. The client never
 * repeats a POST by itself, because a request that timed out may still have
 * reached the server and made the customer.
 */

import { ACCOUNT_STATUSES, CUSTOMER_TYPES, ID_DOCUMENT_TYPES } from './account'
import { api } from './client'
import type {
  CustomerPage,
  CustomerSearchQuery,
  CustomerSummary,
  RegisterWalkInRequest,
} from './contract'
import {
  readCount,
  readFlag,
  readList,
  readNullableText,
  readObject,
  readOneOf,
  readPercent,
  readText,
} from './read'

const CUSTOMERS_ENDPOINT = '/customers'

/** The shortest search the API accepts. */
export const MIN_CUSTOMER_SEARCH_LENGTH = 2

/** The longest search the API accepts. */
export const MAX_CUSTOMER_SEARCH_LENGTH = 80

function readCustomerSummary(value: unknown, path: string): CustomerSummary {
  const record = readObject(value, path, 'a customer')
  return {
    id: readText(record, 'id', path),
    displayName: readText(record, 'displayName', path),
    email: readNullableText(record, 'email', path),
    phone: readText(record, 'phone', path),
    hasLogin: readFlag(record, 'hasLogin', path),
    emailVerified: readFlag(record, 'emailVerified', path),
    customerType: readOneOf(record, 'customerType', path, CUSTOMER_TYPES),
    companyName: readNullableText(record, 'companyName', path),
    idDocumentType: readOneOf(record, 'idDocumentType', path, ID_DOCUMENT_TYPES),
    idDocumentLast4: readText(record, 'idDocumentLast4', path),
    billingSuburb: readText(record, 'billingSuburb', path),
    billingCity: readText(record, 'billingCity', path),
    accountStatus: readOneOf(record, 'accountStatus', path, ACCOUNT_STATUSES),
    tradeDiscountPercent: readPercent(record, 'tradeDiscountPercent', path),
    noShowCount: readCount(record, 'noShowCount', path),
    homeBranchCode: readText(record, 'homeBranchCode', path),
  }
}

function readCustomerPage(value: unknown, path: string): CustomerPage {
  const record = readObject(value, path, 'a page of customers')
  return {
    items: readList(record, 'items', path, readCustomerSummary),
    page: readCount(record, 'page', path),
    pageSize: readCount(record, 'pageSize', path),
    total: readCount(record, 'total', path),
  }
}

/**
 * GET /api/customers. Best match first.
 *
 * @throws ApiError with status 422 when the search is shorter than two
 *   characters or longer than eighty, and 403 for a customer, whose role the
 *   route does not admit.
 */
export function searchCustomers(query: CustomerSearchQuery, signal?: AbortSignal): Promise<CustomerPage> {
  return api.get(CUSTOMERS_ENDPOINT, readCustomerPage, { query, signal })
}

/**
 * GET /api/customers/{id}.
 *
 * @throws ApiError with status 404 when no customer has that key.
 */
export function getCustomer(id: string, signal?: AbortSignal): Promise<CustomerSummary> {
  return api.get(`${CUSTOMERS_ENDPOINT}/${encodeURIComponent(id)}`, readCustomerSummary, { signal })
}

/**
 * POST /api/customers. Registers a walk in at the assistant's branch.
 *
 * @throws ApiError with status 422 naming each refused field, and 403 when an
 *   administrator names no branch or staff name another branch.
 */
export function registerWalkIn(body: RegisterWalkInRequest): Promise<CustomerSummary> {
  return api.post(CUSTOMERS_ENDPOINT, body, readCustomerSummary)
}
