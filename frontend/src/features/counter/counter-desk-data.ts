/**
 * Derivations shared by the counter desk screens, SC-10 to SC-13.
 *
 * The prototype has no back end, so the questions a counter assistant asks
 * all afternoon ("what is going out today", "is this unit free next week",
 * "who has this booked already") are answered by reading the fixtures the
 * same way every time. Doing that in one module rather than four keeps the
 * diary, the dashboard and the booking screen telling one story: if the
 * diary says a unit is spoken for, the booking screen refuses it for the
 * same reason and names the same reservation.
 *
 * Periods are half open, [start, end), which is what the schema and the
 * hire terms both say. A hire returned on the 10th frees the 10th.
 */

import type {
  Asset,
  AssetStatus,
  Branch,
  BranchCode,
  CustomerProfile,
  ProductModel,
  Rental,
  Reservation,
  ReservationStatus,
} from '../../shared/types'
import {
  TODAY,
  assets,
  branches,
  customers,
  productModels,
  rentals,
  reservations,
} from '../../shared/fixtures'
import { daysBetween, humanise } from '../../shared/format'

const MS_PER_DAY = 86_400_000

/* ------------------------------------------------------------------ dates */

/** ISO date strings sort and compare correctly as plain strings, so the
 *  helpers below only ever build them, never parse them for comparison. */
export function addDays(iso: string, days: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d) + days * MS_PER_DAY)
    .toISOString()
    .slice(0, 10)
}

