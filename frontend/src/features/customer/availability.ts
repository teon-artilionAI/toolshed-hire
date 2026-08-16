/**
 * Availability arithmetic for the customer flow.
 *
 * The whole point of Toolshed Hire is that the same spanner cannot be
 * promised to two people at once, so this module is where the prototype
 * either earns that claim or does not. Every number the customer sees on
 * SC-01 to SC-04 is derived here from the assets, reservations and rentals
 * fixtures. Nothing is hard coded and nothing is invented.
 *
 * A unit at a branch is free on a given day when all three hold:
 *
 *   1. It is serviceable. Quarantined, in maintenance, retired and lost
 *      units are off the fleet and can never be hired.
 *   2. It is not physically out. A unit on hire is busy until its rental
 *      is due back; a unit whose rental is already overdue is busy for the
 *      whole horizon, because nobody can promise a date for it.
 *   3. It is not committed to a booking. Held, confirmed and collected
 *      reservations that overlap the day take units out of the pool.
 *
 * Rules two and three overlap, because a collected reservation's units are
 * also on hire. Allocated asset identifiers are used to net that off so a
 * unit is never counted against the pool twice.
 *
 * A period is free only if every day in it is free, so period availability
 * is the minimum across the days, not the average.
 */

import { assets, branches, rentals, reservations } from '../../shared/fixtures'
import type {
  Asset,
  AssetStatus,
  Branch,
  BranchCode,
  ReservationStatus,
  Uuid,
} from '../../shared/types'
import { isOverdue } from '../../shared/format'
import { reasonFor } from './availability-reason'
import { AVAILABILITY_HORIZON_DAYS, addDays, eachDay } from './hire-period'

/** Units in these states are off the fleet and never appear as free. */
const OFF_FLEET: ReadonlySet<AssetStatus> = new Set<AssetStatus>([
  'QUARANTINED',
  'MAINTENANCE',
  'RETIRED',
  'LOST',
])

/** Reservation states that hold stock. Draft, cancelled, closed, expired
 *  and no-show bookings release their units back to the pool. */
const HOLDS_STOCK: ReadonlySet<ReservationStatus> = new Set<ReservationStatus>([
  'HELD',
  'CONFIRMED',
  'COLLECTED',
])

/**
 * Driving order between the three branches, nearest first. Used only to
 * word the "try another branch" suggestion, never as hire data.
 */
const BRANCH_NEIGHBOURS: Record<BranchCode, BranchCode[]> = {
  CBD: ['BEL', 'SOM'],
  BEL: ['CBD', 'SOM'],
  SOM: ['BEL', 'CBD'],
}

/** When a unit currently on hire is due back, for hires still running to
 *  time. A unit missing from this map cannot be promised a return date. */
const DUE_BACK_BY_ASSET: ReadonlyMap<Uuid, string> = (() => {
  const map = new Map<Uuid, string>()
  for (const rental of rentals) {
    for (const item of rental.items) {
      if (item.returnedAt) continue
      if (isOverdue(rental.dueBackOn)) continue
      map.set(item.assetId, rental.dueBackOn)
    }
  }
  return map
})()

/** Units that should already have come back and have not. Distinct from a
 *  unit that is simply out, because nobody can put a date on these. */
const OVERDUE_ASSETS: ReadonlySet<Uuid> = new Set(
  rentals.flatMap((rental) =>
    isOverdue(rental.dueBackOn)
      ? rental.items.filter((item) => !item.returnedAt).map((item) => item.assetId)
      : [],
  ),
)

function isPhysicallyOut(asset: Asset, day: string): boolean {
  if (asset.status !== 'ON_HIRE') return false
  const dueBackOn = DUE_BACK_BY_ASSET.get(asset.id)
  // No due date on record, so the unit is treated as busy for the whole
  // horizon rather than optimistically offered to somebody else.
  if (dueBackOn === undefined) return true
  return day < dueBackOn
}

/** Units of a model held at a branch, whatever their state. */
export function fleetAt(modelId: Uuid, branchCode: BranchCode): Asset[] {
  return assets.filter(
    (a) => a.productModelId === modelId && a.branchCode === branchCode,
  )
}

interface DayCount {
  /** Serviceable units physically out on hire on this day. */
  out: number
  /** Serviceable units committed to somebody else's booking on this day. */
  booked: number
  free: number
}

