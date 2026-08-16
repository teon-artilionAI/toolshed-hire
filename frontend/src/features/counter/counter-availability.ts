/**
 * Can this unit take this period, and if not, what do we offer instead.
 *
 * This is the part of the system the client is actually buying. The paper
 * diary cannot answer it, which is why two customers occasionally arrive
 * for the same breaker. Every rule that makes a unit unavailable lives
 * here, and every screen that shows a conflict names the same reason.
 *
 * A unit is unavailable when it is out of service, when it is physically
 * still out on a hire that has not come back, or when a live booking
 * already overlaps the period. Periods are half open: a hire ending on the
 * 16th frees the 16th.
 */

import type { Asset, Branch, BranchCode, Rental, RentalStatus, Reservation, ReservationStatus } from '../../shared/types'
import { TODAY, assets, branches, rentals, reservations } from '../../shared/fixtures'
import { daysBetween, formatDate, humanise } from '../../shared/format'
import { addDays, assetById, isServiceable } from './counter-desk-data'

/** Statuses that hold a unit for someone. A cancelled, expired or
 *  no-show booking releases the unit, which is why they are not here. */
const BLOCKING: ReservationStatus[] = ['HELD', 'CONFIRMED', 'COLLECTED']

const OPEN_RENTALS: RentalStatus[] = ['OPEN', 'OVERDUE', 'PARTIALLY_RETURNED']

export function overlaps(aStart: string, aEnd: string, bStart: string, bEnd: string): boolean {
  return aStart < bEnd && bStart < aEnd
}

export function bookingsForAsset(assetId: string): Reservation[] {
  return reservations.filter(
    (r) =>
      BLOCKING.includes(r.status) &&
      r.lines.some((line) => line.allocatedAssetIds.includes(assetId)),
  )
}

/** The hire this unit is physically out on right now, if any. A unit that
 *  has not come back cannot be promised to anyone, whatever the diary says. */
export function openRentalForAsset(assetId: string): Rental | undefined {
  return rentals.find(
    (rental) =>
      OPEN_RENTALS.includes(rental.status) &&
      rental.items.some((item) => item.assetId === assetId && !item.returnedAt),
  )
}

export type UnitState =
  | { kind: 'free' }
  | { kind: 'out-of-service'; reason: string }
  | { kind: 'still-out'; rental: Rental; freeFrom: string; daysLate: number }
  | { kind: 'clash'; reservation: Reservation; freeFrom: string }

/** Why this specific unit can or cannot take this specific period. */
export function unitState(asset: Asset, startDate: string, endDate: string): UnitState {
  if (!isServiceable(asset)) {
    return {
      kind: 'out-of-service',
      reason: `${asset.tag} is ${humanise(asset.status).toLowerCase()}`,
    }
  }

  const outNow = openRentalForAsset(asset.id)
  if (outNow) {
    const late = outNow.dueBackOn < TODAY
    // A late unit has no promised return date, so the earliest we offer it
    // is tomorrow, and only once it is actually back on the shelf.
    const freeFrom = late ? addDays(TODAY, 1) : outNow.dueBackOn
    if (startDate < freeFrom) {
      return {
        kind: 'still-out',
        rental: outNow,
        freeFrom,
        daysLate: late ? daysBetween(outNow.dueBackOn, TODAY) : 0,
      }
    }
  }

  const clash = bookingsForAsset(asset.id).find((r) =>
    overlaps(startDate, endDate, r.startDate, r.endDate),
  )
  if (clash) return { kind: 'clash', reservation: clash, freeFrom: clash.endDate }
  return { kind: 'free' }
}

/** One line of plain English for a unit's state, used by the unit picker
 *  and the conflict panel alike so the two can never disagree. */
export function unitStateSummary(state: UnitState): string {
  switch (state.kind) {
    case 'free':
      return 'Free for these dates'
    case 'out-of-service':
      return `${state.reason}, so it cannot go out`
    case 'still-out':
      return state.daysLate > 0
        ? `Still out on ${state.rental.reference}, ${state.daysLate} days late`
        : `Out until ${formatDate(state.rental.dueBackOn)} on ${state.rental.reference}`
    case 'clash':
      return `Held for ${state.reservation.reference}, ${formatDate(state.reservation.startDate)} to ${formatDate(state.reservation.endDate)}`
  }
}

export function unitsForModel(modelId: string, branch: BranchCode): Asset[] {
  return assets.filter((a) => a.productModelId === modelId && a.branchCode === branch)
}

