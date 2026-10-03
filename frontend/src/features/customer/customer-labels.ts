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
  AccountStatus,
  ChargeStatus,
  ChargeType,
  CustomerType,
  IdDocumentType,
  RentalStatus,
  ReservationStatus,
} from '../../shared/api/contract'

/** Keyed by the statuses the API sends for a reservation. */
export const RESERVATION_STATUS_LABEL: Record<ReservationStatus, string> = {
  DRAFT: 'Not finished',
  HELD: 'Held for you',
  CONFIRMED: 'Confirmed',
  COLLECTED: 'Out with you',
  RETURNED: 'Returned',
  CANCELLED: 'Cancelled',
  NO_SHOW: 'Not collected',
  EXPIRED: 'Expired',
}

/** Where a hire stands, keyed by the statuses the API sends for a rental. */
export const HIRE_STATUS_LABEL: Record<RentalStatus, string> = {
  OPEN: 'Out with you',
  OVERDUE: 'Overdue',
  PARTIALLY_RETURNED: 'Partly returned',
  RETURNED: 'Returned',
  SETTLED: 'Returned and settled',
}

/** What a charge on a hire is for, in the words a customer reads. */
export const HIRE_CHARGE_LABEL: Record<ChargeType, string> = {
  HIRE: 'Hire',
  DEPOSIT_HOLD: 'Deposit held',
  DEPOSIT_RELEASE: 'Deposit returned to you',
  DEPOSIT_FORFEIT: 'Deposit kept',
  LATE_FEE: 'Late return',
  DAMAGE_RECOVERY: 'Damage or loss',
  CLEANING: 'Cleaning',
  ADJUSTMENT: 'Adjustment',
}

/** Where a charge stands, in the words a customer reads. */
export const HIRE_CHARGE_STATUS_LABEL: Record<ChargeStatus, string> = {
  PENDING: 'Not settled yet',
  SETTLED: 'Settled',
  WAIVED: 'Waived',
  REVERSED: 'Reversed',
}

export const ID_DOC_LABEL: Record<IdDocumentType, string> = {
  SA_ID: 'South African ID',
  PASSPORT: 'Passport',
  DRIVING_LICENCE: 'Driving licence',
}

/** Where an account stands, in the words a customer reads. */
export const ACCOUNT_STATUS_LABEL: Record<AccountStatus, string> = {
  ACTIVE: 'Good standing',
  ON_HOLD: 'On hold',
  BLACKLISTED: 'Closed to new bookings',
}

export const CUSTOMER_TYPE_LABEL: Record<CustomerType, string> = {
  INDIVIDUAL: 'Individual',
  TRADE: 'Trade account',
}