function countForDay(fleet: Asset[], branchCode: BranchCode, modelId: Uuid, day: string): DayCount {
  const serviceable = fleet.filter((a) => !OFF_FLEET.has(a.status))
  const outIds = new Set(
    serviceable.filter((a) => isPhysicallyOut(a, day)).map((a) => a.id),
  )

  let booked = 0
  for (const reservation of reservations) {
    if (reservation.branchCode !== branchCode) continue
    if (!HOLDS_STOCK.has(reservation.status)) continue
    if (day < reservation.startDate || day >= reservation.endDate) continue
    for (const line of reservation.lines) {
      if (line.productModelId !== modelId) continue
      // Units already counted as out must not be counted a second time.
      const alreadyOut = line.allocatedAssetIds.filter((id) => outIds.has(id)).length
      booked += Math.max(0, line.quantity - alreadyOut)
    }
  }

  const free = Math.max(0, serviceable.length - outIds.size - booked)
  return { out: outIds.size, booked, free }
}

export interface BranchAvailability {
  branch: Branch
  /** Units of this model held here, in any state. */
  fleetUnits: number
  /** Units off the fleet for repair, quarantine or write off. */
  offFleetUnits: number
  /** Peak units out on hire during the period. */
  outUnits: number
  /** Peak units committed to other bookings during the period. */
  bookedUnits: number
  /** Units still out past their due date, so no return date can be given. */
  overdueUnits: number
  /** Free for every day of the period, which is the only number that can
   *  honestly be offered to a customer. */
  availableUnits: number
  /** Plain sentence saying why units are not free, or null when the whole
   *  fleet at this branch is free. */
  reason: string | null
}

/** Availability of one model at one branch across a whole period. */
export function availabilityAt(
  modelId: Uuid,
  branchCode: BranchCode,
  startIso: string,
  endIso: string,
): BranchAvailability {
  const branch = branches.find((b) => b.code === branchCode)
  if (!branch) {
    throw new Error(
      `Unknown branch code "${branchCode}". Valid codes come from fixtures.branches.`,
    )
  }

  const fleet = fleetAt(modelId, branchCode)
  const offFleetUnits = fleet.filter((a) => OFF_FLEET.has(a.status)).length
  const workshopUnits = fleet.filter(
    (a) => a.status === 'QUARANTINED' || a.status === 'MAINTENANCE',
  ).length
  const withdrawnUnits = fleet.filter(
    (a) => a.status === 'RETIRED' || a.status === 'LOST',
  ).length
  const overdueUnits = fleet.filter((a) => OVERDUE_ASSETS.has(a.id)).length

  const days = eachDay(startIso, endIso)
  let availableUnits = Number.POSITIVE_INFINITY
  let outUnits = 0
  let bookedUnits = 0
  for (const day of days) {
    const count = countForDay(fleet, branchCode, modelId, day)
    availableUnits = Math.min(availableUnits, count.free)
    outUnits = Math.max(outUnits, count.out)
    bookedUnits = Math.max(bookedUnits, count.booked)
  }
  if (!Number.isFinite(availableUnits)) availableUnits = 0

  return {
    branch,
    fleetUnits: fleet.length,
    offFleetUnits,
    outUnits,
    bookedUnits,
    overdueUnits,
    availableUnits,
    reason: reasonFor({
      fleetUnits: fleet.length,
      workshopUnits,
      withdrawnUnits,
      outUnits,
      bookedUnits,
      overdueUnits,
      availableUnits,
    }),
  }
}

/** Availability of one model at every branch, in fixture branch order. */
export function availabilityEverywhere(
  modelId: Uuid,
  startIso: string,
  endIso: string,
): BranchAvailability[] {
  return branches.map((b) => availabilityAt(modelId, b.code, startIso, endIso))
}

/** Total units of a model free anywhere for the period. */
export function totalAvailable(modelId: Uuid, startIso: string, endIso: string): number {
  return availabilityEverywhere(modelId, startIso, endIso).reduce(
    (sum, row) => sum + row.availableUnits,
    0,
  )
}

/**
 * The closest branch that can actually supply the quantity asked for, so
 * a customer told "not here" is told where instead rather than left stuck.
 */
export function nearestBranchWithStock(
  modelId: Uuid,
  from: BranchCode,
  startIso: string,
  endIso: string,
  quantity = 1,
): BranchAvailability | null {
  for (const code of BRANCH_NEIGHBOURS[from]) {
    const row = availabilityAt(modelId, code, startIso, endIso)
    if (row.availableUnits >= quantity) return row
  }
  return null
}

export interface DayAvailability {
  date: string
  availableUnits: number
  serviceableUnits: number
}

/** The day by day strip on SC-03. One entry per day, starting at `startIso`. */
export function availabilityStrip(
  modelId: Uuid,
  branchCode: BranchCode,
  startIso: string,
  days = AVAILABILITY_HORIZON_DAYS,
): DayAvailability[] {
  const fleet = fleetAt(modelId, branchCode)
  const serviceableUnits = fleet.filter((a) => !OFF_FLEET.has(a.status)).length
  return Array.from({ length: days }, (_, offset) => {
    const date = addDays(startIso, offset)
    return {
      date,
      availableUnits: countForDay(fleet, branchCode, modelId, date).free,
      serviceableUnits,
    }
  })
}
