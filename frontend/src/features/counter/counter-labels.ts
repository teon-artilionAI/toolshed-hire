/**
 * The words the counter screens use for the API's enumerations.
 *
 * Staff read the account standing plainly, because they have to act on it.
 * "On hold" and "Blacklisted" are what an owner says at the counter, so that
 * is what the screens say. The customer screens keep softer words of their
 * own, in the customer folder.
 */

import type {
  AccountStatus,
  ConditionGrade,
  CustomerType,
  IdDocumentType,
} from '../../shared/api/contract'

export const ACCOUNT_STANDING_LABEL: Record<AccountStatus, string> = {
  ACTIVE: 'Good standing',
  ON_HOLD: 'Account on hold',
  BLACKLISTED: 'Blacklisted',
}

/** The status pill each standing is drawn with, so colour follows the words. */
export const ACCOUNT_STANDING_PILL: Record<AccountStatus, string> = {
  ACTIVE: 'AVAILABLE',
  ON_HOLD: 'OVERDUE',
  BLACKLISTED: 'OVERDUE',
}

/** Why a customer who is not in good standing cannot be booked for. */
export const NO_BOOKING_BECAUSE: Record<Exclude<AccountStatus, 'ACTIVE'>, string> = {
  ON_HOLD: 'The account is on hold, so no new booking can be made until an administrator lifts the hold.',
  BLACKLISTED: 'The account is blacklisted, so the branch does not hire to this customer.',
}

export const ID_DOCUMENT_LABEL: Record<IdDocumentType, string> = {
  SA_ID: 'South African ID',
  PASSPORT: 'Passport',
  DRIVING_LICENCE: 'Driving licence',
}

export const CUSTOMER_TYPE_LABEL: Record<CustomerType, string> = {
  INDIVIDUAL: 'Individual',
  TRADE: 'Trade account',
}

/** What each grade means, said out loud at the counter. */
export const CONDITION_GRADE_LABEL: Record<ConditionGrade, string> = {
  A: 'A, as new',
  B: 'B, good working order',
  C: 'C, worn but serviceable',
}

/** Whether a customer may be booked for. Only good standing may. */
export function canBookFor(status: AccountStatus): status is 'ACTIVE' {
  return status === 'ACTIVE'
}
