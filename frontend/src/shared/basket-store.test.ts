/**
 * Tests for the hire basket.
 *
 * Adding, changing and removing a model, the rule that a basket is for one
 * period at one branch, and the count the shell shows. The reservation the
 * basket remembers is in basket-store.booking.test.ts, and what survives a
 * reload is in basket-storage.test.ts.
 */

import { describe, expect, it, vi } from 'vitest'
import { MAX_QUANTITY } from './api/catalogue'
import { BASKET_STORAGE_KEY } from './basket-storage'
import {
  addToBasket,
  basketSnapshot,
  basketUnitCount,
  clearBasket,
  removeFromBasket,
  setBasketQuantity,
  setBasketTerms,
  subscribeToBasket,
} from './basket-store'
import type { BasketAddition } from './basket-store'

const COMPACTOR = 'cp-100-plate-compactor'
const RAMMER = 'bs-60-4-trench-rammer'

const AT_CBD = { from: '2026-10-09', to: '2026-10-12', branchCode: 'CBD' }

function addition(modelSlug: string, quantity = 1, terms = AT_CBD): BasketAddition {
  return { modelSlug, quantity, ...terms }
}

function stored(): string | null {
  return window.sessionStorage.getItem(BASKET_STORAGE_KEY)
}

describe('adding to the basket', () => {
  it('starts empty, with no period, no branch and nothing stored', () => {
    expect(basketSnapshot()).toEqual({ from: '', to: '', branchCode: '', lines: [], reservationId: null, setAside: null })
    expect(basketUnitCount(basketSnapshot())).toBe(0)
    expect(stored()).toBeNull()
  })

  it('takes its period and branch from the first model added', () => {
    expect(addToBasket(addition(COMPACTOR, 2))).toEqual({ outcome: 'added', quantity: 2 })

    expect(basketSnapshot()).toEqual({
      ...AT_CBD,
      lines: [{ modelSlug: COMPACTOR, quantity: 2 }],
      reservationId: null,
      setAside: null,
    })
  })

  it('keeps a second model for the same period and branch as its own line', () => {
    addToBasket(addition(COMPACTOR, 2))
    addToBasket(addition(RAMMER))

    expect(basketSnapshot().lines).toEqual([
      { modelSlug: COMPACTOR, quantity: 2 },
      { modelSlug: RAMMER, quantity: 1 },
    ])
  })

  it('raises the quantity of a model it already holds, up to the most a booking may ask for', () => {
    addToBasket(addition(COMPACTOR, 2))

    expect(addToBasket(addition(COMPACTOR, 3))).toEqual({ outcome: 'added', quantity: 5 })
    expect(addToBasket(addition(COMPACTOR, MAX_QUANTITY))).toEqual({
      outcome: 'added',
      quantity: MAX_QUANTITY,
    })
    expect(basketSnapshot().lines).toEqual([{ modelSlug: COMPACTOR, quantity: MAX_QUANTITY }])
  })

  it('tells every subscriber, and stops telling one that has left', () => {
    const listener = vi.fn()
    const leave = subscribeToBasket(listener)

    addToBasket(addition(COMPACTOR))
    leave()
    addToBasket(addition(RAMMER))

    expect(listener).toHaveBeenCalledTimes(1)
  })
})

describe('one period and one branch', () => {
  it.each([
    ['another collection day', { ...AT_CBD, from: '2026-10-10' }],
    ['another return day', { ...AT_CBD, to: '2026-10-13' }],
    ['another branch', { ...AT_CBD, branchCode: 'BLV' }],
  ])('asks before adding a model for %s, and changes nothing', (_what, terms) => {
    addToBasket(addition(COMPACTOR))
    const before = basketSnapshot()

    expect(addToBasket(addition(RAMMER, 1, terms))).toEqual({ outcome: 'conflict', basket: AT_CBD })
    expect(basketSnapshot()).toBe(before)
  })

  it('moves the whole basket to the new period and branch when the person chooses that', () => {
    const elsewhere = { from: '2026-11-02', to: '2026-11-05', branchCode: 'SMW' }
    addToBasket(addition(COMPACTOR, 2))

    expect(addToBasket(addition(RAMMER, 1, elsewhere), 'moveBasket')).toEqual({
      outcome: 'added',
      quantity: 1,
    })
    expect(basketSnapshot()).toEqual({
      ...elsewhere,
      lines: [
        { modelSlug: COMPACTOR, quantity: 2 },
        { modelSlug: RAMMER, quantity: 1 },
      ],
      reservationId: null,
      setAside: null,
    })
  })

  it('has no period to disagree with once the last model is taken out', () => {
    addToBasket(addition(COMPACTOR))
    removeFromBasket(COMPACTOR)

    expect(addToBasket(addition(RAMMER, 1, { ...AT_CBD, branchCode: 'BLV' })).outcome).toBe('added')
    expect(basketSnapshot().branchCode).toBe('BLV')
  })

  it('moves to another period or another branch when the person changes it on the basket', () => {
    addToBasket(addition(COMPACTOR))

    setBasketTerms({ to: '2026-10-16' })
    setBasketTerms({ branchCode: 'BLV' })

    expect(basketSnapshot()).toMatchObject({ from: '2026-10-09', to: '2026-10-16', branchCode: 'BLV' })
  })
})

describe('changing and removing', () => {
  it('changes the quantity of one line and leaves the others', () => {
    addToBasket(addition(COMPACTOR))
    addToBasket(addition(RAMMER))

    setBasketQuantity(RAMMER, 4)

    expect(basketSnapshot().lines).toEqual([
      { modelSlug: COMPACTOR, quantity: 1 },
      { modelSlug: RAMMER, quantity: 4 },
    ])
  })

  it.each([
    [0, 1],
    [-3, 1],
    [99, MAX_QUANTITY],
    [2.9, 2],
    [Number.NaN, 1],
  ])('keeps a quantity of %s inside what a booking may ask for', (asked, kept) => {
    addToBasket(addition(COMPACTOR))

    setBasketQuantity(COMPACTOR, asked)

    expect(basketSnapshot().lines[0].quantity).toBe(kept)
  })

  it('removes one line, and is empty again when the last one goes', () => {
    addToBasket(addition(COMPACTOR))
    addToBasket(addition(RAMMER))

    removeFromBasket(COMPACTOR)
    expect(basketSnapshot().lines).toEqual([{ modelSlug: RAMMER, quantity: 1 }])

    removeFromBasket(RAMMER)
    expect(basketSnapshot()).toEqual({ from: '', to: '', branchCode: '', lines: [], reservationId: null, setAside: null })
    expect(stored()).toBeNull()
  })

  it('leaves the basket alone when asked about a model it does not hold', () => {
    addToBasket(addition(COMPACTOR))
    const before = basketSnapshot()

    setBasketQuantity(RAMMER, 3)
    removeFromBasket(RAMMER)

    expect(basketSnapshot()).toBe(before)
  })

  it('empties in one go', () => {
    addToBasket(addition(COMPACTOR, 3))

    clearBasket()

    expect(basketSnapshot().lines).toEqual([])
    expect(stored()).toBeNull()
  })
})

describe('the count the shell shows', () => {
  it('is every unit across every line', () => {
    addToBasket(addition(COMPACTOR, 2))
    addToBasket(addition(RAMMER, 3))

    expect(basketUnitCount(basketSnapshot())).toBe(5)
  })
})
