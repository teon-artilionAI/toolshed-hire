/**
 * Tests for the reservation the hire basket remembers.
 *
 * While a booking is under way the basket knows the reservation the server
 * made from it. When the basket changes underneath that reservation, or the
 * person steps back from it, the reservation is set aside, so the next booking
 * can carry on with it or cancel it and no draft is left behind.
 */

import { describe, expect, it } from 'vitest'
import { BASKET_STORAGE_KEY } from './basket-storage'
import {
  addToBasket,
  basketSnapshot,
  forgetBookingUnderWay,
  forgetReservationSetAside,
  noteBookingUnderWay,
  removeFromBasket,
  setBasketQuantity,
  setBasketTerms,
  setBookingAside,
} from './basket-store'
import type { BasketAddition } from './basket-store'

const COMPACTOR = 'cp-100-plate-compactor'
const RAMMER = 'bs-60-4-trench-rammer'
const RESERVATION_ID = '5f0c2a9e-0000-4000-8000-000000000124'
const NEXT_RESERVATION_ID = '5f0c2a9e-0000-4000-8000-000000000125'

const AT_CBD = { from: '2026-10-09', to: '2026-10-12', branchCode: 'CBD' }

function addition(modelSlug: string, quantity = 1, terms = AT_CBD): BasketAddition {
  return { modelSlug, quantity, ...terms }
}

function stored(): string | null {
  return window.sessionStorage.getItem(BASKET_STORAGE_KEY)
}

describe('a booking that is under way', () => {
  it('is remembered with the basket it was made from', () => {
    addToBasket(addition(COMPACTOR))

    noteBookingUnderWay(RESERVATION_ID)

    expect(basketSnapshot().reservationId).toBe(RESERVATION_ID)
  })

  it.each([
    ['another model is added', () => addToBasket(addition(RAMMER))],
    ['a quantity changes', () => setBasketQuantity(COMPACTOR, 2)],
    ['the period changes', () => setBasketTerms({ to: '2026-10-14' })],
    ['a model is removed', () => removeFromBasket(RAMMER)],
  ])('is set aside when %s, because it was priced for the basket as it was', (_what, change) => {
    addToBasket(addition(COMPACTOR))
    addToBasket(addition(RAMMER))
    noteBookingUnderWay(RESERVATION_ID)

    change()

    expect(basketSnapshot().reservationId).toBeNull()
    expect(basketSnapshot().setAside).toEqual({ reservationId: RESERVATION_ID, fitsBasket: false })
    expect(basketSnapshot().lines.length).toBeGreaterThan(0)
  })

  it.each([
    ['a quantity is set to what it already is', () => setBasketQuantity(COMPACTOR, 1)],
    ['the period is set to what it already is', () => setBasketTerms({ to: AT_CBD.to })],
    ['a model the basket does not hold is removed', () => removeFromBasket('no-such-tool')],
  ])('stays under way when %s, which is no change', (_what, change) => {
    addToBasket(addition(COMPACTOR))
    noteBookingUnderWay(RESERVATION_ID)
    const before = basketSnapshot()

    change()

    expect(basketSnapshot()).toBe(before)
  })

  it('is forgotten for good once it is over, with nothing set aside', () => {
    addToBasket(addition(COMPACTOR))
    noteBookingUnderWay(RESERVATION_ID)

    forgetBookingUnderWay()

    expect(basketSnapshot().reservationId).toBeNull()
    expect(basketSnapshot().setAside).toBeNull()
    expect(basketSnapshot().lines).toHaveLength(1)
  })

  it('cannot be remembered against an empty basket', () => {
    noteBookingUnderWay(RESERVATION_ID)

    expect(basketSnapshot().reservationId).toBeNull()
  })
})

describe('a reservation that was set aside', () => {
  it('still fits the basket when the person only steps back to look at the basket', () => {
    addToBasket(addition(COMPACTOR))
    noteBookingUnderWay(RESERVATION_ID)

    setBookingAside()

    expect(basketSnapshot().reservationId).toBeNull()
    expect(basketSnapshot().setAside).toEqual({ reservationId: RESERVATION_ID, fitsBasket: true })
    expect(JSON.parse(stored() ?? '')).toMatchObject({
      reservationId: null,
      setAside: { reservationId: RESERVATION_ID, fitsBasket: true },
    })
  })

  it('stops fitting once the basket changes after that', () => {
    addToBasket(addition(COMPACTOR))
    noteBookingUnderWay(RESERVATION_ID)
    setBookingAside()

    setBasketQuantity(COMPACTOR, 3)

    expect(basketSnapshot().setAside).toEqual({ reservationId: RESERVATION_ID, fitsBasket: false })
  })

  it('gives way to the next reservation made from the basket', () => {
    addToBasket(addition(COMPACTOR))
    noteBookingUnderWay(RESERVATION_ID)
    setBookingAside()

    noteBookingUnderWay(NEXT_RESERVATION_ID)

    expect(basketSnapshot().reservationId).toBe(NEXT_RESERVATION_ID)
    expect(basketSnapshot().setAside).toBeNull()
  })

  it('becomes the booking under way again when it is carried on with', () => {
    addToBasket(addition(COMPACTOR))
    noteBookingUnderWay(RESERVATION_ID)
    setBookingAside()

    noteBookingUnderWay(RESERVATION_ID)

    expect(basketSnapshot().reservationId).toBe(RESERVATION_ID)
    expect(basketSnapshot().setAside).toBeNull()
  })

  it('is forgotten once it is out of the way, and the basket is kept', () => {
    addToBasket(addition(COMPACTOR))
    noteBookingUnderWay(RESERVATION_ID)
    setBasketQuantity(COMPACTOR, 2)

    forgetReservationSetAside()

    expect(basketSnapshot().setAside).toBeNull()
    expect(basketSnapshot().lines).toEqual([{ modelSlug: COMPACTOR, quantity: 2 }])
  })

  it('goes with the basket when the last model is taken out', () => {
    addToBasket(addition(COMPACTOR))
    noteBookingUnderWay(RESERVATION_ID)

    removeFromBasket(COMPACTOR)

    expect(basketSnapshot().setAside).toBeNull()
    expect(stored()).toBeNull()
  })
})
