/**
 * Tests for the retry rule and the freshness rules of the server state cache.
 *
 * The rule itself is a pure function, so most of this checks it directly. The
 * last group runs real reads through the cache with `fetch` replaced, to prove
 * the cache actually obeys the rule it was given.
 */

import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api-problem'
import type { ApiFailureKind } from '../api-problem'
import { jsonResponse, mockApi, problemResponse } from '../../test/api-mock'
import {
  CANCELLED,
  CONFIRMED,
  LIST_ROUTE,
  REFERENCE,
  RESERVATION_ID,
  pageOf,
} from '../../test/reservation-samples'
import { adminQueries } from './admin-queries'
import { listBranches } from './catalogue'
import { catalogueQueries } from './catalogue-queries'
import { locatorQueries, overviewQueries } from './counter-queries'
import {
  CATALOGUE_FRESH_MS,
  MAX_QUERY_RETRIES,
  REPORT_FRESH_MS,
  RETRY_BASE_DELAY_MS,
  RETRY_MAX_DELAY_MS,
  createQueryClient,
  retryDelay,
  shouldRetry,
} from './query-client'
import { rememberReservation, reservationQueries } from './reservation-queries'

function failure(kind: ApiFailureKind, status: number | null): ApiError {
  return new ApiError({ kind, status, title: 'Test', detail: 'Test', requestPath: '/api/test' })
}

/** Long enough for both retries and their waits to have run. */
const ALL_RETRIES_MS = RETRY_BASE_DELAY_MS * 2 ** MAX_QUERY_RETRIES

describe('shouldRetry', () => {
  it('tries again when nothing answered', () => {
    expect(shouldRetry(0, failure('transport', null))).toBe(true)
    expect(shouldRetry(1, failure('transport', null))).toBe(true)
  })

  it.each([502, 503, 504])('tries again when the gateway answered %i for the API', (status) => {
    expect(shouldRetry(0, failure('gateway', status))).toBe(true)
  })

  it('stops after two retries, however the call failed', () => {
    expect(shouldRetry(MAX_QUERY_RETRIES, failure('transport', null))).toBe(false)
    expect(shouldRetry(MAX_QUERY_RETRIES, failure('gateway', 502))).toBe(false)
  })

  it.each([400, 401, 403, 404, 409, 422])('never retries a %i, because the API said no', (status) => {
    expect(shouldRetry(0, failure('problem', status))).toBe(false)
  })

  it('does not retry a fault the API reported itself', () => {
    expect(shouldRetry(0, failure('problem', 500))).toBe(false)
  })

  it('does not retry an answer in the wrong shape', () => {
    expect(shouldRetry(0, failure('malformed', 200))).toBe(false)
  })

  it('does not retry something that was never an API failure', () => {
    expect(shouldRetry(0, new TypeError('undefined is not a function'))).toBe(false)
  })
})

describe('retryDelay', () => {
  it('doubles the wait each time', () => {
    expect(retryDelay(0)).toBe(RETRY_BASE_DELAY_MS)
    expect(retryDelay(1)).toBe(RETRY_BASE_DELAY_MS * 2)
  })

  it('never waits longer than the ceiling', () => {
    expect(retryDelay(20)).toBe(RETRY_MAX_DELAY_MS)
  })
})