/** 0 is Monday, because a trade counter's week starts on Monday. */
export function weekdayIndex(iso: string): number {
  const [y, m, d] = iso.split('-').map(Number)
  return (new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7
}

export const WEEKDAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export function weekdayName(iso: string): string {
  return WEEKDAY_NAMES[weekdayIndex(iso)]
}

export function startOfWeek(iso: string): string {
  return addDays(iso, -weekdayIndex(iso))
}

export function weekDays(iso: string): string[] {
  const first = startOfWeek(iso)
  return Array.from({ length: 7 }, (_, i) => addDays(first, i))
}

/* ---------------------------------------------------------------- lookups */

const MODELS = new Map(productModels.map((m) => [m.id, m]))
const ASSETS = new Map(assets.map((a) => [a.id, a]))
const CUSTOMERS = new Map(customers.map((c) => [c.id, c]))
const RENTAL_BY_RESERVATION = new Map(rentals.map((r) => [r.reservationId, r]))

export function modelById(id: string): ProductModel {
  const model = MODELS.get(id)
  if (!model) {
    throw new Error(
      `No product model with id "${id}". Every reservation line must point at an entry in fixtures.productModels.`,
    )
  }
  return model
}

export function assetById(id: string): Asset {
  const asset = ASSETS.get(id)
  if (!asset) {
    throw new Error(
      `No asset with id "${id}". Every allocation must point at an entry in fixtures.assets.`,
    )
  }
  return asset
}

export function customerById(id: string): CustomerProfile {
  const customer = CUSTOMERS.get(id)
  if (!customer) {
    throw new Error(
      `No customer with id "${id}". Every reservation must point at an entry in fixtures.customers.`,
    )
  }
  return customer
}

export function branchByCode(code: BranchCode): Branch {
  const branch = branches.find((b) => b.code === code)
  if (!branch) {
    throw new Error(`Unknown branch code "${code}". Valid codes come from fixtures.branches.`)
  }
  return branch
}

export function rentalForReservation(reservationId: string): Rental | undefined {
  return RENTAL_BY_RESERVATION.get(reservationId)
}

/* ------------------------------------------------------------------ scope */

/** Counter staff work at one branch, but a manager covering the group
 *  needs the same figures across all three. */
export type BranchScope = BranchCode | 'ALL'

export function inScope(code: BranchCode, scope: BranchScope): boolean {
  return scope === 'ALL' || code === scope
}

/* ------------------------------------------------------------ diary shape */

export interface CollectionEntry {
  key: string
  reservation: Reservation
  customer: CustomerProfile
  /** "2 x GBH 2-26 DRE Rotary Hammer" */
  headline: string
  units: number
  rental?: Rental
}

export interface ReturnEntry {
  key: string
  reservation: Reservation
  customer: CustomerProfile
  headline: string
  units: number
  rental?: Rental
  dueOn: string
  collected: boolean
  overdue: boolean
  daysLate: number
  outstandingUnits: number
}

export function unitCount(reservation: Reservation): number {
  return reservation.lines.reduce((total, line) => total + line.quantity, 0)
}

export function linesHeadline(reservation: Reservation): string {
  return reservation.lines
    .map((line) => `${line.quantity} x ${modelById(line.productModelId).name}`)
    .join(', ')
}

/** Shown on the diary as something going out. A no-show stays on the page:
 *  the whole point of replacing the paper book is that nothing disappears. */
const DIARY_OUT: ReservationStatus[] = ['HELD', 'CONFIRMED', 'COLLECTED', 'NO_SHOW']

/** Shown on the diary as something coming back. */
const DIARY_BACK: ReservationStatus[] = ['HELD', 'CONFIRMED', 'COLLECTED', 'CLOSED']

function toCollection(reservation: Reservation): CollectionEntry {
  return {
    key: reservation.id,
    reservation,
    customer: customerById(reservation.customerId),
    headline: linesHeadline(reservation),
    units: unitCount(reservation),
    rental: rentalForReservation(reservation.id),
  }
}

function toReturn(reservation: Reservation): ReturnEntry {
  const rental = rentalForReservation(reservation.id)
  const dueOn = rental?.dueBackOn ?? reservation.endDate
  const outstandingUnits = rental
    ? rental.items.filter((item) => !item.returnedAt).length
    : unitCount(reservation)
  const overdue = outstandingUnits > 0 && dueOn < TODAY
  return {
    key: reservation.id,
    reservation,
    customer: customerById(reservation.customerId),
    headline: linesHeadline(reservation),
    units: unitCount(reservation),
    rental,
    dueOn,
    collected: rental !== undefined,
    overdue,
    daysLate: overdue ? daysBetween(dueOn, TODAY) : 0,
    outstandingUnits,
  }
}

export function collectionsOn(dateIso: string, scope: BranchScope): CollectionEntry[] {
  return reservations
    .filter(
      (r) =>
        inScope(r.branchCode, scope) &&
        r.startDate === dateIso &&
        DIARY_OUT.includes(r.status),
    )
    .map(toCollection)
    .sort((a, b) => a.reservation.reference.localeCompare(b.reservation.reference))
}

export function returnsOn(dateIso: string, scope: BranchScope): ReturnEntry[] {
  return reservations
    .filter((r) => inScope(r.branchCode, scope) && DIARY_BACK.includes(r.status))
    .map(toReturn)
    .filter((entry) => entry.dueOn === dateIso)
    .sort((a, b) => a.reservation.reference.localeCompare(b.reservation.reference))
}

/** Everything still out past its due date, whatever day it was due. */
export function overdueReturns(scope: BranchScope): ReturnEntry[] {
  return reservations
    .filter((r) => inScope(r.branchCode, scope) && DIARY_BACK.includes(r.status))
    .map(toReturn)
    .filter((entry) => entry.overdue)
    .sort((a, b) => b.daysLate - a.daysLate)
}

/** Late fees accrued so far, at the model's daily late fee per unit still
 *  out. This is the figure the customer is quoted over the counter. */
export function lateFeeRunning(entry: ReturnEntry): number {
  if (!entry.rental || !entry.overdue) return 0
  return entry.rental.items
    .filter((item) => !item.returnedAt)
    .reduce(
      (total, item) =>
        total + modelById(assetById(item.assetId).productModelId).lateFeePerDay * entry.daysLate,
      0,
    )
}

/* ----------------------------------------------------------- fleet health */

const OUT_OF_SERVICE: AssetStatus[] = ['QUARANTINED', 'MAINTENANCE', 'RETIRED', 'LOST']

export function isServiceable(asset: Asset): boolean {
  return !OUT_OF_SERVICE.includes(asset.status)
}

export function assetsWithStatus(status: AssetStatus, scope: BranchScope): Asset[] {
  return assets.filter((a) => a.status === status && inScope(a.branchCode, scope))
}

export interface ReallocationFlag {
  reservation: Reservation
  customer: CustomerProfile
  reason: string
}

/** A booking that cannot go out as it stands: a line with no unit set
 *  aside, or a unit that has since been withdrawn from service. */
export function bookingsNeedingReallocation(scope: BranchScope): ReallocationFlag[] {
  const flags: ReallocationFlag[] = []
  for (const reservation of reservations) {
    if (!inScope(reservation.branchCode, scope)) continue
    if (reservation.status !== 'HELD' && reservation.status !== 'CONFIRMED') continue
    if (reservation.endDate < TODAY) continue
    for (const line of reservation.lines) {
      const model = modelById(line.productModelId)
      if (line.allocatedAssetIds.length < line.quantity) {
        flags.push({
          reservation,
          customer: customerById(reservation.customerId),
          reason: `${line.quantity - line.allocatedAssetIds.length} of ${line.quantity} ${model.name} still to be set aside`,
        })
        continue
      }
      for (const assetId of line.allocatedAssetIds) {
        const asset = assetById(assetId)
        if (!isServiceable(asset)) {
          flags.push({
            reservation,
            customer: customerById(reservation.customerId),
            reason: `${asset.tag} is ${humanise(asset.status).toLowerCase()} and cannot go out`,
          })
        }
      }
    }
  }
  return flags
}

