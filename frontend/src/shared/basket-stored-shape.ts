/**
 * The hire basket as it is written to the tab's storage, and read back.
 *
 * basket-store.ts keeps the basket and basket-storage.ts keeps one string.
 * This turns the one into the other. Storage can be edited by hand, so
 * nothing read back is taken on trust. A string that is not exactly what this
 * version writes is dropped, and the basket starts empty.
 */

import { MAX_QUANTITY, MIN_QUANTITY } from './api/catalogue'
import { logEvent } from './api/log'
import type { Basket, BasketLine, SetAsideReservation } from './basket-store'

/** The shape written to storage. A later change to it gets a new number, and
 *  a basket stored under an older one is dropped and not guessed at. Version 2
 *  added the reservation that was set aside. */
const STORED_VERSION = 2

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isStoredLine(value: unknown): value is BasketLine {
  if (!isRecord(value)) return false
  const { modelSlug, quantity } = value
  return (
    typeof modelSlug === 'string' &&
    modelSlug !== '' &&
    typeof quantity === 'number' &&
    Number.isInteger(quantity) &&
    quantity >= MIN_QUANTITY &&
    quantity <= MAX_QUANTITY
  )
}

function isStoredSetAside(value: unknown): value is SetAsideReservation {
  if (!isRecord(value)) return false
  const { reservationId, fitsBasket } = value
  return typeof reservationId === 'string' && reservationId !== '' && typeof fitsBasket === 'boolean'
}

/** The basket as the one string that is kept. */
export function serialiseBasket(basket: Basket): string {
  return JSON.stringify({ version: STORED_VERSION, ...basket })
}

/** Read a stored basket back, or null when it is not one this code wrote. */
export function parseStoredBasket(raw: string): Basket | null {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch (cause) {
    logEvent('warn', 'basket.stored_basket_dropped', { reason: `not JSON, ${String(cause)}` })
    return null
  }
  const record = isRecord(parsed) ? parsed : {}
  const { version, from, to, branchCode, lines, reservationId, setAside } = record
  const storedLines: readonly unknown[] = Array.isArray(lines) ? lines : []
  const wellFormed =
    version === STORED_VERSION &&
    typeof from === 'string' &&
    typeof to === 'string' &&
    typeof branchCode === 'string' &&
    storedLines.length > 0 &&
    storedLines.every(isStoredLine) &&
    (reservationId === null || typeof reservationId === 'string') &&
    (setAside === null || isStoredSetAside(setAside))
  if (!wellFormed) {
    logEvent('warn', 'basket.stored_basket_dropped', { reason: 'not the shape this version writes' })
    return null
  }
  return {
    from,
    to,
    branchCode,
    lines: storedLines.filter(isStoredLine).map(({ modelSlug, quantity }) => ({ modelSlug, quantity })),
    reservationId,
    setAside: isStoredSetAside(setAside)
      ? { reservationId: setAside.reservationId, fitsBasket: setAside.fitsBasket }
      : null,
  }
}
