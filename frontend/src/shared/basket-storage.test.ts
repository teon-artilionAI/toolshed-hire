/**
 * Tests for the copy of the hire basket in the tab's storage.
 *
 * The basket survives a reload and is gone when the tab closes. It is one JSON
 * string under one fixed key, and what is read back is checked before it is
 * believed, because storage can be edited by hand.
 *
 * A reload is a fresh copy of the module reading storage again, so these tests
 * load the module a second time and do not reach inside it.
 */

import { describe, expect, it, vi } from 'vitest'
import { BASKET_STORAGE_KEY } from './basket-storage'
import {
  addToBasket,
  basketSnapshot,
  basketUnitCount,
  noteBookingUnderWay,
  setBasketQuantity,
} from './basket-store'

const COMPACTOR = 'cp-100-plate-compactor'
const RAMMER = 'bs-60-4-trench-rammer'
const RESERVATION_ID = '5f0c2a9e-0000-4000-8000-000000000124'

const AT_CBD = { from: '2026-10-09', to: '2026-10-12', branchCode: 'CBD' }

/** A basket exactly as this version writes it, for a test to spoil one part of. */
const STORED = {
  version: 2,
  ...AT_CBD,
  lines: [{ modelSlug: COMPACTOR, quantity: 1 }],
  reservationId: null,
  setAside: null,
}

function stored(): string | null {
  return window.sessionStorage.getItem(BASKET_STORAGE_KEY)
}

/** What a reload does. The module is loaded again and reads storage again. */
async function afterReload(): Promise<typeof import('./basket-store')> {
  vi.resetModules()
  return import('./basket-store')
}

describe('after a reload', () => {
  it('comes back as it was, with the booking that was under way', async () => {
    addToBasket({ modelSlug: COMPACTOR, quantity: 2, ...AT_CBD })
    addToBasket({ modelSlug: RAMMER, quantity: 1, ...AT_CBD })
    noteBookingUnderWay(RESERVATION_ID)
    const before = basketSnapshot()

    const reloaded = await afterReload()

    expect(reloaded.basketSnapshot()).toEqual(before)
    expect(reloaded.basketUnitCount(reloaded.basketSnapshot())).toBe(3)
  })

  it('still knows the reservation that was set aside, so it can be cancelled later', async () => {
    addToBasket({ modelSlug: COMPACTOR, quantity: 2, ...AT_CBD })
    noteBookingUnderWay(RESERVATION_ID)
    setBasketQuantity(COMPACTOR, 1)

    const reloaded = await afterReload()

    expect(reloaded.basketSnapshot().reservationId).toBeNull()
    expect(reloaded.basketSnapshot().setAside).toEqual({
      reservationId: RESERVATION_ID,
      fitsBasket: false,
    })
  })

  it('is gone when the tab was closed, which empties the storage of the tab', async () => {
    addToBasket({ modelSlug: COMPACTOR, quantity: 1, ...AT_CBD })
    window.sessionStorage.clear()

    const reloaded = await afterReload()

    expect(reloaded.basketSnapshot().lines).toEqual([])
  })

  it('keeps one fixed key in the storage of the tab, and nothing in the lasting one', () => {
    addToBasket({ modelSlug: COMPACTOR, quantity: 1, ...AT_CBD })

    expect(Object.keys(window.sessionStorage)).toEqual([BASKET_STORAGE_KEY])
    expect(JSON.parse(stored() ?? '')).toEqual({
      version: 2,
      ...AT_CBD,
      lines: [{ modelSlug: COMPACTOR, quantity: 1 }],
      reservationId: null,
      setAside: null,
    })
    // The session hint is the starting point of every test. The basket adds nothing to it.
    expect(Object.keys(window.localStorage)).toEqual(['toolshed.session-hint'])
  })

  it.each([
    ['text that is not JSON', 'not json {'],
    ['a shape from an older version', JSON.stringify({ version: 1, ...AT_CBD, lines: [{ modelSlug: COMPACTOR, quantity: 1 }], reservationId: null })],
    ['a basket with no line', JSON.stringify({ ...STORED, lines: [] })],
    ['a line with no model', JSON.stringify({ ...STORED, lines: [{ modelSlug: '', quantity: 1 }] })],
    ['a quantity above the most a booking may ask for', JSON.stringify({ ...STORED, lines: [{ modelSlug: COMPACTOR, quantity: 500 }] })],
    ['a quantity that is text', JSON.stringify({ ...STORED, lines: [{ modelSlug: COMPACTOR, quantity: '2' }] })],
    ['a set aside reservation with no id', JSON.stringify({ ...STORED, setAside: { fitsBasket: true } })],
    ['a list', JSON.stringify([1, 2, 3])],
  ])('starts empty when storage holds %s', async (_what, raw) => {
    window.sessionStorage.setItem(BASKET_STORAGE_KEY, raw)

    const reloaded = await afterReload()

    expect(reloaded.basketSnapshot().lines).toEqual([])
  })
})

describe('a browser that refuses web storage', () => {
  it('still keeps the basket in memory', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('The quota has been exceeded.', 'QuotaExceededError')
    })

    expect(addToBasket({ modelSlug: COMPACTOR, quantity: 2, ...AT_CBD })).toEqual({ outcome: 'added', quantity: 2 })
    expect(basketUnitCount(basketSnapshot())).toBe(2)
    setItem.mockRestore()
  })

  it('starts empty and does not throw when storage cannot be read', async () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('Access is denied.', 'SecurityError')
    })

    const reloaded = await afterReload()

    expect(reloaded.basketSnapshot().lines).toEqual([])
    getItem.mockRestore()
  })
})
