/**
 * Customer facing names for the domain enumerations.
 *
 * The stored values are engineering names such as `NO_SHOW`. A person
 * looking at their own booking should read "Not collected" instead, so the
 * translation happens once here rather than being reinvented per screen.
 * Staff screens keep the engineering wording, which is why this map lives
 * in the customer feature folder and not in the shared layer.
 */

import type {
  ChargeKind,
  CustomerProfile,
  RentalStatus,
  ReservationStatus,
} from '../../shared/types'

export const RESERVATION_STATUS_LABEL: Record<ReservationStatus, string> = {
  DRAFT: 'Not finished',
  HELD: 'Held for you',
  CONFIRMED: 'Confirmed',
  COLLECTED: 'Out with you',
  CLOSED: 'Finished',
  CANCELLED: 'Cancelled',
  NO_SHOW: 'Not collected',
  EXPIRED: 'Expired',
}

export const RENTAL_STATUS_LABEL: Record<RentalStatus, string> = {
  OPEN: 'Out with you',
  OVERDUE: 'Overdue',
  PARTIALLY_RETURNED: 'Part returned',
  RETURNED: 'Returned',
  SETTLED: 'Settled',
}

export const CHARGE_KIND_LABEL: Record<ChargeKind, string> = {
  HIRE: 'Hire charge',
  DEPOSIT: 'Deposit held',
  LATE_FEE: 'Late fee',
  DAMAGE: 'Damage charge',
  REFUND: 'Deposit released',
}

export const ID_DOC_LABEL: Record<CustomerProfile['idDocType'], string> = {
  SA_ID: 'South African ID',
  PASSPORT: 'Passport',
  DRIVING_LICENCE: 'Driving licence',
}

/** Bookings in these states have not been collected yet, so they can still
 *  be cancelled by the customer without involving the counter. */
export const CANCELLABLE_STATUSES: ReservationStatus[] = [
  'DRAFT',
  'HELD',
  'CONFIRMED',
]

/** Bookings in these states are live: either coming up or out on hire. */
export const CURRENT_STATUSES: ReservationStatus[] = [
  'DRAFT',
  'HELD',
  'CONFIRMED',
  'COLLECTED',
]