describe('the freshness rules', () => {
  it('treat catalogue data as fresh for a minute', () => {
    const client = createQueryClient()

    expect(client.getQueryDefaults(catalogueQueries.branches().queryKey).staleTime).toBe(
      CATALOGUE_FRESH_MS,
    )
    expect(client.getQueryDefaults(catalogueQueries.model('cp-100').queryKey).staleTime).toBe(60_000)
  })

  it('never treat availability as fresh, and refetch it on every use', () => {
    const client = createQueryClient()
    const defaults = client.getQueryDefaults(
      catalogueQueries.availability({ from: '2026-03-12', to: '2026-03-16' }).queryKey,
    )

    expect(defaults.staleTime).toBe(0)
    expect(defaults.refetchOnMount).toBe('always')
    expect(defaults.refetchOnWindowFocus).toBe('always')
  })

  it('never treat a quote as fresh, and refetch it on every use', () => {
    const client = createQueryClient()
    const defaults = client.getQueryDefaults(
      catalogueQueries.modelQuote('cp-100', { from: '2026-03-12', to: '2026-03-16', quantity: 2 })
        .queryKey,
    )

    expect(defaults.staleTime).toBe(0)
    expect(defaults.refetchOnMount).toBe('always')
    expect(defaults.refetchOnWindowFocus).toBe('always')
    expect(defaults.refetchOnReconnect).toBe('always')
  })

  it.each([
    ['a list of reservations', reservationQueries.list({ page: 1 }).queryKey],
    ['one reservation', reservationQueries.detail(REFERENCE).queryKey],
    ["the counter's dashboard", overviewQueries.dashboard('BLV').queryKey],
    ['a day of the diary', overviewQueries.diary({ branchCode: 'BLV', from: '2026-03-12', days: 1 }).queryKey],
    ['a locator search', locatorQueries.search({ q: 'TSH', page: 1, pageSize: 20 }).queryKey],
    ["the owner's dashboard", adminQueries.dashboard().queryKey],
    ['a page of the audit trail', adminQueries.auditEvents({ page: 1, pageSize: 20 }).queryKey],
    ['a page of the notification log', adminQueries.notifications({ page: 1, pageSize: 20 }).queryKey],
  ])('never treat %s as fresh, and refetch it on every use', (_what, queryKey) => {
    const defaults = createQueryClient().getQueryDefaults(queryKey)

    expect(defaults.staleTime).toBe(0)
    expect(defaults.refetchOnMount).toBe('always')
    expect(defaults.refetchOnWindowFocus).toBe('always')
    expect(defaults.refetchOnReconnect).toBe('always')
  })

  it('treat a report as fresh for a minute, so a return to the window does not work it out again', () => {
    const query = { from: '2026-09-01', to: '2026-10-01', groupBy: 'model', page: 1, pageSize: 20 } as const
    const defaults = createQueryClient().getQueryDefaults(adminQueries.report(query).queryKey)

    expect(defaults.staleTime).toBe(REPORT_FRESH_MS)
    expect(defaults.refetchOnWindowFocus).toBeUndefined()
  })

  it('never retry a write', () => {
    expect(createQueryClient().getDefaultOptions().mutations?.retry).toBe(false)
  })
})

describe('the answer of a reservation write', () => {
  it('is kept under the id and under the reference, and puts every list out of date', async () => {
    mockApi({ [LIST_ROUTE]: () => jsonResponse(pageOf([CONFIRMED])) })
    const client = createQueryClient()
    const list = reservationQueries.list({ page: 1 })
    await client.fetchQuery(list)
    expect(client.getQueryState(list.queryKey)?.isInvalidated).toBe(false)

    rememberReservation(client, CANCELLED)

    expect(client.getQueryData(reservationQueries.detail(RESERVATION_ID).queryKey)).toEqual(CANCELLED)
    expect(client.getQueryData(reservationQueries.detail(REFERENCE).queryKey)).toEqual(CANCELLED)
    expect(client.getQueryState(list.queryKey)?.isInvalidated).toBe(true)
  })
})

describe('a read through the cache', () => {
  it('is tried again twice when the API cannot be reached, then succeeds', async () => {
    vi.useFakeTimers()
    let attempts = 0
    const network = mockApi({
      'GET /api/branches': () => {
        attempts += 1
        return attempts <= MAX_QUERY_RETRIES
          ? new Response('', { status: 502 })
          : jsonResponse({ items: [] })
      },
    })

    const pending = createQueryClient().fetchQuery(catalogueQueries.branches())
    await vi.advanceTimersByTimeAsync(ALL_RETRIES_MS)

    await expect(pending).resolves.toEqual({ items: [] })
    expect(network.fetch).toHaveBeenCalledTimes(3)
  })

  it('gives up after two retries and reports the failure', async () => {
    vi.useFakeTimers()
    const network = mockApi({
      'GET /api/branches': () => {
        throw new TypeError('Failed to fetch')
      },
    })

    const pending = createQueryClient().fetchQuery(catalogueQueries.branches())
    const outcome = expect(pending).rejects.toMatchObject({ kind: 'transport' })
    await vi.advanceTimersByTimeAsync(ALL_RETRIES_MS)

    await outcome
    expect(network.fetch).toHaveBeenCalledTimes(3)
  })

  it.each([404, 422])('asks once only when the API answers %i', async (status) => {
    const network = mockApi({ 'GET /api/branches': () => problemResponse(status) })

    await expect(
      createQueryClient().fetchQuery({ queryKey: ['catalogue', 'branches'], queryFn: () => listBranches() }),
    ).rejects.toMatchObject({ status })
    expect(network.fetch).toHaveBeenCalledTimes(1)
  })
})
