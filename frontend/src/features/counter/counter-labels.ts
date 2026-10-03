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
  AssetStatus,
  ChargeStatus,
  ChargeType,
  ConditionGrade,
  CustomerType,
  DamageSeverity,
  DamageStatus,
  DiaryCollectionStatus,
  IdDocumentType,
  RentalStatus,
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

/** Where a booking in the diary stands, said the way the branch says it. */
export const DIARY_COLLECTION_LABEL: Record<DiaryCollectionStatus, string> = {
  CONFIRMED: 'Booked, not collected yet',
  COLLECTED: 'Collected',
  RETURNED: 'Collected and back',
  NO_SHOW: 'No show',
}

/** Where a hire stands. */
export const RENTAL_STATUS_LABEL: Record<RentalStatus, string> = {
  OPEN: 'Out with the customer',
  OVERDUE: 'Overdue',
  PARTIALLY_RETURNED: 'Partly back',
  RETURNED: 'Back',
  SETTLED: 'Back and settled',
}

/** What a charge on a hire is for. */
export const CHARGE_TYPE_LABEL: Record<ChargeType, string> = {
  HIRE: 'Hire',
  DEPOSIT_HOLD: 'Deposit held',
  DEPOSIT_RELEASE: 'Deposit released',
  DEPOSIT_FORFEIT: 'Deposit forfeited',
  LATE_FEE: 'Late fee',
  DAMAGE_RECOVERY: 'Recovery charge',
  CLEANING: 'Cleaning',
  ADJUSTMENT: 'Adjustment',
}

/** Where a charge stands. Only the owner waives one. */
export const CHARGE_STATUS_LABEL: Record<ChargeStatus, string> = {
  PENDING: 'Not settled yet',
  SETTLED: 'Settled',
  WAIVED: 'Waived by the owner',
  REVERSED: 'Reversed',
}

/** Where a unit stands, in words that can be read down the phone. */
export const ASSET_STATUS_LABEL: Record<AssetStatus, string> = {
  INTAKE: 'Being booked in, not hireable yet',
  AVAILABLE: 'On the shelf',
  ON_HIRE: 'Out on hire',
  QUARANTINED: 'Quarantined until inspected',
  UNDER_REPAIR: 'In the workshop',
  LOST: 'Reported lost',
  RETIRED: 'Retired from the fleet',
}

/** How bad the damage is, in the words the workshop uses. */
export const DAMAGE_SEVERITY_LABEL: Record<DamageSeverity, string> = {
  MINOR: 'Minor',
  MAJOR: 'Major',
  WRITE_OFF: 'Not worth repairing',
}

/** Where a damage report stands. */
export const DAMAGE_STATUS_LABEL: Record<DamageStatus, string> = {
  OPEN: 'Open, unit in quarantine',
  UNDER_REPAIR: 'In the workshop',
  RESOLVED: 'Resolved, repaired',
  WRITTEN_OFF: 'Written off',
}

/** The status pill each report status is drawn with, so colour follows the words. */
export const DAMAGE_STATUS_PILL: Record<DamageStatus, string> = {
  OPEN: 'QUARANTINED',
  UNDER_REPAIR: 'UNDER_REPAIR',
  RESOLVED: 'RESOLVED',
  WRITTEN_OFF: 'RETIRED',
}

/** A count with its noun, for example "1 unit" or "3 units". */
export function countOf(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`
}

/** Whether a customer may be booked for. Only good standing may. */
export function canBookFor(status: AccountStatus): status is 'ACTIVE' {
  return status === 'ACTIVE'
}
