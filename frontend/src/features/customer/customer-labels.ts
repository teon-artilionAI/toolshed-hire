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
  CustomerType,
  IdDocumentType,
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