export function freeUnits(
  modelId: string,
  branch: BranchCode,
  startDate: string,
  endDate: string,
): Asset[] {
  return unitsForModel(modelId, branch).filter(
    (asset) => unitState(asset, startDate, endDate).kind === 'free',
  )
}

export interface BranchOption {
  branch: Branch
  free: Asset[]
}

/** Where else this model is free over the same dates. The answer a counter
 *  assistant gives before the customer gives up and phones a competitor. */
export function branchAvailability(
  modelId: string,
  startDate: string,
  endDate: string,
): BranchOption[] {
  return branches.map((branch) => ({
    branch,
    free: freeUnits(modelId, branch.code, startDate, endDate),
  }))
}

/** The soonest this unit could take a hire of the same length. */
export function nextFreePeriod(
  asset: Asset,
  startDate: string,
  endDate: string,
): { startDate: string; endDate: string } | undefined {
  const nights = Math.max(1, daysBetween(startDate, endDate))
  let candidate = startDate
  for (let attempt = 0; attempt < 12; attempt += 1) {
    const state = unitState(asset, candidate, addDays(candidate, nights))
    if (state.kind === 'free') {
      return { startDate: candidate, endDate: addDays(candidate, nights) }
    }
    if (state.kind === 'out-of-service') return undefined
    candidate = state.freeFrom
  }
  return undefined
}

/* ------------------------------------------------------- booking a line */

export type AllocationMode = 'AUTO' | 'MANUAL'

export interface BookingLineDraft {
  id: string
  modelId: string
  quantity: number
  mode: AllocationMode
  /** Units the assistant picked by hand. Ignored when the mode is AUTO. */
  assetIds: string[]
}

export interface LineAllocation {
  /** Every unit of this model at this branch, with its state. */
  units: { asset: Asset; state: UnitState }[]
  free: Asset[]
  /** What this line would actually take out. */
  chosen: { asset: Asset; state: UnitState }[]
  /** Chosen units that cannot go out, which is the conflict. */
  blocked: { asset: Asset; state: UnitState }[]
  /** Units still to be found, when there are not enough free ones. */
  shortfall: number
  /** Null when the line is bookable as it stands. */
  problem: string | null
}

/**
 * Work out what a booking line would take out, and what is wrong with it.
 * Pure, so the booking screen and its line editor read the same answer.
 */
export function allocateLine(
  line: BookingLineDraft,
  branch: BranchCode,
  startDate: string,
  endDate: string,
): LineAllocation {
  const units = unitsForModel(line.modelId, branch).map((asset) => ({
    asset,
    state: unitState(asset, startDate, endDate),
  }))
  const free = units.filter((u) => u.state.kind === 'free').map((u) => u.asset)

  const chosen =
    line.mode === 'MANUAL'
      ? line.assetIds.map((id) => {
          const asset = assetById(id)
          return { asset, state: unitState(asset, startDate, endDate) }
        })
      : free.slice(0, line.quantity).map((asset) => ({ asset, state: { kind: 'free' } as UnitState }))

  const blocked = chosen.filter((u) => u.state.kind !== 'free')
  const shortfall = Math.max(0, line.quantity - chosen.filter((u) => u.state.kind === 'free').length)

  let problem: string | null = null
  if (units.length === 0) {
    problem = 'This branch does not carry this model.'
  } else if (blocked.length > 0) {
    problem =
      blocked.length === 1
        ? `${blocked[0].asset.tag} is not free for these dates.`
        : `${blocked.length} of the units picked are not free for these dates.`
  } else if (line.mode === 'MANUAL' && chosen.length > line.quantity) {
    problem = `${chosen.length} units are picked but the quantity is ${line.quantity}. Uncheck one, or raise the quantity.`
  } else if (shortfall > 0) {
    if (line.mode === 'MANUAL' && free.length >= line.quantity) {
      problem = `Pick ${line.quantity} ${line.quantity === 1 ? 'unit' : 'units'} for this line, or let the system pick.`
    } else if (free.length === 0) {
      problem = 'Nothing of this model is free at this branch for these dates.'
    } else {
      problem = `Only ${free.length} of ${line.quantity} are free at this branch for these dates.`
    }
  }

  return { units, free, chosen, blocked, shortfall, problem }
}

/** Next reference in the documented series, so a booking made here looks
 *  like the ones already on file. */
export function nextReservationReference(): string {
  const highest = reservations.reduce(
    (max, r) => Math.max(max, Number(r.reference.slice(-6))),
    0,
  )
  return `TSH-R-26-${String(highest + 1).padStart(6, '0')}`
}
