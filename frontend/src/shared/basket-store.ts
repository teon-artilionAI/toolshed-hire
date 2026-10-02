/**
 * The hire basket.
 *
 * One reservation is one period at one collection branch, with one or more
 * models on it. The basket is a reservation that has not been made yet, so it
 * holds exactly that. A period, a branch, and a line for each model with how
 * many are wanted. It holds no price. The server prices a basket when it is
 * turned into a reservation, and until then there is no figure to keep.
 *
 * ONE PERIOD AND ONE BRANCH
 * =========================
 * A model can only be added for the period and the branch the basket already
 * has. Adding one for anything else is not done quietly. `addToBasket` answers
 * `conflict` and changes nothing, and the screen asks the person which period
 * and branch to keep.
 *
 * A BOOKING THAT IS UNDER WAY
 * ===========================
 * Once the server has made a reservation from the basket, the basket remembers
 * its id. A reload in the middle of a booking can then pick the same
 * reservation up again, and does not make a second one that would compete with
 * the first for the same equipment.
 *
 * A RESERVATION THAT WAS SET ASIDE
 * ================================
 * A reservation is priced for the basket as it was. When the person steps back
 * from it to look at the basket again, or the basket changes underneath it,
 * the reservation stops being the booking under way and is set aside. The
 * basket still remembers its id, and whether the basket has changed since. The
 * next booking reads that. An unchanged basket carries on with the reservation
 * it already has, and a changed one has the old reservation cancelled before a
 * new one is made, so no draft is left behind for every change of mind.
 *
 * An empty basket remembers nothing.
 *
 * The basket lives in memory, outside React, and is copied to the tab's
 * storage on every change through basket-storage.ts. A visitor may build one
 * without an account.
 */

import { MAX_QUANTITY, MIN_QUANTITY } from './api/catalogue'
import { logEvent } from './api/log'
import { clearStoredBasket, readStoredBasket, writeStoredBasket } from './basket-storage'
import { parseStoredBasket, serialiseBasket } from './basket-stored-shape'

/** One model in the basket and how many of it are wanted. */
export interface BasketLine {
  readonly modelSlug: string
  readonly quantity: number
}

export interface Basket {
  /** The collection day as `YYYY-MM-DD`. Empty while the basket is empty. */
  readonly from: string
  /** The return day as `YYYY-MM-DD`, which is not charged. */
  readonly to: string
  /** The code of the collection branch. */
  readonly branchCode: string
  readonly lines: readonly BasketLine[]
  /** The reservation the server made from this basket, while a booking is
   *  under way. Null otherwise. */
  readonly reservationId: string | null
  /** A reservation made from this basket that is no longer the booking under
   *  way. Null when there is none. */
  readonly setAside: SetAsideReservation | null
}

/** A reservation the person stepped back from, or that the basket has changed
 *  underneath. */
export interface SetAsideReservation {
  readonly reservationId: string
  /** True while the basket is still what the reservation was made from. */
  readonly fitsBasket: boolean
}

/** A model, a quantity, and the period and branch it was chosen for. */
export interface BasketAddition extends BasketLine {
  from: string
  to: string
  branchCode: string
}

/** The period and the branch a basket is for. */
export type BasketTerms = Pick<Basket, 'from' | 'to' | 'branchCode'>

/**
 * - `added`: the model is in the basket. `quantity` is how many of it the
 *   basket now holds, which is capped at the most one booking may ask for.
 * - `conflict`: the basket is for another period or branch, and was left as it
 *   was. `basket` says what it is for.
 */
export type AddOutcome =
  | { outcome: 'added'; quantity: number }
  | { outcome: 'conflict'; basket: BasketTerms }

/**
 * What to do when the model was chosen for another period or branch.
 *
 * - `ask`: change nothing and answer `conflict`.
 * - `moveBasket`: move the whole basket to the new period and branch, then add.
 */
export type OnDifferentTerms = 'ask' | 'moveBasket'

const EMPTY_BASKET: Basket = Object.freeze({
  from: '',
  to: '',
  branchCode: '',
  lines: Object.freeze([]),
  reservationId: null,
  setAside: null,
})

type Listener = () => void

const listeners = new Set<Listener>()

function clampQuantity(quantity: number): number {
  if (!Number.isFinite(quantity)) return MIN_QUANTITY
  return Math.min(Math.max(MIN_QUANTITY, Math.trunc(quantity)), MAX_QUANTITY)
}

function restore(): Basket {
  const raw = readStoredBasket()
  return (raw === null ? null : parseStoredBasket(raw)) ?? EMPTY_BASKET
}

let current: Basket = restore()

/** Replace the basket, copy it to storage and tell every subscriber. A basket
 *  with no lines is the empty basket, with no period and no branch. */
function commit(next: Basket): void {
  current = next.lines.length === 0 ? EMPTY_BASKET : next
  if (current === EMPTY_BASKET) clearStoredBasket()
  else writeStoredBasket(serialiseBasket(current))
  logEvent('info', 'basket.changed', {
    lines: current.lines.length,
    units: basketUnitCount(current),
    booking_under_way: current.reservationId !== null,
    reservation_set_aside: current.setAside !== null,
  })
  listeners.forEach((listener) => listener())
}

/** The basket as it stands. The same object until the basket changes. */
export function basketSnapshot(): Basket {
  return current
}

