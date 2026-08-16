/**
 * Fleet arithmetic for the admin screens.
 *
 * Every figure the owner reads is derived here from the fixtures rather
 * than stored anywhere, so the dashboard, the branch table and the asset
 * register can never quietly disagree with one another.
 *
 * Used by SC-19. Kept out of the screen file so the screen stays about
 * layout and interaction rather than sums.
 */

import type { AssetStatus, BranchCode, ReservationStatus } from '../../shared/types'
import {
  assets, branches, charges, productModels, rentals, reservations,
} from '../../shared/fixtures'
import { daysBetween, isOverdue } from '../../shared/format'

/** A unit that is off the road earns nothing and cannot be hired out. */
export const OFF_ROAD: AssetStatus[] = ['QUARANTINED', 'MAINTENANCE']
/** Retired and lost units have left the fleet, so they do not drag utilisation down. */
export const OUT_OF_FLEET: AssetStatus[] = ['RETIRED', 'LOST']
/** Bookings that will never be collected are not money on the books. */
const NOT_ON_THE_BOOKS: ReservationStatus[] = ['CANCELLED', 'NO_SHOW', 'EXPIRED']
/** Rentals still in the customer's hands. */
const STILL_OUT: string[] = ['OPEN', 'OVERDUE', 'PARTIALLY_RETURNED']
/** The share of the hireable fleet the business aims to keep out on hire. */
export const UTILISATION_TARGET = 55

export interface BranchPosition {
  code: BranchCode
  name: string
  units: number
  onHire: number
  available: number
  offRoad: number
  /** Units on hire as a percentage of the hireable fleet. */
  utilisation: number
  /** Hire value of every booking that is still expected to run. */
  booked: number
  chargedToDate: number
  unitsOverdue: number
  /** Replacement value of units still out late, plus unpaid late fees. */
  exposure: number
}

function replacementValueOf(assetId: string): number {
  const asset = assets.find((a) => a.id === assetId)
  const model = productModels.find((m) => m.id === asset?.productModelId)
  return model?.replacementValue ?? 0
}

/** Rentals at a branch that are still out and past their return date. */
export function overdueRentalsAt(code: BranchCode) {
  return rentals.filter(
    (r) => r.branchCode === code && STILL_OUT.includes(r.status) && isOverdue(r.dueBackOn),
  )
}

function positionFor(code: BranchCode): BranchPosition {
  const branch = branches.find((b) => b.code === code)
  const fleet = assets.filter((a) => a.branchCode === code)
  const hireable = fleet.filter((a) => !OUT_OF_FLEET.includes(a.status))
  const onHire = fleet.filter((a) => a.status === 'ON_HIRE').length

  const booked = reservations
    .filter((r) => r.branchCode === code && !NOT_ON_THE_BOOKS.includes(r.status))
    .reduce((sum, r) => {
      const days = daysBetween(r.startDate, r.endDate)
      return sum + r.lines.reduce((s, l) => s + l.quantity * l.ratePerDaySnapshot * days, 0)
    }, 0)

  const rentalIds = new Set(rentals.filter((r) => r.branchCode === code).map((r) => r.id))
  const branchCharges = charges.filter((c) => rentalIds.has(c.rentalId))
  const chargedToDate = branchCharges
    .filter((c) => c.kind === 'HIRE' || c.kind === 'LATE_FEE')
    .reduce((sum, c) => sum + c.amount, 0)

  const late = overdueRentalsAt(code)
  const lateIds = new Set(late.map((r) => r.id))
  const stillOut = late.flatMap((r) => r.items.filter((i) => !i.returnedAt))
  const unpaidLateFees = branchCharges
    .filter((c) => c.kind === 'LATE_FEE' && !c.settled && lateIds.has(c.rentalId))
    .reduce((sum, c) => sum + c.amount, 0)

  return {
    code,
    name: branch?.name ?? code,
    units: fleet.length,
    onHire,
    available: fleet.filter((a) => a.status === 'AVAILABLE').length,
    offRoad: fleet.filter((a) => OFF_ROAD.includes(a.status)).length,
    utilisation: hireable.length === 0 ? 0 : Math.round((onHire / hireable.length) * 100),
    booked,
    chargedToDate,
    unitsOverdue: stillOut.length,
    exposure: stillOut.reduce((s, i) => s + replacementValueOf(i.assetId), 0) + unpaidLateFees,
  }
}

/** The position at each of the three branches, worked out once. */
export const BRANCH_POSITIONS: BranchPosition[] = branches.map((b) => positionFor(b.code))

/** Roll a set of branches up into one line. Utilisation is recalculated
 *  across the combined fleet rather than averaged, because averaging three
 *  branches of different sizes gives a number that means nothing. */
export function combine(rows: BranchPosition[], name: string): BranchPosition {
  const codes = new Set(rows.map((r) => r.code))
  const onHire = rows.reduce((s, r) => s + r.onHire, 0)
  const hireable = assets.filter(
    (a) => codes.has(a.branchCode) && !OUT_OF_FLEET.includes(a.status),
  ).length
  const sum = (pick: (r: BranchPosition) => number) => rows.reduce((s, r) => s + pick(r), 0)

  return {
    code: rows[0]?.code ?? 'CBD',
    name,
    units: sum((r) => r.units),
    onHire,
    available: sum((r) => r.available),
    offRoad: sum((r) => r.offRoad),
    utilisation: hireable === 0 ? 0 : Math.round((onHire / hireable) * 100),
    booked: sum((r) => r.booked),
    chargedToDate: sum((r) => r.chargedToDate),
    unitsOverdue: sum((r) => r.unitsOverdue),
    exposure: sum((r) => r.exposure),
  }
}
