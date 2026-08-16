/**
 * What the hire basket holds, and how it starts out.
 *
 * The basket mirrors a Reservation: one collection branch and one period
 * for the whole booking, with a line per product model. Quantities live
 * here rather than on the assets, because a customer books "two rotary
 * hammers", and which two tags they get is the counter's business at
 * checkout, not the customer's at booking.
 *
 * The prototype has no back end, so the basket is seeded rather than
 * restored. It is seeded deliberately: one line that the default branch can
 * supply and one it cannot, so both the happy path and the conflict path
 * are on screen the moment the screen opens.
 */

import { reservations } from '../../shared/fixtures'
import type { Uuid } from '../../shared/types'
import { catalogue, modelById } from './catalogue-data'

export interface BasketItem {
  modelId: Uuid
  quantity: number
}

/** A rotary hammer, which Cape Town CBD can supply, and a generator, which
 *  it cannot. Looked up by catalogue number so reordering the fixtures
 *  cannot quietly empty the basket. */
const DEMO_SKUS = ['TSH-PM-0101', 'TSH-PM-0701']

/**
 * The next reference in the series, carried on from the fixture bookings so
 * a confirmation reads like the rest of the system rather than a random
 * number.
 */
export function nextReference(): string {
  const highest = reservations.reduce((max, reservation) => {
    const tail = Number.parseInt(reservation.reference.slice(-6), 10)
    return Number.isFinite(tail) ? Math.max(max, tail) : max
  }, 0)
  return `TSH-R-26-${String(highest + 1).padStart(6, '0')}`
}

/** The demonstration basket, plus whatever SC-03 sent through in the query. */
export function seedBasket(addModelId: string | null, addQuantity: number): BasketItem[] {
  const seeded: BasketItem[] = catalogue
    .filter((model) => DEMO_SKUS.includes(model.sku))
    .map((model) => ({ modelId: model.id, quantity: 1 }))

  if (!addModelId || !modelById(addModelId)) return seeded

  const existing = seeded.find((line) => line.modelId === addModelId)
  if (existing) {
    existing.quantity += addQuantity
    return seeded
  }
  return [...seeded, { modelId: addModelId, quantity: addQuantity }]
}