export function subscribeToBasket(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** How many units the basket holds across every line. The shell shows this. */
export function basketUnitCount(basket: Basket): number {
  return basket.lines.reduce((units, line) => units + line.quantity, 0)
}

/**
 * What becomes of the reservation the basket remembers once the basket changes.
 *
 * It was priced for the basket as it was, so it is no longer the booking under
 * way and no longer fits. It is kept as set aside, so the next booking can
 * cancel it before it makes another.
 */
function setAsideByAChange(basket: Basket): SetAsideReservation | null {
  const reservationId = basket.reservationId ?? basket.setAside?.reservationId
  return reservationId === undefined ? null : { reservationId, fitsBasket: false }
}

/** The basket with other lines or other terms. The reservation it remembers
 *  was made from it as it was, so that one is set aside. */
function changed(change: Partial<Pick<Basket, 'from' | 'to' | 'branchCode' | 'lines'>>): Basket {
  return { ...current, ...change, reservationId: null, setAside: setAsideByAChange(current) }
}

function sameTerms(basket: Basket, addition: BasketAddition): boolean {
  return (
    basket.from === addition.from &&
    basket.to === addition.to &&
    basket.branchCode === addition.branchCode
  )
}

/**
 * Add a model to the basket.
 *
 * A model the basket already holds has its quantity raised, up to the most one
 * booking may ask for.
 *
 * @param addition The model, how many, and the period and branch it is for.
 * @param onDifferentTerms What to do when the basket is for another period or
 *   branch. The default asks, which changes nothing.
 */
export function addToBasket(
  addition: BasketAddition,
  onDifferentTerms: OnDifferentTerms = 'ask',
): AddOutcome {
  const { modelSlug, from, to, branchCode } = addition
  const empty = current.lines.length === 0
  if (!empty && !sameTerms(current, addition) && onDifferentTerms === 'ask') {
    return {
      outcome: 'conflict',
      basket: { from: current.from, to: current.to, branchCode: current.branchCode },
    }
  }
  const held = current.lines.find((line) => line.modelSlug === modelSlug)?.quantity ?? 0
  const quantity = clampQuantity(held + clampQuantity(addition.quantity))
  // A model already at the most a booking may ask for, on the same terms, is
  // the basket as it was. Nothing is committed, so nothing is set aside.
  if (quantity === held && sameTerms(current, addition)) return { outcome: 'added', quantity }
  const lines =
    held > 0
      ? current.lines.map((line) => (line.modelSlug === modelSlug ? { modelSlug, quantity } : line))
      : [...current.lines, { modelSlug, quantity }]
  commit(changed({ from, to, branchCode, lines }))
  return { outcome: 'added', quantity }
}

/** Change how many of one model are wanted. A model the basket does not hold
 *  is left alone, and so is one that already has that quantity. */
export function setBasketQuantity(modelSlug: string, quantity: number): void {
  const wanted = clampQuantity(quantity)
  const held = current.lines.find((line) => line.modelSlug === modelSlug)
  if (held === undefined || held.quantity === wanted) return
  const lines = current.lines.map((line) =>
    line.modelSlug === modelSlug ? { modelSlug, quantity: wanted } : line,
  )
  commit(changed({ lines }))
}

/** Take one model out. Taking the last one out empties the basket. */
export function removeFromBasket(modelSlug: string): void {
  const lines = current.lines.filter((line) => line.modelSlug !== modelSlug)
  if (lines.length === current.lines.length) return
  commit(changed({ lines }))
}

/** Move the whole basket to another period, another branch, or both. An empty
 *  basket has neither, so there is nothing to move. Terms it already has are
 *  not a change. */
export function setBasketTerms(terms: Partial<BasketTerms>): void {
  if (current.lines.length === 0) return
  const next = { from: current.from, to: current.to, branchCode: current.branchCode, ...terms }
  if (next.from === current.from && next.to === current.to && next.branchCode === current.branchCode) return
  commit(changed(next))
}

/** Remember the reservation the server made from the basket as it stands. It
 *  takes the place of any that was set aside. */
export function noteBookingUnderWay(reservationId: string): void {
  if (current.lines.length === 0 || current.reservationId === reservationId) return
  commit({ ...current, reservationId, setAside: null })
}

/**
 * Step back from the booking under way and keep the basket, so the person can
 * look at it again or change it.
 *
 * The reservation is set aside and still fits the basket. If nothing changes,
 * the next booking carries on with it and makes no other.
 */
export function setBookingAside(): void {
  if (current.reservationId === null) return
  commit({
    ...current,
    reservationId: null,
    setAside: { reservationId: current.reservationId, fitsBasket: true },
  })
}

/** Forget the reservation and keep the basket. This is for a reservation that
 *  is over, released or lost, which leaves nothing to carry on with or cancel. */
export function forgetBookingUnderWay(): void {
  if (current.reservationId === null) return
  commit({ ...current, reservationId: null })
}

/** Forget the reservation that was set aside, once it is out of the way. */
export function forgetReservationSetAside(): void {
  if (current.setAside === null) return
  commit({ ...current, setAside: null })
}

/** Empty the basket, once it has been booked or the person has signed out. */
export function clearBasket(): void {
  if (current === EMPTY_BASKET) return
  commit(EMPTY_BASKET)
}

/** Put the basket back to how it starts. The basket lives in a module, so a
 *  test file would otherwise inherit what the last one added. */
export function resetBasketForTests(): void {
  current = EMPTY_BASKET
  listeners.clear()
}
