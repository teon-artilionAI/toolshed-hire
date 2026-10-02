/**
 * Tests for the reservation endpoints, with the network replaced at `fetch`.
 *
 * Each function makes the one request the contract describes and reads the
 * answer into a reservation. A body that breaks the contract fails at the
 * boundary, with the name of the field, and never reaches a screen.
 */

import { describe, expect, it } from 'vitest'
import { createdResponse, jsonResponse, mockApi, problemResponse } from '../../test/api-mock'
import {
  CANCELLED,
  CONFIRMED,
  CREATE_REQUEST,
  CREATE_ROUTE,
  DRAFT,
  HELD,
  LIST_ROUTE,
  REFERENCE,
  RESERVATION_ID,
  cancelRoute,
  confirmRoute,
  detailRoute,
  holdRoute,
  pageOf,
} from '../../test/reservation-samples'
import { failureOf } from '../../test/session-samples'
import {
  cancelReservation,
  confirmReservation,
  createReservation,
  getReservation,
  holdReservation,
  listReservations,
} from './reservations'

describe('the six reservation routes', () => {
  it('creates a draft from the body the contract describes', async () => {
    const network = mockApi({ [CREATE_ROUTE]: () => createdResponse(DRAFT) })

    expect(await createReservation(CREATE_REQUEST)).toEqual(DRAFT)
    expect(network.requestsTo(CREATE_ROUTE)[0].body).toEqual(CREATE_REQUEST)
  })

  it('holds and confirms with no body', async () => {
    const network = mockApi({
      [holdRoute()]: () => jsonResponse(HELD),
      [confirmRoute()]: () => jsonResponse(CONFIRMED),
    })

    expect(await holdReservation(RESERVATION_ID)).toEqual(HELD)
    expect(await confirmReservation(RESERVATION_ID)).toEqual(CONFIRMED)
    expect(network.requestsTo(holdRoute())[0].body).toBeUndefined()
    expect(network.requestsTo(confirmRoute())[0].body).toBeUndefined()
  })

  it.each([
    ['no reason', null],
    ['a reason', 'The job has been postponed'],
  ])('cancels with %s', async (_what, reason) => {
    const network = mockApi({ [cancelRoute()]: () => jsonResponse(CANCELLED) })

    expect(await cancelReservation(RESERVATION_ID, reason)).toEqual(CANCELLED)
    expect(network.requestsTo(cancelRoute())[0].body).toEqual({ reason })
  })

  it('lists with the status, the page and the page size, and leaves out what is not set', async () => {
    const network = mockApi({ [LIST_ROUTE]: () => jsonResponse(pageOf([CONFIRMED, DRAFT])) })

    const page = await listReservations({ status: 'CONFIRMED', page: 2, pageSize: 20 })
    await listReservations({ page: 1 })

    expect(page.items).toEqual([CONFIRMED, DRAFT])
    const [filtered, bare] = network.requestsTo(LIST_ROUTE)
    expect(filtered.query.toString()).toBe('status=CONFIRMED&page=2&pageSize=20')
    expect(bare.query.toString()).toBe('page=1')
  })

  it('reads one by its reference, and encodes what it is given', async () => {
    const network = mockApi({
      [detailRoute(REFERENCE)]: () => jsonResponse(CONFIRMED),
      'GET /api/reservations/a%2Fb': () => problemResponse(404),
    })

    expect(await getReservation(REFERENCE)).toEqual(CONFIRMED)
    expect((await failureOf(getReservation('a/b'))).status).toBe(404)
    expect(network.requests).toHaveLength(2)
  })

  it('sends a write once, and does not repeat it when it fails', async () => {
    const network = mockApi({ [holdRoute()]: () => problemResponse(409) })

    expect((await failureOf(holdReservation(RESERVATION_ID))).status).toBe(409)
    expect(network.requestsTo(holdRoute())).toHaveLength(1)
  })
})

describe('a reservation in the wrong shape', () => {
  it.each([
    ['a status it has not heard of', { ...DRAFT, status: 'PARKED' }, /status/],
    ['a total that is a number', { ...DRAFT, estimatedTotalIncVat: 4444.44 }, /estimatedTotalIncVat/],
    ['a deposit with one decimal', { ...DRAFT, depositTotal: '5555.5' }, /depositTotal/],
    ['a discount that is not a percentage', { ...DRAFT, discountPercent: 'none' }, /discountPercent/],
    ['a date that is not a date', { ...DRAFT, from: 'next Friday' }, /from/],
    ['a hold expiry that is not an instant', { ...HELD, holdExpiresAt: 'soon' }, /holdExpiresAt/],
    ['a missing hold expiry', { ...DRAFT, holdExpiresAt: undefined }, /holdExpiresAt/],
    ['no time of creation', { ...DRAFT, createdAt: null }, /createdAt/],
    ['a flag that is text', { ...DRAFT, canCancel: 'yes' }, /canCancel/],
    ['lines that are not a list', { ...DRAFT, lines: null }, /lines/],
    ['a line with a rate that is a number', { ...DRAFT, lines: [{ ...DRAFT.lines[0], dailyRate: 340 }] }, /dailyRate/],
    ['an asset tag that is not text', { ...DRAFT, lines: [{ ...DRAFT.lines[0], assetTags: [7] }] }, /asset tag/],
  ])('refuses %s, and names the field', async (_what, body, field) => {
    mockApi({ [detailRoute()]: () => jsonResponse(body) })

    const failure = await failureOf(getReservation(RESERVATION_ID))

    expect(failure.kind).toBe('malformed')
    expect(failure.detail).toMatch(field)
  })

  it('refuses a page whose items are not reservations', async () => {
    mockApi({ [LIST_ROUTE]: () => jsonResponse({ items: [{ id: RESERVATION_ID }], page: 1, pageSize: 20, total: 1 }) })

    expect((await failureOf(listReservations({}))).kind).toBe('malformed')
  })
})
